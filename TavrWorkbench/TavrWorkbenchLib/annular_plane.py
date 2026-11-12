"""Annular Plane tab: correct the three hinge points, then regenerate everything that depends on them.

Workflow
    1. The case's hinge points (LCC / RCC / NCC) are draggable; the annulus contour, its diameters and
       the STJ / coronary heights are shown locked for reference. Nothing is written while dragging.
    2. Apply:
       a. computes the new annulus contour (the annulus measurement pipeline: reslice the segmentation
          through the new plane, intensity-guided correction, closed spline), its max / min diameters
          and the LCH / RCH / STJ heights against the new plane - entirely in memory;
       b. only if all of that succeeded: backs up the files in effect to <output>/<case>/archive/v<N>
          (plus any saved Measurements corrections for the old plane, which are moved there);
       c. writes the new hinge points, contour, diameters and heights to <output>/<case>/annular_plane/,
          which from then on replace the data-map files for this case (Measurements loads them).
    3. The regenerated contour / diameters / heights are shown; corrections are made in Measurements.
The shared dataset is never modified.
"""
import os

import numpy as np
import qt
import slicer

from .annulus_pipeline import (height_plane, load_images, read_point_lps, recompute_annulus,
                               recompute_coronary_height, recompute_stj_height, write_contour, write_line,
                               write_point)
from .cases import reference_points
from .constants import CONTOUR_FOV, HEIGHT_FOV, HINGE_KEYS
from .geometry import unit
from .storage import now_iso

FLIP = np.array([-1.0, -1.0, 1.0])  # LPS <-> RAS
# Cusp-overlap views: (button text, the two hinge points that overlap)
OVERLAP_VIEWS = [("LR", "LCC", "RCC"), ("LN", "LCC", "NCC"), ("RN", "RCC", "NCC")]
SLICE_VIEWS = ("Red", "Yellow", "Green")
# Slicer's standard views, expressed for SetSliceToRASByNTP (screen x = T, screen y = N x T):
# the normal points towards Inferior (axial), Left (sagittal), Anterior (coronal); keeping every oblique
# view's normal on the same side and its "up" towards the patient's top keeps it un-mirrored, upright.
VIEW_NORMAL_SIDE = {"Red": np.array([0.0, 0.0, -1.0]), "Yellow": np.array([-1.0, 0.0, 0.0]),
                    "Green": np.array([0.0, 1.0, 0.0])}
ANTERIOR = np.array([0.0, 1.0, 0.0])
OSTIUM_LETTER = {"lch": "L", "rch": "R"}
MAX_D_COLOR = [1.0, 0.41568627450980394, 0.0]
MIN_D_COLOR = [0.23529411764705882, 0.7725490196078432, 0.3686274509803922]


def _separator():
    line = qt.QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: white;")
    return line


class AnnularPlanePanel:
    """Panel + logic of the Annular Plane tab. `module` is the TavrWorkbenchWidget."""

    def __init__(self, module):
        self.m = module
        self.widget = qt.QWidget()
        layout = qt.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hingeLabel = qt.QLabel("")
        self.hingeLabel.setTextFormat(qt.Qt.RichText)
        layout.addWidget(self.hingeLabel)

        row = qt.QHBoxLayout()
        self.resetButton = qt.QPushButton("Reset hinge points")
        self.resetButton.setToolTip("Put the hinge points back where they were when the case was loaded")
        self.resetButton.connect("clicked()", self.reset)
        self.alignButton = qt.QPushButton("Align to annular plane")
        self.alignButton.setToolTip("Red = plane through LCC, RCC and NCC; Green / Yellow = long axis")
        self.alignButton.connect("clicked()", self.align_view)
        row.addWidget(self.resetButton)
        row.addWidget(self.alignButton)
        layout.addLayout(row)

        overlap_row = qt.QHBoxLayout()
        overlap_row.addWidget(qt.QLabel("Cusp overlap:"))
        self.overlapButtons = []
        for text, a, b in OVERLAP_VIEWS:
            button = qt.QPushButton(text)
            third = [k for k in HINGE_KEYS if k not in (a, b)][0]
            button.setToolTip(f"{a} / {b} cusp overlap: in the annular plane (Red) the coronal line runs through "
                              f"{a} and {b} and the sagittal line through {third}. Green (coronal) shows {a} and {b}; "
                              f"Yellow (sagittal) looks along the {a}-{b} line, so they overlap, with {third}. "
                              f"3D looks along the same line.")
            button.connect("clicked()", lambda a=a, b=b: self.align_overlap(a, b))
            overlap_row.addWidget(button)
            self.overlapButtons.append(button)
        layout.addLayout(overlap_row)

        self.showSegCheck = qt.QCheckBox("Show segmentation")
        self.showSegCheck.setToolTip("Show / hide the segmentation outline while correcting the hinge points")
        self.showSegCheck.setChecked(True)
        self.showSegCheck.connect("toggled(bool)", lambda _on: self.m._applySegmentationDisplay())
        layout.addWidget(self.showSegCheck)

        self.applyButton = qt.QPushButton("Apply: back up && regenerate")
        self.applyButton.setToolTip("Back up the current hinge points, annulus contour, diameters and heights "
                                    "to archive/v<N>, then regenerate them from the new hinge points")
        self.applyButton.setStyleSheet("font-weight: bold;")
        self.applyButton.connect("clicked()", self.apply)
        layout.addWidget(self.applyButton)
        layout.addWidget(_separator())

        self.resultLabel = qt.QLabel("")
        self.resultLabel.setTextFormat(qt.Qt.RichText)
        self.resultLabel.setWordWrap(True)
        layout.addWidget(self.resultLabel)
        self.last_result = None   # html of the last Apply in this session (per case id)
        self._saved_view_settings = None   # crosshair / slice-intersection settings before entering the tab

    # ------------------------------------------------------------------ panel state
    def refresh(self):
        meas = self.m.meas
        loaded = self.m._case_loaded
        ok = loaded and meas.has_hinges()
        for b in [self.resetButton, self.alignButton, self.applyButton] + self.overlapButtons:
            b.setEnabled(ok)
        if not loaded:
            self.hingeLabel.setText("")
            self.resultLabel.setText("")
            return
        if not ok:
            missing = [k for k in HINGE_KEYS if k not in meas.hinges]
            self.hingeLabel.setText(f"<i>This case has no hinge point file for {', '.join(missing)}.</i>")
            return
        moves = meas.hinge_moves_mm()
        html = "<b>Hinge points</b> <span style='color:#888'>(moved since loaded)</span><table cellpadding=2>"
        for k in HINGE_KEYS:
            d = moves[k]
            txt = f"<span style='color:#c60'>{d:.1f} mm</span>" if d > 1e-3 else "unchanged"
            html += f"<tr><td>{k}</td><td>{txt}</td></tr>"
        html += "</table>"
        tilt = self._tilt_change_deg()
        if tilt is not None and meas.hinges_moved():
            html += f"Plane tilt changed by <b>{tilt:.1f}°</b> &nbsp; <i>(not applied yet)</i>"
        self.hingeLabel.setText(html)
        self._show_status()

    def _show_status(self):
        cid = self.m.caseId()
        version = self.m.store.plane_fix_version(cid)
        if self.last_result and self.last_result[0] == cid:
            self.resultLabel.setText(self.last_result[1])
        elif version:
            when = self.m.store.meas_status.get(cid, {}).get("plane_fixed_at", "")
            self.resultLabel.setText(f"Annular plane fixed (v{version}, {when}). The contour, diameters and "
                                     f"heights shown are the regenerated ones; the earlier files are in "
                                     f"<i>archive/</i>.")
        else:
            self.resultLabel.setText("<i>No annular-plane fix applied to this case yet.</i>")

    def _plane_ras(self, loaded=False):
        """(centroid, normal, u) of the hinge plane in RAS, or None."""
        pts = self.m.meas.hinge_points_lps(loaded=loaded)
        if not all(k in pts for k in HINGE_KEYS):
            return None
        L, R, N = (pts[k] for k in HINGE_KEYS)
        normal = np.cross(N - L, R - L)
        if np.linalg.norm(normal) < 1e-8:
            return None
        normal = unit(normal)
        if normal[2] < 0:
            normal = -normal
        return (L + R + N) / 3.0 * FLIP, normal * FLIP, unit(N - L) * FLIP

    def _tilt_change_deg(self):
        now, before = self._plane_ras(), self._plane_ras(loaded=True)
        if now is None or before is None:
            return None
        return float(np.degrees(np.arccos(np.clip(abs(np.dot(now[1], before[1])), -1.0, 1.0))))

    # ------------------------------------------------------------------ views
    def show_segmentation(self):
        return bool(self.showSegCheck.checked)

    def enter(self):
        slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        self._enable_crosshairs()
        self.align_view()
        qt.QTimer.singleShot(250, self.align_view)  # slice widgets need a moment to get their final size
        self.refresh()

    def leave(self):
        """Leaving the tab: put the crosshair / slice-intersection settings back as they were."""
        self._restore_crosshairs()

    @staticmethod
    def _slice_display_nodes():
        lm = slicer.app.layoutManager()
        out = []
        for name in SLICE_VIEWS:
            widget = lm.sliceWidget(name)
            if widget is None:
                continue
            try:
                node = widget.sliceLogic().GetSliceDisplayNode()
            except Exception:
                node = None
            if node is not None:
                out.append(node)
        return out

    def _enable_crosshairs(self):
        """Slice-intersection lines (the crosshair of each view): interactive (drag / rotate) and thick.
        Slicer's crosshair cursor is left as it is."""
        if self._saved_view_settings is None:
            saved = []
            for d in self._slice_display_nodes():
                try:
                    saved.append((d, d.GetIntersectingSlicesVisibility(), d.GetIntersectingSlicesInteractive(),
                                  d.GetIntersectingSlicesLineThicknessMode()))
                except Exception:
                    pass
            self._saved_view_settings = saved
        for d in self._slice_display_nodes():
            try:  # Slicer >= 5.2
                d.SetIntersectingSlicesVisibility(True)   # the lines must be shown to be dragged
                d.SetIntersectingSlicesInteractive(True)
                d.SetIntersectingSlicesTranslationEnabled(True)
                d.SetIntersectingSlicesRotationEnabled(True)
                d.SetIntersectingSlicesLineThicknessMode(slicer.vtkMRMLSliceDisplayNode.ThickLines)
            except Exception as e:
                print(f"[TavrWorkbench] slice intersections not configurable in this Slicer version: {e}")

    def _restore_crosshairs(self):
        saved, self._saved_view_settings = self._saved_view_settings, None
        for d, visible, interactive, thickness in saved or []:
            try:
                d.SetIntersectingSlicesVisibility(visible)
                d.SetIntersectingSlicesInteractive(interactive)
                d.SetIntersectingSlicesLineThicknessMode(thickness)
            except Exception:
                pass

    def _orient(self, view, normal, up, center, fov):
        """Point slice view `view` along `normal` through `center`, with `up` towards the top of the screen,
        oriented like Slicer's own view of the same name (never mirrored or upside down)."""
        widget = slicer.app.layoutManager().sliceWidget(view)
        if widget is None:
            return
        n = unit(normal)
        if np.dot(n, VIEW_NORMAL_SIDE[view]) < 0:
            n = -n
        y = np.asarray(up, float) - np.dot(up, n) * n
        if np.linalg.norm(y) < 1e-6:
            return
        y = unit(y)
        t = np.cross(y, n)                          # screen right; Slicer then sets screen up = n x t = y
        sn = widget.mrmlSliceNode()
        sn.SetSliceToRASByNTP(n[0], n[1], n[2], t[0], t[1], t[2], center[0], center[1], center[2], 0)
        self.m.meas._set_fov(sn, fov)

    def _look_3d(self, focal, direction, up):
        """3D camera looking along `direction` at `focal` (like a fluoroscopy projection)."""
        try:
            view = slicer.app.layoutManager().threeDWidget(0).threeDView()
            camera = slicer.modules.cameras.logic().GetViewActiveCameraNode(view.mrmlViewNode())
            dist = 250.0
            pos = np.asarray(focal) - unit(direction) * dist
            camera.SetFocalPoint(*[float(v) for v in focal])
            camera.SetPosition(*[float(v) for v in pos])
            camera.SetViewUp(*[float(v) for v in up])
            camera.ResetClippingRange()
        except Exception as e:
            print(f"[TavrWorkbench] could not orient the 3D view: {e}")

    def align_overlap(self, a, b):
        """Cusp overlap for hinge points a / b (e.g. LCC / RCC), third cusp c (e.g. NCC):
        Red    = annular plane; its crosshair lines: coronal through a and b, sagittal through c
        Green  = coronal: the plane through a and b along the annulus axis (a and b side by side)
        Yellow = sagittal: perpendicular to the a-b line through c (a and b overlap, c in plane)
        3D     = looking along the a-b line."""
        plane = self._plane_ras()
        pts = self.m.meas.hinge_points_lps()
        if plane is None or not all(k in pts for k in HINGE_KEYS):
            return
        centroid, n, _u = plane
        third = [k for k in HINGE_KEYS if k not in (a, b)][0]
        pa, pb, pc = pts[a] * FLIP, pts[b] * FLIP, pts[third] * FLIP
        d = (pb - pa) - np.dot(pb - pa, n) * n          # a -> b, within the annular plane
        if np.linalg.norm(d) < 1e-6:
            return
        d = unit(d)
        across = unit(np.cross(n, d))                    # in-plane, perpendicular to a-b
        self._orient("Red", n, ANTERIOR, centroid, CONTOUR_FOV)
        self._orient("Green", across, n, (pa + pb) / 2.0, HEIGHT_FOV)   # contains a, b and the annulus axis
        self._orient("Yellow", d, n, pc, HEIGHT_FOV)                     # contains c; a and b project together
        self._look_3d((pa + pb) / 2.0, d, n)

    def align_view(self):
        """Red = annular plane (through LCC, RCC, NCC); Green / Yellow = coronal / sagittal long-axis planes
        through its centre, i.e. Slicer's standard views tilted onto the annulus."""
        plane = self._plane_ras()
        if plane is None:
            return
        c, n, u = plane
        ant = ANTERIOR - np.dot(ANTERIOR, n) * n          # in-plane direction closest to anterior
        ant = unit(ant) if np.linalg.norm(ant) > 1e-6 else u
        self._orient("Red", n, ANTERIOR, c, CONTOUR_FOV)
        self._orient("Green", ant, n, c, HEIGHT_FOV)
        self._orient("Yellow", np.cross(n, ant), n, c, HEIGHT_FOV)
        try:
            slicer.app.layoutManager().threeDWidget(0).threeDView().setFocalPoint(float(c[0]), float(c[1]), float(c[2]))
        except Exception:
            pass

    def reset(self):
        self.m.meas.reset_hinges()
        self.refresh()

    # ------------------------------------------------------------------ apply
    def apply(self):
        m, meas = self.m, self.m.meas
        if not m._case_loaded or not meas.has_hinges():
            return
        if not m.outDir():
            slicer.util.errorDisplay("Select an output folder first.")
            return
        cid = m.caseId()
        if not meas.hinges_moved() and not slicer.util.confirmYesNoDisplay(
                "The hinge points have not been moved. Regenerate the annulus contour, diameters and "
                "heights from the current hinge points anyway?"):
            return
        if meas.is_dirty() and not slicer.util.confirmYesNoDisplay(
                "There are unsaved contour / height edits from the Measurements tab. Apply regenerates the "
                "annulus contour and heights, so those edits will be discarded. Continue?"):
            return
        version_preview, _dir = m.store.next_archive_dir(cid)
        if not slicer.util.confirmYesNoDisplay(
                f"Case {cid}: back up the current hinge points, annulus contour, diameters and heights to "
                f"archive/v{version_preview}, then regenerate them from the new hinge points?"):
            return

        sample = m._effectiveSample(m.current_index)
        slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            try:
                result = self._compute(sample)          # a) everything in memory first
            except Exception as e:
                import traceback
                traceback.print_exc()
                slicer.util.errorDisplay(f"Could not regenerate the measurements for case {cid}; "
                                         f"nothing was changed.\n\n{e}")
                return
            try:
                version, adir = self._backup_and_write(cid, sample, result)   # b) + c)
            except Exception as e:
                import traceback
                traceback.print_exc()
                slicer.util.errorDisplay(f"Writing the new files for case {cid} failed:\n{e}\n\n"
                                         f"The previous files are in {m.store.next_archive_dir(cid)[1]} "
                                         f"(or the latest archive/v* folder).")
                return
        finally:
            slicer.app.restoreOverrideCursor()

        meas.mark_saved()                 # edits for the old plane were archived / discarded
        m._reloadMeasurementNodes()       # show the regenerated files (hinge "loaded" = new positions)
        self.last_result = (cid, self._result_html(version, adir, result))
        self.refresh()
        self.align_view()
        m.refreshCombo()
        slicer.util.showStatusMessage(f"Case {cid}: annular plane applied (backup in archive/v{version})", 5000)

    # ------------------------------------------------------------------ steps
    def _compute(self, sample):
        m, meas = self.m, self.m.meas
        new = meas.hinge_points_lps()
        old = meas.hinge_points_lps(loaded=True)
        L, R, N = (new[k] for k in HINGE_KEYS)
        oL, oR, oN = (old[k] for k in HINGE_KEYS)

        label_path, _from_saved = m._resolveLabelPath(sample, m.caseId())
        if not label_path:
            raise ValueError("This case has no segmentation; the annulus contour is derived from it.")
        ct, seg = load_images(sample["image"], label_path)
        annulus = recompute_annulus(ct, seg, L, R, N)

        heights, notes = {}, []
        old_point, old_normal = height_plane(oL, oR, oN)
        for key in ("lch", "rch"):
            ostium = self._far_endpoint(key, old_point, old_normal)
            source = "current line"
            if ostium is None:
                files = reference_points(sample, "coronary_ostia_points")
                letter = OSTIUM_LETTER[key]
                if letter in files:
                    ostium, source = read_point_lps(files[letter]), "ostium point file"
            if ostium is None:
                notes.append(f"{key.upper()}: no height line or ostium point for this case - not regenerated.")
                continue
            foot, length = recompute_coronary_height(ostium, L, R, N)
            heights[key] = {"p1": ostium, "p2": foot, "length": length, "label": key.upper(),
                            "old": self._line_length(key), "source": source}
        stj_files = reference_points(sample, "stj_points")
        if len(stj_files) == 3:
            pts = {c: read_point_lps(p) for c, p in stj_files.items()}
            cusp, point, foot, h, _dists = recompute_stj_height(pts, L, R, N)
            heights["stj"] = {"p1": point, "p2": foot, "length": h, "label": f"STJ_H_{cusp}", "cusp": cusp,
                              "old": self._line_length("stj"), "source": "STJ points L/R/N"}
        else:
            point = self._far_endpoint("stj", old_point, old_normal)
            if point is not None:
                foot, h = recompute_coronary_height(point, L, R, N)
                heights["stj"] = {"p1": point, "p2": foot, "length": h, "label": "STJ_H", "cusp": "",
                                  "old": self._line_length("stj"), "source": "current line (cusp kept)"}
                notes.append("STJ: the three STJ points were not found, so the STJ point of the current line was "
                             "kept (the closest cusp could not be re-chosen).")
            else:
                notes.append("STJ: no STJ points or height line for this case - not regenerated.")
        return {"hinges": new, "annulus": annulus, "heights": heights, "notes": notes}

    def _far_endpoint(self, key, plane_point, normal):
        """LPS endpoint of a height line farthest from the (old) annular plane: the ostium / STJ point."""
        node = self.m.meas.heights.get(key)
        if node is None or node.GetNumberOfControlPoints() == 0:
            return None
        pts = self.m.meas._get_pts(node) * FLIP
        dist = np.abs((pts - plane_point) @ normal)
        return pts[int(np.argmax(dist))]

    def _line_length(self, key):
        node = self.m.meas.heights.get(key)
        if node is None or node.GetNumberOfControlPoints() != 2:
            return None
        p = self.m.meas._get_pts(node)
        return float(np.linalg.norm(p[1] - p[0]))

    def _backup_and_write(self, cid, sample, result):
        store = self.m.store
        version, adir, manifest = store.archive_before_plane_fix(cid, sample)
        os.makedirs(store.plane_dir(cid), exist_ok=True)

        def target(group, name):
            return store.plane_file(cid, (group, name))

        for k in HINGE_KEYS:
            write_point(target("hinge_points", k), k, result["hinges"][k])
        a = result["annulus"]
        write_contour(target("contours", "annulus"), a["contour_lps"], a["area_mm2"], a["perimeter_mm"])
        write_line(target("max_diameters", "annulus"), "L", a["max_pts"][0], a["max_pts"][1], MAX_D_COLOR)
        write_line(target("min_diameters", "annulus"), "L_1", a["min_pts"][0], a["min_pts"][1], MIN_D_COLOR)
        for key in ("stj", "lch", "rch"):
            path = target("heights", key)
            h = result["heights"].get(key)
            if h is not None:
                write_line(path, h["label"], h["p1"], h["p2"])
            elif os.path.isfile(path):
                os.remove(path)  # a regenerated file from an earlier fix no longer matches (it is archived)

        hinges = result["hinges"]
        corr = a.get("correction") or {}
        row = {"applied_at": now_iso(),
               "area_mm2": round(a["area_mm2"], 2), "perimeter_mm": round(a["perimeter_mm"], 2),
               "max_d_mm": round(a["max_d_mm"], 2), "min_d_mm": round(a["min_d_mm"], 2),
               "mean_d_mm": round(a["mean_d_mm"], 2), "eccentricity": round(a["eccentricity"], 4),
               "corrected": a["corrected"], "iou_vs_original": corr.get("iou_vs_original", ""),
               "stj_cusp": (result["heights"].get("stj") or {}).get("cusp", "")}
        for k in HINGE_KEYS:
            for axis, v in zip("xyz", hinges[k]):
                row[f"{k.lower()}_{axis}"] = round(float(v), 4)
        for key in ("lch", "rch"):
            h = result["heights"].get(key)
            row[f"{key}_mm"] = round(h["length"], 2) if h else ""
        h = result["heights"].get("stj")
        row["stj_height_mm"] = round(h["length"], 2) if h else ""
        manifest["notes"] = result["notes"]
        store.record_plane_fix(cid, version, adir, manifest, row)
        return version, adir

    @staticmethod
    def _result_html(version, adir, result):
        a = result["annulus"]
        corr = a.get("correction") or {}
        html = (f"<b>Applied (v{version})</b> &nbsp; previous files backed up to:<br><i>{adir}</i><br>"
                "<b>ANNULUS</b> (regenerated)<table cellpadding=2>"
                f"<tr><td>Area</td><td>{a['area_mm2']:.1f} mm²</td></tr>"
                f"<tr><td>Perimeter</td><td>{a['perimeter_mm']:.1f} mm</td></tr>"
                f"<tr><td>Max / min ⌀</td><td>{a['max_d_mm']:.1f} / {a['min_d_mm']:.1f} mm</td></tr>"
                f"<tr><td>Mean ⌀ / ecc.</td><td>{a['mean_d_mm']:.1f} mm / {a['eccentricity']:.3f}</td></tr>")
        if a["corrected"]:
            html += f"<tr><td>HU correction</td><td>IoU {corr.get('iou_vs_original', '')} vs. segmentation</td></tr>"
        html += "</table><b>HEIGHTS</b> (regenerated)<table cellpadding=2>"
        names = {"stj": "STJ height", "lch": "LCH", "rch": "RCH"}
        for key in ("stj", "lch", "rch"):
            h = result["heights"].get(key)
            if h is None:
                html += f"<tr><td>{names[key]}</td><td><i>not regenerated</i></td></tr>"
                continue
            old = f" (was {h['old']:.1f})" if h.get("old") is not None else ""
            cusp = f" [{h['cusp']}]" if h.get("cusp") else ""
            html += f"<tr><td>{names[key]}{cusp}</td><td>{h['length']:.1f} mm{old}</td></tr>"
        html += "</table>"
        for note in result["notes"]:
            html += f"<br><span style='color:#c60'>{note}</span>"
        return html