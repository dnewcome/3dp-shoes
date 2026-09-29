"""Build a reproducible, explicitly provisional OpenRun sewing experiment.

Uses the recovered 2D pieces as spring rest shapes, not flattened last regions.
The inferred seam map is exported for inspection/editing before production use.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import trimesh
from scipy.spatial import Delaunay, cKDTree
from scipy.interpolate import RBFInterpolator
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import nearest_points
from shapely import union_all
from svgpathtools import parse_path
from prepare_patterns import ROOT, sample


def holes(panel, perimeter_only=True):
    outline = LineString(panel["outline"])
    result = []
    for feature in panel["features"]:
        p = parse_path(feature["d_mm"])
        x0,x1,y0,y1 = p.bbox()
        xy = np.array([(x0+x1)/2, (y0+y1)/2])
        if (feature["kind"] == "cut" and p.isclosed() and
                abs(x1-x0-2) < .03 and abs(y1-y0-2) < .03 and
                (not perimeter_only or outline.distance(Point(xy)) < 5.5) and
                all(np.linalg.norm(xy - q) > .4 for q in result)):
            result.append(xy)
    return np.array(sorted(result, key=lambda xy: outline.project(Point(xy))))


def infer_seams(panels):
    """Source-specific hole topology, checked by counts and measured chain lengths.

    Indices follow the source path order; exported coordinates make hypotheses
    inspectable. This is not an assertion of the manufacturer's assembly method.
    """
    by_name = {p["name"]:p for p in panels}
    for p in panels:
        p["holes"] = holes(p)
    if [len(by_name[n]["holes"]) for n in ["sole","vamp","quarter","tongue"]] != [48,67,51,7]:
        raise ValueError("Source topology differs from audited EU42 reference; map seams explicitly")
    seams = []

    def seam(name, a, ai, b, bi):
        av, bv = by_name[a]["holes"][ai], by_name[b]["holes"][bi]
        if len(av) != len(bv):
            raise ValueError("Unequal stitch counts")
        la, lb = (float(np.linalg.norm(np.diff(x,axis=0),axis=1).sum()) for x in (av,bv))
        seams.append({"name":name,"a":a,"b":b,"a_xy":av.tolist(),"b_xy":bv.tolist(),
            "status":"inferred; inspect before cutting", "length_a_mm":la,"length_b_mm":lb,
            "difference_mm":la-lb,"difference_percent":100*(la-lb)/max(la,lb)})

    seam("forefoot_to_sole", "vamp", list(range(20,59)), "sole", list(range(28,48))+list(range(19)))
    seam("heel_to_sole", "quarter", list(range(20,31)), "sole", list(range(18,29)))
    seam("side_A_lower", "vamp", list(range(59,67)), "quarter", list(range(19,11,-1)))
    seam("side_B_lower", "vamp", list(range(19,11,-1)), "quarter", list(range(31,39)))
    seam("side_A_top", "vamp", list(range(6)), "quarter", list(range(6)))
    seam("side_B_top", "vamp", list(range(6,12)), "quarter", list(range(45,51)))
    # Six inner holes on each overlap flap form a second run, at 6.28 mm pitch.
    v = by_name["vamp"]
    candidates = np.array([p for p in holes(v, False) if np.min(np.linalg.norm(v["holes"]-p,axis=1))>.4])
    for name, start, qi in [("side_A_return",5,list(range(6,12))),
                            ("side_B_return",6,list(range(44,38,-1)))]:
        current = v["holes"][start]
        chain = []
        available = candidates.copy()
        for _ in range(6):
            j = np.argmin(np.linalg.norm(available-current,axis=1))
            current = available[j]; chain.append(current)
            available = np.delete(available,j,axis=0)
        old = len(v["holes"])
        v["holes"] = np.vstack([v["holes"], chain])
        seam(name,"vamp",list(range(old,old+6)),"quarter",qi)
    return seams


def mesh_panel(panel, landmarks, spacing):
    poly = Polygon(panel["outline"]).simplify(.12, preserve_topology=True)
    boundary = np.asarray(poly.exterior.coords[:-1])
    dense = []
    for a,b in zip(boundary,np.roll(boundary,-1,axis=0)):
        n = max(1,int(np.ceil(np.linalg.norm(b-a)/spacing)))
        dense.extend(a+(b-a)*t for t in np.linspace(0,1,n,endpoint=False))
    x0,y0,x1,y1 = poly.bounds
    grid = np.array([(x,y) for x in np.arange(x0+spacing/2,x1,spacing)
                     for y in np.arange(y0+spacing/2,y1,spacing) if poly.contains(Point(x,y))])
    points = np.vstack([dense, grid, landmarks])
    points = np.unique(points.round(7), axis=0)
    f = Delaunay(points).simplices
    f = np.array([t for t in f if poly.buffer(1e-6).covers(Polygon(points[t]))])
    area = sum(Polygon(points[t]).area for t in f)
    coverage = area/poly.area
    if coverage < .998:
        raise ValueError(f'{panel["name"]}: triangulation coverage only {coverage:.3%}')
    used = np.unique(f)
    remap = np.full(len(points),-1); remap[used] = np.arange(len(used))
    points, f = points[used], remap[f]
    dist, idx = cKDTree(points).query(landmarks)
    if np.max(dist) > .01:
        raise ValueError("A sewing landmark was lost during triangulation")
    return points, f, coverage


def rigid_2d(a,b):
    ca,cb = a.mean(0),b.mean(0)
    u,_,vt = np.linalg.svd((a-ca).T @ (b-cb))
    r = u @ vt
    if np.linalg.det(r)<0:
        u[:,-1] *= -1; r = u @ vt
    return r, cb-ca@r


def prepare(panels, seams, last):
    """Initial drape is only a solver starting guess; flat rest metrics are retained."""
    lower = last.submesh([np.where(last.face_normals[:,2]<-.15)[0]], append=True)
    projected = union_all([Polygon(t[:,:2]) for t in lower.triangles
                           if Polygon(t[:,:2]).area>1e-6]).buffer(0)
    if projected.geom_type == "MultiPolygon":
        projected = max(projected.geoms,key=lambda p:p.area)
    projected = Polygon(projected.exterior)
    sole = panels[0]
    marks = [sample(parse_path(f["d_mm"]),2) for f in sole["features"]
             if f["kind"] == "mark" and parse_path(f["d_mm"]).length()>150]
    source = np.vstack(marks)
    border = np.array([projected.exterior.interpolate(t).coords[0]
                       for t in np.arange(0,projected.length,2)])
    fits=[]
    for sign in (1,-1):
        reflection=np.diag([sign,1]); s=source@reflection
        r=np.eye(2); trans=border.mean(0)-s.mean(0)
        for _ in range(80):
            _,idx=cKDTree(border).query(s@r+trans)
            r,trans=rigid_2d(s,border[idx])
        rms=float(np.sqrt(np.mean(cKDTree(border).query(s@r+trans)[0]**2)))
        fits.append((rms,reflection@r,trans,sign))
    rms,r,trans,sign=min(fits,key=lambda fit:fit[0])

    def bottom(xy):
        origins = np.c_[xy, np.full(len(xy),last.bounds[0,2]-10)]
        locations, rays, _ = last.ray.intersects_location(origins,np.tile([0,0,1],(len(xy),1)),multiple_hits=False)
        near = cKDTree(lower.vertices[:,:2]).query(xy)[1]
        z = lower.vertices[near,2].copy()
        z[rays] = locations[:,2]
        return z

    def top(xy):
        origins = np.c_[xy,np.full(len(xy),last.bounds[1,2]+10)]
        locations,rays,_ = last.ray.intersects_location(origins,np.tile([0,0,-1],(len(xy),1)),multiple_hits=False)
        near = cKDTree(last.vertices[:,:2]).query(xy)[1]
        z = last.vertices[near,2].copy(); z[rays] = locations[:,2]
        return z

    # Flat bottom piece starts below the last. Sewing raises its perimeter.
    xy = sole["uv"]@r+trans
    sole["initial"] = np.c_[xy,bottom(xy)-2]
    hole_xy = sole["holes"]@r+trans
    target_xy = []
    for pt in hole_xy:
        target_xy.append(nearest_points(projected.exterior,Point(pt))[0].coords[0])
    target_xy = np.array(target_xy)
    target_z = bottom(target_xy)+10
    sole_targets = np.c_[target_xy,target_z]
    targets = {"sole":sole_targets}
    by_name = {p["name"]:p for p in panels}
    v = by_name["vamp"]
    outer_seam = seams[0]
    anchor_uv = np.array(outer_seam["a_xy"])
    anchor_xyz = sole_targets[list(range(28,48))+list(range(19))]
    # Additional dorsal landmarks prevent harmonic collapse across the last.
    extra_uv=[]; extra_xyz=[]
    for y in np.arange(25,200,15):
        section = Polygon(v["outline"]).intersection(LineString([(120,y),(300,y)]))
        pieces = list(section.geoms) if hasattr(section,"geoms") else [section]
        for line in pieces:
            if line.is_empty or line.length<4: continue
            uv = np.array(line.interpolate(.5,normalized=True).coords[0])
            y3 = y-175
            vert = last.vertices[abs(last.vertices[:,1]-y3)<4]
            if not len(vert): continue
            cx = (vert[:,0].min()+vert[:,0].max())/2
            # Rear split branches sit on the instep sides; front is over the toes.
            xx = cx if len(pieces)==1 else cx+sign*np.sign(uv[0]-215)*25
            q = np.array([[xx,y3]])
            extra_uv.append(uv); extra_xyz.append([xx,y3,top(q)[0]+2])
    warp = RBFInterpolator(np.vstack([anchor_uv,extra_uv]), np.vstack([anchor_xyz,extra_xyz]), smoothing=1)
    v["initial"] = warp(v["uv"])
    targets["vamp"] = warp(v["holes"])
    q = by_name["quarter"]
    au=[]; az=[]
    for seam in seams:
        if seam["a"] == "quarter":
            au.extend(seam["a_xy"])
            ids = cKDTree(sole["holes"]).query(seam["b_xy"])[1]
            az.extend(sole_targets[ids])
        elif seam["b"] == "quarter":
            au.extend(seam["b_xy"])
            az.extend(warp(np.array(seam["a_xy"])))
    # Heel collar landmark; the rest is free to relax.
    au.append([174,339]); az.append([6,110,75])
    au=np.array(au);az=np.array(az)
    au,idx=np.unique(au,axis=0,return_index=True);az=az[idx]
    qw = RBFInterpolator(au,az,smoothing=2)
    q["initial"] = qw(q["uv"])
    tongue=by_name["tongue"]
    # Tongue length runs along source X; rounded right end is provisionally the root.
    u=tongue["uv"]
    txy=np.c_[sign*(u[:,1]-262)*.95, (265-u[:,0])*.95-65]
    tongue["initial"]=np.c_[txy,top(txy)+3]
    # Export explicit approximate tongue-to-vamp stitch coordinates for review.
    th=tongue["holes"]
    tx=np.c_[sign*(th[:,1]-262)*.95,(265-th[:,0])*.95-65]
    tz=np.c_[tx,top(tx)+3]
    ids=cKDTree(v["initial"]).query(tz)[1]
    seams.append({"name":"tongue_root_APPROXIMATE", "a":"tongue", "b":"vamp",
                  "a_xy":th.tolist(),"b_xy":v["uv"][ids].tolist(),
                  "status":"Unverified attachment hypothesis; not matched source holes"})
    # Move initially penetrating vertices outside the last before collision solving.
    for panel in panels:
        pts=panel["initial"]
        close, distance, faces=last.nearest.on_surface(pts)
        inside=last.contains(pts)
        move=inside|(distance<1.2)
        pts[move]=close[move]+last.face_normals[faces[move]]*1.5
    sole["pin"] = np.where(np.array([projected.buffer(-15).contains(Point(pt)) for pt in xy]))[0][::8].tolist()
    return {"footbed_registration_rms_mm":rms,"scale_factor":1.0,
            "source_pattern_xy_reflected":sign==-1,
            "note":"Rigid registration only. Initial drape is a hypothesis, not a fitted result."}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patterns",type=Path,default=ROOT/"build/patterns/patterns.json")
    ap.add_argument("--output",type=Path,default=ROOT/"build/assembly")
    ap.add_argument("--spacing",type=float,default=6)
    args=ap.parse_args()
    if args.spacing<=0: ap.error("spacing must be positive")
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(args.patterns.read_text()); panels=manifest["panels"]
    for p in panels: p["outline"]=sample(parse_path(p["outline_d_mm"]),1)
    seams=infer_seams(panels)
    for p in panels:
        lm=[p["holes"]]
        for seam in seams:
            if seam["a"]==p["name"]:lm.append(seam["a_xy"])
            if seam["b"]==p["name"]:lm.append(seam["b_xy"])
        p["uv"],p["faces"],p["coverage"]=mesh_panel(p,np.vstack(lm),args.spacing)
        print(p["name"],len(p["uv"]),"vertices",f'coverage {p["coverage"]:.4%}',flush=True)
    last=trimesh.load(ROOT/"assets/openrun/OpenRun_42_LAST.stl")
    last=last.simplify_quadric_decimation(face_count=6000)
    last.fix_normals()
    registration=prepare(panels,seams,last)
    payload={"units":"mm","status":"PROVISIONAL; NOT A FIT APPROVAL", "registration":registration,
        "material":"Uncalibrated isotropic cloth; perforations and seam allowances not separately modeled",
        "attribution":manifest["attribution"],"seams":seams,"panels":[],
        "last":{"vertices":last.vertices.tolist(),"faces":last.faces.tolist()}}
    for p in panels:
        payload["panels"].append({"name":p["name"],"uv":p["uv"].tolist(),
            "faces":p["faces"].tolist(),"initial":p["initial"].tolist(),"pin":p.get("pin",[]),
            "coverage":p["coverage"]})
    (args.output/"sewing_input.json").write_text(json.dumps(payload)+"\n")
    (args.output/"seams.json").write_text(json.dumps(seams,indent=2)+"\n")
    print(json.dumps(registration,indent=2))
    print("Prepared sewing_input.json. Next: blender --background --python cad/sew_blender.py")


if __name__=="__main__": main()
