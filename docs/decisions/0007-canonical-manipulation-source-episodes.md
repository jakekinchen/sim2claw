# Decision 0007: Canonical manipulation source episodes

Status: implemented; one scene-v2 source episode independently admitted; no
trained checkpoint or learned-policy success claimed

Date: 2026-07-18 America/Chicago

## Decision

Raw manipulation collection is upstream of ACT and GR00T. New recordings use
`sim2claw.manipulation_source_episode.v1` under ignored storage:

```text
datasets/manipulation_source_recordings/<label>__<recording-id>/
  samples.jsonl
  rgb/top/*.png
  rgb/wrist/*.png
  initial_evaluator_privileged_state.json
  evaluator_privileged_state.jsonl
  overhead_c922.mp4
  recording_receipt.json
```

The canonical row carries synchronized top and wrist RGB references, language,
robot joint/proprioceptive and end-effector state, selected-piece and continuous
target poses, absolute joint targets, contacts and simulator events, action
ownership, assistance/intervention markers, and exact lineage. Full MuJoCo
integration state is stored out of line and is forbidden from both policy
adapters.

ACT and GR00T receive separate derived adapters. The ACT adapter exposes robot
and structured-goal state plus action targets; language and RGB remain metadata
for that state-policy contract. The GR00T adapter exposes top/wrist RGB,
language, proprioception, and action targets. Neither adapter can consume a raw
episode without a separately owned, hash-bound strict-success verdict.

## Current workcell identity

This source contract is new evidence for the operator-updated pawn workcell:

- scene: `operator_updated_chess_workcell_v2`;
- board pose: `board_robotward_72mm_20260718_v2`;
- board center in the table frame: `(0.040, -0.093) m`;
- change from the prior registration: `+0.072 m` along table-frame `+y`;
- layout: `two_sided_sparse_pawns_rows_1_2_7_8_v1`, sixteen active pawns.

An independent zero-offset IK census on this moved geometry rejects the older
ACT metadata topology as a new-data source: brown A2–H1 neck targets have
left-arm residuals of 101–184 mm and are not reachable. Tan A8–H7 targets have
0.0–1.4 mm residuals and empty A5–F5 plus A6–H6 are the reachable destination
band; G5 and H5 remain excluded because their residuals are 3.6 mm and 32.6 mm.
The canonical source split therefore uses tan A8, B7, C8, D7, E8, F7 for
training and G8, H7 as zero-row held-outs. This does not mutate the frozen ACT
contract; it prevents that old metadata choice from contaminating scene-v2
collection.

Frozen rook/king tasks continue to resolve
`photo_aligned_chess_workcell_v1` at their historical board center. This
decision does not relabel their receipts or grant those checkpoints pawn
authority.

## Executor compatibility and admission

Recorded simulation actions are rounded to float32 before both execution and
serialization. The evaluator restores the separately recorded initial
`mjSTATE_INTEGRATION`, executes every row at exactly 20 Hz with ten 0.005-second
MuJoCo steps per sample, and requires exact state equality with every recorded
post-action integration state.

The pawn evaluator protects all fifteen non-target pawns and checks selected
identity, wrong-piece jaw contact, ejection, lift, final XY/height/upright/speed,
gripper clearance, final jaw contact, action count, ownership, assistance, and
exact replay. Operator outcome labels are metadata only.

- A strict full-episode success may enter ordinary imitation data.
- Raw failed actions remain counterexample and evaluation evidence and
  contribute zero behavior-cloning rows.
- A correction may enter only as an expert/teleoperator suffix from the exact
  pre-failure integration state after independent full-prefix-plus-suffix
  replay passes the same evaluator. The failed prefix remains provenance only.
- Held-out pawn identities contribute zero training rows.

## Evidence boundary

The first independently admitted source is a deterministic geometric-expert
episode for `tan_pawn_c8` to `c6`. It uses the mechanism
`air_recenter_partial_release_vertical_extract_v1`: re-center while airborne,
lower under closed-jaw control, partially release in place, extract vertically,
and fully open only after gripper clearance. This avoids sweeping the adjacent
`tan_pawn_d7` during jaw opening.

The episode contains 562 float32 actions executed at 20 Hz with ten MuJoCo
physics steps per action. The separate CPU/fp32 replay evaluator reproduced
every saved integration state exactly and passed all consequence gates. This
admits the source rows to the ACT and GR00T adapters; it does not establish a
learned-policy success, a held-out success, a checkpoint, or physical
authority. GPU work remains disallowed until a bounded multi-episode dataset,
zero-row held-out receipt, loader proof, and training/evaluation identities are
frozen.
