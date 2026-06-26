"""waffle_sole.py — parametric flexible cupsole (outsole + foxing wall) for custom Vans-style shoes.

    python3 cad/waffle_sole.py  ->  build/waffle_sole.stl

Body is built as pure cuts (outer block minus inner cup cavity) so it stays a single
watertight solid with no fragile additive fusion. The tread is cut into the bottom by
driving manifold3d directly (trimesh's manifold engine silently ignores long tool lists).

The footprint comes from OUTLINE_FILE — any .svg (drop in your own from Inkscape, etc.) or the
.json polyline written by cad/trace_outline.py (which traces ~/Pictures/vans.png). The outline
is auto-fitted: longest axis -> +Y, scaled so its length = OUTLINE_LENGTH, centered, heel at y=0.
"""
import os
import json
import math
import numpy as np
from build123d import (BuildSketch, BuildLine, Spline, make_face, extrude, offset, Pos, Rot,
                       Kind, Face, Plane, mirror, import_svg)
import trimesh
import manifold3d as m3d

# ---------------------------------------------------------------- footprint outline (SVG or JSON)
SIDE          = "right"   # "right" = outline as-is; "left" mirrors across the centerline
OUTLINE_FILE  = os.path.join(os.path.dirname(__file__), "sole_outline.svg")  # .svg or .json
OUTLINE_LENGTH = 297.0    # scale the outline so its long axis = this many mm (None = file units)

# ---------------------------------------------------------------- heights
SOLE_T   = 8.0      # slab thickness (cup floor) — lug top to insole top
WALL_H   = 1.0      # foxing/cup wall (top rim) height ABOVE floor — 1.0 = flat TEST COUPON;
                    #   use ~16 for the real cup the upper laps into
WALL_T   = 5.0      # foxing/cup wall thickness (radial)

# ---------------------------------------------------------------- tread
TREAD_STYLE = "diamond_ribs"  # "diamond_ribs" = ±45° raised ribs w/ diamond recesses | "ribs"
TREAD_DEPTH = 1.0     # *** raised ridge height (mm) *** — 1.0 for test prints, 3-4 for a real sole
RIB_W       = 2.5     # raised rib width
DIAMOND_PITCH = 9.0   # rib spacing / diamond-cell size for "diamond_ribs"
RIB_PITCH   = 8.0     # rib spacing for parallel "ribs"
RIB_ANGLE   = 90.0    # parallel-rib direction (deg from +X): 90=transverse, 0=lengthwise, 45=diag

# ---------------------------------------------------------------- meshing
LINEAR_TOL = 0.12   # STL chord tolerance (mm) — keep tread crisp
ANG_TOL    = 0.3


def _raw_outline_face():
    """Largest closed Face from OUTLINE_FILE (.svg path, or .json polyline -> periodic spline)."""
    if OUTLINE_FILE.lower().endswith(".svg"):
        faces = []
        for s in import_svg(OUTLINE_FILE):
            if isinstance(s, Face):
                faces.append(s)
            else:
                try:
                    faces.append(make_face(s))   # close a wire into a face
                except Exception:
                    pass
        if not faces:
            raise ValueError(f"no closed region found in {OUTLINE_FILE}")
        return max(faces, key=lambda f: f.area)
    pts = np.array(json.load(open(OUTLINE_FILE)), dtype=float)
    with BuildSketch() as sk:
        with BuildLine():
            Spline(*[tuple(xy) for xy in pts], periodic=True)
        make_face()
    return sk.sketch.faces()[0]


def outline_face():
    """Fitted footprint Face: long axis -> +Y, scaled to OUTLINE_LENGTH, centered, heel at y=0."""
    f = _raw_outline_face()
    bb = f.bounding_box()
    if (bb.max.X - bb.min.X) > (bb.max.Y - bb.min.Y):    # lay the long axis along Y
        f = Rot(0, 0, 90) * f
        bb = f.bounding_box()
    if OUTLINE_LENGTH:
        f = f.scale(OUTLINE_LENGTH / (bb.max.Y - bb.min.Y))
        bb = f.bounding_box()
    f = Pos(-(bb.min.X + bb.max.X) / 2.0, -bb.min.Y, 0) * f   # center width, heel at y=0
    if SIDE == "left":
        f = mirror(f, Plane.YZ)
    return f


def cup_solid():
    """Outer footprint block minus the inner cup cavity -> single solid cupsole shell."""
    outer = outline_face()
    inner = offset(outer, -WALL_T, kind=Kind.ARC)   # cup interior footprint

    block  = extrude(outer, SOLE_T + WALL_H)                       # z: 0 .. H
    cavity = Pos(0, 0, SOLE_T) * extrude(inner, WALL_H + 1.0)      # z: floor .. top+1
    return block - cavity


def to_trimesh(part):
    verts, faces = part.tessellate(tolerance=LINEAR_TOL, angular_tolerance=ANG_TOL)
    m = trimesh.Trimesh(vertices=[(v.X, v.Y, v.Z) for v in verts], faces=faces)
    m.merge_vertices(); m.update_faces(m.nondegenerate_faces()); m.fix_normals()
    return m


def _mesh_to_manifold(m):
    mesh = m3d.Mesh(vert_properties=m.vertices.astype(np.float32),
                    tri_verts=m.faces.astype(np.uint32))
    return m3d.Manifold(mesh)


def _manifold_to_trimesh(man):
    mesh = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                           faces=np.asarray(mesh.tri_verts))


def _rib_families():
    """List of (angle_deg, pitch) RAISED-rib families for the selected TREAD_STYLE."""
    if TREAD_STYLE == "diamond_ribs":
        return [(45.0, DIAMOND_PITCH), (-45.0, DIAMOND_PITCH)]   # crossing -> diamond cells
    if TREAD_STYLE == "ribs":
        return [(RIB_ANGLE, RIB_PITCH)]
    raise ValueError(f"unknown TREAD_STYLE {TREAD_STYLE!r}")


def tread_cutter():
    """Cutter that recesses the whole bottom by TREAD_DEPTH EXCEPT under the raised ribs.

    cutter = (full-field recess slab) - (union of rib bars). Subtracting it from the body
    sinks the floor by TREAD_DEPTH everywhere the ribs aren't, leaving the ribs standing
    TREAD_DEPTH proud. For "diamond_ribs" the ±45° bars cross into a net of diamond recesses.
    """
    bb = outline_face().bounding_box()
    cx, cy = (bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0
    W, L = (bb.max.X - bb.min.X) * 1.3, (bb.max.Y - bb.min.Y) * 1.3
    diag = math.hypot(L, W)

    # full-field recess: z in [-0.3 .. TREAD_DEPTH]
    recess = m3d.Manifold.cube((W, L, TREAD_DEPTH + 0.3), center=True) \
        .translate((cx, cy, (TREAD_DEPTH - 0.3) / 2.0))

    bars = []
    for ang, pitch in _rib_families():
        th = math.radians(ang)
        nx, ny = math.cos(th), math.sin(th)              # spacing normal
        n = int(diag / pitch) + 2
        for k in range(-n, n + 1):
            bars.append(
                m3d.Manifold.cube((RIB_W, diag * 1.2, TREAD_DEPTH + 2.0), center=True)
                .rotate((0, 0, ang))
                .translate((cx + k * pitch * nx, cy + k * pitch * ny, TREAD_DEPTH / 2.0)))
    ribs = m3d.Manifold.batch_boolean(bars, m3d.OpType.Add)
    return recess - ribs                                  # recess everywhere except the ribs


def part():
    body = _mesh_to_manifold(to_trimesh(cup_solid()))
    return _manifold_to_trimesh(body - tread_cutter())


if __name__ == "__main__":
    os.makedirs("build", exist_ok=True)
    m = part()
    m.export("build/waffle_sole.stl")
    bb = (m.bounds[1] - m.bounds[0]).round(1)
    print("waffle_sole:", bb, "mm  bodies:", len(m.split(only_watertight=False)),
          "watertight:", m.is_watertight, "vol_cm3:", round(m.volume / 1000.0, 1))
