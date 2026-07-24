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

## C2-to-C1 dual-camera follow-up

The owner requested the canonical SAIL-bound recording
`20260719T031324Z-bf91502b` in the forward `c2 to c1` direction, with the D405
wrist stream read alongside the C922. Its source samples SHA-256 is
`b93fed706dd205197e9e068aec62d8fe552b822be150218dff5601a1a5eec183`.
The live follower pose was already inside the unchanged start envelope, so no
separate alignment move was needed.

Three unchanged robot replays completed and released torque. The first two are
excluded as dual-camera evidence:

- attempt 1 replay receipt
  `b700dc674d080dfa408b5bfc5e7050462c52102c8e7a89eadee81e3fc7ab0f70`;
  its D405 MP4 lacked a `moov` index;
- attempt 2 replay receipt
  `374b4a505a8d0c51ed671640e3c53c2870f290956f773827cc23dc98c8033f7c`;
  the nominally playable wrist file contained only 80 decoded frames through
  5.267 seconds.

A camera-only endurance test passed, but the D405 at 15 fps dropped under
SO-101 traffic. A separate torque-off stress test used 631 gateway reads at
20 Hz and established that the D405's supported 424x240-at-5-fps mode
sustains 173 frames through 34.4 seconds while the C922 records concurrently.
The final physical replay used that frozen capture mode:

- replay receipt SHA-256:
  `df593d3d07db928179d7c4ec18d85ecfccb2c8942030648ef83b36d9c0dcc59f`;
- dual-camera receipt SHA-256:
  `3fafb113a7b89e0b80640b9c7b4cc2016db16ecafcb9f46cba79a79a1330499f`;
- source rows completed: `527 / 527`;
- commands within 0.25 degrees: `501 / 527`;
- safety-clamped samples: `70 / 527`;
- C922: 1,049 frames through 34.966667 seconds, SHA-256
  `1643520f5e53ff4694df2cd3ffe102b9f947eb9742678a3e0f2d2f74ba0ececc`;
- D405: 175 frames through 34.8 seconds, SHA-256
  `adbacc699b073f2f9142b9dc7497ce889c3a5c4bdf5433d548691dfe2352e711`;
- follower torque after replay: off.

The overhead start/end comparison has only 64 of 307,200 pixels above a
20-level luma difference and no piece-sized component. The wrist view shows
the jaws centering around the pawn but not carrying it away. During the
critical approach/closure window, requested-to-sent clamp error stayed at or
below 1.758 degrees, while requested-to-actual body tracking error reached
7.824 degrees and the shoulder/elbow/wrist chain commonly lagged by 5-8
degrees. This makes approach timing plus grasp retention the leading
mechanism, but not a resolved one: current telemetry was disabled and the
wrist stream has neither metric depth nor admitted camera-to-gripper
extrinsics. The physical task score remains `0 / 11`.

## Verification

Focused gateway, replay, current-measurement, and Studio-live tests pass:
`43 passed`. All 11 frozen S2 artifacts remain hash-identical, with one
campaign event, four anchor replays, and zero measurement trials. The
preregistered five empty-gripper cycles,
synchronized force/deformation/angle/current measurement, metric object
registration, and evaluator-owned task consequence remain required before a
score-changing calibration claim.
