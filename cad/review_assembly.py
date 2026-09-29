"""Create offline interactive review, strain evidence, seam map and prototype GLB."""
from pathlib import Path
import json
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from prepare_patterns import ROOT, parse_path, sample


def main():
    out=ROOT/"build/assembly"
    data=json.loads((out/"sewing_input.json").read_text())
    frames=json.loads((out/"simulation_frames.json").read_text())
    report=json.loads((out/"simulation_report.json").read_text())
    patterns=json.loads((ROOT/"build/patterns/patterns.json").read_text())
    sole_report=json.loads((ROOT/"build/soles/sole_report.json").read_text())
    sole=trimesh.load(ROOT/"build/soles/sole_source.stl")
    sole.apply_translation(-np.array(sole_report["source_to_print_translation_mm"]))
    light_sole=sole.simplify_quadric_decimation(face_count=4500)
    final=np.array(frames["snapshots"][-1]["vertices_mm"])
    last=trimesh.Trimesh(data["last"]["vertices"],data["last"]["faces"])
    inside=last.contains(final)
    distance=last.nearest.on_surface(final)[1]
    report["vertices_inside_last_more_than_0_5mm"]=int(np.count_nonzero(inside&(distance>.5)))
    report["max_vertex_penetration_mm"]=float(max(distance[inside],default=0))
    report["convergence_note"]="Finite time solve; no convergence or fit approval asserted"
    report["sole_interface"]="Visual reference only; sole-to-upper glue contact not solved"
    (out/"simulation_report.json").write_text(json.dumps(report,indent=2)+"\n")
    flat=[];initial=[];face_panels=[];seam_edges=[]
    for i,p in enumerate(data["panels"]):
        uv=np.array(p["uv"]);uv-=np.array([145,200])
        flat.extend(np.c_[uv,np.zeros(len(uv))].tolist())
        initial.extend(p["initial"]);face_panels.extend([i]*len(p["faces"]))
    pmap={p["name"]:p for p in data["panels"]}
    for s in data["seams"]:
        for a,b in zip(s["a_xy"],s["b_xy"]):
            ai=int(np.argmin(np.linalg.norm(np.array(pmap[s["a"]]["uv"])-a,axis=1)))+frames["ranges"][s["a"]][0]
            bi=int(np.argmin(np.linalg.norm(np.array(pmap[s["b"]]["uv"])-b,axis=1)))+frames["ranges"][s["b"]][0]
            seam_edges.append([ai,bi])
    payload={"frames":frames["snapshots"],"faces":frames["faces"],"flat":flat,"initial":initial,
        "facePanels":face_panels,"seamEdges":seam_edges,"last":data["last"],
        "sole":{"vertices":light_sole.vertices.tolist(),"faces":light_sole.faces.tolist()},
        "report":report,"patterns":[{k:p[k] for k in ["id","name","width_mm","height_mm"]} for p in patterns["panels"]]}
    template=(ROOT/"cad/assembly_viewer.html").read_text()
    (out/"viewer.html").write_text(template.replace("__DATA__",json.dumps(payload,separators=(",",":"))))
    colors=["#b8a077","#2373a1","#c67535","#845391"]
    scene=trimesh.Scene()
    for p,color in zip(data["panels"],colors):
        lo,hi=frames["ranges"][p["name"]]
        m=trimesh.Trimesh(final[lo:hi]/1000,p["faces"])
        m.visual.face_colors=matplotlib.colors.to_rgba_array(color)[0]*255
        scene.add_geometry(m,node_name=p["name"])
    sm=light_sole.copy();sm.apply_scale(.001);sm.visual.face_colors=[55,65,62,255]
    scene.add_geometry(sm,node_name="prototype sole")
    scene.export(out/"shoe_prototype.glb")
    fig=plt.figure(figsize=(14,7))
    for i,(title,verts) in enumerate([("Initial placement (not a fit result)",np.array(initial)),
                                     (f'Cloth sewing / frame {report["frames"]} / NOT VALIDATED',final)]):
        ax=fig.add_subplot(1,2,i+1,projection="3d")
        for p,c in zip(data["panels"],colors):
            lo,hi=frames["ranges"][p["name"]];v=verts[lo:hi]
            ax.add_collection3d(Poly3DCollection(v[np.array(p["faces"])],facecolor=c,linewidths=0))
        ax.add_collection3d(Poly3DCollection(light_sole.triangles,facecolor="#414d49",linewidths=0))
        ax.set(xlim=(-90,90),ylim=(-185,155),zlim=(-5,145))
        ax.set_box_aspect([180,340,150]);ax.view_init(25,-65);ax.set_title(title,fontsize=11);ax.axis("off")
    fig.tight_layout();fig.savefig(out/"assembly_preview.png",dpi=140);plt.close(fig)
    with PdfPages(out/"seam_map.pdf") as pdf:
        for p in patterns["panels"]:
            fig,ax=plt.subplots(figsize=(9,11))
            for f in [{"kind":"cut","d_mm":p["outline_d_mm"]},*p["features"]]:
                xy=sample(parse_path(f["d_mm"]),1)
                ax.plot(*xy.T,color=".75" if f["kind"]=="mark" else ".35",lw=.5)
            for i,s in enumerate(data["seams"]):
                if s["a"]!=p["name"] and s["b"]!=p["name"]:continue
                xy=np.array(s["a_xy"] if s["a"]==p["name"] else s["b_xy"])
                ax.plot(*xy.T,"o-",ms=2,lw=.8,label=s["name"])
                ax.text(*xy[0],f'S{i+1}:1',fontsize=6)
                ax.text(*xy[-1],f'S{i+1}:{len(xy)}',fontsize=6)
            ax.set_aspect("equal");ax.invert_yaxis();ax.set_title(f'{p["id"]} {p["name"]} / inferred seams / review only')
            ax.legend(fontsize=7,loc="upper left",bbox_to_anchor=(1,1))
            fig.text(.05,.02,"Open Run / Open Footwear / CC BY-SA 4.0. NOT a 1:1 cutting sheet.",fontsize=8)
            fig.tight_layout(rect=(0,.03,1,1));pdf.savefig(fig);plt.close(fig)
    text=["# Prototype review — NOT VALIDATED FOR CUTTING", "",
        "The four original OpenRun EU 42 pieces have been recovered at PDF scale. "
        "The old raster traces were not used. Original cut edges, notches and marking lines are retained. "
        "The vamp's 0.004 mm closure defect is repaired. No new seam allowance is added.","",
        "## Files", "", "- `viewer.html`: standalone offline 3D review; orbit, timeline, strain, last and sole controls.",
        "- `sewing.blend`: editable sewing springs, flat rest shape and evaluated final snapshot.",
        "- `shoe_prototype.glb`: evaluated upper plus prototype sole; glTF units are metres.",
        "- `sewn_upper_mm.obj`: evaluated upper only, numeric units mm.",
        "- `seams.json` / `seam_map.pdf`: inferred hole correspondences; tongue root remains approximate.",
        "- `../patterns/`: dimensioned source/mirrored SVGs and 1:1/tiled PDFs.",
        "- `../soles/`: mirrored prototype STL pair, numeric units mm.","",
        "## Dimensions", "", "| Piece | Width × height (mm) |", "|---|---:|"]
    for p in patterns["panels"]:text.append(f'| {p["id"]} {p["name"]} | {p["width_mm"]:.2f} × {p["height_mm"]:.2f} |')
    dims=sole_report["soles"]["source"]["dimensions_mm"]
    text += ["",f'Each sole: {dims[0]:.2f} × {dims[1]:.2f} × {dims[2]:.2f} mm. '
        "Both exported STLs reload as one watertight positive-volume body. "
        "They retain the reference midsole upper surface and add a 3 mm base with 1.2 mm tread recesses.","",
        "## What the simulation actually checked", "",
        "Blender cloth uses the recovered flat meshes for spring rest lengths, with loose edges "
        "as sewing springs and last collision. Self collision is disabled for the overlapping lap "
        "seams; layer-aware allowance collision is unresolved. The footbed interior is held by "
        "a fixture. The initial wrapped geometry is only a starting guess. "
        "Material constants are uncalibrated and perforations/seam thickness are omitted. "
        "The printed sole is a visual reference, not a solved glue-contact interface.","",
        f'Footbed-to-last rigid registration RMS: {report["registration"]["footbed_registration_rms_mm"]:.2f} mm. '
        "No scale change was applied. The best registration reflects the sheet in XY.","",
        "### Flat seam chain lengths", "", "Lengths below follow hole centres, not cut perimeters. "
        "A mismatch can indicate required gathering/ease or an incorrect correspondence; it is not automatically allowable stretch.","",
        "| Inferred join | A (mm) | B (mm) | A−B (mm) |", "|---|---:|---:|---:|"]
    for s in data["seams"]:
        if "difference_mm" in s:text.append(f'| {s["name"]} | {s["length_a_mm"]:.2f} | {s["length_b_mm"]:.2f} | {s["difference_mm"]:.2f} |')
    text += ["", "### Final solver residuals", "", "| Join | RMS gap (mm) | Max gap (mm) |", "|---|---:|---:|"]
    for n,s in report["seams"].items():text.append(f'| {n} | {s["rms_gap_mm"]:.2f} | {s["max_gap_mm"]:.2f} |')
    text += ["", "| Piece | RMS edge strain | 95th percentile absolute strain |", "|---|---:|---:|"]
    for n,p in report["panels"].items():text.append(f'| {n} | {p["rms_edge_strain_percent"]:.1f}% | {p["p95_abs_edge_strain_percent"]:.1f}% |')
    text += ["", f'Vertices more than 0.5 mm inside the last: {report["vertices_inside_last_more_than_0_5mm"]}. '
        f'Maximum sampled penetration: {report["max_vertex_penetration_mm"]:.2f} mm. '
        "This is a vertex check, not a proof that all triangles are collision-free.","",
        "## Next fit decisions", "", "Confirm the style and handedness; measure both feet (length, width, ball and instep girths). "
        "Specify upper fabric, thickness, stretch in both grain directions, seam construction and printer bed dimensions. "
        "Resolve the 10–15% sole joining-length mismatch and tongue attachment before using expensive material. "
        "Then calibrate cloth properties, revise seams/patterns, rerun, and make a paper or scrap-material fitting.","",
        "Print patterns at actual size (100%), with fit-to-page disabled. Check every 100 mm bar. "
        "Tiles overlap by 8 mm; align duplicated geometry at matching row/column boundaries. "
        "Use one source and one mirrored set for the pair, with fabric face orientation checked.","",
        "Reference geometry: Open Run by Open Footwear, https://www.openfootwear.com/openrun.html, CC BY-SA 4.0. "
        "Generated derivatives remain in ignored build/."]
    (out/"review.md").write_text("\n".join(text)+"\n")
    print("Wrote viewer.html, review.md, seam_map.pdf, assembly_preview.png, shoe_prototype.glb")


if __name__=="__main__":main()
