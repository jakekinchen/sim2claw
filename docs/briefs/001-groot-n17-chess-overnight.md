# Slice Brief 001 - groot n17 chess overnight

**Date:** 2026-07-18

## Objective

Advance the photo-aligned chess simulator from one phase-conditioned ACT rook
lift to a language-and-RGB-conditioned GR00T N1.7 pick/place candidate on one
bounded Brev worker.

## Product / Project Value

This establishes the intended policy-server architecture and tests whether a
general VLA can respond to named piece/square goals instead of replaying one
fixed state trajectory.

## Acceptance Criteria

- Freeze model/source, embodiment, training cases, held-out cases, evaluator,
  reward non-authority, budget, and teardown before training.
- Export only consequence-passing RGB/language/state/action demonstrations.
- Prove the exact NVIDIA loader and policy server on one A100-80GB worker.
- Run a bounded post-training/evaluation campaign and report pass, partial, or
  negative without promotion overclaim.
- Delete paid compute and prove empty final inventory.

## Expected Files

- `configs/tasks/chess_pick_place_groot_v1.json`
- `configs/groot/sim2claw_so101_config.py`
- `src/sim2claw/groot_chess.py`
- `tests/test_groot_chess.py`
- Brev setup/run scripts, workflow evidence, run receipts, and ignored data.

## Test Plan

Validate contract invariants, board coordinates, two held-out expert cases,
GR00T LeRobot structure, pinned NVIDIA loader, finite policy actions, and every
closed-loop consequence gate.

## Validation Commands

```bash
uv run pytest -q
uv run sim2claw groot-expert-eval --split held_out --episode-index 0
uv run sim2claw groot-expert-eval --split held_out --episode-index 2
brev --no-check-latest ls --json
```

## Evidence To Record

Source/model hashes, dataset receipt, failed counterexamples, CUDA/GPU identity,
training command and checkpoints, action traces, evaluator verdicts, spend, and
post-deletion inventory.

## Reachability / Demo Proof

The local constructive expert must first demonstrate upright released placement
of both the rook and king on their declared squares with the other active piece
remaining within the displacement margin.

## Cross-Doc Impact

Update `GOAL.md`, build plan, dependency decision, autonomous milestones,
session/reviewer/manager logs, and the dated run log.

## Out Of Scope

Full-board robustness, all chess piece geometries, chess legality, physical
camera/serial/motion, calibration promotion, TensorRT production deployment,
and any claim that a synthetic pass transfers to hardware.

## Stop Conditions

Stop and delete the worker at 08:30 CDT, at $50 projected/actual campaign spend,
on unrecoverable model/license/auth failure, or when the bounded campaign has
produced its selected evidence. Never create a second worker automatically.
