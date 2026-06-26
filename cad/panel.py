"""panel.py — parametric upper PANEL from an extracted OpenRun SVG outline.

    python3 cad/panel.py  ->  build/panel.stl

Loads a true-scale panel outline (cad/panels/panel_N.svg), extrudes it to PANEL_THICK, and
punches a parametric row of STITCH HOLES around the perimeter (inset from the edge, evenly
spaced by arc length) — the whipstitch holes the Kevlar thread passes through. Holes are cut
with manifold3d (fast/robust for many tools). Watertight single body.
"""
import os
import numpy as np
from build123d import import_svg, Face, make_face, extrude, offset, Kind
import trimesh
import manifold3d as m3d

HERE = os.path.dirname(__file__)
PANEL_FILE = os.path.join(HERE, "panels", "panel_2.svg")   # which panel to build

PANEL_THICK  = 4.0     # panel material thickness (mm) — EVA/felt ~3-5, canvas ~1.5-2
STITCH_INSET = 5.0     # stitch-hole row distance in from the cut edge (mm)
STITCH_PITCH = 7.0     # hole center-to-center along the perimeter (mm)
HOLE_D       = 2.2     # stitch hole diameter (mm) — sized to the awl/needle + Kevlar thread


def panel_face():
    faces = [s for s in import_svg(PANEL_FILE) if isinstance(s, Face)]
    if not faces:                       # fall back: close the outline wire into a face
        faces = [make_face(s) for s in import_svg(PANEL_FILE)]
    return max(faces, key=lambda f: f.area)


def stitch_xy(face):
    """Evenly arc-length-spaced points along the outline offset inward by STITCH_INSET."""
    inner = offset(face, -STITCH_INSET, kind=Kind.ARC)
    wire = max(inner.wires(), key=lambda w: w.length)
    M = 3000
    pts = np.array([( (wire @ (i / M)).X, (wire @ (i / M)).Y ) for i in range(M + 1)])
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    n = max(8, int(round(d[-1] / STITCH_PITCH)))
    s = np.linspace(0, d[-1], n, endpoint=False)
    return np.c_[np.interp(s, d, pts[:, 0]), np.interp(s, d, pts[:, 1])], n


def _to_manifold(m):
    return m3d.Manifold(m3d.Mesh(vert_properties=m.vertices.astype(np.float32),
                                 tri_verts=m.faces.astype(np.uint32)))


def _to_trimesh(man):
    msh = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(msh.vert_properties)[:, :3],
                           faces=np.asarray(msh.tri_verts))


def part():
    face = panel_face()
    solid = extrude(face, PANEL_THICK)
    v, f = solid.tessellate(tolerance=0.15, angular_tolerance=0.3)
    body = trimesh.Trimesh(vertices=[(p.X, p.Y, p.Z) for p in v], faces=f)
    body.merge_vertices(); body.update_faces(body.nondegenerate_faces()); body.fix_normals()

    xy, n = stitch_xy(face)
    holes = [m3d.Manifold.cylinder(PANEL_THICK + 2.0, HOLE_D / 2.0, circular_segments=24)
             .translate((float(x), float(y), -1.0)) for x, y in xy]
    drilled = _to_manifold(body) - m3d.Manifold.batch_boolean(holes, m3d.OpType.Add)
    return _to_trimesh(drilled), n


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "..", "build"), exist_ok=True)
    m, n = part()
    m.export(os.path.join(HERE, "..", "build", "panel.stl"))
    bb = (m.bounds[1] - m.bounds[0]).round(1)
    print(f"panel({os.path.basename(PANEL_FILE)}):", bb, "mm  stitch holes:", n,
          "bodies:", len(m.split(only_watertight=False)), "watertight:", m.is_watertight)
