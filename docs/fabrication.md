# Pattern and sewing review

This workflow is an EU 42 reference prototype, not a custom-fitted shoe. It uses the locally
downloaded OpenRun pattern PDF, last and midsole. The traced sneaker outsole and older
last-flattening experiments remain separate.

## Rebuild

Install `requirements.txt`, Poppler (`pdfinfo`, `pdftocairo`), and Blender. The sewing scene was
tested with Blender 5.2; Blender is a separate executable, not a Python dependency.

```bash
python3 cad/prepare_patterns.py
python3 cad/reference_soles.py
python3 cad/assemble_reference.py
blender --background --factory-startup --python cad/sew_blender.py -- --frames 120
python3 cad/review_assembly.py
python3 -m unittest discover -s tests -v
```

All Python scripts resolve default paths relative to the repository. `prepare_patterns.py`
converts the PDF into SVG and reads the PDF page dimensions as the scale authority. It retains
original path geometry rather than fitting a smoothing spline through a screenshot. The
microscopic open/self-crossing join in the vamp is repaired only within a 0.01 mm tolerance;
larger defects stop extraction. The source hash and dimensions are recorded in `patterns.json`.
The assembly inference is specific to this EU 42 reference; it is not an automatic size-grading
or arbitrary-pattern sewing tool.

## Pattern outputs

`build/patterns/` contains:

- `P1_sole`, `P2_vamp`, `P3_quarter`, and `P4_tongue`, each as source and mirrored SVGs in mm.
- `patterns_full_size.pdf`, with one piece per custom-size page.
- `patterns_A4.pdf` and `patterns_Letter.pdf`, tiled at actual size with 8 mm overlap.
- `overview.png` and `patterns.json`, for review and machine-readable dimensions.

Black lines retain the source cutting convention, including perforations. Grey lines are
markings, not cuts. The source's construction geometry is retained: **no extra seam allowance,
grain direction, or new stitch line is invented**. Small overlaid source hole paths may be
present in the vector sheet; assembly landmark detection merges centres within 0.4 mm.

Print at 100% / actual size, disable “fit to page”, and measure the 100 mm bar. Assemble tiles
by row and column, aligning duplicated linework in the 8 mm overlap; do not scale pages to
make the edges match. PDFs show the source side. Use the mirrored SVGs for the other foot or
reverse a paper template while keeping fabric face orientation explicit. The sheet's axis-aligned
width and height are cutting-layout dimensions, not foot width and length.

The large `sole` pattern is the **fabric sole piece**, not an STL outline to extrude. Its
perimeter participates in the sewing experiment. Do not silently replace it with the 297 mm
sneaker trace.

## Virtual sewing

`assemble_reference.py` builds meshes from those same flat outlines and finds the 2 mm joining
holes. It checks the expected source topology, triangulation coverage and preservation of seam
landmarks. Small cosmetic perforations are retained in the patterns but omitted from cloth
mechanics. Source-to-last alignment is rigid, with a mirrored candidate tested; there is no
hidden size rescaling.

The inferred correspondence is recorded as explicit paired coordinates in `seams.json` and
drawn in `seam_map.pdf`. Most side seams have matching pitch and chain lengths. The forefoot
chain is about 54 mm shorter than the associated sole chain, and the heel chain about 26 mm
shorter. The original construction may require gathering or a material/process we have not
established. These differences must not be treated as allowable canvas stretch.

The tongue-root attachment is an approximate hypothesis, not a recovered manufacturer seam.
Other joins are inferred from hole ordering and pitch; confirm their intended construction.

`sew_blender.py` creates actual loose-edge sewing springs, last collision,
interior footbed fixtures, and a separate flat rest shape. It verifies that the rest-shape key
does not accidentally replace the starting drape. The solver's uncalibrated numerical settings
are saved in `simulation_report.json`. It is a geometric cloth experiment, not a simulation of
foot comfort, walking, adhesion, seam strength, or the chosen textile's measured mechanics.

Self collision is disabled in this provisional solve: the sewing holes are inside the cut
edges and the lap-seam allowances overlap. An all-vertex self-collision model fights these
overlaps. Layer-aware seam collision remains unresolved, so the result may contain fabric
self-intersections and cannot approve the seam construction.

See Blender's [cloth shape and sewing documentation](https://docs.blender.org/manual/en/2.81/physics/cloth/settings/shape.html)
and [current implementation of separate rest coordinates](https://github.com/blender/blender/blob/main/source/blender/blenkernel/intern/cloth.cc).

Open `build/assembly/viewer.html` directly in a browser. It needs no server or external script.
Its initial-placement mode shows the starting guess; the timeline shows evaluated solver
frames. Strain colours measure differences from the flat piece. Red does not encode a
material-specific failure threshold. The final snapshot can remain wrinkled or have open seams.

In `sewing.blend`, the final evaluated upper is saved as a separate mesh so it survives opening
the file without a cloth cache. To rerun, hide the saved result, unhide the `LIVE` object, return
to frame 1, and play sequentially. The fixture pins part of the sole to its starting position.
The last is shown as wireframe, and the printed sole is a visual interface reference.

`review.md` includes flat seam chain lengths, final seam gaps, edge strain and sampled last
penetration. A vertex penetration check does not prove all triangles are free of intersection.
Passing a numerical threshold would still require material calibration and a physical fitting.

## Printed soles

`reference_soles.py` retains the reference midsole top and adds a flat 3 mm base with 1.2 mm
diamond tread recesses. Both STL exports reload as one watertight positive-volume body. The
source and mirrored versions are roughly **123.5 × 295.2 × 29.5 mm** each. The reference upper
surface is intended for the OpenRun construction; the glue contact with the simulated upper
has not been solved. There are no added perimeter sewing holes in these soles.

STL and OBJ coordinates are millimetres. Blender and glTF coordinates are metres. The small
vertical translation needed to put each STL on Z=0 is recorded in `sole_report.json` and undone
when displaying it beside the reference last. Printer bed fit, flexible material properties,
shrinkage and attachment method still need to be specified. These files are prototypes.

## Measurements needed before final cutting

Record the following without deriving dimensions from a shoe-size label:

| Input | Left foot | Right foot |
|---|---|---|
| Standing foot length, mm | pending | pending |
| Standing width at ball, mm | pending | pending |
| Ball girth, mm | pending | pending |
| Instep girth, mm | pending | pending |
| Heel/ankle fit requirement | pending | pending |

Also specify the upper material, thickness, grain direction, measured stretch in each direction,
lining/insole layers, joining method, seam allowance, and printer build volume. A validated
reference-last fit alone does not establish wearer fit. Confirm seam mapping, resolve the sole
chain mismatch and tongue attachment, calibrate material behaviour, rerun, then make a paper
or scrap-fabric fitting before cutting final material.

The generated geometry derives from **Open Run by Open Footwear, CC BY-SA 4.0**, and remains
under ignored `build/`. Keep that attribution and license with shared derivatives.
