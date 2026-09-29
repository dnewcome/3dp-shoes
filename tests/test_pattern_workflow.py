"""Geometry and scale checks, plus optional integration checks for generated artifacts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"cad"))
from prepare_patterns import read_vectors, MM_PER_PT, svg_document, parse_path, sample
from assemble_reference import mesh_panel, rigid_2d
from reference_soles import prototype


class GeometryTests(unittest.TestCase):
    def test_pdf_points_and_nested_transforms(self):
        svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 720">
        <defs><path d="M0 0 L700 0 L700 700 Z"/></defs>
        <g transform="translate(10 20)"><path fill="none" stroke="rgb(10%,10%,10%)"
        transform="scale(2)" d="M0 0 L72 0 L72 36 Z"/></g></svg>'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.svg";p.write_text(svg)
            paths=read_vectors(p,(254,254))
        self.assertEqual(len(paths),1)
        x0,x1,y0,y1=paths[0]["path"].bbox()
        self.assertAlmostEqual(x1-x0,50.8,places=8)
        self.assertAlmostEqual(y1-y0,25.4,places=8)
        self.assertAlmostEqual(x0,10*MM_PER_PT,places=8)

    def test_scale_aspect_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.svg";p.write_text('<svg viewBox="0 0 100 100"/>')
            with self.assertRaises(ValueError):read_vectors(p,(100,200))

    def test_concave_mesh_preserves_sewing_landmarks(self):
        outline=np.array([[0,0],[30,0],[30,30],[20,30],[20,10],[10,10],[10,30],[0,30],[0,0]])
        landmarks=np.array([[2,2],[28,2],[5,25]])
        uv,faces,coverage=mesh_panel({"name":"notched","outline":outline},landmarks,4)
        self.assertGreater(coverage,.998)
        for point in landmarks:self.assertLess(np.min(np.linalg.norm(uv-point,axis=1)),1e-6)
        for face in faces:self.assertTrue(Polygon(outline).buffer(1e-6).covers(Polygon(uv[face])))

    def test_rigid_registration_does_not_change_scale(self):
        a=np.array([[0,0],[20,0],[0,40],[5,7]],dtype=float)
        rotation=np.array([[0,-1],[1,0]])
        b=a@rotation+[3,8]
        r,t=rigid_2d(a,b)
        np.testing.assert_allclose(a@r+t,b,atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(r),1)

    def test_sole_boolean_and_mirror_roundtrip(self):
        source=trimesh.creation.box([30,60,5]);source.apply_translation([0,0,5.5])
        m,offset=prototype(source)
        self.assertTrue(m.is_volume)
        self.assertAlmostEqual(m.bounds[0,2],0,places=5)
        mirror=m.copy();mirror.apply_transform(np.diag([-1,1,1,1]))
        self.assertTrue(mirror.is_volume)
        self.assertAlmostEqual(m.volume,mirror.volume,places=5)
        with self.assertRaises(ValueError):prototype(source,base_depth=1,tread_depth=2)


@unittest.skipUnless((ROOT/"build/assembly/simulation_frames.json").exists(),"Generate reference artifacts first")
class GeneratedArtifactTests(unittest.TestCase):
    def test_all_four_vector_patterns_valid_and_mirrored(self):
        data=json.loads((ROOT/"build/patterns/patterns.json").read_text())
        self.assertEqual([p["name"] for p in data["panels"]],["sole","vamp","quarter","tongue"])
        self.assertAlmostEqual(data["source_page_mm"][0],297,places=2)
        for p in data["panels"]:
            path=parse_path(p["outline_d_mm"])
            self.assertTrue(path.isclosed());self.assertTrue(Polygon(sample(path)).is_valid)
            x0,x1,y0,y1=path.bbox()
            self.assertAlmostEqual(x1-x0,p["width_mm"],places=5)
            for side in ["source","mirrored"]:
                f=ROOT/f'build/patterns/{p["id"]}_{p["name"]}_{side}.svg'
                svg=ET.parse(f).getroot()
                self.assertTrue(svg.attrib["width"].endswith("mm"))

    def test_simulation_keeps_initial_geometry_and_finite_frames(self):
        data=json.loads((ROOT/"build/assembly/sewing_input.json").read_text())
        frames=json.loads((ROOT/"build/assembly/simulation_frames.json").read_text())
        expected=np.vstack([p["initial"] for p in data["panels"]])
        np.testing.assert_allclose(frames["snapshots"][0]["vertices_mm"],expected,atol=2e-5)
        for s in frames["snapshots"]:
            self.assertEqual(np.shape(s["vertices_mm"]),expected.shape)
            self.assertTrue(np.isfinite(s["vertices_mm"]).all())
        report=json.loads((ROOT/"build/assembly/simulation_report.json").read_text())
        self.assertFalse(report["material_calibrated"])
        self.assertEqual(report["status"],"NOT VALIDATED FOR CUTTING")

    def test_seams_reference_real_mesh_vertices(self):
        data=json.loads((ROOT/"build/assembly/sewing_input.json").read_text())
        panels={p["name"]:np.array(p["uv"]) for p in data["panels"]}
        for s in data["seams"]:
            self.assertEqual(len(s["a_xy"]),len(s["b_xy"]))
            for side in ["a","b"]:
                for xy in s[side+"_xy"]:
                    self.assertLess(np.min(np.linalg.norm(panels[s[side]]-xy,axis=1)),.01)

    def test_exported_soles_are_watertight_mirrors(self):
        meshes=[trimesh.load(ROOT/f"build/soles/sole_{s}.stl") for s in ["source","mirrored"]]
        for m in meshes:self.assertTrue(m.is_volume);self.assertEqual(len(m.split()),1)
        np.testing.assert_allclose(meshes[0].extents,meshes[1].extents,atol=1e-5)
        self.assertAlmostEqual(meshes[0].volume,meshes[1].volume,places=3)


if __name__=="__main__":unittest.main()
