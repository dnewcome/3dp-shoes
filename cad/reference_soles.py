"""Print prototypes based on the matching OpenRun midsole, retaining its upper surface.

Adds a flat waffle outsole below the reference midsole and exports a mirrored pair.
These are geometry-checked prototypes; fit/material/printer suitability is not certified.
"""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import trimesh
import manifold3d as m3d
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

ROOT=Path(__file__).resolve().parents[1]


def to_manifold(mesh):
    result=m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices,dtype=np.float32),
                              tri_verts=np.asarray(mesh.faces,dtype=np.uint32)))
    if result.status()!=m3d.Error.NoError or result.is_empty():
        raise ValueError(f"Invalid manifold: {result.status()}")
    return result


def to_mesh(manifold):
    m=manifold.to_mesh()
    mesh=trimesh.Trimesh(np.asarray(m.vert_properties)[:,:3],np.asarray(m.tri_verts))
    if not mesh.is_volume or len(mesh.split())!=1:
        raise ValueError("Sole must be one watertight, consistently oriented solid")
    return mesh


def prototype(source,base_depth=3.0,tread_depth=1.2,pitch=9,rib_width=2.5):
    if not 0<tread_depth<base_depth or not 0<rib_width<pitch:
        raise ValueError("Require 0 < tread < base depth, and 0 < rib width < pitch")
    z=float(source.bounds[0,2])
    section=source.section(plane_origin=[0,0,z+.05],plane_normal=[0,0,1])
    if section is None:raise ValueError("Cannot recover bottom footprint")
    polygon=max((Polygon(c[:,:2]) for c in section.discrete),key=lambda p:p.area).buffer(.25)
    # Bottom section is extended 0.25 mm to prevent a hairline joint at the rim.
    poly=np.asarray(orient(polygon,sign=1).exterior.coords[:-1])
    slab=m3d.CrossSection([poly]).extrude(base_depth+.15).translate([0,0,z-base_depth])
    body=to_manifold(source)+slab
    center=source.bounds.mean(0)
    width,length=source.extents[:2]+20
    diagonal=math.hypot(width,length)*1.3
    recess=m3d.Manifold.cube([width,length,tread_depth+.1],center=True).translate(
        [center[0],center[1],z-base_depth+(tread_depth-.1)/2])
    bars=[]
    for angle in [-45,45]:
        a=math.radians(angle)
        for k in range(-math.ceil(diagonal/pitch),math.ceil(diagonal/pitch)+1):
            bars.append(m3d.Manifold.cube([rib_width,diagonal,tread_depth+1],center=True)
                .rotate([0,0,angle]).translate([center[0]+k*pitch*math.cos(a),
                    center[1]+k*pitch*math.sin(a),z-base_depth+tread_depth/2]))
    cutter=recess-m3d.Manifold.batch_boolean(bars,m3d.OpType.Add)
    result=to_mesh(body-cutter)
    # Print Z=0. The same translation is recorded for the assembly scene.
    result.apply_translation([0,0,base_depth-z])
    return result,base_depth-z


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source",type=Path,default=ROOT/"assets/openrun/OpenRun_42_MIDSOLE.stl")
    ap.add_argument("--output",type=Path,default=ROOT/"build/soles")
    ap.add_argument("--base-depth",type=float,default=3)
    ap.add_argument("--tread-depth",type=float,default=1.2)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source=trimesh.load(args.source)
    mesh,offset=prototype(source,args.base_depth,args.tread_depth)
    report={"status":"Printable prototype geometry; upper interface and wearer fit unverified",
        "attribution":"Open Run by Open Footwear / CC BY-SA 4.0",
        "source":str(args.source),"source_to_print_translation_mm":[0,0,offset],
        "base_added_mm":args.base_depth,"tread_depth_mm":args.tread_depth,
        "reference_top_surface_retained":True,"soles":{},
        "assembly_note":"Uses the OpenRun midsole; not the unrelated traced 297 mm outsole.",
        "printer_build_volume_verified":False,"material_verified":False}
    for side in ["source","mirrored"]:
        m=mesh.copy()
        if side=="mirrored":m.apply_transform(np.diag([-1,1,1,1]))
        path=args.output/f"sole_{side}.stl";m.export(path)
        check=trimesh.load(path)
        if not check.is_volume or len(check.split())!=1:raise ValueError("STL round-trip failed")
        report["soles"][side]={"dimensions_mm":check.extents.tolist(),"watertight":check.is_watertight,
            "bodies":len(check.split()),"volume_cm3":float(check.volume/1000)}
    (args.output/"sole_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
