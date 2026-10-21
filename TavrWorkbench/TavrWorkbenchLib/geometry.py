"""Pure-numpy contour geometry (no Slicer / scipy needed)."""
import json

import numpy as np


def unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def fit_plane(pts):
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    return c, vt[0], vt[1], vt[2]  # centroid, u, v, normal


def convex_hull_idx(xy):
    order = np.lexsort((xy[:, 1], xy[:, 0]))

    def cross(o, a, b):
        return (xy[a][0] - xy[o][0]) * (xy[b][1] - xy[o][1]) - (xy[a][1] - xy[o][1]) * (xy[b][0] - xy[o][0])

    def half(idxs):
        h = []
        for i in idxs:
            while len(h) >= 2 and cross(h[-2], h[-1], i) <= 0:
                h.pop()
            h.append(i)
        return h

    return half(order)[:-1] + half(order[::-1])[:-1]


def feret_pair_points(xy):
    """Return ((max_p1, max_p2), (min_p1, min_p2)); all four points lie ON the contour."""
    H = xy[convex_hull_idx(xy)]
    d = np.linalg.norm(H[:, None, :] - H[None, :, :], axis=2)
    i, j = np.unravel_index(np.argmax(d), d.shape)
    max_pts = (H[i], H[j])

    # minimum caliper width over hull edges
    best_w, best_P, best_perp = np.inf, None, None
    n = len(H)
    for k in range(n):
        e = H[(k + 1) % n] - H[k]
        L = np.linalg.norm(e)
        if L < 1e-9:
            continue
        perp = np.array([-e[1], e[0]]) / L
        dist = (H - H[k]) @ perp
        jj = int(np.argmax(np.abs(dist)))
        if abs(dist[jj]) < best_w:
            best_w, best_P, best_perp = abs(dist[jj]), H[jj], perp

    # chord through the far vertex, along the min-width direction, ending on the contour
    P, perp = best_P, best_perp
    nrm = np.array([perp[1], -perp[0]])
    s = (xy - P) @ nrm
    s2 = np.roll(s, -1)
    B = np.roll(xy, -1, axis=0)
    cand = []
    for k in np.where(s * s2 <= 0)[0]:
        if abs(s[k] - s2[k]) < 1e-12:
            continue
        cand.append(xy[k] + (B[k] - xy[k]) * (s[k] / (s[k] - s2[k])))
    q = max(cand, key=lambda z: abs((z - P) @ perp)) if cand else P - perp * best_w
    return max_pts, (P, q)


def _open_ring(pts):
    pts = np.asarray(pts, dtype=float)
    if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-6:
        pts = pts[:-1]
    return pts


def compute_metrics(pts3d):
    """Area, perimeter, Feret max/min diameter (+ endpoints), eccentricity and plane of a closed contour.
    Returns None for degenerate input (< 3 points)."""
    pts = _open_ring(pts3d)
    if len(pts) < 3:
        return None
    c, u, v, n = fit_plane(pts)
    xy = np.column_stack([(pts - c) @ u, (pts - c) @ v])
    x, y = xy[:, 0], xy[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    perim = float(np.linalg.norm(np.roll(xy, -1, axis=0) - xy, axis=1).sum())
    (a1, a2), (b1, b2) = feret_pair_points(xy)

    def lift(p):
        return c + p[0] * u + p[1] * v

    max_d, min_d = float(np.linalg.norm(a1 - a2)), float(np.linalg.norm(b1 - b2))
    ecc = float(np.sqrt(max(0.0, 1 - (min_d / max_d) ** 2))) if max_d > 0 else 0.0
    return {
        "area": float(area), "perimeter": perim, "max_d": max_d, "min_d": min_d,
        "mean_d": (max_d + min_d) / 2, "ecc": ecc,
        "max_pts": (lift(a1), lift(a2)), "min_pts": (lift(b1), lift(b2)),
        "plane": (c, u, v, n),
    }


def resample_closed(pts3d, n):
    """n points equally spaced (by arc length) along a closed polyline."""
    pts = _open_ring(pts3d)
    closed = np.vstack([pts, pts[:1]])
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))])
    t = np.linspace(0, cum[-1], int(n), endpoint=False)
    return np.column_stack([np.interp(t, cum, closed[:, k]) for k in range(3)])


def read_mrk_points(path):
    """Control points of a .mrk.json as an (N,3) array in Slicer world (RAS) coordinates."""
    with open(path) as f:
        mk = json.load(f)["markups"][0]
    pts = np.array([cp["position"] for cp in mk["controlPoints"]], dtype=float)
    if mk.get("coordinateSystem", "LPS").upper() == "LPS":
        pts = pts * np.array([-1.0, -1.0, 1.0])
    return pts
