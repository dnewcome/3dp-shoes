# Shoe patterns project progress

**Updated 2026-09-29**

This note records the two attempts described by the project owner and the current state of the
pattern, sole and sewing work. The key correction is that the recent prototype used OpenRun as
a convenient reference already present in the workspace. The owner has not selected OpenRun
as the shoe to reproduce.

## Attempt 1 — initial traces

The project owner reports that the first attempt was made with Claude. It produced screenshots
and initial traces. The repository contains an early sole outline, outline-tracing code, a
parametric last, raster-extracted panel previews, and experiments that flatten panels from a
last. The available project history does not yet record which of these came from that Claude
session, what was tried there, or which problems were found. This note therefore treats those
files as the starting state without assigning authorship or reconstructing undocumented steps.

The main goal remains the one the owner started with: clean, measured patterns for a pair of
shoes, printable soles that fit those uppers, and an assembled 3D model useful for checking the
construction before cutting fabric.

## Attempt 2 — vector recovery and sewing prototype

The second attempt inspected the existing traces and discovered a separate OpenRun EU 42
reference set in the workspace: an upper-pattern PDF, last, and midsole. OpenRun is an example
design and EU 42 its size label; it was **not** a decision about the owner's intended shoe or
fit. The OpenRun reference and the traced approximately 297 mm sneaker sole are different
designs. Work based on one cannot demonstrate that the other fits.

Using OpenRun as an explicitly provisional data source, this attempt added a repeatable workflow:

- Recover all four pattern pieces from the PDF's vector paths instead of tracing a raster image.
  Preserve the source cut lines, notches, holes and grey markings; write dimensioned source and
  mirrored SVGs, a full-size PDF, and tiled A4 and Letter PDFs. Repair only the approximately
  0.004 mm gap at the vamp outline. No extra seam allowance is added.
- Infer sewing correspondences from the reference hole rows and save their paired coordinates.
  Create triangulated cloth pieces from those same flat outlines, then use Blender sewing
  springs with the flat pieces as the rest shapes, last collision, and a footbed fixture.
- Generate a source and mirrored prototype sole pair from the OpenRun midsole, retaining its
  upper surface and adding a 3 mm base with 1.2 mm diamond tread recesses.
- Assemble a local browser viewer, Blender scene, seam map, dimension report and limitations
  note so the output can be inspected and regenerated.

The interactive model is [build/assembly/viewer.html](../build/assembly/viewer.html); the detailed
measurements and run instructions are in [docs/fabrication.md](fabrication.md). Generated files
are under ignored `build/` and are not committed.

## What the current measurements say

The recovered OpenRun pattern dimensions are axis-aligned cut-piece bounds, not foot
measurements:

| Piece | Width × height |
|---|---:|
| Fabric sole | 140.31 × 312.09 mm |
| Vamp | 162.49 × 236.62 mm |
| Quarter | 235.83 × 123.49 mm |
| Tongue | 130.68 × 87.98 mm |

The inferred side-overlap stitch chains agree in length to within the hole-sampling precision.
The forefoot chain is 496.98 mm on the vamp and 550.54 mm on the fabric sole, a 53.56 mm
difference. The heel chain differs by 25.66 mm. Those gaps could involve gathering or a
misidentified seam; the available source material does not establish which. They need to be
resolved before using valuable fabric.

The Blender result closes the inferred top side seams closely, but the largest final forefoot
sewing-spring gap is 16.38 mm; the approximate tongue join has an 11.02 mm maximum gap. The
95th-percentile absolute edge strain ranges from 43.9% on the fabric sole to 154.0% on the tongue.
These are solver measurements against the flat pattern, not measured stretch limits for a real
fabric. Cloth stiffness is uncalibrated, fabric perforations are omitted from the mechanics,
and self-collision is disabled because the provisional lap seams overlap. The result is useful
for reviewing hypotheses, not for approving fit or construction.

The footbed-to-last alignment is a rigid reflected alignment with 4.77 mm RMS outline error.
The sole STL pair each measures approximately 123.48 × 295.15 × 29.46 mm and reloads as one
watertight body. That checks mesh integrity only. The sole upper surface, upper assembly and
wearer fit have not been physically checked together.

The pattern recovery, landmark-preservation, triangulation, registration and sole-mesh checks
passed nine automated tests during this attempt. Their scope is geometry and file generation,
not shoe fit or sewing quality.

## Decisions and evidence still needed

Before this workflow can deliver the shoe the owner wants, establish which shoe construction the
patterns should reproduce. Then record measurements for both feet: standing length and ball
width, ball girth, instep girth, and heel/ankle requirements. Record the upper fabric and lining,
thickness, stretch in both grain directions, seam method and allowance, and printer build volume
and intended sole material.

With those inputs, choose or make a matching last and outsole, verify the seam map against the
intended construction, explain or revise the forefoot and heel length differences, calibrate the
cloth simulation, and check the sole-to-upper interface. Review the new paper or scrap-fabric
pattern and assembly before cutting the final material. Keep the OpenRun-based artifacts labelled
as a reference experiment unless the owner chooses that design.

## Rebuild the second-attempt artifacts

From the repository root, with the OpenRun reference files installed locally, run:

```bash
python3 cad/prepare_patterns.py
python3 cad/reference_soles.py
python3 cad/assemble_reference.py
blender --background --factory-startup --python cad/sew_blender.py -- --frames 120
python3 cad/review_assembly.py
```

See [fabrication notes](fabrication.md) for output descriptions, scale checks, licence
attribution, and the limits of the simulation. The OpenRun source is by Open Footwear and is
licensed CC BY-SA 4.0; the reference assets are local inputs, not newly authored project assets.
