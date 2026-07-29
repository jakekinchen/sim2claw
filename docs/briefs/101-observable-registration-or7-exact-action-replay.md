# Brief 101 — Observable registration OR7 exact-action replay

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Run exactly one CPU/fp64 successor replay of the immutable C6 action and plant
trace with the OR6 task-bounded gripper zero-offset candidate.

## Acceptance

- freeze a new contract and implementation before the run;
- require exact C6 requested and gateway-sent hashes, timestamps, row order,
  identified-applied trace, initialization, current workcell, evaluator, and
  post-action settle;
- require the candidate diff to contain only
  `gripper_zero_offset_rad: -0.17453 -> 0.0494823931`;
- preserve current MuJoCo contact, object, joint-plant, and collision settings;
- permit no clipping, smoothing, action offset, retiming, IK, observed state,
  grasp/release marker, latch, endpoint, support projection, or camera update;
- emit a 531-row trace and selected-jaw contact pairs/counts;
- report first selected-jaw contact, first pawn motion above `1 mm`, maximum
  planar displacement, final center error, tilt, exclusions, and all frozen
  task gates;
- compare every advancement metric to immutable C6;
- never rewrite or rerun the C6 output.

## Stop

The OR7 receipt is immutable regardless of sign. A task success requires every
frozen gate. A material advancement may be selected-jaw contact, a later
catastrophic divergence, or better final task consequence, but must not be
relabeled transfer unless the matching outcome gates pass.
