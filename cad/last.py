"""last.py — parametric shoe LAST lofted up from the traced sole outline.

    python3 cad/last.py  ->  build/last.stl

The last is the 3D foot form the upper is built on. We reuse cad/sole_outline.json as the
BOTTOM footprint (one source of truth with the sole), lift the toe (toe spring), and dome each
cross-section up to a dorsal-height profile that peaks at the instep. Lofting the sections gives
a watertight solid. Next step (separate file) draws seam/topline curves on this last and
flattens each panel to 2D cut patterns.
"""
import os
import json
import numpy as np
from build123d import (BuildSketch, BuildLine, Line, Spline, make_face, loft, Plane, Pos, Rot)
import trimesh

OUTLINE_JSON   = os.path.join(os.path.dirname(__file__), "sole_outline.json")
LAST_WIDTH_SCALE = 0.90   # pull the foot form in from the outsole outline (which flares w/ foxing)
TOE_SPRING     = 12.0     # how far the toe of the bottom lifts off the ground (mm)
TOE_SPRING_T   = 0.72     # fraction of length where the toe spring starts rising
N_STATIONS     = 18       # cross-sections lofted heel->toe
N_DOME         = 11       # points sampling each section's domed top

# dorsal height (mm, above the bottom) at fractions of length, heel(0) -> toe(1)
HEIGHT_PROFILE = [
    (0.00, 44.0),   # heel back (rounded)
    (0.08, 62.0),
    (0.16, 71.0),
    (0.26, 75.0),   # instep — tallest
    (0.36, 72.0),
    (0.46, 64.0),
    (0.56, 54.0),
    (0.66, 45.0),   # ball
    (0.76, 37.0),
    (0.86, 29.0),
    (0.94, 24.0),
    (1.00, 20.0),   # toe
]


def _outline():
    p = np.array(json.load(open(OUTLINE_JSON)), dtype=float)
    p[:, 0] *= LAST_WIDTH_SCALE
    return p


def _segments(p):
    return list(zip(p, np.roll(p, -1, axis=0)))


def width_at(segs, y):
    """min/max x where the closed outline crosses the line Y=y (scanline, robust to curl)."""
    xs = []
    for (x0, y0), (x1, y1) in segs:
        if y0 != y1 and (y0 - y) * (y1 - y) <= 0:
            t = (y - y0) / (y1 - y0)
            xs.append(x0 + t * (x1 - x0))
    return (min(xs), max(xs)) if len(xs) >= 2 else None


def height_at(t):
    ts = [a for a, _ in HEIGHT_PROFILE]
    hs = [b for _, b in HEIGHT_PROFILE]
    return float(np.interp(t, ts, hs))


def bottom_z(t):
    if t <= TOE_SPRING_T:
        return 0.0
    return TOE_SPRING * ((t - TOE_SPRING_T) / (1.0 - TOE_SPRING_T)) ** 2


def section(xL, xR, h, bz, y):
    """Closed face at station Y=y: flat bottom [xL..xR], elliptical dome of height h, lifted bz."""
    cx = (xL + xR) / 2.0
    rx = (xR - xL) / 2.0
    # top dome points (local: u across width, v = height above bottom)
    dome = []                                       # ordered xL -> xR to match the Spline below
    for x in np.linspace(xL, xR, N_DOME)[1:-1]:
        v = h * float(np.sqrt(max(0.0, 1.0 - ((x - cx) / rx) ** 2)))
        dome.append((x, v))
    with BuildSketch() as sk:                       # build in local XY (x=width, y=height)
        with BuildLine():
            Line((xR, 0.0), (xL, 0.0))              # flat bottom
            Spline((xL, 0.0), *dome, (xR, 0.0))     # domed top
        make_face()
    # stand it up into the X-Z plane at station y, bottom lifted to bz
    return (Pos(0.0, y, bz) * Rot(90, 0, 0) * sk.sketch).faces()[0]


def last_solid():
    p = _outline()
    segs = _segments(p)
    ymin, ymax = p[:, 1].min(), p[:, 1].max()
    L = ymax - ymin
    secs = []
    for t in np.linspace(0.03, 0.97, N_STATIONS):
        y = ymin + t * L
        w = width_at(segs, y)
        if w is None:
            continue
        xL, xR = w
        if xR - xL < 4.0:
            continue
        secs.append(section(xL, xR, height_at(t), bottom_z(t), y))
    return loft(secs)


def to_trimesh(part, tol=0.2):
    v, f = part.tessellate(tolerance=tol, angular_tolerance=0.3)
    m = trimesh.Trimesh(vertices=[(p.X, p.Y, p.Z) for p in v], faces=f)
    m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.fix_normals()
    return m


if __name__ == "__main__":
    os.makedirs("build", exist_ok=True)
    m = to_trimesh(last_solid())
    m.export("build/last.stl")
    bb = (m.bounds[1] - m.bounds[0]).round(1)
    print("last:", bb, "mm  bodies:", len(m.split(only_watertight=False)),
          "watertight:", m.is_watertight, "vol_cm3:", round(m.volume / 1000.0, 1))
