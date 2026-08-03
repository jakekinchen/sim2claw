# OR71 host-native analytic 3D renderer capability

OR71 tests one narrow seam: can the frozen MuJoCo scene manifest and a single
development-role replay state be converted into a deterministic, nonempty CPU
image without using a GL runtime?

The candidate frame is built only from world body poses in the frozen state
trace and declared geom type, local pose, size, orientation, and RGBA in the
shared scene manifest. Boxes and analytic primitives are projected directly.
Mesh geoms are explicitly approximated by their declared manifest bounds and
counted; this does not establish mesh-exact or MuJoCo-raster-equivalent output.

Physical videos, validation episodes, evaluator-heldout episodes, target color
statistics, and OR63/OR66/OR67 screen-space artifacts remain closed. No camera,
appearance, state, physics, timing, or contact parameter is fit. A pass proves
only that a 3D-scene-derived rendering seam exists and permits a new contract
for development-only shared-camera baseline work.
