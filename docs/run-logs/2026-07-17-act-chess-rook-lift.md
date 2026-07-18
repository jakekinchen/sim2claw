# ACT Chess-Rook Lift Run Log

Request: start the chessboard simulator and run an ACT episode that grabs a
chess piece.

Repo/path: `/Users/kelly/Developer/sim2claw`

Date: 2026-07-17 America/Chicago

Proof class: learned-policy simulation episode. Physical authority remained
closed.

## Frozen boundary

The repo-native task contract is
`configs/tasks/chess_rook_lift_v1.json`. It binds:

- `black_rook_a8`, the left simulated SO-101, and a 2,020-step horizon;
- eight synthetic training seeds/poses and held-out seed `9101` with zero
  training rows;
- one-observation, 50-action conditional-VAE ACT chunks;
- a separately invoked CPU/fp32 evaluator;
- 40 mm maximum/final lift gates, contact-duration gates, model-owned controls,
  and zero assistance;
- no camera, serial, gateway, network, Brev, or physical authority.

## Runtime and training

Direct runtime pins: Python 3.12, MuJoCo 3.10.0, NumPy 2.5.1, Pillow 12.3.0,
and PyTorch 2.11.0. Training ran locally on Apple MPS; the evaluator ran on CPU
in float32.

```bash
uv run python -m unittest discover -s tests -v
uv run sim2claw act-train
uv run sim2claw act-eval \
  --checkpoint outputs/polycam_chess_table/act/chess_rook_lift_v1/checkpoint.pt
```

The accepted training run used 8 episodes / 16,160 frames / 16,160 action
windows, 2,400 AdamW updates, and a fresh 957,350-parameter model. Its final
loss was `0.0317452289`; training did not promote the checkpoint.

## Evaluator-owned iteration record

| Attempt | Contract SHA-256 | Checkpoint SHA-256 | Result |
| --- | --- | --- | --- |
| 1 | `b8454c83…51278` | `77174c52…32013` | Terminal negative: receding-10, zero contact, zero lift |
| 2 | `4ffbc5b9…33b6` | `0384d90a…fc18` | Terminal negative: 77 consecutive contacts, 6.56 mm maximum lift |
| 3 | `4c3c4f95…518f` | `f0a58e49…4fc` | PASS: held rook above board |

Both failed attempts remain preserved under ignored
`outputs/polycam_chess_table/act/chess_rook_lift_v1/attempt_00{1,2}/` with
their own training/evaluation receipts. The held-out pose and success
thresholds did not change across the revisions.

## Accepted episode

| Measurement | Result | Gate |
| --- | ---: | ---: |
| Maximum rook rise | 0.0948761926 m | at least 0.040 m |
| Final rook rise | 0.0940103038 m | at least 0.040 m |
| Longest jaw-contact run | 1,083 control steps | at least 80 |
| Final 200-step contact fraction | 1.0 | at least 0.6 |
| Model-owned actions | 2,020 / 2,020 | all |
| Assistance frames | 0 | exactly 0 |

Artifact identities:

- task contract SHA-256:
  `4c3c4f95a9a7d72acebaed993091c576baf125f9ed0454a960dfd2d5906c518f`;
- checkpoint SHA-256:
  `f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc`;
- action trace SHA-256:
  `ae05cd5923203ca4e253a3fecb971c4a876e876864a1505dd8b7eacd41f58d58`;
- MP4 SHA-256:
  `a0a2357a5e0ce3498ce68a7c59a9999a58098ac897e0c0f930e3fa15c572b57f`.

## Interpretation

This is accepted evidence for one model-owned ACT simulation episode on a
fixed state/phase task. The progress features and single held-out pose make it
a narrow capability proof. The arm can disturb surrounding simulated pieces,
and no visual policy or collision-avoidance claim is made. Nothing here opens
or proves a physical robot path.
