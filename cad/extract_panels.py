"""extract_panels.py — pull the OpenRun upper panels out of the pattern PDF as true-scale SVGs.

    python3 cad/extract_panels.py  ->  cad/panels/panel_{1..4}.svg  (+ build/panels_preview.png)

The pattern PDF is line-art (cut outlines + stitch/vent holes), so vector import gives messy
open/:combined paths. Instead we rasterize and segment: render the sheet, flood from the border,
and every region ENCLOSED by cut-lines is a panel. Each panel's outer contour is traced, smoothed,
PCA-oriented (long axis +Y), centered, and written as an SVG in millimetres (the holes are
dropped — we regenerate stitch/vent holes parametrically on the panel part).
"""
import os
import math
import numpy as np
from PIL import Image
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE   = os.path.dirname(__file__)
PDF    = os.path.join(HERE, "..", "assets", "openrun", "OpenRun_42_PATTERNS.pdf")
DPI    = 150
MMPX   = 25.4 / DPI
N_PTS  = 120          # outline points per panel after resampling
N_PANELS = 4


def render_png():
    out = os.path.join(HERE, "..", "build", "openrun_page")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.system(f'pdftocairo -png -r {DPI} -gray "{PDF}" "{out}" 2>/dev/null')
    return out + "-1.png"


def panel_masks(png):
    """The N_PANELS largest white regions enclosed by cut-lines (holes filled), biggest first."""
    im = np.array(Image.open(png).convert("L"))
    lbl, n = ndimage.label(im > 128)
    sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
    border = set(np.unique(np.concatenate([lbl[0], lbl[-1], lbl[:, 0], lbl[:, -1]])))
    ranked = sorted(((s, i + 1) for i, s in enumerate(sizes) if (i + 1) not in border),
                    reverse=True)[:N_PANELS]
    return [ndimage.binary_fill_holes(lbl == i) for _, i in ranked], im


def outer_contour(mask):
    cs = plt.contour(mask.astype(float), levels=[0.5])
    seg = max(cs.allsegs[0], key=len)
    plt.close("all")
    return seg * MMPX                       # (x, y) mm, image coords


def resample(poly, n):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))]
    s = np.linspace(0, d[-1], n, endpoint=False)
    return np.c_[np.interp(s, d, poly[:, 0]), np.interp(s, d, poly[:, 1])]


def smooth(poly, passes=4):
    for _ in range(passes):
        poly = 0.25 * np.roll(poly, 1, 0) + 0.5 * poly + 0.25 * np.roll(poly, -1, 0)
    return poly


def normalize(poly):
    p = poly - poly.mean(0)
    _, _, vt = np.linalg.svd(p, full_matrices=False)
    ang = math.atan2(vt[0, 1], vt[0, 0]) - math.pi / 2     # long axis -> +Y
    c, s = math.cos(-ang), math.sin(-ang)
    p = p @ np.array([[c, -s], [s, c]]).T
    p -= [(p[:, 0].max() + p[:, 0].min()) / 2, (p[:, 1].max() + p[:, 1].min()) / 2]
    return p


def write_svg(poly, path):
    P = np.c_[poly[:, 0], -poly[:, 1]]                       # SVG y-down; import_svg(flip_y) restores
    n = len(P)
    d = f"M {P[0,0]:.3f},{P[0,1]:.3f} "
    for i in range(n):
        p0, p1, p2, p3 = P[(i - 1) % n], P[i], P[(i + 1) % n], P[(i + 2) % n]
        c1, c2 = p1 + (p2 - p0) / 6.0, p2 - (p3 - p1) / 6.0
        d += f"C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {p2[0]:.3f},{p2[1]:.3f} "
    d += "Z"
    mn = P.min(0); w, h = np.ptp(P, 0)
    open(path, "w").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" '
        f'viewBox="{mn[0]:.2f} {mn[1]:.2f} {w:.2f} {h:.2f}">'
        f'<path d="{d}" fill="none" stroke="black" stroke-width="0.5"/></svg>')


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "panels"), exist_ok=True)
    png = render_png()
    masks, im = panel_masks(png)
    fig, ax = plt.subplots(figsize=(7, 9))
    ax.imshow(im, cmap="gray", alpha=0.35)
    cols = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]
    for k, mask in enumerate(masks):
        poly = normalize(smooth(resample(outer_contour(mask), N_PTS)))
        write_svg(poly, os.path.join(HERE, "panels", f"panel_{k+1}.svg"))
        ys, xs = np.where(mask)
        ax.contour(mask, levels=[0.5], colors=cols[k], linewidths=1.4)
        ax.text(xs.mean(), ys.mean(), f"P{k+1}\n{np.ptp(poly[:,0]):.0f}x{np.ptp(poly[:,1]):.0f}mm",
                color=cols[k], fontsize=11, ha="center", weight="bold")
        print(f"panel_{k+1}.svg  {np.ptp(poly[:,0]):.0f} x {np.ptp(poly[:,1]):.0f} mm")
    ax.axis("off"); ax.set_title("OpenRun panels extracted")
    plt.tight_layout(); plt.savefig(os.path.join(HERE, "..", "build", "panels_preview.png"), dpi=90)
    print("wrote cad/panels/*.svg + build/panels_preview.png")
