# Overnight dual-camera simulator calibration

Date: 2026-07-24

Proof status: terminal diagnostic, partial aggregate reduction rejected

Task score: unchanged `0/11`

## Source

- Recording: `20260724T050132Z-02baf745`
- Samples: `911`
- Source samples SHA-256:
  `334ea676f4c2a48a22fd039ef2911946f608fdbfe293cea4383dba88f59da254`
- Exact contiguous float64 action SHA-256:
  `4dcdabd0b8681c4d811884458d3e4bbff523c7435ade38f22570c7fbca61d142`
- C922: `1,625` frames, file SHA-256
  `3072f4dc07acbb98ac324d48843c9fc8c44ddb22ff2c13570cab0e09402bf134`
- D405 browser stream: `270` frames, file SHA-256
  `e6de4b9e6a748ac1994516501c64979253f9c41918681c39cfcb58f6f325b425`

The raw `full_episode / success / C2→C1` label is preserved but is not
measurement admission. Deterministic segmentation found six complete
excursions although the owner intended five.

## Derived empty-gripper diagnostic

- Diagnostic SHA-256:
  `c6791f9434aa8e9d4eb1e48547cebb28cbf29a3f4bd544e19dc239870c5a33a6`
- Receipt file SHA-256:
  `fef884776e1f7cbbfafd11e542874f800234a3ca5f4f0aae2ae58b37c441da93`
- Embedded receipt digest:
  `53f6a9fecea55feb3aaf6895f35f20a841490d5487863239d5a0b72809eab042`
- All six cycles: median lag `0.150000 s`; maximum lag `0.400000 s`.
- Retrospective cycles 2–6: median lag `0.150000 s`, median aligned gripper
  RMSE `1.0217°`, and maximum body motion `5.011°`.
- Simulator replays used: `0`.

Force, deformation, metric depth, camera-to-gripper extrinsics, metric object
pose, and strict task consequence remain unavailable.

## Single action-frozen simulator comparison

Budget: one family, two variants, `2/2` replays, zero retries.

| Metric | Current ranges | Follower endpoint ranges |
| --- | ---: | ---: |
| Aggregate body-joint RMSE | 3.4281° | 2.2801° |
| Shoulder-lift RMSE | 6.2144° | 0.5131° |
| Elbow RMSE | 4.0139° | 4.8839° |
| Wrist-flex RMSE | 1.8005° | 1.0427° |
| Gripper RMSE | 0.101116 rad | 0.101118 rad |

Aggregate body RMSE improved `33.49%`, but elbow regressed `0.8700°` beyond
the frozen `0.25°` ceiling and gripper non-regression failed. Strict task
consequence was unavailable. The evaluator returned
`diagnostic_joint_range_tie_or_loss_no_promotion`.

- Raw comparison SHA-256:
  `cb6a35965a640a7052b023cb15fc3bc8acd03ef9def44bfb9f26a2c4471ca427`
- Evaluation SHA-256:
  `2bf577af5278dc7a5c8a06e10916db0a4eabbef1dcff99236db80339ed6c1802`
- Receipt file SHA-256:
  `4e49fe686e6fdb5417278daf58a0897e3782fbe3942c5e8a3833228b034f4cc8`
- Embedded receipt digest:
  `410000a8c66a581223207027562c551d3199e289307c1f5866cefcb5958c2eb6`

## Offline identifiability audit

The audit used the same hash-bound telemetry with zero simulator replays and
zero physical trials.

- Shoulder lift: `0.0°` command span and no direction changes; range scale and
  offset are not identifiable.
- Elbow: `10.022°` span, below the frozen `15°` minimum; range scale and offset
  are not identifiable.
- Wrist flex: broad span but only one reverse command change; bidirectional
  identification is unavailable.
- Shoulder pan, wrist roll, and gripper have sufficient unloaded,
  bidirectional excitation for diagnostic fits only.
- The common best sample-quantized lag is about `0.15 s` on sufficiently
  excited channels. It is not command-application latency.

Report SHA-256:
`22227ca7373efe18c51d68f750d3f44aa11c668b50a9e76260c2d72981264330`

Receipt file SHA-256:
`2d9cb53787cac06383360fec88029b141a7b581078aa0594c399ff504900c7bb`

Embedded receipt digest:
`2f7b0073a6d052a6db1436e183bb6594d20616f70dae5e0f5a51f9f415a8b719`

## Advisor reconciliation

GPT-5.6 in the Robotics and Sims project correctly prioritized independent
command/application/read/camera timestamps, per-sample availability,
calibration operating envelopes, sensor health, and reset receipts. It is
advice only. Its first answer incorrectly referenced a bootstrap-CI gate that
is not part of this evaluator and recommended a shoulder-only change before
the zero-span result was known. Neither statement was adopted.

## Decision

No simulator parameter, task score, posterior, policy, training set, or
physical authority changed. The next packet must provide independent timing,
reset/calibration health, and bidirectional shoulder-lift/elbow excitation
before another range hypothesis. Contact/load and strict task consequence
remain separately required.
