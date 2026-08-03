# Executor session 188: OR116

- Estimated one shared development footprint and one shared material, then
  froze them before the development render.
- Intersected the frozen pixel rays with the transformed tabletop plane and
  rendered a `248`-triangle capsule shaft plus `100`-triangle terminal sphere
  in the exact OR95 z-buffer. Reprojection error stayed below `1.2e-13 px`.
- Outside-board edge F1 improves by `0.044163` and the object ROI by `0.730876`;
  every development row improves and board-edge delta is exactly zero.
- Full-frame similarity improves only `0.000157` versus the preregistered
  `0.001` minimum. Reject the card, keep validation unopened, and attribute the
  single-material appearance miss next.
