# OR76 host-native mesh z-buffer renderer capability

OR76 tests a footage-blind structural renderer seam under the exact OR73
camera. It hash-verifies all manifest-referenced binary STL assets, reverses the
declared MuJoCo compiler mesh preprocessing, composes geom-local and body-world
poses, triangulates analytic primitives, and rasterizes with a per-pixel inverse
depth buffer.

The one-frame capability budget uses a frozen deterministic maximum of `512`
triangles per mesh instance. Source triangle totals and rasterized totals are
both reported, so this cannot be mistaken for mesh-exact output. Analytic
spheres, cylinders, and capsules are also explicitly tessellated at frozen low
resolution. A pass proves asset ingestion and depth-tested occlusion only; it
does not establish MuJoCo raster equivalence or visual fidelity.

The card reads one development state frame and zero physical pixels. It fits no
camera, appearance, timing, state, or physics parameter; creates no video; and
keeps validation and evaluator-heldout roles closed.
