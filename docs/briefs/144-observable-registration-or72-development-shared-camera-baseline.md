# OR72 development-only shared-camera baseline

OR72 measures the untouched OR71 analytic renderer across all four frozen
development episodes before any shared camera, time, or appearance parameter is
tuned. The camera is the scene manifest's suggested camera; time zero is video
frame zero; declared RGBA is used without transformation.

Each complete state-trace duration is sampled at `5 Hz`. The nearest simulator
state is rendered at `320×240`; the corresponding full physical frame is area
resized from `640×480` with no crop or warp. The unchanged OR55 full-frame
linear-pixel, motion-union, phase, and tolerant-edge metrics are reported per
episode and pooled.

Physical pixels are evaluator targets only and cannot enter candidate
construction. Validation and evaluator-heldout roles remain unopened. The card
performs no fit, parameter selection, simulator replay, physics/state change,
hardware action, promotion, or transfer claim. A below-target baseline is the
expected information needed to freeze a bounded shared parameter family.
