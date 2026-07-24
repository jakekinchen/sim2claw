# Current 100 mm Bounded Physical Replay

Date: 2026-07-23

Proof class: `physical_command_replay_observation_unqualified`

The owner confirmed that the overhead view showed the intended task setup, not
an uncleared workcell, and authorized the follower to be positioned
autonomously. The leader arm was not used. This run is physical motion and
camera evidence, but it is not exact-action, task-success, calibration,
training, promotion, or transfer evidence.

## Selection and positioning

The requested E2-to-E1 endpoint required a two-stage 144-degree relocation and
landed slightly beyond the current MuJoCo joint envelope. The closest eligible
one-session endpoint was recording `20260719T033023Z-fd7005f3` (`b2 to c2`) in
reverse:

- source samples SHA-256:
  `67b77efe4e17083fc8da724fcca228dc43c1c8e203ace7c51d1e2c5e02fdef0b`;
- maximum initial body travel: 85.6264 degrees;
- simulated direct-interpolation contact pairs: zero;
- complete reverse trace envelope: passed.

Attempt 1 stopped before motion when motor ID 2 did not acknowledge the
one-attempt torque-enable write. Attempt 2 moved partially and then stopped
when a duplicate Studio live tab reclaimed the serial port. Both were
preserved separately and torque-off was reverified. The gateway was repaired
to use the Feetech API's existing bounded retry window for enable/disable
writes. Attempt 3 completed at 5 degrees/second with final residuals
`[0.5275, -0.6154, -0.1758, -1.0769, 0.3516, 0.0]` degrees and released
torque.

Positioning receipts:

- failed-before-motion:
  `c6499a318aed48e8d771e39336faca45aede8311849d08f561165ab50a821e81`;
- interrupted competing-serial-owner:
  `391b443276165752b3a9d4e865a07cd8bd0ab14f108f93d017c162ff28243add`;
- completed:
  `adde20513e5da908d33e7caddfd518cd8367b611fee04b2d3efad59da22d28d8`.

## Replay and video

The first capture wrapper rejected the manipulation source before opening the
gateway because its default allowed root was the ACT dataset. It commanded no
motion and is preserved with receipt SHA-256
`d08feb65eda55f3c0543d12ac3eeb462b519080e703c607ce314c243b076a36f`.

The corrected, explicitly root-bound replay completed:

- source rows requested/completed: `566 / 566`;
- commands sent within 0.25-degree exactness: `394 / 566`;
- gateway safety-clamped samples: `175 / 566`;
- replay direction: reverse;
- replay receipt SHA-256:
  `602e8b748140476940ce20b00e4362e20a6405638e969c532ad0c38df064fd8e`;
- camera capture receipt SHA-256:
  `fda49752b4bf261e4c40419bbd477096f55377e1aaa7b29ce65533621bcbce87`;
- C922 video SHA-256:
  `c5ddb94b769787fa7006a83b86263246374085e6de20e81e8fd15cacf973650e`;
- video: 932 frames, 640x480, 30 fps, 31.066667 seconds;
- final follower torque: off.

The sampled start and end frames show no obvious board-state change. No
independent metric task evaluator ran, and the command clamping prevents an
exact-action claim. The strict task score therefore remains `0 / 11`.

## Verification

Focused gateway, replay, current-measurement, and Studio-live tests pass:
`43 passed`. All 11 frozen S2 artifacts remain hash-identical, with one
campaign event, four anchor replays, and zero measurement trials. The
preregistered five empty-gripper cycles,
synchronized force/deformation/angle/current measurement, metric object
registration, and evaluator-owned task consequence remain required before a
score-changing calibration claim.
