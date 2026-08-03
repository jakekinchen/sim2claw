# OR78 static development full-mesh comparison

OR78 asked one narrow question: does replacing analytic mesh bounds and painter ordering with the OR77 full-source-mesh depth renderer improve the four frozen development opening frames under the exact OR73 camera, without fitting anything?

It does. Mean full-frame similarity improves from `0.790402` to `0.810144`, and tolerant-edge F1 improves from `0.276779` to `0.291565`. All four episode similarities are between `0.806377` and `0.812414`. The renderer reads the 18 hash-bound unique STL assets once, binds all 36 mesh definitions, and rasterizes all 802,680 source mesh triangles in each frame.

All 13 preregistered gates pass. The run decoded only frame zero from the four development videos, opened no validation or evaluator-heldout evidence, performed no fit or replay, and used no physical pixels in candidate construction.

This is a static development structural advance, not a temporal, camera-fidelity, physics, generalization, transfer, or simulator-promotion result. Before spending the 423-frame temporal budget, the next card must prove that a compiled rasterizer is byte-equivalent to the accepted Python OR78 frame while materially reducing runtime.
