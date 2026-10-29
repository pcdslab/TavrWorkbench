"""Measurement correction: contours with live metrics, derived diameter lines, height viewing.

* The CONTOUR is the source of truth. Area, perimeter, max/min diameter and the two diameter
  lines are recomputed live every time a control point moves (Slicer's own point dragging).
* One selection drives the four-up view: Red always shows the active contour's plane (editable).
  ANNULUS / SOV / STJ -> Green/Yellow = two perpendicular long-axis planes through the contour's
  centre (shows the plane's position and tilt); STJ-H / LCH / RCH -> Green/Yellow = long-axis planes
  through the selected height point. Heights are read-only.
* Hinge points, centerline points and .vtp models from the data map are loaded view-only.
* While the module is in Segmentation mode every node here is shown (optionally) and locked.
"""
import numpy as np
import qt
import slicer
from vtk.util.numpy_support import vtk_to_numpy

from .cases import collect_case_assets, is_file
from .constants import (CONTOUR_FOV, EDITOR_GROUP_KEYS, HEIGHT_COLORS, HEIGHT_FOV, HEIGHT_NAMES, HEIGHT_SEL,
                        HEIGHTS, PLANE_COLORS, PLANES, SELECTIONS)
from .geometry import compute_metrics, read_mrk_points, resample_closed, unit

METRIC_ROWS = [("Area (mm²)", "area"), ("Perimeter (mm)", "perimeter"), ("Max ⌀ (mm)", "max_d"),
               ("Min ⌀ (mm)", "min_d"), ("Mean ⌀ (mm)", "mean_d"), ("Eccentricity", "ecc")]


def _is_markups(node):
    return node is not None and node.IsA("vtkMRMLMarkupsNode")


class MeasurementEditor:
    def __init__(self, on_update=None):
        self._on_update = on_update
        self.selection = PLANES[0]
        self.mode_active = False        # True while the module is in Measurements mode
        self.show_all_heights = True
        self.show_in_review = True      # visibility while in Segmentation mode
        self._tags = []
        self._guard = False
        self._reset()

    def _reset(self):
        self.nodes = {}          # plane -> {"curve", "max", "min"}
        self.heights = {}        # height key -> main markups node (used for the height values)
        self.height_parts = {}   # height key -> every node its file added (incl. the main one)
        self.extras = []         # (group, node): view-only hinge points / centerline markups and models
        self.stray = []          # extra nodes found inside contour files (always hidden)
        self.orig = {}           # plane -> original control points
        self.orig_metrics = {}   # plane -> metrics of the original contour
        self.dirty = set()
        self.from_saved = set()
        self.active_plane = None
        self.cur = None          # metrics of the active contour
        self._last = None

    # ============================================================ queries
    def has_contours(self):
        return bool(self.nodes)

    def is_dirty(self):
        return bool(self.dirty)

    def is_heights_view(self):
        return self.selection in HEIGHT_SEL

    def available_selections(self):
        return [k for k in SELECTIONS if k in self.nodes or HEIGHT_SEL.get(k) in self.heights]

    def all_nodes(self):
        out = []
        for nodes in self.nodes.values():
            out.extend(nodes.values())
        for parts in self.height_parts.values():
            out.extend(parts)
        out.extend(node for _group, node in self.extras)
        out.extend(self.stray)
        return out

    # ============================================================ loading
    def load(self, sample, saved_contour_path=None):
        """Create every measurement node of `sample`. saved_contour_path(plane) -> path of an earlier
        correction (or None); when given, that correction replaces the original control points."""
        self.clear()
        self._guard = True
        try:
            for plane in PLANES:
                self._load_plane(sample, plane, saved_contour_path)
            self._load_heights(sample)
            self._load_extras(sample)
        finally:
            self._guard = False

        available = self.available_selections()
        if available and self.selection not in available:
            self.selection = available[0]
        if self.selection in self.nodes:
            plane = self.selection
        elif self.nodes:
            plane = "annulus" if "annulus" in self.nodes else next(iter(self.nodes))
        else:
            plane = None
        if plane:
            self._activate_plane(plane)
        self.apply_visibility()

    def _load_plane(self, sample, plane, saved_contour_path):
        path = (sample.get("contours") or {}).get(plane)
        if not is_file(path):
            return
        try:
            curve, parts = self._load_markups_all(path)
        except Exception as e:
            print(f"[TavrWorkbench] WARNING: could not load contour {plane} from {path}: {e}")
            curve, parts = None, []
        self.stray.extend(parts[1:])  # anything else in the contour file: tracked, hidden, removed with the case
        if curve is None:
            return
        curve.SetName(f"{plane}_contour")
        self._style(curve, PLANE_COLORS[plane], 0.5)
        try:
            curve.SetCurveTypeToCardinalSpline()
        except Exception:
            pass
        nodes = {"curve": curve}
        # Diameter lines are derived from the contour, so they are always rebuilt rather than loaded
        for key in ("max", "min"):
            line = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", f"{plane}_{key}_d")
            line.CreateDefaultDisplayNodes()
            line.AddControlPointWorld(0, 0, 0)
            line.AddControlPointWorld(1, 0, 0)
            self._style(line, PLANE_COLORS[plane], 1.0)
            line.SetLocked(True)
            nodes[key] = line

        self.orig[plane] = self._get_pts(curve).copy()
        self.orig_metrics[plane] = compute_metrics(self._dense_pts(curve))
        saved = saved_contour_path(plane) if saved_contour_path else None
        if saved:
            try:
                self._set_pts(curve, read_mrk_points(saved))
                self.from_saved.add(plane)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not read saved contour {saved}: {e}")
        self.nodes[plane] = nodes
        m = compute_metrics(self._dense_pts(curve))
        if m:
            self._update_lines(nodes, m)

    @staticmethod
    def _load_markups_all(path):
        """Load a .mrk.json and return (first_node, all_nodes_it_added). slicer.util.loadMarkups returns only
        the first markup of a file; files holding several (e.g. a height line + its points) add the rest
        silently, and those must be tracked too so they can be hidden and removed with the case."""
        def markup_ids():
            return {n.GetID() for n in slicer.util.getNodesByClass("vtkMRMLMarkupsNode")}

        before = markup_ids()
        first = slicer.util.loadMarkups(path)
        added = [slicer.mrmlScene.GetNodeByID(i) for i in sorted(markup_ids() - before)]
        added = [n for n in added if n is not None]
        if first is not None:
            added = [first] + [n for n in added if n.GetID() != first.GetID()]
        return (added[0] if added else None), added

    def _load_heights(self, sample):
        for key in HEIGHTS:
            path = (sample.get("heights") or {}).get(key)
            if not is_file(path):
                continue
            try:
                node, parts = self._load_markups_all(path)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not load height {key} from {path}: {e}")
                continue
            if node is None:
                continue
            for i, part in enumerate(parts):
                part.SetName(f"height_{key}" if i == 0 else f"height_{key}_{i}")
                self._style_height(part, key)
            self.heights[key] = node            # used for the height values
            self.height_parts[key] = parts      # everything the file added (shown / hidden together)

    def _load_extras(self, sample):
        markups, models = collect_case_assets(sample)
        for key, path in markups.items():
            group = key.split(".")[0]
            if group in EDITOR_GROUP_KEYS:
                continue
            try:
                _node, parts = self._load_markups_all(path)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not load markup {key} from {path}: {e}")
                continue
            for i, node in enumerate(parts):
                node.SetName(key if i == 0 else f"{key}_{i}")
                if not node.GetDisplayNode():
                    node.CreateDefaultDisplayNodes()
                self._slice_intersections(node.GetDisplayNode())
                node.SetLocked(True)
                self.extras.append((group, node))

        for key, path in models.items():
            try:
                node = slicer.util.loadModel(path)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: could not load model {key} from {path}: {e}")
                continue
            if node is None:
                continue
            node.SetName(key)
            if not node.GetDisplayNode():
                node.CreateDefaultDisplayNodes()
            d = node.GetDisplayNode()
            if d:
                lower = key.lower()
                if lower.endswith("surface"):
                    d.SetColor(0.9, 0.85, 0.2)
                    d.SetOpacity(0.35)
                elif lower.endswith("curve"):
                    d.SetColor(1.0, 0.1, 0.1)
                    if hasattr(d, "SetLineWidth"):
                        d.SetLineWidth(3)
                self._slice_intersections(d)
            self.extras.append((key.split(".")[0], node))

    def clear(self):
        """Remove every node of the current case from the scene."""
        self._detach()
        for node in self.all_nodes():
            try:
                slicer.mrmlScene.RemoveNode(node)
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: failed removing node: {e}")
        self._reset()

    def forget(self):
        """The scene is being closed: drop node references without touching the scene."""
        self._detach()
        self._reset()

    # ============================================================ styling
    @staticmethod
    def _slice_intersections(display_node):
        if display_node is not None and hasattr(display_node, "SetSliceIntersectionVisibility"):
            try:
                display_node.SetSliceIntersectionVisibility(True)
            except Exception:
                pass

    @staticmethod
    def _style(node, color, thickness):
        if not node.GetDisplayNode():
            node.CreateDefaultDisplayNodes()
        d = node.GetDisplayNode()
        d.SetSelectedColor(*color)
        d.SetColor(*color)
        d.SetPointLabelsVisibility(False)
        d.SetPropertiesLabelVisibility(False)
        d.SetGlyphScale(1.6)
        d.SetLineThickness(thickness)

    @staticmethod
    def _style_height(node, key):
        if not node.GetDisplayNode():
            node.CreateDefaultDisplayNodes()
        d = node.GetDisplayNode()
        col = HEIGHT_COLORS[key]
        d.SetSelectedColor(*col)
        d.SetColor(*col)
        d.SetGlyphScale(2.5)
        d.SetTextScale(3.0)
        d.SetLineThickness(0.8)
        d.SetPropertiesLabelVisibility(False)
        d.SetPointLabelsVisibility(True)
        n = node.GetNumberOfControlPoints()
        for i in range(n):
            node.SetNthControlPointLabel(i, key.upper() if n == 1 else f"{key.upper()}{i + 1}")
        node.SetLocked(True)
        try:  # show the point/line in slice views even when slightly off-plane (Slicer >= 5)
            d.SetSliceDisplayModeToProjection()
        except Exception:
            pass

    # ============================================================ curve helpers
    @staticmethod
    def _get_pts(curve):
        n = curve.GetNumberOfControlPoints()
        out = np.zeros((n, 3))
        for i in range(n):
            p = [0.0, 0.0, 0.0]
            curve.GetNthControlPointPositionWorld(i, p)
            out[i] = p
        return out

    def _set_pts(self, curve, pts):
        was = self._guard
        self._guard = True
        wm = curve.StartModify()
        try:
            if curve.GetNumberOfControlPoints() != len(pts):
                curve.RemoveAllControlPoints()
                for p in pts:
                    curve.AddControlPointWorld(float(p[0]), float(p[1]), float(p[2]))
            else:
                for i, p in enumerate(pts):
                    curve.SetNthControlPointPositionWorld(i, float(p[0]), float(p[1]), float(p[2]))
        finally:
            curve.EndModify(wm)
            self._guard = was

    def _dense_pts(self, curve):
        pts = curve.GetCurvePointsWorld()
        arr = vtk_to_numpy(pts.GetData()).copy() if pts is not None and pts.GetNumberOfPoints() else np.zeros((0, 3))
        return arr if len(arr) >= 4 else self._get_pts(curve)

    def _update_lines(self, nodes, m):
        was = self._guard
        self._guard = True
        try:
            for key, pts in (("max", m["max_pts"]), ("min", m["min_pts"])):
                line = nodes.get(key)
                if line is not None:
                    for i in range(2):
                        line.SetNthControlPointPositionWorld(i, *[float(v) for v in pts[i]])
        finally:
            self._guard = was

    # ============================================================ live update
    def _attach(self, curve):
        ev = slicer.vtkMRMLMarkupsNode
        self._tags.append((curve, curve.AddObserver(ev.PointModifiedEvent, self._on_curve_modified)))
        self._tags.append((curve, curve.AddObserver(ev.PointEndInteractionEvent, self._on_curve_modified)))

    def _detach(self):
        for node, tag in self._tags:
            try:
                node.RemoveObserver(tag)
            except Exception:
                pass
        self._tags = []

    def _activate_plane(self, plane):
        self._detach()
        self.active_plane = plane
        curve = self.nodes[plane]["curve"]
        self._last = self._get_pts(curve)
        self._attach(curve)
        self._refresh(mark=False)

    def _on_curve_modified(self, caller, event):
        if self._guard or self.active_plane is None:
            return
        cur = self._get_pts(caller)
        if self._last is not None and cur.shape == self._last.shape and np.allclose(cur, self._last, atol=1e-6):
            return  # nothing actually moved
        self._last = cur
        self._refresh(mark=True)

    def _refresh(self, mark=True):
        if self.active_plane is None:
            return
        nodes = self.nodes[self.active_plane]
        m = compute_metrics(self._dense_pts(nodes["curve"]))
        if m is None:
            return
        self.cur = m
        self._update_lines(nodes, m)
        if mark:
            self.dirty.add(self.active_plane)
        self._notify()

    def _notify(self):
        if self._on_update:
            try:
                self._on_update()
            except Exception as e:
                print(f"[TavrWorkbench] WARNING: measurement panel update failed: {e}")

    # ============================================================ mode / selection
    def set_mode_active(self, active):
        self.mode_active = bool(active)
        self.apply_visibility()
        if self.mode_active and self.nodes:
            self._apply_layout()
            self._align_soon()

    def set_show_all_heights(self, show):
        self.show_all_heights = bool(show)
        self.apply_visibility()

    def set_show_in_review(self, show):
        self.show_in_review = bool(show)
        self.apply_visibility()

    def select(self, key):
        if key not in SELECTIONS:
            return
        self.selection = key
        if key in self.nodes and key != self.active_plane:
            self._activate_plane(key)
        if self.mode_active and self.nodes:
            self.apply_visibility()
            self._apply_layout()
            self._align_soon()
        self._notify()

    def apply_visibility(self):
        if not self.mode_active:
            # Segmentation review: everything (incl. centerline) for context, all locked
            for n in self.all_nodes():
                n.SetDisplayVisibility(self.show_in_review and n not in self.stray)
                if _is_markups(n):
                    n.SetLocked(True)
            return
        heights_view = self.is_heights_view()
        # contours + diameter lines: active plane only in the contour view, all planes in the heights view
        for plane, nodes in self.nodes.items():
            active = plane == self.active_plane
            for n in nodes.values():
                n.SetDisplayVisibility(active or heights_view)
            nodes["curve"].SetLocked(not active)
        sel_height = HEIGHT_SEL.get(self.selection)
        all_heights = not heights_view or self.show_all_heights
        for key, parts in self.height_parts.items():
            for n in parts:
                n.SetDisplayVisibility(all_heights or key == sel_height)
        # Centerline (points, curve, surface) belongs to segmentation review only;
        # hinge points are shown for context in the heights view.
        for group, n in self.extras:
            n.SetDisplayVisibility(heights_view and group != "centerline")
        for n in self.stray:
            n.SetDisplayVisibility(False)

    def _apply_layout(self):
        # Four-up for contours and heights alike: Red = contour plane, Green/Yellow = long axis, + 3D
        slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    def _align_soon(self):
        self.align_view()
        qt.QTimer.singleShot(250, self.align_view)  # slice widgets need a moment to get their final size

    # ============================================================ views
    @staticmethod
    def _set_fov(slice_node, fov):
        w, h = slice_node.GetDimensions()[:2]
        a = w / h if h else 1.0
        slice_node.SetFieldOfView(fov * a if a >= 1 else fov, fov if a >= 1 else fov / a, 1)
        slice_node.UpdateMatrices()

    def align_view(self):
        if not self.mode_active or self.cur is None:
            return
        widget = slicer.app.layoutManager().sliceWidget("Red")
        if widget is None:
            return
        c, u, v, n = self.cur["plane"]
        red = widget.mrmlSliceNode()
        red.SetSliceToRASByNTP(n[0], n[1], n[2], u[0], u[1], u[2], c[0], c[1], c[2], 0)
        self._set_fov(red, CONTOUR_FOV)
        if self.is_heights_view():
            self._align_height_views()
        else:
            self._align_contour_views()

    def _orient_slice(self, name, a, n, point):
        """Slice whose horizontal axis is `a` and vertical axis is `n`, through `point`."""
        widget = slicer.app.layoutManager().sliceWidget(name)
        if widget is None:
            return
        sn = widget.mrmlSliceNode()
        normal = unit(np.cross(a, n))
        sn.SetSliceToRASByNTP(normal[0], normal[1], normal[2], a[0], a[1], a[2], point[0], point[1], point[2], 0)
        self._set_fov(sn, HEIGHT_FOV)

    def _align_height_views(self):
        """Green/Yellow = long-axis planes (contain the annulus axis) through the selected height point."""
        fr = self.annulus_frame()
        if fr is None:
            return
        c, u, v, n = fr
        node = self.heights.get(HEIGHT_SEL.get(self.selection))
        p = self._get_pts(node).mean(axis=0) if node is not None and node.GetNumberOfControlPoints() else c
        n = unit(n)
        d = (p - c) - np.dot(p - c, n) * n
        a = unit(d) if np.linalg.norm(d) > 1e-3 else unit(u - np.dot(u, n) * n)
        b = unit(np.cross(n, a))
        self._orient_slice("Green", a, n, p)
        self._orient_slice("Yellow", b, n, p)
        try:
            slicer.app.layoutManager().threeDWidget(0).threeDView().setFocalPoint(float(p[0]), float(p[1]), float(p[2]))
        except Exception:
            pass

    def _align_contour_views(self):
        """Green/Yellow = two perpendicular long-axis planes through the active contour's centre; both
        contain the contour's normal, so the contour shows up as a line across each view."""
        c, u, v, n = self.cur["plane"]
        n = unit(n)
        fr = self.annulus_frame()
        if fr is not None and np.dot(n, fr[3]) < 0:
            n = -n  # keep "up the aortic root" pointing up in both views
        a = unit(u - np.dot(u, n) * n)
        b = unit(np.cross(n, a))
        self._orient_slice("Green", a, n, c)
        self._orient_slice("Yellow", b, n, c)
        try:
            slicer.app.layoutManager().threeDWidget(0).threeDView().setFocalPoint(float(c[0]), float(c[1]), float(c[2]))
        except Exception:
            pass

    def annulus_frame(self):
        """(centroid, u, v, n) of the CURRENT annulus contour with n pointing up the aortic root."""
        if "annulus" not in self.nodes:
            return None
        m = compute_metrics(self._dense_pts(self.nodes["annulus"]["curve"]))
        if m is None:
            return None
        c, u, v, n = m["plane"]
        up = None
        if "stj" in self.nodes:
            up = self._dense_pts(self.nodes["stj"]["curve"]).mean(axis=0) - c
        else:
            pts = [self._get_pts(nd) for nd in self.heights.values() if nd.GetNumberOfControlPoints() > 0]
            if pts:
                up = np.vstack(pts).mean(axis=0) - c
        if up is not None and np.dot(up, n) < 0:
            n = -n
        return c, u, v, n

    # ============================================================ actions
    def resample(self, n_points):
        if self.active_plane is None:
            return
        curve = self.nodes[self.active_plane]["curve"]
        new = resample_closed(self._dense_pts(curve), n_points)
        self._set_pts(curve, new)
        try:
            curve.SetCurveTypeToCardinalSpline()
        except Exception:
            pass
        self._last = new
        self._refresh(mark=True)

    def reset_plane(self):
        p = self.active_plane
        if p is None:
            return
        self._set_pts(self.nodes[p]["curve"], self.orig[p])
        self._last = self.orig[p].copy()
        self.dirty.discard(p)
        self._refresh(mark=False)

    # ============================================================ saving
    def save_nodes(self, path_for):
        """Write contour + diameter lines of every plane; path_for(plane, key) -> file path."""
        for plane, nodes in self.nodes.items():
            for key in ("curve", "max", "min"):
                path = path_for(plane, key)
                if not slicer.util.saveNode(nodes[key], path):
                    raise IOError(f"could not save {plane} {key} to {path}")

    def metrics_rows(self):
        rows = []
        for plane, nodes in self.nodes.items():
            m = compute_metrics(self._dense_pts(nodes["curve"]))
            if m is None:
                continue
            rows.append({
                "plane": plane,
                "area_mm2": round(m["area"], 2), "perimeter_mm": round(m["perimeter"], 2),
                "max_d_mm": round(m["max_d"], 2), "min_d_mm": round(m["min_d"], 2),
                "mean_d_mm": round(m["mean_d"], 2), "eccentricity": round(m["ecc"], 4),
                "n_control_pts": nodes["curve"].GetNumberOfControlPoints(),
            })
        return rows

    def mark_saved(self):
        self.dirty.clear()
        self._notify()

    # ============================================================ panel text
    def info_html(self):
        p, m = self.active_plane, self.cur
        if p is None or m is None:
            return ""
        o = self.orig_metrics.get(p) or m
        html = f"<b>{p.upper()}</b> &nbsp; control pts: {self.nodes[p]['curve'].GetNumberOfControlPoints()}"
        if p in self.dirty:
            html += " &nbsp; <span style='color:#c60'>edited</span>"
        if p in self.from_saved:
            html += " &nbsp; <i>(saved correction loaded)</i>"
        html += "<table cellpadding=3><tr><td></td><td><b>now</b></td><td><b>original</b></td><td><b>Δ</b></td></tr>"
        for label, k in METRIC_ROWS:
            html += f"<tr><td>{label}</td><td>{m[k]:.2f}</td><td>{o[k]:.2f}</td><td>{m[k] - o[k]:+.2f}</td></tr>"
        return html + "</table>"

    def heights_html(self):
        fr = self.annulus_frame()
        if fr is None:
            return ""
        if not self.heights:
            return "<i>No height files for this case.</i>"
        c, u, v, n = fr
        html = ("<b>HEIGHTS</b> <span style='color:#888'>(above current annulus plane, mm)</span>"
                "<table cellpadding=3><tr><td></td><td><b>height</b></td><td><b>line length</b></td></tr>")
        for key in HEIGHTS:
            node = self.heights.get(key)
            if node is None or node.GetNumberOfControlPoints() == 0:
                continue
            pts = self._get_pts(node)
            h = (pts - c) @ n
            if len(pts) == 2:
                htxt = f"{h[0]:.1f} → {h[1]:.1f} (Δ {abs(h[1] - h[0]):.1f})"
                ltxt = f"{np.linalg.norm(pts[1] - pts[0]):.1f}"
            else:
                htxt = ", ".join(f"{x:.1f}" for x in h)
                ltxt = "–"
            col = "#%02x%02x%02x" % tuple(int(255 * x) for x in HEIGHT_COLORS[key])
            html += (f"<tr><td><span style='color:{col}'>●</span> {HEIGHT_NAMES[key]}</td>"
                     f"<td>{htxt}</td><td>{ltxt}</td></tr>")
        return html + "</table>"