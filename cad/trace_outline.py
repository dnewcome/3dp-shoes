"""trace_outline.py — extract the sole silhouette from a palette PNG and save a normalized outline.

    python3 cad/trace_outline.py  ->  cad/sole_outline.json  (+ build/trace_overlay.png)

Background is the two checkerboard grays (palette idx 3 & 5); everything else is the sole.
Output points are: centered, rotated so the long axis is +Y, toe at +Y, scaled to TARGET_LEN mm.
"""
import os, sys, json
import numpy as np
from PIL import Image
from scipy import ndimage

# Your own photo/scan of a sole, segmented to a palette PNG (checkerboard background).
# Override with: python3 cad/trace_outline.py /path/to/your/sole.png  (or set VANS_PNG).
SRC        = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VANS_PNG", "vans.png")
BG_IDX     = {3, 5}      # checkerboard grays
TARGET_LEN = 297.0       # scale overall length to men's US9 outsole (mm)
N_POINTS   = 72          # outline points after resampling


def sole_mask():
    im = Image.open(SRC)
    idx = np.array(im)
    mask = ~np.isin(idx, list(BG_IDX))
    mask = ndimage.binary_fill_holes(mask)
    lbl, n = ndimage.label(mask)                      # keep largest blob only
    if n > 1:
        big = 1 + np.argmax([(lbl == i).sum() for i in range(1, n + 1)])
        mask = lbl == big
    mask = ndimage.binary_closing(mask, iterations=2)
    return ndimage.binary_fill_holes(mask)


def contour_xy(mask):
    """Longest 0.5 iso-contour of the mask, as ordered (x,y) in image pixels (y down)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cs = plt.contour(mask.astype(float), levels=[0.5])
    segs = cs.allsegs[0]
    plt.close("all")
    v = max(segs, key=len)                            # [:, (x, y)]
    return v


def resample(poly, n):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))]
    s = np.linspace(0, d[-1], n, endpoint=False)
    return np.c_[np.interp(s, d, poly[:, 0]), np.interp(s, d, poly[:, 1])]


def smooth(poly, passes=4):
    """Periodic 3-tap smoothing to remove pixel-stair noise from the traced contour."""
    for _ in range(passes):
        poly = 0.25 * np.roll(poly, 1, 0) + 0.5 * poly + 0.25 * np.roll(poly, -1, 0)
    return poly


def normalize(poly):
    p = poly.astype(float)
    p[:, 1] *= -1.0                                   # image y-down -> math y-up
    p -= p.mean(0)
    # rotate long axis -> Y via PCA
    u, s, vt = np.linalg.svd(p - p.mean(0), full_matrices=False)
    major = vt[0]
    ang = np.arctan2(major[1], major[0]) - np.pi / 2  # bring major axis to +Y
    c, sn = np.cos(-ang), np.sin(-ang)
    p = p @ np.array([[c, -sn], [sn, c]]).T
    # orient toe (end nearer the widest cross-section) to +Y
    ys = p[:, 1]
    lo, hi = ys.min(), ys.max()
    band = (hi - lo) * 0.12
    w_top = np.ptp(p[ys > hi - band, 0]) if (ys > hi - band).any() else 0
    w_bot = np.ptp(p[ys < lo + band, 0]) if (ys < lo + band).any() else 0
    # the heel is narrower & rounder than the ball/toe; ensure the BROADER (ball) end is up-ish.
    # Widest section sits ~forefoot; put more length below it (heel) -> toe up.
    ywidest = p[np.argmax(np.abs(p[:, 0]))][1]
    if ywidest < p[:, 1].mean():
        p[:, 1] *= -1.0
    # scale to target length, recenter
    p *= TARGET_LEN / np.ptp(p[:, 1])
    p[:, 1] -= p[:, 1].min()                           # heel ~ y=0
    p[:, 0] -= (p[:, 0].max() + p[:, 0].min()) / 2     # center width
    return p


def write_svg(poly, path):
    """Smooth closed SVG path (Catmull-Rom -> cubic bezier). y is negated so build123d's
    import_svg(flip_y=True) restores the math (toe-up) orientation. Units are mm."""
    P = np.c_[poly[:, 0], -poly[:, 1]]                 # SVG is y-down
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
    os.makedirs("build", exist_ok=True)
    mask = sole_mask()
    raw = contour_xy(mask)
    poly = normalize(smooth(resample(raw, N_POINTS)))
    json.dump(poly.round(3).tolist(), open("cad/sole_outline.json", "w"))
    write_svg(poly, "cad/sole_outline.svg")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(9, 8))
    ax[0].imshow(mask, cmap="gray"); ax[0].plot(raw[:, 0], raw[:, 1], "r-", lw=1); ax[0].set_title("mask + contour")
    ax[1].plot(poly[:, 0], poly[:, 1], "b.-", ms=3); ax[1].plot(*poly[0], "go"); ax[1].set_aspect("equal")
    ax[1].grid(alpha=.3); ax[1].set_title(f"normalized  {np.ptp(poly[:,0]):.0f}x{np.ptp(poly[:,1]):.0f}mm")
    plt.tight_layout(); plt.savefig("build/trace_overlay.png", dpi=95)
    print(f"wrote cad/sole_outline.json ({len(poly)} pts), bbox "
          f"{np.ptp(poly[:,0]):.1f} x {np.ptp(poly[:,1]):.1f} mm")
