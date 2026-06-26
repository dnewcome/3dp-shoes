"""flatten.py — flatten last surface regions into 2D cut patterns with a distortion map.

    python3 cad/flatten.py  ->  build/flatten.png

For each panel region (from panelize_last) we take the surface patch and find a 2D layout that
best preserves edge lengths: PCA-project to a plane, then spring-relax every edge toward its true
3D length (a mass-spring / position-based solve). Near-developable patches (the sole) flatten with
~zero distortion; doubly-curved ones (toe/heel) can't flatten flat, and the residual edge strain
IS the ease/stretch the canvas must absorb. Output: each pattern's size (mm) + an area-distortion
heatmap. This is the cordwainer "peel the taped last flat" step, done numerically.
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
REGIONS = ["sole", "lateral", "medial"]
DECIMATE = 1800          # simplify each region to ~this many faces before flattening (speed)
ITERS    = 2500
STEP     = 0.6


def region_submesh(m, labels, name):
    sub = m.submesh([np.where(labels == name)[0]], append=True)
    parts = sub.split(only_watertight=False)
    if len(parts) > 1:
        sub = max(parts, key=lambda p: len(p.faces))
    try:
        if len(sub.faces) > DECIMATE:
            sub = sub.simplify_quadric_decimation(DECIMATE)
    except Exception:
        pass
    return sub


def flatten(sub):
    V3, F, E = sub.vertices, sub.faces, sub.edges_unique
    rest = np.linalg.norm(V3[E[:, 0]] - V3[E[:, 1]], axis=1)
    C = V3 - V3.mean(0)
    _, _, Vt = np.linalg.svd(C, full_matrices=False)
    V2 = C @ Vt[:2].T                                    # PCA planar init
    deg = np.bincount(E.ravel(), minlength=len(V2)).astype(float); deg[deg == 0] = 1
    for _ in range(ITERS):
        vec = V2[E[:, 0]] - V2[E[:, 1]]
        d = np.linalg.norm(vec, axis=1); d[d < 1e-9] = 1e-9
        f = ((d - rest) / d)[:, None] * vec
        disp = np.zeros_like(V2)
        np.add.at(disp, E[:, 0], -f)
        np.add.at(disp, E[:, 1], f)
        V2 += STEP * disp / deg[:, None]
    return V2, V3, F, E, rest


def tri_area(P, F):
    a, b = P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]
    if P.shape[1] == 3:
        return 0.5 * np.linalg.norm(np.cross(a, b), axis=1)
    return 0.5 * np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "..", "build"), exist_ok=True)
    m = trimesh.load(LAST)
    labels = np.load(os.path.join(HERE, "last_regions.npz"), allow_pickle=True)["labels"]

    fig = plt.figure(figsize=(5 * len(REGIONS), 8))
    for k, name in enumerate(REGIONS):
        sub = region_submesh(m, labels, name)
        V2, V3, F, E, rest = flatten(sub)
        a3, a2 = tri_area(V3, F), tri_area(V2, F)
        ratio = a2 / np.maximum(a3, 1e-9)                # >1 stretch, <1 compress
        strain = (np.linalg.norm(V2[E[:, 0]] - V2[E[:, 1]], axis=1) - rest) / rest
        rms = float(np.sqrt(np.mean(strain ** 2)) * 100)

        ax = fig.add_subplot(2, len(REGIONS), k + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(V3[F], facecolor="#cfc3a6", linewidths=0))
        b = sub.bounds
        for i, a in enumerate("xyz"):
            getattr(ax, f"set_{a}lim")(b[0, i], b[1, i])
        ax.set_box_aspect(b[1] - b[0]); ax.view_init(20, -70); ax.axis("off")
        ax.set_title(f"{name}  (3D patch)", fontsize=10)

        ax2 = fig.add_subplot(2, len(REGIONS), len(REGIONS) + k + 1)
        tpc = ax2.tripcolor(V2[:, 0], V2[:, 1], F, facecolors=ratio,
                            cmap="RdBu_r", vmin=0.85, vmax=1.15, edgecolors="none")
        ax2.set_aspect("equal"); ax2.axis("off")
        ax2.set_title(f"{name} flat — {np.ptp(V2[:,0]):.0f}×{np.ptp(V2[:,1]):.0f} mm  RMS {rms:.1f}%",
                      fontsize=9)
        fig.colorbar(tpc, ax=ax2, fraction=0.04, label="area ratio")
        print(f"{name:8s} flat {np.ptp(V2[:,0]):5.0f}×{np.ptp(V2[:,1]):5.0f} mm  "
              f"RMS edge strain {rms:4.1f}%  faces {len(F)}")

    plt.tight_layout()
    plt.savefig(os.path.join(HERE, "..", "build", "flatten.png"), dpi=95, bbox_inches="tight")
    print("wrote build/flatten.png")
