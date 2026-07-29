# Brief 099 — Observable registration OR5 method successor

Decision: NUDGE. Evidence anchor: 95.

## Why v1 remains negative

The frozen v1 evaluator required every fit view to exceed `75 px/rad`.
Sensitivity was monotonic and rank-1, with a mean of `83.149 px/rad`, but its
minimum was `72.087 px/rad`. Preserve the v1 negative and its receipt.

## One bounded successor

Freeze one v2 declaration for the same single gripper-zero-offset family.
Replace the arbitrary every-view magnitude floor with:

- a nonzero lower bound far from numerical noise for every view;
- a separately gated aggregate Jacobian singular value;
- rank one and same-sign response across all views;
- the same zero gripper-excitation rejection for gain;
- the same fit/validation cohorts, parameter bounds, and frozen mechanisms.

This change is permissible only because the sensitivity diagnostic depends on
simulator geometry and joint telemetry, not the annotation pixel values, and
the v3 validation annotation outcomes remain unopened. V2 may not fit the
offset, open validation, or run a dynamic replay.
