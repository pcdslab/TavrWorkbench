#!/usr/bin/env python3
"""
Parametric TAVR valve generator (self-expanding, supra-annular style) -> STL, millimetres.
Needs only Python 3 + numpy:   pip install numpy

Command line:
    python tavr_valve_v2.py --annulus_min 22 --annulus_max 26 --coronary_h 13 --coronary_h2 14 --stj_h 22 --stj_d 28

From Python (also works in the 3D Slicer Python console):
    import tavr_valve_v2 as tv
    tv.make_valve(annulus_min=22, annulus_max=26, coronary_h=13, stj_h=22, stj_d=28, out="valve_out")

Coordinates: z = valve axis. z = 0 is the annulus plane, +z toward the aorta, -z toward the LV outflow tract.
All heights are measured from the annulus plane. All numbers are mm.

Writes: valve_full.stl, valve_frame.stl, valve_skirt.stl, valve_leaflets.stl, valve_params.json

TavrWorkbench (Valve tab) calls make_valve(write=False, verbose=False, ...) and uses the returned meshes:
    rep["meshes"] = {"frame": (V, F), "skirt": (V, F) or None, "leaflets": (V, F) or None}   (valve coordinates)
    rep["report_lines"] = the printed report, rep["params"] = all parameters used.
"""
import argparse, json, math, os, struct
import numpy as np

# ---------------------------------------------------------------- parameters
DEFAULTS = dict(
    # anatomy (what you measure on the CT)
    annulus_min=22.0,    # annulus short-axis diameter
    annulus_max=26.0,    # annulus long-axis diameter
    coronary_h=13.0,     # lowest coronary ostium height above the annulus plane
    coronary_h2=None,    # the other coronary ostium height (optional)
    stj_h=22.0,          # sinotubular junction height above the annulus plane
    stj_d=28.0,          # STJ diameter
    asc_aorta_d=34.0,    # ascending aorta diameter (caps the outflow flare)
    # valve sizing / overall shape
    oversize=8.0,        # oversizing at the annulus plane, in percent
    shape=0.3,           # 0 = round frame ... 1 = full annulus ellipse (fades to round toward the STJ)
    frame_height=45.0,   # total frame height
    inflow_depth=5.0,    # how far the frame bottom sits below the annulus plane
    waist=0.80,          # waist diameter / inflow diameter
    waist_pos=0.40,      # waist position as a fraction of frame height (from the bottom)
    flare=1.10,          # outflow diameter / inflow diameter (capped by asc_aorta_d)
    # frame cell pattern
    cells=14,            # cells around the circumference
    rows=7,              # node rows along the height
    row_growth=1.12,     # each row is this much taller than the one below (cells grow toward the outflow)
    curve=0.6,           # 0 = straight diamond struts, 1 = strongly curved lens-shaped cells
    strut_w=0.45,        # strut width (along the surface)
    strut_t=0.35,        # strut thickness (radial)
    crown_stagger=3.0,   # every other outflow crown is this much taller
    tabs=3,              # number of eyelet tabs on the outflow crowns (0 = none)
    # skirt (sealing fabric)
    skirt_h=12.0,        # highest point of the skirt above the annulus (auto-lowered under the coronaries)
    skirt_scallop=4.0,   # depth of the scalloped top edge
    skirt_thk=0.15,
    coronary_margin=2.0, # minimum gap between the skirt top and the lowest coronary ostium
    # leaflets
    commissure_h=20.0,   # leaflet commissure height above the annulus plane
    leaflet_base=2.0,    # leaflet belly (lowest attachment) above the annulus plane
    leaflet_thk=0.3,
    sag=4.0,             # how far the free edge sags between commissures
    # switches
    no_leaflets=False, no_skirt=False,
    no_conform=False,    # do not pinch the frame to the STJ diameter
    out=".",
)

HELP = dict(
    annulus_min="annulus short-axis diameter", annulus_max="annulus long-axis diameter",
    coronary_h="lowest coronary ostium height above annulus", coronary_h2="other coronary ostium height (optional)",
    stj_h="STJ height above annulus", stj_d="STJ diameter", asc_aorta_d="ascending aorta diameter (caps outflow flare)",
    oversize="oversizing at the annulus plane, percent", shape="0 round ... 1 full annulus ellipse",
    frame_height="total frame height", inflow_depth="frame bottom depth below the annulus plane",
    waist="waist diameter / inflow diameter", waist_pos="waist position, fraction of height from the bottom",
    flare="outflow diameter / inflow diameter", cells="cells around the circumference", rows="node rows along the height",
    row_growth="row height growth factor", curve="0 straight struts ... 1 curved lens cells",
    strut_w="strut width", strut_t="strut thickness", crown_stagger="extra height of every other outflow crown",
    tabs="number of eyelet tabs", skirt_h="highest point of skirt above annulus", skirt_scallop="skirt scallop depth",
    skirt_thk="skirt thickness", coronary_margin="min gap skirt top to lowest coronary ostium",
    commissure_h="leaflet commissure height above annulus", leaflet_base="leaflet belly height above annulus",
    leaflet_thk="leaflet thickness", sag="free-edge sag", no_leaflets="leave out the leaflets",
    no_skirt="leave out the skirt", no_conform="do not pinch the frame to the STJ diameter", out="output folder",
)


# ---------------------------------------------------------------- helpers
def sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def ellipse_perimeter(a, b):
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def merge(parts):
    Vs, Fs, off = [], [], 0
    for V, F in parts:
        Vs.append(V)
        Fs.append(F + off)
        off += len(V)
    return np.vstack(Vs), np.vstack(Fs)


def write_stl(path, V, F):
    tri = V[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    rec = np.zeros(len(F), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as f:
        f.write(b"TAVR parametric valve".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(F)))
        f.write(rec.tobytes())


def ribbon(pts, nrm, w, t, sides=8, closed=False):
    """Strut with an elliptical cross-section: width w across the surface, thickness t along the surface normal."""
    pts = np.asarray(pts, float)
    N = len(pts)
    tan = (np.roll(pts, -1, 0) - np.roll(pts, 1, 0)) if closed else np.gradient(pts, axis=0)
    tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-12
    bi = np.cross(tan, nrm)
    bi /= np.linalg.norm(bi, axis=1, keepdims=True) + 1e-12
    n2 = np.cross(bi, tan)
    ang = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = (pts[:, None, :] + 0.5 * w * np.cos(ang)[None, :, None] * bi[:, None, :]
            + 0.5 * t * np.sin(ang)[None, :, None] * n2[:, None, :])
    V = ring.reshape(-1, 3)
    K = N if closed else N - 1
    k = np.arange(K)[:, None]
    s = np.arange(sides)[None, :]
    k1 = (k + 1) % N
    a = (k * sides + s).ravel()
    b = (k * sides + (s + 1) % sides).ravel()
    c = (k1 * sides + (s + 1) % sides).ravel()
    d = (k1 * sides + s).ravel()
    F = [np.c_[a, c, b], np.c_[a, d, c]]
    if not closed:
        c0, c1 = len(V), len(V) + 1
        V = np.vstack([V, pts[0], pts[-1]])
        s0 = np.arange(sides)
        s1 = (s0 + 1) % sides
        F.append(np.c_[np.full(sides, c0), s0, s1])
        base = (N - 1) * sides
        F.append(np.c_[np.full(sides, c1), base + s1, base + s0])
    return V, np.vstack(F)


def grid_solid(T, B, periodic_u=False):
    """Closed thin solid between two surface grids T and B (nu x nv x 3). Outward-facing triangles."""
    nu, nv = T.shape[:2]
    V = np.vstack([T.reshape(-1, 3), B.reshape(-1, 3)])
    off = nu * nv
    idx = np.arange(nu * nv).reshape(nu, nv)
    i0 = idx if periodic_u else idx[:-1]
    i1 = np.roll(idx, -1, axis=0) if periodic_u else idx[1:]
    a, b = i0[:, :-1].ravel(), i1[:, :-1].ravel()
    c, d = i1[:, 1:].ravel(), i0[:, 1:].ravel()
    eu, ev = np.gradient(T, axis=0), np.gradient(T, axis=1)
    sgn = np.sign(np.sum((B - T) * np.cross(eu, ev))) or 1.0
    F = [np.c_[a, c, b], np.c_[a, d, c],                                   # T side
         np.c_[a + off, b + off, c + off], np.c_[a + off, c + off, d + off]]  # B side

    def wall(p0, p1):
        return [np.c_[p0, p1, p1 + off], np.c_[p0, p1 + off, p0 + off]]
    F += wall(i0[:, 0], i1[:, 0])            # v = 0 edge, +u
    F += wall(i1[:, -1], i0[:, -1])          # v = 1 edge, -u
    if not periodic_u:
        F += wall(idx[-1, :-1], idx[-1, 1:])  # u = 1 edge, +v
        F += wall(idx[0, 1:], idx[0, :-1])    # u = 0 edge, -v
    F = np.vstack(F)
    if sgn < 0:
        F = F[:, ::-1]
    return V, F


# ---------------------------------------------------------------- main builder
def make_valve(write=True, verbose=True, **kw):
    """Build the valve. write=False: no files (meshes are returned in rep["meshes"]); verbose=False: no printing."""
    unknown = set(kw) - set(DEFAULTS)
    if unknown:
        raise TypeError("unknown parameter(s): " + ", ".join(sorted(unknown)))
    p = dict(DEFAULTS)
    p.update(kw)
    notes = []

    # ---- annulus -> frame sizing
    A, B = sorted([p["annulus_max"] / 2, p["annulus_min"] / 2], reverse=True)
    Dp = ellipse_perimeter(A, B) / math.pi            # perimeter-derived annulus diameter
    rc = Dp / 2
    Af, Bf = rc + p["shape"] * (A - rc), rc + p["shape"] * (B - rc)
    m_target = 0.5 * (Af + Bf) * (1 + p["oversize"] / 100)   # mean radius wanted AT the annulus plane
    ecc0 = (Af - Bf) / (Af + Bf)

    H = p["frame_height"]
    z_bot = -p["inflow_depth"]
    z_top = z_bot + H
    if z_top < 12:
        raise ValueError("frame_height must be at least 12 mm taller than inflow_depth")
    waist = p["waist"]
    tw = float(np.clip(p["waist_pos"], 0.15, 0.70))
    cf = 0.04                                          # small extra outward flare of the crowns
    stj_h = max(p["stj_h"], 1.0)

    def g_raw(z, fl):
        t = np.clip((np.asarray(z, float) - z_bot) / H, 0, 1)
        lo = waist + (1 - waist) * sstep((tw - t) / tw)
        up = waist + (fl - waist) * sstep((t - tw) / (0.85 - tw))
        return np.where(t <= tw, lo, up) * (1 + cf * sstep((t - 0.85) / 0.15))

    cap_r = p["asc_aorta_d"] / 2 if p["asc_aorta_d"] else 1e9
    flare_eff = p["flare"]
    for _ in range(4):
        m0 = m_target / float(g_raw(0.0, flare_eff))
        flare_eff = min(p["flare"], cap_r / (m0 * (1 + cf)))
    if flare_eff < p["flare"] - 1e-9:
        notes.append(f"Outflow flare limited to {flare_eff:.2f} so the frame fits the ascending aorta ({p['asc_aorta_d']} mm).")

    s_pinch = 1.0
    if p["stj_d"] and not p["no_conform"]:
        s_pinch = min(1.0, (p["stj_d"] / 2) / (m0 * float(g_raw(stj_h, flare_eff))))
        if s_pinch < 1:
            notes.append(f"Frame pinched to the STJ diameter ({p['stj_d']} mm) at z={stj_h:.0f}.")

    def g(z):
        gz = g_raw(z, flare_eff)
        if s_pinch < 1:
            gz = gz * (1 - (1 - s_pinch) * np.exp(-0.5 * ((np.asarray(z, float) - stj_h) / 5.0) ** 2))
        return gz

    def axes(z):
        z = np.asarray(z, float)
        m = m0 * g(z)
        e = ecc0 * (1 - sstep(z / stj_h))              # annulus ellipse fades to a circle at the STJ
        return m * (1 + e), m * (1 - e)

    def pos(th, z):
        th, z = np.broadcast_arrays(np.asarray(th, float), np.asarray(z, float))
        a, b = axes(z)
        return np.stack([a * np.cos(th), b * np.sin(th), z], -1)

    def surf_normal(th, z):
        d1 = pos(th + 1e-3, z) - pos(th - 1e-3, z)
        d2 = pos(th, z + 1e-2) - pos(th, z - 1e-2)
        n = np.cross(d1, d2)
        n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12
        flip = np.sum(n * pos(th, z) * np.array([1, 1, 0]), axis=-1) < 0
        n[flip] = -n[flip]
        return n

    # ---- frame: rows of nodes, curved diamond struts -> lens-shaped cells
    n, R = int(p["cells"]), int(p["rows"])
    dth = 2 * np.pi / n
    pitch = p["row_growth"] ** np.arange(R)
    zr = z_bot + H * np.concatenate([[0], np.cumsum(pitch)]) / pitch.sum()
    stag = p["crown_stagger"]
    t01 = np.linspace(0, 1, 19)
    fcurve = (1 - p["curve"]) * t01 + p["curve"] * sstep(t01)
    sw, st = p["strut_w"], p["strut_t"]
    frame_parts = []
    for j in range(R):
        off = 0.5 * (j % 2)
        for i in range(n):
            th0 = (i + off) * dth
            for sg in (+1, -1):
                th1 = th0 + sg * dth / 2
                i1 = int(round(th1 / dth - 0.5 * ((j + 1) % 2))) % n
                z1 = zr[j + 1] + (stag if (j + 1 == R and i1 % 2 == 0) else 0.0)
                th = th0 + sg * (dth / 2) * fcurve
                z = zr[j] + (z1 - zr[j]) * t01
                frame_parts.append(ribbon(pos(th, z), surf_normal(th, z), sw, st))

    n_tabs = int(p["tabs"])
    if n_tabs > 0:
        th_nodes = (np.arange(0, n, 2) + 0.5 * (R % 2)) * dth
        for k in range(n_tabs):
            target = (np.pi / 6 + k * 2 * np.pi / n_tabs) % (2 * np.pi)
            dd = np.abs(((th_nodes - target + np.pi) % (2 * np.pi)) - np.pi)
            th_t = float(th_nodes[np.argmin(dd)])
            zt = zr[R] + stag
            eth = pos(th_t + 1e-3, zt) - pos(th_t - 1e-3, zt)
            eth /= np.linalg.norm(eth)
            ez = pos(th_t, zt + 1e-2) - pos(th_t, zt - 1e-2)
            ez /= np.linalg.norm(ez)
            psi = np.linspace(0, 2 * np.pi, 28, endpoint=False)
            rx, rz = 0.8, 1.6
            ring = (pos(th_t, zt)[None, :] + rx * np.cos(psi)[:, None] * eth[None, :]
                    + (rz + rz * np.sin(psi))[:, None] * ez[None, :])
            nr = np.tile(surf_normal(th_t, zt), (len(psi), 1))
            frame_parts.append(ribbon(ring, nr, 0.35, st, closed=True))
    Vf, Ff = merge(frame_parts)

    # ---- skirt (inside the frame), scalloped edges, lowered under the coronary ostia
    cors = [c for c in (p["coronary_h"], p["coronary_h2"]) if c is not None]
    z_cor_low = min(cors) if cors else None
    off_s = st / 2 + 0.03
    skirt = None
    z_s = None
    if not p["no_skirt"]:
        z_s = p["skirt_h"]
        if z_cor_low is not None and z_s > z_cor_low - p["coronary_margin"]:
            z_s = z_cor_low - p["coronary_margin"]
            notes.append(f"Skirt top lowered from {p['skirt_h']:.1f} to {z_s:.1f} to stay {p['coronary_margin']} mm below the lowest coronary ostium.")
        sc = min(p["skirt_scallop"], max(0.5, (z_s - z_bot) - 3.0))
        sb = 1.5
        th = np.linspace(0, 2 * np.pi, 360, endpoint=False)
        ztop = z_s - sc * np.abs(np.sin(n * th / 2)) ** 0.75
        zbot = z_bot + sb * 0.5 * (1 + np.cos(n * th))
        vv = np.linspace(0, 1, 14)[None, :]
        Z = zbot[:, None] + (ztop - zbot)[:, None] * vv
        TH = th[:, None] * np.ones((1, Z.shape[1]))
        P0, N0 = pos(TH, Z), surf_normal(TH, Z)
        skirt = grid_solid(P0 - N0 * off_s, P0 - N0 * (off_s + p["skirt_thk"]), periodic_u=True)

    # ---- leaflets (three, supra-annular)
    leaflets = None
    z_comm = min(p["commissure_h"], z_top - 6.0)
    if z_comm < p["commissure_h"]:
        notes.append(f"Commissure height limited to {z_comm:.1f} (frame top is {z_top:.1f}).")
    if not p["no_leaflets"]:
        off_l = off_s + p["skirt_thk"] + 0.05
        zlb = p["leaflet_base"]

        def one_leaflet(phi0, nu=30, nv=18):
            u = np.linspace(0, 1, nu)[:, None]
            v = np.linspace(0, 1, nv)[None, :]
            su = np.sin(np.pi * u)
            z_att = zlb + (z_comm - 1.0 - zlb) * (1 - su ** 0.9)
            z_free = z_comm - p["sag"] * su ** 0.7
            z = z_att + v * (z_free - z_att)
            phi = phi0 + u * (2 * np.pi / 3) + 0 * v
            P0, N0 = pos(phi, z), surf_normal(phi, z)
            P = P0 - N0 * off_l
            k = 1 - 0.92 * su ** 0.7 * v ** 1.5
            P[..., 0] *= k
            P[..., 1] *= k
            nl = np.cross(np.gradient(P, axis=0), np.gradient(P, axis=1))
            nl /= np.linalg.norm(nl, axis=-1, keepdims=True) + 1e-12
            return grid_solid(P, P + nl * p["leaflet_thk"])
        leaflets = merge([one_leaflet(k * 2 * np.pi / 3 + np.pi / 6) for k in range(3)])

    # ---- write
    out = p["out"]
    parts = [(Vf, Ff)] + [m for m in (skirt, leaflets) if m is not None]
    Vall, Fall = merge(parts)
    if write:
        os.makedirs(out, exist_ok=True)
        write_stl(os.path.join(out, "valve_frame.stl"), Vf, Ff)
        if skirt is not None:
            write_stl(os.path.join(out, "valve_skirt.stl"), *skirt)
        if leaflets is not None:
            write_stl(os.path.join(out, "valve_leaflets.stl"), *leaflets)
        write_stl(os.path.join(out, "valve_full.stl"), Vall, Fall)
        with open(os.path.join(out, "valve_params.json"), "w") as f:
            json.dump(p, f, indent=2)

    # ---- report
    def D(z):
        return ellipse_perimeter(*[float(v) for v in axes(z)]) / math.pi

    def cell_at(z):
        j = int(np.clip(np.searchsorted(zr, z) - 1, 0, R - 1))
        h1 = zr[min(j + 2, R)] - zr[j]
        h0 = zr[j + 1] - zr[max(j - 1, 0)]
        return 0.5 * (h0 + h1), dth * float(np.mean(axes(z)))

    z_w = z_bot + tw * H
    rep = {}
    L = ["---- TAVR valve report (mm) ----",
         f"Annulus {p['annulus_min']} x {p['annulus_max']}  ->  perimeter-derived diameter {Dp:.1f}",
         f"Frame at annulus plane: {D(0):.1f}  (oversizing {100 * (D(0) / Dp - 1):.1f}%)",
         f"Frame inflow (bottom) {D(z_bot):.1f} | waist {D(z_w):.1f} at z={z_w:+.1f} | outflow (top) {D(z_top):.1f}",
         f"Frame spans z = {z_bot:.1f} to {z_top:+.1f}",
         f"At STJ height (z={stj_h:.0f}): frame {D(stj_h):.1f} vs STJ {p['stj_d']}"]
    for lab, zc in (("lowest/first", p["coronary_h"]), ("other", p["coronary_h2"])):
        if zc is None:
            continue
        ch, cw = cell_at(zc)
        line = f"Coronary ostium ({lab}) at z={zc}: frame cell there is about {ch:.0f} x {cw:.0f}"
        if z_s is not None:
            line += f"; skirt top {z_s:.1f} (gap {zc - z_s:.1f})"
        L.append(line)
    L.append(f"Leaflet commissures at z={z_comm:.1f}, belly at z={p['leaflet_base']}")
    L += ["NOTE: " + s for s in notes]
    L.append(f"Triangles: {len(Fall):,}" + (f"   Files in: {os.path.abspath(out)}" if write else ""))
    if verbose:
        print("\n".join(L))
    rep.update(annulus_dp=Dp, frame_at_annulus=D(0), frame_bottom=D(z_bot), waist=D(z_w), outflow=D(z_top),
               at_stj=D(stj_h), skirt_top=z_s, commissure=z_comm, notes=notes, out=os.path.abspath(out),
               z_bottom=z_bot, z_top=z_top, report_lines=L, params=p,
               meshes={"frame": (Vf, Ff), "skirt": skirt, "leaflets": leaflets})
    return rep


def main():
    ap = argparse.ArgumentParser(description="Parametric TAVR valve -> STL (mm). All heights from the annulus plane.")
    for k, v in DEFAULTS.items():
        if isinstance(v, bool):
            ap.add_argument("--" + k, action="store_true", help=HELP.get(k, ""))
        elif k == "out":
            ap.add_argument("--out", default=".", help=HELP[k])
        elif isinstance(v, int):
            ap.add_argument("--" + k, type=int, default=v, help=HELP.get(k, "") + f" (default {v})")
        else:
            ap.add_argument("--" + k, type=float, default=v, help=HELP.get(k, "") + f" (default {v})")
    make_valve(**vars(ap.parse_args()))


if __name__ == "__main__":
    main()