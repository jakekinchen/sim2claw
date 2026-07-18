# Executor Session 001 - groot n17 chess local foundation

**Date:** 2026-07-18

## Slice

Fresh dynamic chess task, evaluator, expert controller, and GR00T dataset export.

## Files Changed

Task/modality configs, square geometry helper, `groot_chess.py`, CLI routes,
PyArrow pin, tests, workflow scaffold, and decision/run documentation.

## Tests / Validation

- `uv run pytest -q`: 15 passed.
- All 24 training and 4 held-out expert episodes passed the frozen gates.
- Held-out commands cover rook a8 to c6 and king e8 to e6, neither of which is
  a training case.

## Reachability

Verified upright released placements with 1.1--13.7 mm final planar error in
the accepted sweep. Rejected full-board trajectories that displaced a queen by
0.888 m, then declared a sparse two-piece curriculum rather than hiding it.

## Evidence

The reward remains diagnostic only. The consequence evaluator checks lift,
target error, height, uprightness, settling speed, gripper clearance, distractor
displacement, final contact, action ownership, and assistance.

## Step-9 Flags For Reviewer

N1.7 is Early Access; local format validity is not NVIDIA-loader proof. Sparse
occupancy is a first curriculum rung and cannot be described as full-board
chess manipulation.

## Next Suggested Slice

Finish dataset encoding, run the exact pinned NVIDIA loader on Brev, and only
then start a short post-training smoke checkpoint.
