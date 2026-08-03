# OR106 — Post-final two-class robot material palette calibration

OR105 proves that the renderer collapsed upstream structural and servo material
classes to a single neutral gray. OR106 tests whether restoring only that class
distinction materially improves retained-video similarity.

The frozen family is the Cartesian product of four shared structural grayscale
albedos and four shared servo grayscale albedos. One pair applies to every mesh,
frame, episode, and both robots. The identity gray/gray pair is included and
must reproduce OR95 sampled metrics exactly. Geometry, camera, response, replay
actions/state, dynamics, timing, and contact remain fixed.

Selection uses three deterministic samples in each of seven development
episodes. Development requires a mean full-frame linear-similarity gain of
`0.004` and at least `14/21` samples gaining `0.002`; regional edge regressions
are bounded. Only then is the selected pair evaluated once, without refit, on
three samples in each of four already-open validation episodes.

This is retrospective renderer material calibration. It cannot establish an
untouched-cohort same-video claim, physics or kinematic fidelity, transfer, or
simulator promotion. Pixel warp/compositing, projected footage textures,
per-frame colors, replay, hardware, and paid compute are prohibited.
