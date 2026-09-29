"""Run inside Blender: blender -b --python cad/sew_blender.py -- --frames 120

Creates an editable cloth scene, actual sewing springs, a flat rest shape,
evaluated simulation snapshots and quantitative seam/strain measurements.
Millimetres in the interchange file are converted to Blender metres.
"""
import argparse
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]


def obj_mesh(name, vertices, faces, edges=()):
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,edges,faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def material(name,color):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1)
    mat.use_nodes=True
    shader=mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=(*color,1)
    shader.inputs["Roughness"].default_value=.8
    return mat


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=ROOT/"build/assembly/sewing_input.json")
    ap.add_argument("--frames",type=int,default=120)
    args=ap.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if args.frames<2:ap.error("frames must be at least 2")
    out=args.input.parent;data=json.loads(args.input.read_text())
    bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC";scene.unit_settings.length_unit="MILLIMETERS"
    scene.gravity=(0,0,-.2)  # assembly experiment, not a wear/load simulation
    scene.frame_end=args.frames
    last=obj_mesh("Reference last (collision)",np.array(data["last"]["vertices"])/1000,data["last"]["faces"])
    last.modifiers.new("Last collision","COLLISION")
    last.collision.thickness_outer=.0008
    last.collision.thickness_inner=.0002
    last.data.materials.append(material("Last",(.55,.58,.59)))
    offsets={};all_v=[];all_rest=[];all_f=[];ranges={};pins=[];face_material=[]
    palette=[(.65,.53,.32),(.06,.30,.53),(.75,.29,.08),(.38,.17,.49)]
    for index,p in enumerate(data["panels"]):
        offset=len(all_v); offsets[p["name"]]=offset
        v=np.array(p["initial"])/1000;uv=np.array(p["uv"])/1000
        rest=np.c_[uv,np.zeros(len(uv))]
        all_v.extend(v.tolist());all_rest.extend(rest.tolist())
        all_f.extend((np.array(p["faces"])+offset).tolist())
        face_material.extend([index]*len(p["faces"]))
        ranges[p["name"]]=(offset,len(all_v))
        pins.extend(offset+i for i in p["pin"])
    seams=[];seam_indices=[]
    panels={p["name"]:p for p in data["panels"]}
    for s in data["seams"]:
        pairs=[]
        for a,b in zip(s["a_xy"],s["b_xy"]):
            ai=int(np.argmin(np.linalg.norm(np.array(panels[s["a"]]["uv"])-a,axis=1)))+offsets[s["a"]]
            bi=int(np.argmin(np.linalg.norm(np.array(panels[s["b"]]["uv"])-b,axis=1)))+offsets[s["b"]]
            pairs.append([ai,bi]);seams.append([ai,bi])
        seam_indices.append((s["name"],np.array(pairs)))
    cloth=obj_mesh("Upper - LIVE sewing simulation",all_v,all_f,seams)
    for p,c in zip(data["panels"],palette):cloth.data.materials.append(material(p["name"],c))
    for poly,idx in zip(cloth.data.polygons,face_material):poly.material_index=idx
    cloth.shape_key_add(name="Initial drape")
    rest_key=cloth.shape_key_add(name="FLAT PATTERNS - physical rest lengths")
    for vertex,co in zip(rest_key.data,all_rest):vertex.co=co
    rest_key.value=0.0
    group=cloth.vertex_groups.new(name="Footbed fixture")
    if pins:group.add(pins,1,"REPLACE")
    modifier=cloth.modifiers.new("Sew original flat patterns","CLOTH")
    settings=modifier.settings
    settings.rest_shape_key=rest_key
    settings.quality=30
    settings.time_scale=.15
    settings.mass=.005
    settings.tension_stiffness=100
    settings.compression_stiffness=100
    settings.shear_stiffness=50
    settings.bending_stiffness=.001
    settings.air_damping=10
    settings.use_sewing_springs=True
    settings.sewing_force_max=2
    settings.vertex_group_mass=group.name
    settings.pin_stiffness=1
    collision=modifier.collision_settings
    collision.use_collision=True;collision.distance_min=.0005
    # Joining is at interior hole centres: allowances overlap by design. A simple
    # all-vertex self collision model fights these lap seams and destabilizes the
    # solve. Layer-aware allowance collision remains an explicit unresolved task.
    collision.use_self_collision=False;collision.self_distance_min=.0005
    collision.self_friction=5
    collision.collision_quality=4
    modifier.point_cache.frame_start=1;modifier.point_cache.frame_end=args.frames
    cloth["STATUS"]="PROVISIONAL - seam map and material unverified; inspect simulation_report.json"
    cloth["Rest geometry"]="Original recovered 2D patterns in millimetres, converted to metres."
    readme=bpy.data.texts.new("READ ME - simulation limits")
    readme.write("This scene runs sewing springs against the reference last.\n"
        "The initial wrapped shape is only an initialization. Flat patterns set spring rest lengths.\n"
        "Seams are inferred; tongue-root seam is approximate. Read seams.json.\n"
        "Cloth is isotropic and uncalibrated; perforations, seam thickness, glue, and foot compliance are omitted.\n"
        "The footbed fixture holds interior vertices; this is not a free drape test.\n"
        "Fit is NOT approved. Read simulation_report.json for residual errors.\n"
        "The saved snapshot shows the evaluated last frame. Hide it and unhide LIVE to rerun from frame 1.\n"
        "Generated reference geometry: Open Run by Open Footwear, CC BY-SA 4.0.\n")
    # Set a useful viewport on opening the file.
    for area in bpy.context.screen.areas:
        if area.type=="VIEW_3D":
            area.spaces.active.region_3d.view_distance=.55
            area.spaces.active.region_3d.view_location=Vector((0,-.02,.04))
            area.spaces.active.shading.type="MATERIAL"
    bpy.context.view_layer.objects.active=cloth;cloth.select_set(True);last.select_set(False)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"sewing.blend"))
    snapshots=[]
    for frame in range(1,args.frames+1):
        scene.frame_set(frame)
        deps=bpy.context.evaluated_depsgraph_get()
        evaluated=cloth.evaluated_get(deps)
        mesh=evaluated.to_mesh()
        current=np.array([v.co[:] for v in mesh.vertices])
        evaluated.to_mesh_clear()
        if not np.all(np.isfinite(current)):
            raise RuntimeError(f"Nonfinite simulation at frame {frame}")
        if frame==1 and not np.allclose(current,all_v,atol=1e-7):
            raise RuntimeError("Rest shape altered the starting drape; refuse misleading simulation")
        if frame==1 or frame%10==0 or frame==args.frames:
            snapshots.append({"frame":frame,"vertices_mm":(current*1000).tolist()})
            gap=np.linalg.norm(current[np.array(seams)[:,0]]-current[np.array(seams)[:,1]],axis=1)
            print(f"Frame {frame}: seam RMS {np.sqrt(np.mean(gap**2))*1000:.2f} mm",flush=True)
    current_mm=current*1000
    report={"status":"NOT VALIDATED FOR CUTTING", "frames":args.frames,
            "solver_settings":{"quality":settings.quality,"time_scale":settings.time_scale,
                "vertex_mass_kg":settings.mass,"tension":settings.tension_stiffness,
                "compression":settings.compression_stiffness,"shear":settings.shear_stiffness,
                "bending":settings.bending_stiffness,"max_sewing_force":settings.sewing_force_max},
            "material_calibrated":False,"seam_map_verified":False,"tongue_attachment_verified":False,
            "collision_model":"Blender last collision / 0.5 mm cloth margin / self collision OFF for lap seams",
            "registration":data["registration"],"panels":{},"seams":{},
            "limitations":["No material calibration or foot scan", "Perforations omitted from mechanics",
                           "No separate seam allowance mechanics", "Self intersections not prevented", "Fixed footbed fixture",
                           "Initial pre-drape can affect equilibrium; no convergence guarantee"]}
    all_rest=np.array(all_rest)*1000
    for p in data["panels"]:
        lo,hi=ranges[p["name"]];faces=np.array(p["faces"])
        edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)+lo
        restlen=np.linalg.norm(all_rest[edges[:,0]]-all_rest[edges[:,1]],axis=1)
        final_len=np.linalg.norm(current_mm[edges[:,0]]-current_mm[edges[:,1]],axis=1)
        strain=final_len/restlen-1
        report["panels"][p["name"]]={"rms_edge_strain_percent":float(np.sqrt(np.mean(strain**2))*100),
            "p95_abs_edge_strain_percent":float(np.percentile(abs(strain),95)*100),
            "max_abs_edge_strain_percent":float(np.max(abs(strain))*100)}
    for name,pairs in seam_indices:
        gap=np.linalg.norm(current_mm[pairs[:,0]]-current_mm[pairs[:,1]],axis=1)
        report["seams"][name]={"rms_gap_mm":float(np.sqrt(np.mean(gap**2))),"max_gap_mm":float(max(gap))}
    (out/"simulation_report.json").write_text(json.dumps(report,indent=2)+"\n")
    (out/"simulation_frames.json").write_text(json.dumps({"snapshots":snapshots,"faces":all_f,"ranges":ranges})+"\n")
    # Persist an evaluated mesh separately: physics caches need not survive reopening.
    snapshot=obj_mesh(f"Sewn result at frame {args.frames} - inspect errors",current.tolist(),all_f)
    for mat in cloth.data.materials:snapshot.data.materials.append(mat)
    for poly,idx in zip(snapshot.data.polygons,face_material):poly.material_index=idx
    cloth.hide_set(True);cloth.hide_render=True
    last.display_type="WIRE";last.hide_render=True
    bpy.ops.object.select_all(action="DESELECT");snapshot.select_set(True)
    bpy.context.view_layer.objects.active=snapshot
    bpy.ops.wm.obj_export(filepath=str(out/"sewn_upper_mm.obj"),export_selected_objects=True,
                          global_scale=1000,forward_axis="Y",up_axis="Z")
    bpy.ops.export_scene.gltf(filepath=str(out/"sewn_upper.glb"),use_selection=True,export_format="GLB")
    sole_path=ROOT/"build/soles/sole_source.stl"
    if sole_path.exists():
        bpy.ops.wm.stl_import(filepath=str(sole_path),global_scale=.001)
        sole=bpy.context.object;sole.name="Printed sole prototype - visual interface reference"
        sole_info=json.loads((sole_path.parent/"sole_report.json").read_text())
        sole.location.z=-sole_info["source_to_print_translation_mm"][2]/1000
        sole.data.materials.append(material("Outsole",(.15,.17,.18)))
        sole["Interface validation"]="Visual reference only; not a cloth collision object"
        bpy.ops.object.select_all(action="DESELECT")
        sole.select_set(True);snapshot.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(out/"shoe_prototype.glb"),use_selection=True,export_format="GLB")
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"sewing.blend"))
    print("Saved sewing.blend and simulation_report.json",flush=True)


if __name__=="__main__":main()
