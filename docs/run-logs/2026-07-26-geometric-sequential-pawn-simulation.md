# Geometric Sequential Pawn Simulation

## Outcome

One persistent canonical MuJoCo scene completed two geometric pawn
manipulations in sequence:

1. `tan_pawn_c8`: strict pick-and-place from `c8` to `a6`.
2. Collision-free return to the canonical open-jaw reset.
3. `tan_pawn_e8`: strict grasp, lift, return to `e8`, release, and clear.

The sequence used `1,184 x 6` little-endian float32 absolute joint targets at
20 Hz with ten 5 ms MuJoCo steps per action. No action row was clipped, no
wrong pawn was contacted, and the second command reproduced an exact final
MuJoCo integration state on an independent replay.

This is simulation geometric-command evidence. It is not learned-policy
evidence and has no physical authority.

## Frozen action arrays

Ignored run artifacts:

- receipt:
  `runs/geometric-pawn-sequence/20260726-c8-a6-then-e8-return-v4/sequence_receipt.json`
- combined array:
  `runs/geometric-pawn-sequence/20260726-c8-a6-then-e8-return-v4/combined_actions_float32.npy`

Raw C-order float32 SHA-256 identities:

| Segment | Shape | SHA-256 |
| --- | ---: | --- |
| `c8 -> a6` | `562 x 6` | `92150231e76270ccf27faddc5b9181105c556d4d0812a6e5daf200a388a75d64` |
| interstage reset | `200 x 6` | `8212cdcb817c9de9bab035117552fe8a9e504873784ff46f7078fa1b6c20d059` |
| `e8` grasp-return | `422 x 6` | `929021b7cfe963a05cd8fc50faf4b9c157186980f81145e01d3c37ad6cb23423` |
| combined sequence | `1184 x 6` | `2eb7486b370c04a6a9d4516d8e6092369a129e3d74e2d2c6b3ac5779fa82d38e` |

Joint order is:

`shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper`.

## Evaluator consequences

### Stage 1: `tan_pawn_c8 -> a6`

- separately owned CPU/fp32 pawn evaluator: strict pass
- maximum rise: `0.1005661608 m`
- final XY error: `0.0099539779 m`
- final height error: `0.0010107396 m`
- final upright cosine: `0.9999999998`
- final speed: `0.0001675668 m/s`
- gripper clearance: `0.1192284519 m`
- maximum other-pawn displacement: `8.2173e-8 m`
- wrong-pawn contact: false
- final jaw/pawn contact: false
- exact persistent-state replay match: true

### Stage 2: `tan_pawn_e8` grasp-return

The frozen pawn consequence thresholds were reused with the target set to the
pawn's own pre-grasp position. This is therefore a strict
`grasp_lift_return_release` result, not a second pick-and-place result.

- all reused gates: pass
- maximum rise: `0.0939858836 m`
- return XY error: `0.0065916069 m`
- final height error: `1.3612e-7 m`
- final upright cosine: `0.9999999961`
- final speed: `0.0001937878 m/s`
- gripper clearance: `0.1090592325 m`
- maximum other-pawn displacement: `6.9531e-8 m`
- wrong-pawn contact: false
- final jaw/pawn contact: false
- maximum IK residual: `0.0009531572 m`
- clipped rows: `0`
- exact independent replay: true

## Transfer boundary

The passing sequence is not physical-transfer-ready. Its wrist-roll targets
remain from `1.9942` to `2.0135 rad` (`114.26` to `115.37 deg`), while the
observed physical repeated-episode start is approximately `-119.7 deg`.
That raw transition is about `234 deg`, beyond the reviewed `180 deg`
wrist-roll excursion gate.

A transfer-oriented diagnostic subtracted pi from every C8 wrist-roll target
and used the matching `-1.1281 rad` (`-64.63 deg`) reset. It was unclipped and
exactly replayable, but failed the task gates:

- maximum rise: `0.0149589153 m` (requires `>= 0.04 m`)
- final XY error: `0.0871472831 m`
- final height error: `0.0137186148 m`
- final upright cosine: `-0.1356657750`
- raw transformed-action SHA-256:
  `75dbfdaa433e6c9701cd14a475091950216ea87c2f75987b4c099ee4d09b8239`

The wrist mismatch must be solved geometrically in simulation before any
physical pawn command is considered.

## Reproduction

```bash
uv run python tools/run_geometric_pawn_sequence.py \
  --base-episode runs/geometric-pawn-sequence/20260726-c8-a6-canonical-v2 \
  --output runs/geometric-pawn-sequence/20260726-c8-a6-then-e8-return-v4
```
