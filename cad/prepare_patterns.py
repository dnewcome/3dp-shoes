"""Recover dimensioned OpenRun patterns without raster tracing or losing notches.

Run from any directory: python3 cad/prepare_patterns.py
The PDF page box is the scale authority, not the SVG's unitless width attribute.
Original cut edges already include the source construction geometry: no extra
seam allowance or invented stitch line is added. Outputs stay in ignored build/.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import Polygon, LineString
from svgpathtools import parse_path, Line, Path as SVGPath
from svgpathtools.path import transform
from svgpathtools.parser import parse_transform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[1]
MM_PER_PT = 25.4 / 72
ATTRIBUTION = "Open Run v1 / Open Footwear / CC BY-SA 4.0"


def sample(path, spacing=0.4):
    """Include every original segment endpoint, including tiny notch corners."""
    points = []
    for seg in path:
        count = max(1, math.ceil(seg.length() / spacing))
        points.extend(seg.point(t) for t in np.linspace(0, 1, count, endpoint=False))
    points.append(path[-1].end)
    return np.array([[z.real, z.imag] for z in points])


def read_vectors(svg, page_mm):
    root = ET.parse(svg).getroot()
    box = np.array([float(v) for v in root.attrib["viewBox"].split()])
    sx, sy = np.array(page_mm) / box[2:]
    if not np.isclose(sx, sy, rtol=1e-4):
        raise ValueError("PDF and SVG page aspect ratios differ; cannot trust scale")
    scale = np.array([[sx, 0, -sx * box[0]], [0, sy, -sy * box[1]], [0, 0, 1]])
    records = []

    def walk(node, parent, inherited):
        if node.tag.split("}")[-1] == "defs":
            return
        matrix = parent @ parse_transform(node.get("transform", ""))
        style = dict(inherited)
        style.update(node.attrib)
        style.update(dict(re.findall(r"([\w-]+)\s*:\s*([^;]+)", node.get("style", ""))))
        if node.tag.split("}")[-1] == "path" and style.get("fill") == "none":
            path = transform(parse_path(node.attrib["d"]), scale @ matrix)
            # PDF export leaves the vamp outline open by about four microns.
            # Close only sub-0.01 mm gaps, recording the repair for auditing.
            gap = abs(path.start - path.end)
            repair = 0.0
            if path.length() > 150 and 0 < gap < 0.01:
                path.append(Line(path.end, path.start))
                repair = gap
            stroke = style.get("stroke", "")
            levels = re.findall(r"[\d.]+", stroke)
            # This PDF export uses percent RGB. Fail rather than guess on other styles.
            if not stroke.startswith("rgb(") or "%" not in stroke:
                raise ValueError(f"Unsupported source stroke: {stroke}")
            kind = "mark" if np.mean([float(v) for v in levels]) > 35 else "cut"
            records.append({"path": path, "kind": kind, "xy": sample(path),
                            "closure_repair_mm": repair})
        for child in node:
            walk(child, matrix, style)

    walk(root, np.eye(3), {})
    return records


def extract(records):
    outlines = []
    for record in records:
        p = record["path"]
        if record["kind"] == "cut" and p.isclosed():
            polygon = Polygon(record["xy"])
            if polygon.area > 4000:
                if not polygon.is_valid:
                    clean = polygon.buffer(0)
                    deviation = polygon.boundary.hausdorff_distance(clean.boundary)
                    if clean.geom_type != "Polygon" or deviation > 0.01 or not all(
                            isinstance(seg, Line) for seg in p):
                        raise ValueError("Invalid source outline exceeds repair tolerance")
                    xy = np.asarray(clean.exterior.coords)
                    z = xy[:, 0] + 1j * xy[:, 1]
                    record["path"] = SVGPath(*[Line(a,b) for a,b in zip(z[:-1],z[1:])])
                    record["xy"] = xy
                    record["closure_repair_mm"] = max(record["closure_repair_mm"], deviation)
                    polygon = clean
                outlines.append((polygon, record))
    outlines.sort(key=lambda item: item[0].area, reverse=True)
    if len(outlines) != 4:
        raise ValueError(f"Expected four OpenRun outlines; found {len(outlines)}")
    panels = []
    # Source area ranking identifies the four pieces; no PCA rotation or rescaling.
    for number, ((polygon, outline), name) in enumerate(zip(outlines,
            ["sole", "vamp", "quarter", "tongue"]), 1):
        features = [r for r in records if r is not outline and
                    polygon.buffer(0.05).covers(LineString(r["xy"]))]
        # svgpathtools bbox is xmin,xmax,ymin,ymax.
        xmin, xmax, ymin, ymax = outline["path"].bbox()
        panels.append({"id": f"P{number}", "name": name, "outline": outline,
                       "features": features, "bounds": [xmin, ymin, xmax, ymax]})
    return panels


def svg_document(panel, mirrored=False):
    x0, y0, x1, y1 = panel["bounds"]
    w, h = x1 - x0, y1 - y0
    width, height = max(180, w + 36), h + 70
    side = "mirrored" if mirrored else "source"
    matrix = np.array([[-1 if mirrored else 1, 0, x1 if mirrored else -x0],
                       [0, 1, -y0], [0, 0, 1]])
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.6f}mm" '
             f'height="{height:.6f}mm" viewBox="0 0 {width:.6f} {height:.6f}">',
             '<style>text {font-family:sans-serif;font-size:3.2px}</style>',
             f'<text x="8" y="7">{panel["id"]} {panel["name"]} / {side} / mm / scale 1:1</text>',
             '<text x="8" y="13">Black: source cut. Grey: source mark. No added allowance.</text>',
             '<g transform="translate(18 25)" fill="none" stroke-width="0.2">']
    for r in [panel["outline"], *panel["features"]]:
        p = transform(r["path"], matrix)
        lines.append(f'<path d="{p.d()}" stroke="{"#999" if r["kind"] == "mark" else "#111"}"/>')
    lines.extend(['</g>', f'<g stroke="#167398" stroke-width="0.2" fill="none">'
        f'<path d="M18,20 h{w:.5f} M18,18 v4 M{18+w:.5f},18 v4 '
        f'M12,25 v{h:.5f} M10,25 h4 M10,{25+h:.5f} h4"/></g>',
        f'<text x="{18+w/2:.5f}" y="19" text-anchor="middle">{w:.2f} mm</text>',
        f'<text transform="translate(9 {25+h/2:.5f}) rotate(-90)" text-anchor="middle">{h:.2f} mm</text>',
        f'<path d="M18,{h+37:.5f} h100 m-100,-2 v4 m100,-4 v4" fill="none" stroke="black" stroke-width="0.2"/>',
        f'<text x="18" y="{h+44:.5f}">100 mm check bar. Print at 100%; disable fit-to-page.</text>',
        f'<text x="8" y="{h+53:.5f}">{ATTRIBUTION}</text>',
        f'<text x="8" y="{h+59:.5f}">Reference size EU 42; wearer fit and seam mapping unverified.</text>',
        '</svg>'])
    return "\n".join(lines)


def draw_panel(ax, panel, offset=(0, 0)):
    origin = np.array(panel["bounds"][:2])
    for r in [panel["outline"], *panel["features"]]:
        xy = r["xy"] - origin + offset
        ax.plot(*xy.T, color="0.6" if r["kind"] == "mark" else "0.12", lw=0.5)


def pdf_patterns(panels, output, paper=None):
    with PdfPages(output) as pdf:
        for panel in panels:
            x0, y0, x1, y1 = panel["bounds"]
            w, h = x1-x0, y1-y0
            pw, ph = paper or (max(180, w + 36), h + 70)
            usable_w, usable_h = pw-24, ph-48
            nx = max(1, math.ceil((w-8)/(usable_w-8))) if paper else 1
            ny = max(1, math.ceil((h-8)/(usable_h-8))) if paper else 1
            for row in range(ny):
                for col in range(nx):
                    fig = plt.figure(figsize=(pw/25.4, ph/25.4))
                    ax = fig.add_axes([0, 0, 1, 1])
                    ax.set(xlim=(0, pw), ylim=(ph, 0), aspect="equal")
                    ax.axis("off")
                    ax.text(10, 8, f'{panel["id"]} {panel["name"]} / SOURCE side / EU 42', fontsize=9)
                    ax.text(10, 14, f'{w:.2f} x {h:.2f} mm | tile {row+1},{col+1} of {ny},{nx}', fontsize=8)
                    # Clip each tile to an exactly dimensioned viewport with 8 mm overlap.
                    a = fig.add_axes([12/pw, 28/ph, usable_w/pw, usable_h/ph])
                    tx, ty = col*(usable_w-8), row*(usable_h-8)
                    a.set(xlim=(tx, tx+usable_w), ylim=(ty+usable_h, ty), aspect="equal")
                    a.set_xticks([]); a.set_yticks([])
                    for spine in a.spines.values():
                        spine.set_linewidth(0.3); spine.set_edgecolor("0.7")
                    draw_panel(a, panel)
                    ax.plot([12,112], [ph-19, ph-19], color="black", lw=0.5)
                    ax.plot([12,12,112,112], [ph-20,ph-18,ph-18,ph-20], alpha=0)
                    ax.text(12, ph-14, '100 mm check bar / 100% print / 8 mm tile overlap', fontsize=7)
                    ax.text(12, ph-9, ATTRIBUTION, fontsize=7)
                    ax.text(12, ph-4, 'Black = cut; grey = mark. No added allowance. Fit unverified.', fontsize=7)
                    pdf.savefig(fig)
                    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=ROOT/"assets/openrun/OpenRun_42_PATTERNS.pdf")
    ap.add_argument("--output", type=Path, default=ROOT/"build/patterns")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    info = subprocess.run(["pdfinfo", str(args.pdf)], capture_output=True, text=True, check=True).stdout
    match = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info)
    if not match or not re.search(r"Pages:\s+1\b", info):
        raise ValueError("Expected a single-page pattern PDF with known page dimensions")
    page_mm = np.array([float(v) for v in match.groups()]) * MM_PER_PT
    svg = args.output/"source.svg"
    subprocess.run(["pdftocairo", "-svg", str(args.pdf), str(svg)], check=True)
    records = read_vectors(svg, page_mm)
    panels = extract(records)
    manifest = {"units": "mm", "source": str(args.pdf),
        "sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(), "source_page_mm": page_mm.tolist(),
        "attribution": ATTRIBUTION, "source_url": "https://www.openfootwear.com/openrun.html",
        "license": "https://creativecommons.org/licenses/by-sa/4.0/",
        "status": "Reference patterns; seam correspondence and wearer fit unverified",
        "added_seam_allowance_mm": 0, "panels": []}
    for panel in panels:
        stem = f'{panel["id"]}_{panel["name"]}'
        for mirror in (False, True):
            (args.output/f'{stem}_{"mirrored" if mirror else "source"}.svg').write_text(svg_document(panel, mirror))
        x0,y0,x1,y1 = panel["bounds"]
        manifest["panels"].append({"id": panel["id"], "name": panel["name"],
            "width_mm": x1-x0, "height_mm": y1-y0,
            "cut_perimeter_mm": panel["outline"]["path"].length(),
            "closure_repair_mm": panel["outline"]["closure_repair_mm"],
            "source_bounds_mm": panel["bounds"],
            "outline_d_mm": panel["outline"]["path"].d(),
            "features": [{"kind": r["kind"], "d_mm": r["path"].d()} for r in panel["features"]]})
        print(stem, f'{x1-x0:.2f} x {y1-y0:.2f} mm', len(panel["features"]), "preserved features")
    (args.output/"patterns.json").write_text(json.dumps(manifest, indent=2)+"\n")
    pdf_patterns(panels, args.output/"patterns_full_size.pdf")
    pdf_patterns(panels, args.output/"patterns_A4.pdf", (210,297))
    pdf_patterns(panels, args.output/"patterns_Letter.pdf", (215.9,279.4))
    fig, axes = plt.subplots(2,2,figsize=(10,10))
    for ax,panel in zip(axes.flat,panels):
        draw_panel(ax,panel)
        ax.invert_yaxis(); ax.set_aspect("equal"); ax.grid(alpha=.2)
        ax.set_title(f'{panel["id"]} {panel["name"]} (mm)')
    fig.suptitle('Recovered original vectors / reference EU 42 / fit unverified')
    fig.tight_layout(); fig.savefig(args.output/"overview.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
