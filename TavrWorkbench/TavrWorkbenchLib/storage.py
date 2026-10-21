"""Everything read from / written to the output folder (no Slicer imports).

<output>/
    review_status.json            segmentation progress  {cid: {overall, time, mask_edited, mask_saved_at}}
    correction_status.json        measurement progress   {cid: {status, time, planes_edited}}
    annotations.csv               one row per case: every Approve/Flag rating + comment
    corrected_measurements.csv    one row per case+plane: contour metrics
    tavr_workbench.log
    <case_id>/
        review.json               full review of the case (both modes)
        segmentation.seg.nrrd     edited mask (only after "Save mask")
        <plane>_contour.mrk.json  corrected contour (+ _max_d / _min_d diameter lines)
"""
import csv
import json
import os
from datetime import datetime

from .constants import (ANNOTATION_COLUMNS, ANNOTATIONS_CSV, CASE_MASK_FILE, CASE_REVIEW_FILE,
                        CONTOUR_FILE_SUFFIX, MEAS_STATUS_FILE, MEASUREMENT_COLUMNS, MEASUREMENTS_CSV,
                        MEASUREMENT_KEY_TO_LABEL, RATING_NONE, RATING_TO_STR, SEG_STATUS_FILE,
                        SEGMENTATION_LABELS, normalize_rating, normalize_review)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def safe_name(name):
    safe = "".join(c for c in str(name) if c.isalnum() or c in ("_", "-", ".")).strip()
    return safe or "unknown_case"


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _read_csv(path, key_fn):
    rows = {}
    if os.path.exists(path):
        try:
            with open(path, newline="") as f:
                for r in csv.DictReader(f):
                    rows[key_fn(r)] = r
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not read {path}: {e}")
    return rows


def _write_csv(path, cols, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


class OutputStore:
    def __init__(self):
        self.root = ""
        self.seg_status = {}
        self.meas_status = {}

    # ---------------------------------------------------------------- paths
    def set_root(self, root):
        self.root = str(root or "")
        self.reload()

    def path(self, *parts):
        return os.path.join(self.root, *parts) if self.root else ""

    def case_dir(self, cid):
        return self.path(safe_name(cid))

    def ensure_case_dir(self, cid):
        d = self.case_dir(cid)
        os.makedirs(d, exist_ok=True)
        return d

    def case_path(self, cid, filename):
        return os.path.join(self.case_dir(cid), filename) if self.root else ""

    def contour_path(self, cid, plane, key):
        return self.case_path(cid, f"{plane}_{CONTOUR_FILE_SUFFIX[key]}.mrk.json")

    def find_saved_contour(self, cid, plane):
        """Corrected contour from an earlier session (also finds folders written by the old
        correct_measurements module, which used the raw case id as folder name)."""
        if not self.root:
            return None
        name = f"{plane}_{CONTOUR_FILE_SUFFIX['curve']}.mrk.json"
        for d in (self.case_dir(cid), self.path(str(cid))):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
        return None

    def edited_mask_path(self, cid):
        p = self.case_path(cid, CASE_MASK_FILE)
        return p if p and os.path.isfile(p) else ""

    # --------------------------------------------------------------- status
    def reload(self):
        self.seg_status = self._read_status(SEG_STATUS_FILE, "overall")
        self.meas_status = self._read_status(MEAS_STATUS_FILE, "status")

    def _read_status(self, filename, rating_key):
        path = self.path(filename)
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not read {path}: {e}")
            return {}
        out = {}
        for cid, entry in (data.items() if isinstance(data, dict) else []):
            if isinstance(entry, dict):
                if rating_key in entry:
                    entry[rating_key] = normalize_rating(entry[rating_key])
                out[str(cid)] = entry
        return out

    def dump(self):
        if not self.root:
            return
        os.makedirs(self.root, exist_ok=True)
        _write_json(self.path(SEG_STATUS_FILE), self.seg_status)
        _write_json(self.path(MEAS_STATUS_FILE), self.meas_status)

    def seg_rating(self, cid):
        return self.seg_status.get(str(cid), {}).get("overall", RATING_NONE)

    def meas_rating(self, cid):
        return self.meas_status.get(str(cid), {}).get("status", RATING_NONE)

    def set_seg_decision(self, cid, rating):
        entry = self.seg_status.setdefault(str(cid), {})
        entry["overall"] = rating
        entry["time"] = now_iso()

    def set_meas_decision(self, cid, rating):
        entry = self.meas_status.setdefault(str(cid), {})
        entry["status"] = rating
        entry["time"] = now_iso()

    def mask_edited(self, cid):
        return bool(self.seg_status.get(str(cid), {}).get("mask_edited"))

    def mark_mask_edited(self, cid):
        entry = self.seg_status.setdefault(str(cid), {})
        entry["mask_edited"] = True
        entry["mask_saved_at"] = now_iso()

    # --------------------------------------------------------- review.json
    def read_review(self, cid):
        path = self.case_path(cid, CASE_REVIEW_FILE)
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return normalize_review(json.load(f).get("review"))
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not read saved review {path}: {e}")
            return None

    def write_review(self, cid, review):
        self.ensure_case_dir(cid)
        _write_json(self.case_path(cid, CASE_REVIEW_FILE),
                    {"case_id": str(cid), "saved_at": now_iso(), "review": review})

    # ----------------------------------------------------------------- CSVs
    def upsert_annotation(self, cid, sample, review, mask_status_text):
        path = self.path(ANNOTATIONS_CSV)
        rows = _read_csv(path, lambda r: r.get("case_id", ""))
        mask_path = self.case_path(cid, CASE_MASK_FILE) if self.mask_edited(cid) else (sample.get("label") or "")
        row = {
            "case_id": str(cid),
            "file": sample.get("image", ""),
            "comment": review.get("comment", ""),
            "mask_path": mask_path,
            "mask_status": mask_status_text,
            "overall": RATING_TO_STR.get(review.get("overall", RATING_NONE), ""),
            "measurements_overall": RATING_TO_STR.get(review.get("measurements_overall", RATING_NONE), ""),
            "saved_at": now_iso(),
        }
        seg = review.get("segmentation", {})
        meas = review.get("measurements", {})
        for label in SEGMENTATION_LABELS:
            row[label] = RATING_TO_STR.get(seg.get(label, RATING_NONE), "")
        for label in MEASUREMENT_KEY_TO_LABEL.values():
            row[label] = RATING_TO_STR.get(meas.get(label, RATING_NONE), "")
        rows[str(cid)] = row
        _write_csv(path, ANNOTATION_COLUMNS, rows.values())

    def upsert_measurements(self, cid, metric_rows, dirty_planes):
        """metric_rows: [{plane, area_mm2, ...}] from MeasurementEditor.metrics_rows()."""
        cid = str(cid)
        entry = self.meas_status.setdefault(cid, {})
        edited = list(entry.get("planes_edited", []))
        for p in dirty_planes:
            if p not in edited:
                edited.append(p)
        entry["planes_edited"] = edited
        entry["time"] = now_iso()

        path = self.path(MEASUREMENTS_CSV)
        rows = _read_csv(path, lambda r: (r.get("case_id", ""), r.get("plane", "")))
        for m in metric_rows:
            row = dict(m, case_id=cid, edited=m["plane"] in edited, saved_at=now_iso())
            rows[(cid, m["plane"])] = row
        _write_csv(path, MEASUREMENT_COLUMNS, rows.values())
