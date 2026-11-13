"""Valve tab: build a parametric TAVR valve from the case's measurements, place it in the CT, export it.

* Inputs are read from the measurements in effect (corrections from Measurements and fixes from the
  Annular Plane tab included):
      annulus_min / annulus_max  annulus contour min / max diameter (same definition as Measurements)
      coronary_h / coronary_h2   the lower / higher of LCH and RCH (heights above the annulus plane)
      stj_h                      STJ height;   stj_d  STJ contour perimeter-derived diameter
  They can be edited before building; the other generator settings are under "Valve design".
* Placement (valve coordinates -> CT): z = 0 on the annulus plane at the annulus centre, +z towards
  the STJ (aorta), x along the annulus long (max) diameter so the elliptical frame matches the annulus.
* Export writes <output>/<case>/<case>_valve.stl in CT patient coordinates (LPS, mm), and next to it
  <case>_valve.json with the parameters, the measurements and the valve -> LPS transform.
"""
import json
import os
import tempfile

import ctk
import numpy as np
import qt
import slicer

from .constants import CONTOUR_FOV, HEIGHT_FOV, VALVE_ANATOMY_KEYS, VALVE_COLORS, VALVE_JSON, VALVE_STL
from .geometry import unit
from .storage import now_iso, safe_name
from .valve_generator import DEFAULTS, HELP, make_valve, merge, write_stl

ANTERIOR = np.array([0.0, 1.0, 0.0])
FLIP = np.array([-1.0, -1.0, 1.0])  # RAS <-> LPS
PARTS = ("frame", "skirt", "leaflets")
LABELS = {"annulus_min": "Annulus min ⌀", "annulus_max": "Annulus max ⌀", "coronary_h": "Coronary height (low)",
          "coronary_h2": "Coronary height (high)", "stj_h": "STJ height", "stj_d": "STJ ⌀",
          "asc_aorta_d": "Ascending aorta ⌀"}
INT_RANGES = {"cells": (6, 30), "rows": (3, 15), "tabs": (0, 6)}


def _separator():
    line = qt.QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: white;")
    return line


def _polydata(V, F):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(V, dtype=np.float64), deep=True))
    conn = np.hstack([np.full((len(F), 1), 3), F]).astype(np.int64).ravel()
    cells = vtk.vtkCellArray()
    cells.SetCells(len(F), numpy_to_vtkIdTypeArray(conn, deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(cells)
    return pd


class ValvePanel:
    """Panel + logic of the Valve tab. `module` is the TavrWorkbenchWidget."""

    def __init__(self, module):
        self.m = module
        self.widget = qt.QWidget()
        layout = qt.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.measLabel = qt.QLabel("")
        self.measLabel.setTextFormat(qt.Qt.RichText)
        layout.addWidget(self.measLabel)
        layout.addWidget(_separator())

        # ---- anatomy inputs (filled from the measurements)
        form = qt.QFormLayout()
        self.inputs = {}
        for key in VALVE_ANATOMY_KEYS:
            box = qt.QDoubleSpinBox()
            box.setRange(0.0, 80.0)
            box.setDecimals(1)
            box.setSingleStep(0.5)
            box.setSuffix(" mm")
            box.setToolTip(HELP.get(key, ""))
            if key == "coronary_h2":
                box.setSpecialValueText("none")   # 0 = not used
            form.addRow(LABELS[key] + ":", box)
            self.inputs[key] = box
        layout.addLayout(form)
        self.measuredButton = qt.QPushButton("Use measured values")
        self.measuredButton.setToolTip("Refill the inputs above from this case's measurements")
        self.measuredButton.connect("clicked()", self.fill_from_measurements)
        layout.addWidget(self.measuredButton)

        # ---- valve design (all other generator settings)
        design = ctk.ctkCollapsibleButton()
        design.text = "Valve design"
        design.collapsed = True
        dform = qt.QFormLayout(design)
        self.design = {}
        for key, default in DEFAULTS.items():
            if key in VALVE_ANATOMY_KEYS or key == "out":
                continue
            if isinstance(default, bool):
                w = qt.QCheckBox()
                w.setChecked(default)
            elif isinstance(default, int):
                w = qt.QSpinBox()
                w.setRange(*INT_RANGES.get(key, (0, 100)))
                w.setValue(default)
            else:
                w = qt.QDoubleSpinBox()
                w.setRange(0.0, 100.0)
                w.setDecimals(2)
                w.setSingleStep(0.1 if default < 5 else 0.5)
                w.setValue(default)
            w.setToolTip(HELP.get(key, ""))
            dform.addRow(key.replace("_", " ") + ":", w)
            self.design[key] = w
        resetDesign = qt.QPushButton("Default design")
        resetDesign.connect("clicked()", self.reset_design)
        dform.addRow(resetDesign)
        layout.addWidget(design)

        # ---- actions
        row = qt.QHBoxLayout()
        self.buildButton = qt.QPushButton("Build valve")
        self.buildButton.setToolTip("Generate the valve from the inputs and place it on the annulus")
        self.buildButton.setStyleSheet("font-weight: bold;")
        self.buildButton.connect("clicked()", self.build)
        self.alignButton = qt.QPushButton("Align view")
        self.alignButton.setToolTip("Red = annular plane; Green / Yellow = long axis through the valve")
        self.alignButton.connect("clicked()", self.align_view)
        row.addWidget(self.buildButton)
        row.addWidget(self.alignButton)
        layout.addLayout(row)
        self.exportButton = qt.QPushButton("Export valve STL")
        self.exportButton.setToolTip("Save <output>/<case>/<case>_valve.stl (CT patient coordinates, LPS) + .json")
        self.exportButton.connect("clicked()", self.export)
        layout.addWidget(self.exportButton)

        opts = qt.QHBoxLayout()
        self.showSegCheck = qt.QCheckBox("Show segmentation")
        self.showSegCheck.setToolTip("Segmentation outline in the slices and see-through in 3D")
        self.showSegCheck.setChecked(False)
        self.showSegCheck.connect("toggled(bool)", lambda _on: self.m._applySegmentationDisplay())
        self.showValveCheck = qt.QCheckBox("Show valve")
        self.showValveCheck.setChecked(True)
        self.showValveCheck.connect("toggled(bool)", lambda _on: self._apply_valve_visibility())
        opts.addWidget(self.showSegCheck)
        opts.addWidget(self.showValveCheck)
        layout.addLayout(opts)
        layout.addWidget(_separator())

        self.reportLabel = qt.QLabel("")
        self.reportLabel.setTextFormat(qt.Qt.RichText)
        self.reportLabel.setWordWrap(True)
        layout.addWidget(self.reportLabel)

        self.models = {}          # part -> model node
        self.transform = None     # valve -> RAS transform node
        self.built = None         # {"rep", "params", "measured", "matrix_ras"} of the valve on screen
        self.measured = {}        # inputs read from the measurements
        self.active = False

    # ------------------------------------------------------------------ measurements -> inputs
    def read_measurements(self):
        """{generator key: value} from the case's measurements + the table shown in the panel."""
        meas = self.m.meas
        vals, rows = {}, {}
        for plane in ("annulus", "sov", "stj"):
            rows[plane] = meas.plane_measurements(plane)
        heights = {r["height"]: r["height_mm"] for r in meas.height_rows()}
        if rows["annulus"]:
            vals["annulus_min"] = rows["annulus"]["min_d_mm"]
            vals["annulus_max"] = rows["annulus"]["max_d_mm"]
        cor = sorted(h for k, h in heights.items() if k in ("lch", "rch"))
        if cor:
            vals["coronary_h"] = cor[0]
            vals["coronary_h2"] = cor[1] if len(cor) > 1 else None
        if "stj" in heights:
            vals["stj_h"] = heights["stj"]
        if rows["stj"]:
            vals["stj_d"] = rows["stj"]["perimeter_d_mm"]
        return vals, rows, heights

    def fill_from_measurements(self):
        vals, _rows, _h = self.read_measurements()
        self.measured = vals
        for key, box in self.inputs.items():
            v = vals.get(key)
            if v is None:
                v = 0.0 if key == "coronary_h2" else (DEFAULTS[key] or 0.0)
            box.setValue(float(v))

    def reset_design(self):
        for key, w in self.design.items():
            if isinstance(w, qt.QCheckBox):
                w.setChecked(DEFAULTS[key])
            else:
                w.setValue(DEFAULTS[key])

    def params(self):
        p = {}
        for key, box in self.inputs.items():
            v = float(box.value)
            p[key] = None if (key == "coronary_h2" and v <= 0) else v
        for key, w in self.design.items():
            p[key] = bool(w.checked) if isinstance(w, qt.QCheckBox) else (
                int(w.value) if isinstance(DEFAULTS[key], int) else float(w.value))
        return p

    def _measurement_html(self):
        _vals, rows, heights = self.read_measurements()
        html = "<b>Measurements</b> <span style='color:#888'>(current case, mm)</span><table cellpadding=2>"
        html += "<tr><td></td><td><b>area mm²</b></td><td><b>min ⌀</b></td><td><b>max ⌀</b></td><td><b>perim.</b></td></tr>"
        for plane, name in (("annulus", "Annulus"), ("sov", "SOV"), ("stj", "STJ")):
            r = rows.get(plane)
            if r is None:
                html += f"<tr><td>{name}</td><td colspan=4><i>no contour</i></td></tr>"
            else:
                html += (f"<tr><td>{name}</td><td>{r['area_mm2']:.1f}</td><td>{r['min_d_mm']:.1f}</td>"
                         f"<td>{r['max_d_mm']:.1f}</td><td>{r['perimeter_mm']:.1f}</td></tr>")
        html += "</table>Heights: "
        html += ", ".join(f"{k.upper()} {heights[k]:.1f}" for k in ("lch", "rch", "stj") if k in heights) or "<i>none</i>"
        return html

    # ------------------------------------------------------------------ placement
    def valve_matrix_ras(self):
        """4x4 valve -> RAS: origin = annulus centre, z = annulus axis (towards the STJ), x = long diameter."""
        meas = self.m.meas
        frame = meas.annulus_frame()
        ann = meas.plane_measurements("annulus")
        if frame is None or ann is None:
            return None
        c, u, _v, n = frame
        n = unit(n)
        a, b = ann["max_pts"]
        x = (b - a) - np.dot(b - a, n) * n
        x = unit(x) if np.linalg.norm(x) > 1e-6 else unit(u - np.dot(u, n) * n)
        y = np.cross(n, x)                    # right-handed: x, y, z = n
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, n, c
        return M

    # ------------------------------------------------------------------ case / tab lifecycle
    def on_case_loaded(self):
        self.clear()
        if self.m._case_loaded:
            self.fill_from_measurements()
        self.refresh()

    def refresh(self):
        loaded = self.m._case_loaded
        ok = loaded and self.m.meas.plane_measurements("annulus") is not None
        for w in (self.buildButton, self.alignButton, self.measuredButton):
            w.setEnabled(ok)
        self.exportButton.setEnabled(ok and self.built is not None)
        if not loaded:
            self.measLabel.setText("")
            self.reportLabel.setText("")
            return
        self.measLabel.setText(self._measurement_html() if ok else "<i>This case has no annulus contour.</i>")
        if self.built is None:
            path = self._stl_path()
            done = f"Exported valve: <i>{path}</i>" if path and os.path.isfile(path) else "<i>No valve exported yet.</i>"
            self.reportLabel.setText(done)

    def show_segmentation(self):
        return bool(self.showSegCheck.checked)

    def enter(self):
        self.active = True
        slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)
        self._apply_valve_visibility()
        self.align_view()
        qt.QTimer.singleShot(250, self.align_view)
        self.refresh()

    def leave(self):
        self.active = False
        self._apply_valve_visibility()

    def _apply_valve_visibility(self):
        show = self.active and bool(self.showValveCheck.checked)
        for node in self.models.values():
            node.SetDisplayVisibility(show)

    def align_view(self):
        M = self.valve_matrix_ras()
        if M is None:
            return
        c, n = M[:3, 3], M[:3, 2]
        z_mid = 0.5 * (self.built["rep"]["z_bottom"] + self.built["rep"]["z_top"]) if self.built else 10.0
        mid = c + n * z_mid
        ant = ANTERIOR - np.dot(ANTERIOR, n) * n
        ant = unit(ant) if np.linalg.norm(ant) > 1e-6 else M[:3, 0]
        orient = self.m.plane._orient          # same un-mirrored, upright orientation rules
        orient("Red", n, ANTERIOR, c, CONTOUR_FOV)
        orient("Green", ant, n, mid, HEIGHT_FOV)
        orient("Yellow", np.cross(n, ant), n, mid, HEIGHT_FOV)
        try:
            slicer.app.layoutManager().threeDWidget(0).threeDView().setFocalPoint(*[float(v) for v in mid])
        except Exception:
            pass

    # ------------------------------------------------------------------ build / export
    def build(self):
        M = self.valve_matrix_ras()
        if M is None:
            slicer.util.errorDisplay("This case has no annulus contour; the valve is placed on it.")
            return
        params = self.params()
        slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            try:
                rep = make_valve(write=False, verbose=False, out=tempfile.gettempdir(), **params)
            except Exception as e:
                slicer.util.errorDisplay(f"Could not build the valve:\n{e}")
                return
            self._show_meshes(rep["meshes"], M)
        finally:
            slicer.app.restoreOverrideCursor()
        self.built = {"rep": rep, "params": params, "measured": dict(self.measured), "matrix_ras": M}
        self.reportLabel.setText(self._report_html(rep))
        self.refresh()
        self.align_view()

    def _show_meshes(self, meshes, M):
        cid = self.m.caseId()
        if self.transform is None:
            self.transform = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode", f"{cid}_valve_placement")
        slicer.util.updateTransformMatrixFromArray(self.transform, M)
        for part in PARTS:
            mesh = meshes.get(part)
            node = self.models.get(part)
            if mesh is None:
                if node is not None:
                    slicer.mrmlScene.RemoveNode(node)
                    del self.models[part]
                continue
            pd = _polydata(*mesh)
            if node is None:
                node = slicer.modules.models.logic().AddModel(pd)
                node.SetName(f"{cid}_valve_{part}")
                node.SetAndObserveTransformNodeID(self.transform.GetID())
                d = node.GetDisplayNode()
                d.SetColor(*VALVE_COLORS[part])
                d.SetOpacity(1.0 if part == "frame" else 0.8)
                d.SetVisibility2D(True)                 # outline in the slice views
                d.SetSliceIntersectionThickness(2)
                self.models[part] = node
            else:
                node.SetAndObservePolyData(pd)
        self._apply_valve_visibility()

    def _report_html(self, rep):
        lines = [l for l in rep["report_lines"] if not l.startswith("----") and not l.startswith("Triangles")]
        html = "<b>Valve</b><br>" + "<br>".join(lines)
        sov = self.m.meas.plane_measurements("sov")
        frame = self.m.meas.annulus_frame()
        if sov is not None and frame is not None:
            sov_node = self.m.meas.nodes["sov"]["curve"]
            z = float(np.dot(self.m.meas._dense_pts(sov_node).mean(axis=0) - frame[0], unit(frame[3])))
            V = rep["meshes"]["frame"][0]
            near = V[np.abs(V[:, 2] - z) < 0.75]
            if len(near):
                d_frame = 2 * float(np.mean(np.hypot(near[:, 0], near[:, 1])))
                html += (f"<br>SOV at z={z:.1f}: SOV ⌀ {sov['perimeter_d_mm']:.1f} (perimeter-derived) vs frame "
                         f"≈ {d_frame:.1f}")
        return html

    def _stl_path(self):
        cid = self.m.caseId()
        return self.m.store.case_path(cid, VALVE_STL.format(cid=safe_name(cid))) if cid and self.m.outDir() else ""

    def export(self):
        if self.built is None:
            return
        if not self.m.outDir():
            slicer.util.errorDisplay("Select an output folder first.")
            return
        cid = self.m.caseId()
        path = self._stl_path()
        if os.path.isfile(path) and not slicer.util.confirmYesNoDisplay(f"Replace the exported valve?\n{path}"):
            return
        meshes = [m for m in (self.built["rep"]["meshes"].get(p) for p in PARTS) if m is not None]
        V, F = merge(meshes)
        M_lps = np.diag([-1.0, -1.0, 1.0, 1.0]) @ self.built["matrix_ras"]     # valve -> LPS
        V_lps = V @ M_lps[:3, :3].T + M_lps[:3, 3]
        self.m.store.ensure_case_dir(cid)
        tmp = path + ".tmp"
        write_stl(tmp, V_lps, F)
        os.replace(tmp, path)
        info = {"case_id": cid, "saved_at": now_iso(), "stl": os.path.basename(path),
                "coordinate_system": "LPS", "units": "mm",
                "valve_to_lps": M_lps.tolist(),
                "placement": "z = 0 annulus plane at the annulus centre, +z towards the STJ, x = annulus long diameter",
                "parameters": self.built["params"], "measured": self.built["measured"],
                "report": [l for l in self.built["rep"]["report_lines"] if not l.startswith("Triangles")]}
        with open(self.m.store.case_path(cid, VALVE_JSON.format(cid=safe_name(cid))), "w") as f:
            json.dump(info, f, indent=2)
        self.reportLabel.setText(self._report_html(self.built["rep"]) + f"<br><b>Exported:</b> <i>{path}</i>")
        slicer.util.showStatusMessage(f"Case {cid}: valve exported", 4000)

    # ------------------------------------------------------------------ cleanup
    def clear(self):
        for node in list(self.models.values()) + ([self.transform] if self.transform else []):
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception:
                pass
        self.forget()

    def forget(self):
        self.models, self.transform, self.built = {}, None, None
