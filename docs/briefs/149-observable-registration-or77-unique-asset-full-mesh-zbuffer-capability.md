# OR77 unique-asset full-mesh z-buffer capability

OR77 is a new card, not a post-hoc OR76 gate edit. It derives `18` unique STL
filenames from the already hash-bound manifest, reads and caches each exactly
once, binds all `36` mesh definitions to that cache, and rasterizes all
`802,680` source mesh triangles under the unchanged OR73 camera and software
depth buffer.

Analytic primitives retain OR76's frozen low-resolution tessellation. Thus a
pass proves complete source-mesh ingestion and clean unique-asset resource
accounting, but not complete scene-surface exactness, MuJoCo raster equivalence,
or visual fidelity.

The card uses one development state frame and no physical pixels. It performs
no fit, emits no video, and keeps validation and evaluator-heldout roles closed.
