# Brief 065 — canonical seeded static calibrated ranges

Decision: CONTINUE. Evidence anchor: 100.

## V1 defect

The official V1 static receipt reported a pass, but every selected action
contained a `-0.046123 rad` model joint margin at the live elbow seed. The
physical seed is inside its calibrated hardware range; the compiler had
loaded the narrower stock MuJoCo range and omitted the explicit model-margin
boolean from its final result.

V1 is invalidated before dynamics. Its actions are evaluator-defect evidence,
not admitted action evidence.

## V2 slice

Repeat the exact V1 seed, family universe, grid, action construction, static
geometry, camera, and gateway gates. Change only model range authority:
convert the already bound calibrated physical body ranges through the bound
physical/model transform and apply them to joint and actuator ranges.

## Acceptance

All V1 gates still pass, and every selected action has a nonnegative model
joint margin. V1 actions are never reused as success evidence.

## Stop

Reject closes before dynamics. Pass authorizes only a separately frozen
direct-target and diagnostic `0.11 s` ZOH consequence replay. Physical
authority remains false.
