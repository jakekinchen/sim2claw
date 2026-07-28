# Session 037 — D1→D2 elbow-sag recovery

Date: 2026-07-27
Branch: `codex/geometric-microtransfer-20260727`

## Work completed

- Preserved camera-pose setup v1 and wrist-dominant setup v2 unchanged.
- Read a fresh configuration-free torque-off anchor:
  `[-6.857143, -89.582418, 104.483516, -40.835165, -101.054945, 1.662708]`.
- Reused the reviewed staged follower gateway, motion-tricam recorder, exact
  float64 action contract, CPU/fp64 MuJoCo preview, and guaranteed torque-off
  close.
- Rejected three candidate corridors offline before packet creation. None
  opened a camera or gateway or commanded motion.
- Added one recovery-only source-contact admission bound to the prior
  motion-free Pi view of the contact-free high arm. It admits only robot
  self-contact pairs present at the out-of-calibration model source, forbids
  new pairs or worse penetration, and requires all pairs to clear.
- Froze and independently reviewed one 721-row route. Its only setup clamp was
  elbow `104.483516→102.109890°`; the frozen action moved elbow monotonically
  to `90.614424°`, then held elbow while moving the other five joints.

## Frozen evidence

- Packet SHA-256:
  `98da488eb69a8be9421d76a722d92a5990801c64879a08d7aaa18fc2d8dc0d79`
- Review SHA-256:
  `0aa3d003c94115c9624e797f7758ff3b209fb3012ba98759d239d6b918c8e0ad`
- Action SHA-256:
  `f604504b396c98f8e79365ca8026b13710a26ba67ad35766fbc04a34b205e043`
- Maximum frozen slew: `6.573871°/s`
- CPU/fp64 preview: no new pair, no worse-than-source penetration, no
  external contact, and no final contact pair.

## Physical result

The one authorized recovery attempt stopped safely after 399/721 motion
samples. Requested and gateway-sent bytes were identical for every persisted
sample; no persisted sample was rate limited, clamped, stalled, assisted, or
intervened on.

The last persisted row was sample 398 at `9.975 s`. Elbow was requested at
`90.614424°`, observed at `93.934066°`, and had accumulated 40 no-progress
samples / `0.975 s`. The next planned sample (399 at `10.000 s`) crossed the
gateway's one-second stall-warning boundary and was rejected by the executor.
Because the rejecting gateway sample is not persisted, its requested action
is known from the frozen packet but its returned observed array is not
claimed.

C922, native D405 RGB, and Pi all started before the setup clamp, enclosed the
motion, and closed cleanly:

- C922: 345 callback frames, zero Apple drops, zero writer backpressure.
- D405 RGB: 58 callback frames, zero Apple drops, zero writer backpressure,
  `metric_depth=false`.
- Pi IMX708: 740 frames.

Visual review shows the arm stayed high and made no pawn, board, or table
contact.

## Closeout

The execution receipt reports torque off. A separate fresh configuration-free
postflight confirmed torque off and no camera/gateway process owner, but elbow
settled to `103.956044°`, still `1.846154°` above the calibrated exact-gateway
maximum. Recovery therefore did not produce an exact-gateway-consumable
anchor.

Slice B task action was not frozen or attempted. Slice C remains forbidden.
Twin fidelity remains `0/6`; task score remains `0/11`.

## Evidence paths

- `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/packet.json`
- `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/review.json`
- `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/stage-1/execution_receipt.json`
- `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/postflight_torque_off_receipt.json`

Postflight receipt SHA-256:
`50150d5a590a234a060ec90417dc1abe7d4248118d667bad95290ef9019754e7`.

Accepted proof class:
`physical_recovery_terminal_safe_stop_elbow_stall_no_task_or_transfer_authority`.
