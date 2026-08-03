# OR71 executor session

Date: 2026-08-03

OR71 rendered one deterministic `320×240` PNG on the host CPU using NumPy and
OpenCV. The frame consumed the frozen shared scene manifest and frame zero of
one development-role state trace. It projected body-state-derived 3D poses and
declared geom local poses, sizes, orientations, and RGBA values. All `485`
visible geoms were accounted and projected; the `36` mesh geoms were explicitly
approximated by their declared manifest bounds.

Every frozen capability gate passed: all bodies/geoms were present, the encoded
PNG repeated byte-identically, non-background coverage was `0.946693`, RGB
standard deviation was `97.542174`, and there were `1,136` unique RGB triplets.

This card read one development state trace and zero physical, validation, or
evaluator-heldout video frames. It performed no camera fit, image comparison,
simulator replay, parameter fit, hardware action, or paid compute. The image is
an analytic 3D diagnostic, not a mesh-exact MuJoCo raster, camera match, pixel
similarity result, physics-fidelity result, promotion, or transfer claim.

Focused verification: `2 passed`.
