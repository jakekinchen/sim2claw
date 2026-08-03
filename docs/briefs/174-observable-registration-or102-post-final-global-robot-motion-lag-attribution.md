# OR102 — post-final global robot-motion lag attribution

Fit one integer observation lag to outside-board motion-energy curves on positions `1-7`, then score that exact lag on positions `8-11`. Lags are limited to `-10..10` frames at `5 Hz`; one value applies globally. Require development correlation gain `0.05` and validation gain `0.03` over zero lag. No per-episode lag, interpolation, time warp, rendering, replay, action/state mutation, hardware, paid compute, or promotion. This is post-final timing diagnosis, not untouched validation or kinematic/physics proof.
