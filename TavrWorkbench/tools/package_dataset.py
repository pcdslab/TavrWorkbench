#!/usr/bin/env python3
"""Build a portable TavrWorkbench dataset folder from a data map with absolute paths.

Every file a case references is copied into  <out>/cases/<case_id>/...  and a new data_map.json with
paths RELATIVE to itself is written next to it. The folder can then be shared (OneDrive, Google Drive,
USB disk, zip) and opened from any location on macOS or Windows: in TavrWorkbench just select
<out>/data_map.json as the data map.

    python3 tools/package_dataset.py  data_map_full.json  ~/TAVR_dataset
    python3 tools/package_dataset.py  data_map_full.json  ~/TAVR_batch1 --cases 500-524,568
    python3 tools/package_dataset.py  data_map_full.json  ~/TAVR_dataset --zip
    python3 tools/package_dataset.py  /Volumes/falcon/tavr_application/config/new_data_map_sorted.json  ~/TAVR_dataset --zip
    python3 tools/package_dataset.py /Users/khubaib/Downloads/review/measurement_corrections/new_data_map_sorted.json  /Volumes/falcon/TAVR_dataset_for_review --zip

Re-running is safe: files already copied (same size) are skipped, so an interrupted run just continues.
Only the Python standard library is used.
"""
import argparse
import json
import os
import shutil
import sys
import zipfile

FILE_KEYS = ("image", "label")
GROUP_KEYS = ("hinge_points", "contours", "max_diameters", "min_diameters", "heights", "centerline")
# Longest first, so ".seg.nrrd" wins over ".nrrd"
SUFFIXES = (".seg.nrrd", ".nii.gz", ".mrk.json", ".nrrd", ".nii", ".vtp", ".vtk", ".json")
ALREADY_COMPRESSED = (".gz", ".nrrd", ".zip")


def suffix_of(path):
    name = os.path.basename(path).lower()
    return next((s for s in SUFFIXES if name.endswith(s)), os.path.splitext(name)[1])


def parse_case_filter(text):
    if not text:
        return None
    wanted = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            wanted.update(str(i) for i in range(int(lo), int(hi) + 1))
        elif part:
            wanted.add(part)
    return wanted


def read_samples(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return {}, data
    if "samples" in data:
        return data, data["samples"]
    return data, sum([data.get(k, []) for k in ("training", "validation", "testing")], [])


def safe_name(name):
    return "".join(c for c in str(name) if c.isalnum() or c in "_-.") or "case"


def copy_file(src, dst):
    """Copy unless an identical-size copy is already there. Returns bytes in dst."""
    size = os.path.getsize(src)
    if os.path.exists(dst) and os.path.getsize(dst) == size:
        return size
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    return size


def package(map_path, out_dir, cases=None):
    meta, samples = read_samples(map_path)
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    new_samples, missing, total_bytes = [], [], 0

    for i, sample in enumerate(samples):
        cid = str(sample.get("case_id", i))
        if cases is not None and cid not in cases:
            continue
        image = sample.get("image")
        if not (isinstance(image, str) and os.path.isfile(image)):
            missing.append(f"{cid}: image {image}  -> case skipped")
            continue
        case_rel = f"cases/{safe_name(cid)}"
        new = {"case_id": cid}

        def take(src, rel_name):
            nonlocal total_bytes
            if not (isinstance(src, str) and os.path.isfile(src)):
                missing.append(f"{cid}: {rel_name} {src}")
                return None
            rel = f"{case_rel}/{rel_name}{suffix_of(src)}"
            total_bytes += copy_file(src, os.path.join(out_dir, *rel.split("/")))
            return rel  # forward slashes: valid on macOS and Windows

        for key in FILE_KEYS:
            if sample.get(key):
                rel = take(sample[key], key)
                if rel:
                    new[key] = rel
        for group in GROUP_KEYS:
            entries = sample.get(group)
            if not isinstance(entries, dict):
                continue
            copied = {}
            for name, src in entries.items():
                rel = take(src, f"{group}/{safe_name(name)}")
                if rel:
                    copied[name] = rel
            if copied:
                new[group] = copied
        new_samples.append(new)
        print(f"  [{len(new_samples):3d}] case {cid}")

    # Only portable content goes into the new map ("dirs" etc. held machine-specific paths)
    out_meta = {k: v for k, v in meta.items() if k != "samples" and not isinstance(v, (list, dict))}
    out_meta["totaldatasample"] = len(new_samples)
    out_meta["samples"] = new_samples
    with open(os.path.join(out_dir, "data_map.json"), "w") as f:
        json.dump(out_meta, f, indent=2)

    if missing:
        with open(os.path.join(out_dir, "missing_files.txt"), "w") as f:
            f.write("\n".join(missing) + "\n")
    return len(new_samples), total_bytes, missing


def make_zip(out_dir):
    zip_path = out_dir.rstrip("/\\") + ".zip"
    base = os.path.basename(out_dir.rstrip("/\\"))
    with zipfile.ZipFile(zip_path, "w", allowZip64=True) as zf:
        for root, _dirs, files in os.walk(out_dir):
            for name in sorted(files):
                full = os.path.join(root, name)
                arc = os.path.join(base, os.path.relpath(full, out_dir)).replace(os.sep, "/")
                method = zipfile.ZIP_STORED if name.lower().endswith(ALREADY_COMPRESSED) else zipfile.ZIP_DEFLATED
                zf.write(full, arc, compress_type=method)
    return zip_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_map", help="existing data map (absolute paths)")
    ap.add_argument("out_dir", help="folder to create, e.g. ~/TAVR_dataset")
    ap.add_argument("--cases", help="only these case ids, e.g. 500-524,568")
    ap.add_argument("--zip", action="store_true", help="also write <out_dir>.zip")
    args = ap.parse_args()

    print(f"Packaging {args.data_map} -> {args.out_dir}")
    n, size, missing = package(args.data_map, args.out_dir, parse_case_filter(args.cases))
    print(f"\n{n} cases, {size / 1e9:.2f} GB in {os.path.abspath(os.path.expanduser(args.out_dir))}")
    if missing:
        print(f"WARNING: {len(missing)} referenced file(s) were missing; see missing_files.txt")
    if args.zip:
        print("Writing zip ...")
        print("Zip:", make_zip(os.path.abspath(os.path.expanduser(args.out_dir))))
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
