# Executor session 170: OR98

- Started from admitted active card `OR98`; agent profile and executor context passed.
- Rendered the initial state of all eleven already-open episodes twice with the exact frozen OR95 scene: the baseline and a renderer-only ablation of legacy `photo_background` and child `antler_mug` body IDs `6-7`.
- The ablation changed no camera, table, board, fiducial, robot, action, state, response, or timing parameter and used no fit, family search, replay, hardware, or paid compute.
- Outside-board edge F1 regressed from `0.353964` to `0.346149`; no episode improved by at least `0.01`. Board edge F1 was unchanged and full-frame linear similarity improved only `0.001947`.
- Wholesale background removal is rejected. The legacy background contains some useful coarse scene edges, so the next card must replace or simplify it with explicit renderer-native white-enclosure geometry rather than erase it or composite pixels.
- This remains a post-final diagnostic with no same-video, kinematic, physics, transfer, or promotion claim.
