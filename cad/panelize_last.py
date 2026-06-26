"""panelize_last.py — partition the last surface into wrap panels (the seam-line regions).

    python3 cad/panelize_last.py  ->  build/last_panels.png  (+ cad/last_regions.npz)

This is the last-first answer to "how does a shoe wrap together in pieces": split the 3D last
surface into the OpenRun-style regions — SOLE/footbed (downward faces), and MEDIAL vs LATERAL
wrap (the rest, divided at the dorsal+plantar midline) — and color them. The region boundaries
are the seam lines; each region later flattens to a 2D cut pattern (task #5).
"""
import os
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(__file__)
LAST = os.path.join(HERE, "..", "assets", "openrun", "OpenRun_42_LAST.stl")

SOLE_NZ      = -0.35   # face normal-z below this (pointing down) -> plantar/sole
SOLE_Z_FRAC  = 0.18    # ...and within this fraction of height above the bottom
COLLAR_FRAC  = 0.78    # trim faces above this fraction of height (the ankle cone / opening)

COLORS = {"sole": "#4daf4a", "medial": "#e41a1c", "lateral": "#377eb8", "collar": "#dddddd"}


def regions(m):
    z0, z1 = m.bounds[0, 2], m.bounds[1, 2]
    h = z1 - z0
    c = m.triangles_center
    n = m.face_normals
    cx_mid = (m.bounds[0, 0] + m.bounds[1, 0]) / 2.0
    lab = np.empty(len(m.faces), dtype=object)
    for i in range(len(m.faces)):
        if c[i, 2] > z0 + COLLAR_FRAC * h:
            lab[i] = "collar"                                   # above topline: not covered
        elif n[i, 2] < SOLE_NZ and c[i, 2] < z0 + SOLE_Z_FRAC * h:
            lab[i] = "sole"                                     # plantar / footbed
        else:
            lab[i] = "medial" if c[i, 0] < cx_mid else "lateral"
    return lab


def view(ax, m, cols, elev, azim, light, title):
    tris = m.vertices[m.faces]
    L = np.array(light) / np.linalg.norm(light)
    sh = np.clip(m.face_normals @ L, 0.25, 1.0)
    fc = np.array([matplotlib.colors.to_rgb(c) for c in cols]) * sh[:, None]
    pc = Poly3DCollection(tris, linewidths=0); pc.set_facecolor(np.clip(fc, 0, 1))
    ax.add_collection3d(pc)
    b = m.bounds
    for i, a in enumerate("xyz"):
        getattr(ax, f"set_{a}lim")(b[0, i], b[1, i])
    ax.set_box_aspect(b[1] - b[0]); ax.view_init(elev=elev, azim=azim)
    ax.set_title(title, fontsize=10); ax.axis("off")


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "..", "build"), exist_ok=True)
    m = trimesh.load(LAST)
    lab = regions(m)
    cols = [COLORS[l] for l in lab]
    for r in ("sole", "medial", "lateral", "collar"):
        print(f"  {r:8s}: {int((lab==r).sum()):6d} faces")
    np.savez(os.path.join(HERE, "last_regions.npz"), labels=lab.astype(str))

    fig = plt.figure(figsize=(15, 7))
    view(fig.add_subplot(141, projection="3d"), m, cols,  10,  60, (0.4, 0.3, 0.8), "lateral side")
    view(fig.add_subplot(142, projection="3d"), m, cols,  10, -120, (-0.4, 0.3, 0.8), "medial side")
    view(fig.add_subplot(143, projection="3d"), m, cols,  85, -90, (0.1, 0.1, 1), "top (seam = midline)")
    view(fig.add_subplot(144, projection="3d"), m, cols, -80, -90, (0.1, 0.1, -1), "bottom (sole)")
    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "..", "build", "last_panels.png"), dpi=95, bbox_inches="tight")
    print("wrote build/last_panels.png + cad/last_regions.npz")
