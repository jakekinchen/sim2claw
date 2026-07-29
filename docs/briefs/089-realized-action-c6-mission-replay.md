# Brief 089 — Realized-Action C6 Mission Replay

Decision: `CONTINUE`

Evidence anchor: `108`

## Active card

C6 from the realized-action outcome calibration queue.

## Required slice

Freeze and execute exactly one D1→D2 mission replay:

- bind the physical source, exact `531 x 6` gateway-sent float32 tensor, source
  timestamps, C4 effective plant, C5 negative, current workcell, task-plane
  initialization, and evaluator;
- initialize the selected pawn from the frozen initial C922 D1 metric XY and
  current simulator support/upright state;
- initialize the robot once from the source's first measured state;
- generate the robot trajectory only from the exact sent actions through C4;
- run natural current-MuJoCo contact without observed joint states after
  initialization, grasp/release markers, latches, support projections, camera
  updates, endpoint forcing, IK, offsets, clipping, or action repair;
- settle and score once under the unchanged composable task gates.

## Verification gate

- The run is write-once and contract/implementation/model/evaluator hashes are
  committed before execution.
- Source action shape, dtype, row order, and hash are exact.
- Requested, sent, applied, and object traces remain distinct.
- Numerical task success and promotable mission success are reported
  separately because C5 has no validated contact model.
- A pass cannot be promoted through the unvalidated baseline.
- The immutable receipt and tracked closeout exist.

## Handoff

Activate C7 after the one result. Do not rerun or weaken gates.
