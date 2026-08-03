# OR55 — Evaluator-owned temporal pixel-similarity baseline

Decision: `REDIRECT`

Evidence anchor: `100`

The owner replaced the pending crown-tracker continuation with a bounded goal:
reach `80–90%` temporal pixel similarity between the retained physical episode
and an action-identical simulator rendering within eight hours. Freeze the
evaluator before changing any renderer or simulator parameter.

## Required outcome

Score the immutable OR26 physical and simulator videos over all source-available
frames. Emit per-frame, per-phase, board-region, motion-union, temporal-change,
SSIM, and tolerant-edge diagnostics. The primary score and gates come from the
new goal-loop prompt and cannot be revised after the baseline is observed.

## Frozen constraints

- Bind OR26 receipt, closeout, physical video, simulator video, and motion
  curves by SHA-256.
- Require 531 decoded frames and exactly 516 source-available frames.
- Use no simulator rerun, frame substitution, geometric registration, color
  fit, candidate selection, parameter change, hardware, or held-out access.
- The OR26 board display homography is already baked into the simulator video;
  no additional warp is allowed.
- Missing physical frames are excluded, never filled.

## Terminal rule

Record a passing baseline only if every frozen target gate already passes.
Otherwise report the exact residual by phase and channel and nominate the
largest non-action appearance mechanism for the next bounded card.
