# OR74 executor session

Date: 2026-08-03

OR74 applied the exact OR73 camera to all `423` fixed development timeline
samples with no refit. It emitted four analytic candidate videos and compared
the known-oriented physical frames at `320×240`.

Pooled mean full-frame similarity is `0.781083`, p10 is `0.767943`,
motion-union mean is `0.757441`, and tolerant-edge F1 is `0.285826`. P10 and
motion-union pass. Mean, every-episode mean, every-phase mean, and edge fail.
Episode means cluster in `0.780240–0.782029`; the weakest phase mean is
`0.770849`. The static camera gain therefore generalizes consistently across
development motion, but it does not reach the full target.

The passing motion-union gate and failing edge gate select static
geometry/occlusion and renderer fidelity for the next diagnostic before any
appearance or timing fit. No camera, appearance, timing, state, or physics
parameter changed. No validation/heldout data, simulator replay, hardware, or
paid compute was used. Pixel similarity, event parity, physics fidelity,
promotion, and transfer remain unproved.

Focused verification: `2 passed`.
