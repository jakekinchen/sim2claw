# OR127 renderer-native planar-fixture static comparison

Render OR126's 8x8 procedural fixture as 128 triangles in the exact OR119 shared z-buffer, `0.5 mm` above its conditional support plane. Keep the scene, finite object, camera, workcell transforms, response, and initial states frozen. Compare baseline and candidate on seven development initial frames; open four corroboration frames without refit only if fixture-local edge, fixture-local similarity, and full-frame similarity all improve. No physical-pixel texture or screen-space overlay is permitted.
