# Executor session 178: OR106

- Froze 16 shared structural/servo grayscale pairs and three deterministic
  samples in each of seven development episodes. Geometry, camera, response,
  trace, timing, dynamics, and contact remained fixed.
- Rendered 336 exact full-mesh candidates. The identity gray/gray palette
  reproduced all bound OR95 sampled metrics with maximum absolute error `0.0`.
- Selected structural `1.0`, servo `0.5`. Mean full-frame similarity improved
  `0.837297 -> 0.841802` (`+0.004505`) and `19/21` samples gained at least
  `0.002`.
- Outside-board edge F1 regressed `0.347274 -> 0.313313` (`-0.033961`), beyond
  the frozen `-0.005` bound. The development card therefore failed and no
  validation footage was decoded or rendered.
- All 11 integrity gates passed. No pixel warp/composite, projected texture,
  replay, action/state/dynamics/timing/contact mutation, hardware, or paid
  compute was used.
- This negative shows why the full-frame scalar alone is insufficient: a
  visually washed-out robot improves the scalar while erasing regional edge
  agreement. The next card attributes physical-only operator content.
