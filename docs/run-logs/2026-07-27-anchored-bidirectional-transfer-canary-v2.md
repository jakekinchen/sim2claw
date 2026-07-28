# Anchored bidirectional transfer canary v2

## Outcome

One fresh, preregistered shoulder-pan canary passed both frozen diagnostic
directions:

- prebound simulation to physical execution;
- physical encoder trace to exact simulator replay.

The separately owned evaluator returned
`prospective_diagnostic_bounds_satisfied_no_promotion`. No parameter was fitted
after motion, no action was clipped or assisted, and no task or full-parity
claim is made.

## Terminal-negative predecessor

The first current-pose attempt completed all 37 exact commands and all camera
captures, but stopped terminal-negative because the last encoder sample was
`0.7032967 deg` from the normalized pan anchor. The measured response lag was
about `0.4–0.5 s`, while that packet exposed only `0.35 s` of return time.

No result was repaired. V2 was separately frozen around the new physical
anchor with a fixed one-second final hold.

## Frozen v2 identity

Ignored campaign directory:

`runs/anchored-transfer-canary/fresh-current-pose-v2`

- normalized anchor pan: `-8.0 deg`;
- action shape: `57 x 6`;
- encoding: little-endian float64, C order;
- action SHA-256:
  `11bdce9bb3db55c446b35103f9ddb71aa45677196b8122edbf928ce3e59e90dd`;
- sealed packet file SHA-256:
  `f43ee003c5aac32e7d33fcc85d483edb3f6adecb15579148f35bf589e259648e`;
- candidate-config canonical SHA-256:
  `fbf451821e96c9f236b89feb076b964fd81f52416028f93e627118e296697368`;
- evaluation-contract SHA-256:
  `1f102c20f1e8142275c0cdce6ba2fb3393c3c80d5d7062b6615f3ce96faf636b`.

Rows 0–36 reproduce the reviewed `+-1 deg` shoulder-pan waveform relative to
the current anchor. Rows 37–56 are an unconditional one-second anchor hold.
The maximum commanded pan slew is `2.5 deg/s`; every other channel remains at
the mixed-unit anchor. The final five encoder samples, not merely the final
sample, were required to remain within `0.5 deg` on every joint.

Independent decisions:

- normalization:
  `safe-canary-audit-20260727-fresh-current-pose-v2-normalization-v1`;
- canary:
  `safe-canary-audit-20260727-fresh-current-pose-v2-settled-pan-canary-v1`.

## Physical execution

The single-use execution completed:

- exact healthy gateway samples: `57/57`;
- requested bytes equal gateway-sent bytes: true;
- rate limiting, clipping, stalls, and assistance: none;
- observed pan excursion: `0.7032967 deg`;
- final actual pan: `-8.3516484 deg`;
- final five samples within return tolerance: true.

All observation intervals enclosed the action:

| Camera | Frames | Mode |
| --- | ---: | --- |
| C922 overhead | 144 | 640 x 480 at 30 fps |
| D405 wrist | 24 | 424 x 240 at 5 fps |
| Pi IMX708 | 230 | 1536 x 864 at 30 fps |

The cameras are not exposure-synchronized. The Pi receipt is host-bounded and
does not establish intrinsics, extrinsics, or metric registration.

## Bidirectional evaluator

Both the prebound sim-to-real and post-execution real-to-sim lanes passed the
same frozen bounds. Selected post-execution metrics:

| Metric | Result |
| --- | ---: |
| Physical pan peak-to-peak | `1.0549451 deg` |
| Simulated pan peak-to-peak | `2.0301017 deg` |
| Pan RMSE | `0.3354721 deg` |
| Pan maximum absolute error | `0.7142274 deg` |
| Pan final error | `0.3516471 deg` |
| Largest non-pan maximum absolute error | `0.0545867 deg` |

Replay receipt:

`runs/anchored-transfer-canary/fresh-current-pose-v2/bidirectional-replay-v1/replay_receipt.json`

Its SHA-256 is
`632b5cf579eaad321db2dd974ea1f772f2b7a983f7670fab95e81e781fd14c21`.

## Stop state and proof boundary

A fresh follower-only read after the replay reported torque off, no device
configuration rewrite, and pose
`[-8.3516484,-106.4615385,98.4175824,-100.1758242,-126.3736264,1.6627078]`
in physical mixed units.

This is a tangible prospective, action-frozen bidirectional transfer
diagnostic. It does not approve the joint transform, camera registration,
evaluator, policy, C8-to-A6 task, physical task success, or full digital-twin
parity. No broader physical command inherits authority from this receipt.
