"""Annular-plane recomputation: annulus contour, diameters and heights from the three hinge points.

A port of the batch scripts
    * aortic annulus measurement pipeline   (spline contour + robust HU correction)
    * compute_coronary_hinge_lines.py       (LCH / RCH)
    * STJ height script                     (STJ_H)
for ONE case, runnable inside 3D Slicer without extra packages: only numpy and SimpleITK (both ship
with Slicer). The scipy / scikit-image calls of the original are re-implemented here in numpy, with the
same parameters and behaviour; SimpleITK is used exactly as before for reading and reslicing.

All coordinates in this module are LPS (ITK / SimpleITK physical space), like the original scripts.
Max / min diameters use the extension's own definition (geometry.compute_metrics), so the values match
the Measurements tab.
"""
import json
import os
from collections import deque

import numpy as np

from .constants import ANNULUS_PIPELINE
from .geometry import compute_metrics

MRK_SCHEMA = ("https://raw.githubusercontent.com/slicer/slicer/master/Modules/Loadable/Markups/"
              "Resources/Schema/markups-schema-v1.0.3.json#")
STJ_CUSPS = ("L", "R", "N")


# ============================================================================ markup files
def read_point_lps(path, index=0):
    """One control point of a .mrk.json, in LPS."""
    with open(path) as f:
        markup = json.load(f)["markups"][0]
    points = markup.get("controlPoints") or []
    if len(points) <= index:
        raise ValueError(f"No control point {index + 1} in {path}")
    pos = np.array(points[index]["position"], dtype=float)
    if markup.get("coordinateSystem", "LPS").upper() == "RAS":
        pos = pos * np.array([-1.0, -1.0, 1.0])
    return pos


def _control_point(i, label, pos, associated=""):
    return {
        "id": str(i), "label": label, "description": "", "associatedNodeID": associated,
        "position": [float(pos[0]), float(pos[1]), float(pos[2])],
        "orientation": [-1.0, -0.0, -0.0, -0.0, -1.0, -0.0, 0.0, 0.0, 1.0],
        "selected": True, "locked": False, "visibility": True, "positionStatus": "defined",
    }


def _display(**overrides):
    d = {
        "visibility": True, "opacity": 1.0, "color": [0.4, 1.0, 1.0],
        "selectedColor": [1.0, 0.5, 0.5], "activeColor": [0.4, 1.0, 0.0],
        "propertiesLabelVisibility": True, "pointLabelsVisibility": False,
        "textScale": 3.0, "glyphType": "Sphere3D", "glyphScale": 3.0, "glyphSize": 5.0, "useGlyphScale": True,
        "sliceProjection": False, "sliceProjectionUseFiducialColor": True,
        "sliceProjectionOutlinedBehindSlicePlane": False, "sliceProjectionColor": [1.0, 1.0, 1.0],
        "sliceProjectionOpacity": 0.6, "lineThickness": 0.2, "handlesInteractive": False,
        "translationHandleVisibility": True, "rotationHandleVisibility": True, "scaleHandleVisibility": False,
        "interactionHandleScale": 3.0, "snapMode": "toVisibleSurface",
    }
    d.update(overrides)
    return d


def _write_markup(path, markup):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"@schema": MRK_SCHEMA, "markups": [markup]}, f, indent=4)
    os.replace(tmp, path)


def write_point(path, label, pos_lps):
    """Single-point Fiducial markup (hinge points)."""
    _write_markup(path, {
        "type": "Fiducial", "coordinateSystem": "LPS", "coordinateUnits": "mm", "locked": False,
        "fixedNumberOfControlPoints": False, "labelFormat": "%N-%d", "lastUsedControlPointNumber": 1,
        "controlPoints": [_control_point(1, label, pos_lps)],
        "display": _display(pointLabelsVisibility=True),
    })


def write_contour(path, pts_lps, area_mm2, perimeter_mm):
    """ClosedCurve markup, same layout as save_slicer_contour() of the original pipeline."""
    _write_markup(path, {
        "type": "ClosedCurve", "coordinateSystem": "LPS", "coordinateUnits": "mm", "locked": False,
        "fixedNumberOfControlPoints": False, "labelFormat": "%N-%d",
        "lastUsedControlPointNumber": len(pts_lps),
        "controlPoints": [_control_point(i, f"AC-{i}", p) for i, p in enumerate(pts_lps, start=1)],
        "measurements": [
            {"name": "length", "enabled": True, "value": float(perimeter_mm), "units": "mm",
             "printFormat": "%-#4.4gmm"},
            {"name": "area", "enabled": True, "value": round(area_mm2 / 100.0, 6), "units": "cm2",
             "printFormat": "%-#4.4gcm2"},
        ],
        "display": _display(color=[0.0, 1.0, 1.0], textScale=1.7, glyphScale=2.1),
    })


def write_line(path, label_prefix, p1_lps, p2_lps, selected_color=None):
    """Two-point Line markup (diameters and heights), same layout as the original scripts."""
    length = float(np.linalg.norm(np.asarray(p1_lps) - np.asarray(p2_lps)))
    _write_markup(path, {
        "type": "Line", "coordinateSystem": "LPS", "coordinateUnits": "mm", "locked": False,
        "fixedNumberOfControlPoints": False, "labelFormat": "%N-%d", "lastUsedControlPointNumber": 2,
        "controlPoints": [_control_point(1, f"{label_prefix}-1", p1_lps),
                          _control_point(2, f"{label_prefix}-2", p2_lps)],
        "measurements": [{"name": "length", "enabled": True, "value": length, "units": "mm",
                          "printFormat": "%-#4.4gmm"}],
        "display": _display(selectedColor=selected_color or [0.43529411764705883, 0.7215686274509804,
                                                             0.8235294117647058],
                            lineColorFadingStart=1.0, lineColorFadingEnd=10.0,
                            lineColorFadingSaturation=1.0, lineColorFadingHueOffset=0.0),
    })
    return length


# ============================================================================ plane geometry
def compute_plane(L, N, R, shift_mm=0.0):
    """Annular plane of the measurement pipeline: (centroid, normal, u, w, shifted centroid)."""
    centroid = (L + N + R) / 3.0
    v1, v2 = N - L, R - L
    normal = np.cross(v1, v2)
    norm = np.linalg.norm(normal)
    if norm < 1e-8:
        raise ValueError("The hinge points are (nearly) on one line; they do not define a plane.")
    normal = normal / norm
    if normal[2] < 0:
        normal = -normal
    u = v1 / np.linalg.norm(v1)
    w = np.cross(normal, u)
    w /= np.linalg.norm(w)
    return centroid, normal, u, w, centroid + shift_mm * normal


def height_plane(L, R, N):
    """Plane used by the height scripts: (point on plane, unit normal) through the three hinge points."""
    normal = np.cross(R - L, N - L)
    norm = np.linalg.norm(normal)
    if norm < 1e-8:
        raise ValueError("The hinge points are (nearly) on one line; they do not define a plane.")
    return L, normal / norm


def perpendicular_foot(point, plane_point, normal):
    signed = float(np.dot(point - plane_point, normal))
    return point - signed * normal, abs(signed)


# ============================================================================ SimpleITK I/O
def load_images(ct_path, seg_path):
    import SimpleITK as sitk
    ct = sitk.ReadImage(ct_path)
    seg = sitk.ReadImage(seg_path)
    if seg.GetNumberOfComponentsPerPixel() > 1:
        seg = sitk.VectorIndexSelectionCast(seg, 0)
    return ct, sitk.Cast(seg, sitk.sitkUInt8)


def reslice(image, size_2d, res, origin_2d, direction_2d, nearest, float_output):
    import SimpleITK as sitk
    r = sitk.ResampleImageFilter()
    r.SetSize([size_2d, size_2d, 1])
    r.SetOutputSpacing([res, res, 1.0])
    r.SetOutputOrigin(origin_2d)
    r.SetOutputDirection(direction_2d)
    r.SetInterpolator(sitk.sitkNearestNeighbor if nearest else sitk.sitkLinear)
    r.SetOutputPixelType(sitk.sitkFloat32 if float_output else sitk.sitkUInt8)
    arr = np.squeeze(sitk.GetArrayFromImage(r.Execute(image)))
    if arr.ndim != 2:
        raise ValueError(f"Resliced array is {arr.ndim}D")
    return arr


# ============================================================================ 2D helpers (numpy)
def fill_holes(mask):
    """scipy.ndimage.binary_fill_holes: background not 4-connected to the border becomes foreground."""
    mask = np.asarray(mask, bool)
    H, W = mask.shape
    outside = np.zeros_like(mask)
    queue = deque()
    for r in range(H):
        for c in (0, W - 1):
            if not mask[r, c] and not outside[r, c]:
                outside[r, c] = True
                queue.append((r, c))
    for c in range(W):
        for r in (0, H - 1):
            if not mask[r, c] and not outside[r, c]:
                outside[r, c] = True
                queue.append((r, c))
    while queue:
        r, c = queue.popleft()
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < H and 0 <= cc < W and not mask[rr, cc] and not outside[rr, cc]:
                outside[rr, cc] = True
                queue.append((rr, cc))
    return ~outside


def largest_component(mask):
    """Largest 8-connected region (skimage.measure.label default for 2D): (centroid (row, col), area) or None."""
    mask = np.asarray(mask, bool)
    H, W = mask.shape
    seen = np.zeros_like(mask)
    best = None
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        seen[r0, c0] = True
        queue, pixels = deque([(r0, c0)]), []
        while queue:
            r, c = queue.popleft()
            pixels.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < H and 0 <= cc < W and mask[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True
                        queue.append((rr, cc))
        if best is None or len(pixels) > len(best):
            best = pixels
    if best is None:
        return None
    pts = np.array(best, dtype=float)
    return (float(pts[:, 0].mean()), float(pts[:, 1].mean())), len(best)


def _gaussian_kernel(sigma, truncate=4.0):
    radius = int(truncate * float(sigma) + 0.5)
    x = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / k.sum(), radius


def gaussian_filter1d(values, sigma):
    """scipy.ndimage.gaussian_filter1d (mode='reflect', truncate=4)."""
    k, radius = _gaussian_kernel(sigma)
    padded = np.pad(np.asarray(values, float), radius, mode="symmetric")
    return np.convolve(padded, k, mode="valid")


def gaussian_filter2d(image, sigma):
    """scipy.ndimage.gaussian_filter for a 2D image (mode='reflect', truncate=4)."""
    k, radius = _gaussian_kernel(sigma)
    img = np.asarray(image, float)
    padded = np.pad(img, radius, mode="symmetric")
    rows = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, padded)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, rows)


def find_peaks(x, height):
    """scipy.signal.find_peaks(x, height=...): local maxima (plateaus -> middle), edges excluded."""
    x = np.asarray(x, float)
    peaks, i, n = [], 1, len(x)
    while i < n - 1:
        if x[i - 1] < x[i]:
            j = i
            while j + 1 < n and x[j + 1] == x[i]:
                j += 1
            if j + 1 < n and x[j + 1] < x[i]:
                peaks.append((i + j) // 2)
                i = j
        i += 1
    return np.array([p for p in peaks if x[p] >= height], dtype=int)


def polygon_mask(shape, pts):
    """skimage.draw.polygon2mask: pixel centres inside the (row, col) polygon (even-odd rule)."""
    H, W = shape
    rr, cc = np.mgrid[0:H, 0:W]
    rr, cc = rr.astype(float), cc.astype(float)
    inside = np.zeros(shape, bool)
    pr, pc = np.asarray(pts, float)[:, 0], np.asarray(pts, float)[:, 1]
    n = len(pts)
    for i in range(n):
        r1, c1, r2, c2 = pr[i], pc[i], pr[(i + 1) % n], pc[(i + 1) % n]
        crosses = (r1 > rr) != (r2 > rr)
        with np.errstate(divide="ignore", invalid="ignore"):
            c_at = (c2 - c1) * (rr - r1) / (r2 - r1) + c1
        inside ^= crosses & (cc < c_at)
    return inside


# ============================================================================ prior mask + correction
def build_annulus_mask(sampled, res):
    """Labels at the plane centre (excluding background 0 and coronaries 4) form the prior mask."""
    sampled = np.squeeze(sampled)
    cy, cx = sampled.shape[0] // 2, sampled.shape[1] // 2
    h = int(30 / res) // 2
    centre = sampled[cy - h: cy + h, cx - h: cx + h]
    exclude = {0, 4}
    valid = [int(v) for v in np.unique(centre) if v not in exclude]
    if valid:
        mask = np.isin(sampled, valid)
    else:
        mask = (sampled != 0) & (sampled != 4)
        valid = [int(v) for v in np.unique(sampled) if v not in exclude]
    return fill_holes(mask).astype(np.uint8), valid


def _radial_hu_boundary(prior_mask, ct_slice, res, hu_lo, hu_hi, margin_mm, gap_tolerance_mm, n_rays):
    comp = largest_component(prior_mask)
    if comp is None:
        return None, 0
    (cy, cx), _area = comp
    H, W = prior_mask.shape
    max_r = np.hypot(H, W)
    margin_px = margin_mm / res
    gap_tol_px = max(0.0, gap_tolerance_mm / res)
    step = 0.5

    def hu_at(t, dr, dc):
        ri = int(np.clip(np.round(cy + t * dr), 0, H - 1))
        ci = int(np.clip(np.round(cx + t * dc), 0, W - 1))
        return ct_slice[ri, ci]

    pts, n_clipped = [], 0
    for theta in np.linspace(0, 2 * np.pi, n_rays, endpoint=False):
        dr, dc = np.sin(theta), np.cos(theta)
        r0, prev_t = None, 0.0
        for t in np.arange(1.0, max_r, step):
            ri = int(np.clip(np.round(cy + t * dr), 0, H - 1))
            ci = int(np.clip(np.round(cx + t * dc), 0, W - 1))
            if prior_mask[ri, ci] == 0:
                r0 = t - 0.25
                break
            prev_t = t
        if r0 is None:
            r0 = prev_t
        hit_margin = False
        if hu_lo <= hu_at(r0, dr, dc) <= hu_hi:      # inside the lumen window: walk outwards
            final_t, miss, t = r0, 0.0, r0
            while t <= r0 + margin_px:
                if hu_lo <= hu_at(t, dr, dc) <= hu_hi:
                    miss, final_t = 0.0, t
                else:
                    miss += step
                    if miss > gap_tol_px:
                        break
                t += step
            else:
                hit_margin = True
        else:                                        # outside the window: walk inwards
            final_t, miss, t = r0, 0.0, r0
            while t >= r0 - margin_px:
                if hu_lo <= hu_at(t, dr, dc) <= hu_hi:
                    miss, final_t = 0.0, t
                else:
                    miss += step
                    if miss > gap_tol_px:
                        break
                t -= step
            else:
                hit_margin = True
        n_clipped += int(hit_margin)
        pts.append((cy + final_t * dr, cx + final_t * dc))
    return np.array(pts), n_clipped


def correct_mask_with_intensity(original_mask, ct_slice, res, margin_mm, hu_expansion_k,
                                gap_tolerance_mm, n_rays, ct_smoothing_sigma_mm):
    """Refine the prior mask with CT intensity (robust HU estimate + per-ray radial walk)."""
    hu_vals = ct_slice[original_mask > 0]
    if hu_vals.size == 0:
        return original_mask.copy(), {}
    n_bins = min(100, max(30, len(hu_vals) // 20))
    counts, edges = np.histogram(hu_vals, bins=n_bins)
    centers = (edges[:-1] + edges[1:]) / 2
    smoothed = gaussian_filter1d(counts.astype(float), 2.0)
    peaks = find_peaks(smoothed, height=np.max(smoothed) * 0.1)

    def median_mad():
        med = float(np.median(hu_vals))
        mad = float(np.median(np.abs(hu_vals - med)))
        return med, (1.4826 * mad if mad > 0 else float(np.std(hu_vals)))

    method = "median+MAD (unimodal)"
    if len(peaks) >= 2:
        right, second = peaks[-1], peaks[-2]
        valley = second + int(np.argmin(smoothed[second:right + 1]))
        true_vals = hu_vals[hu_vals >= centers[valley]]
        if len(true_vals) > 0.05 * len(hu_vals):
            hu_mean, hu_std = float(np.mean(true_vals)), float(np.std(true_vals))
            method = f"peak isolated above {centers[valley]:.1f} HU"
        else:
            hu_mean, hu_std = median_mad()
            method = "median+MAD (right peak too small)"
    else:
        hu_mean, hu_std = median_mad()
    if hu_std == 0:
        hu_std = 1.0
    hu_lo, hu_hi = hu_mean - hu_expansion_k * hu_std, hu_mean + hu_expansion_k * hu_std

    walk_ct = gaussian_filter2d(ct_slice, ct_smoothing_sigma_mm / res) if ct_smoothing_sigma_mm > 0 else ct_slice
    pts, n_clipped = _radial_hu_boundary(original_mask, walk_ct, res, hu_lo, hu_hi,
                                         margin_mm, gap_tolerance_mm, n_rays)
    if pts is not None:
        mask = fill_holes(polygon_mask(original_mask.shape, pts)).astype(np.uint8)
    else:
        mask, n_clipped = original_mask.copy(), 0
    inter = np.logical_and(mask, original_mask).sum()
    union = np.logical_or(mask, original_mask).sum()
    return mask, {
        "hu_method": method,
        "hu_mean": round(hu_mean, 2), "hu_std": round(hu_std, 2),
        "hu_lo": round(hu_lo, 2), "hu_hi": round(hu_hi, 2),
        "iou_vs_original": round(float(inter / union) if union else 0.0, 4),
        "pct_rays_margin_limited": round(100.0 * n_clipped / n_rays, 1) if n_rays else 0.0,
    }


# ============================================================================ spline contour
def polar_boundary_samples(mask, n_angles):
    comp = largest_component(mask)
    if comp is None:
        return None
    (cy, cx), _area = comp
    max_r = np.hypot(mask.shape[0], mask.shape[1])
    pts = []
    for theta in np.linspace(0, 2 * np.pi, n_angles, endpoint=False):
        dr, dc = np.sin(theta), np.cos(theta)
        for t in np.arange(1.0, max_r, 0.5):
            ri = int(np.clip(np.round(cy + t * dr), 0, mask.shape[0] - 1))
            ci = int(np.clip(np.round(cx + t * dc), 0, mask.shape[1] - 1))
            if mask[ri, ci] == 0:
                pts.append((cy + (t - 0.25) * dr, cx + (t - 0.25) * dc))
                break
        else:
            pts.append((cy + (max_r - 1) * dr, cx + (max_r - 1) * dc))
    return np.array(pts)


def fit_closed_spline(pts_px, n_eval):
    """Closed (periodic) interpolating cubic spline through (row, col) points, chord-length
    parameterised, evaluated at n_eval equally spaced parameter values: the same curve as
    scipy.interpolate.splprep(s=0, k=3, per=True) + splev in the original pipeline."""
    pts = np.asarray(pts_px, float)
    keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9]
    pts = pts[keep]
    if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts = pts[:-1]
    n = len(pts)
    if n < 4:
        raise ValueError("too few boundary points for a spline")
    closed = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    t = np.r_[0.0, np.cumsum(seg)] / seg.sum()          # knots t_0 .. t_n (t_n = 1)
    h = np.diff(t)                                      # h_0 .. h_{n-1}
    A = np.zeros((n, n))
    for i in range(n):
        hp, hi = h[i - 1], h[i]                         # h[-1] wraps to h[n-1]
        A[i, i - 1] += hp
        A[i, i] += 2 * (hp + hi)
        A[i, (i + 1) % n] += hi
    out = []
    u = np.linspace(0, 1, n_eval, endpoint=False)
    k = np.clip(np.searchsorted(t, u, side="right") - 1, 0, n - 1)
    for dim in range(2):
        y = closed[:, dim]
        rhs = np.array([6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1 if i else n - 1]) / h[i - 1])
                        for i in range(n)])
        M = np.linalg.solve(A, rhs)
        M = np.r_[M, M[0]]
        a, b = t[k + 1] - u, u - t[k]
        hk = h[k]
        out.append((M[k] * a ** 3 + M[k + 1] * b ** 3) / (6 * hk)
                   + (y[k] / hk - M[k] * hk / 6) * a + (y[k + 1] / hk - M[k + 1] * hk / 6) * b)
    return np.column_stack(out)


def spline_area_perimeter(spline_px, res):
    pts_mm = spline_px * res
    perimeter = float(np.linalg.norm(np.diff(pts_mm, axis=0, append=pts_mm[:1]), axis=1).sum())
    x, y = pts_mm[:, 1], pts_mm[:, 0]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return float(area), perimeter


def to_lps(spline_px, origin_2d, u, w, res):
    origin = np.asarray(origin_2d, float)
    return origin[None, :] + spline_px[:, 1:2] * res * u[None, :] + spline_px[:, 0:1] * res * w[None, :]


# ============================================================================ one case
def recompute_annulus(ct_image, seg_image, L, R, N, cfg=None):
    """Annulus contour for the plane through hinge points L, R, N (LPS). Returns a dict with
    contour_lps (control points), dense_lps, area/perimeter (spline), Feret diameters + endpoints,
    and correction details. Raises ValueError when no contour can be found."""
    cfg = dict(ANNULUS_PIPELINE, **(cfg or {}))
    res, half = float(cfg["res"]), float(cfg["half"])
    centroid, normal, u, w, c_shifted = compute_plane(L, N, R, float(cfg["shift_mm"]))
    size_2d = int(2 * half / res)
    origin_2d = (c_shifted - half * u - half * w).tolist()
    direction_2d = [u[0], w[0], normal[0], u[1], w[1], normal[1], u[2], w[2], normal[2]]

    sampled_seg = reslice(seg_image, size_2d, res, origin_2d, direction_2d, nearest=True, float_output=False)
    prior_mask, labels = build_annulus_mask(sampled_seg, res)
    if largest_component(prior_mask) is None:
        raise ValueError("No aortic root / LV label was found in the new annular plane. "
                         "Check the hinge points: the plane may miss the aortic root.")
    final_mask, corr = prior_mask, {}
    if cfg["correct_seg"]:
        ct_slice = reslice(ct_image, size_2d, res, origin_2d, direction_2d, nearest=False, float_output=True)
        corrected, corr = correct_mask_with_intensity(
            prior_mask, ct_slice, res, float(cfg["correction_margin_mm"]),
            float(cfg["correction_hu_expansion_k"]), float(cfg["correction_radial_gap_tolerance_mm"]),
            int(cfg["correction_n_rays"]), float(cfg["correction_ct_smoothing_sigma_mm"]))
        if largest_component(corrected) is not None:
            final_mask = corrected
        else:
            corr["note"] = "correction produced an empty mask; prior mask used"

    polar = polar_boundary_samples(final_mask, int(cfg["spline_polar_points"]))
    if polar is None or len(polar) < 4:
        raise ValueError("Could not trace the annulus boundary in the new plane.")
    spline_px = fit_closed_spline(polar, int(cfg["spline_eval_points"]))
    area, perimeter = spline_area_perimeter(spline_px, res)
    dense_lps = to_lps(spline_px, origin_2d, u, w, res)
    # Control points evenly spaced along the spline (no duplicated start/end point)
    idx = np.round(np.linspace(0, len(spline_px), int(cfg["slicer_contour_points"]), endpoint=False)).astype(int)
    contour_lps = dense_lps[idx]
    feret = compute_metrics(dense_lps)  # same max/min definition as the Measurements tab
    return {
        "contour_lps": contour_lps, "dense_lps": dense_lps,
        "area_mm2": area, "perimeter_mm": perimeter,
        "max_d_mm": feret["max_d"], "min_d_mm": feret["min_d"], "mean_d_mm": feret["mean_d"],
        "eccentricity": feret["ecc"], "max_pts": feret["max_pts"], "min_pts": feret["min_pts"],
        "labels": labels, "corrected": bool(cfg["correct_seg"]) and final_mask is not prior_mask,
        "correction": corr, "plane_centroid": centroid, "plane_normal": normal,
    }


def recompute_coronary_height(ostium_lps, L, R, N):
    """LCH / RCH line: ostium -> its perpendicular foot on the annular plane. Returns (foot, length)."""
    plane_point, normal = height_plane(L, R, N)
    return perpendicular_foot(np.asarray(ostium_lps, float), plane_point, normal)


def recompute_stj_height(stj_points_lps, L, R, N):
    """STJ height = smallest distance of the STJ points (dict cusp -> LPS) to the annular plane.
    Returns (cusp, stj_point, foot, height, {cusp: distance})."""
    centroid = (L + R + N) / 3.0
    _p, normal = height_plane(L, R, N)
    dists = {c: abs(float(np.dot(np.asarray(p, float) - centroid, normal))) for c, p in stj_points_lps.items()}
    cusp = min(dists, key=dists.get)
    point = np.asarray(stj_points_lps[cusp], float)
    foot, _ = perpendicular_foot(point, centroid, normal)
    return cusp, point, foot, dists[cusp], dists
