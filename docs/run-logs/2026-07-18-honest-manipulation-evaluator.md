# Honest Manipulation Evaluator Run Log

Request: the v1 ACT teacher and evaluator let a destructive trajectory count as
success. Make success honest by measuring collateral damage, then re-score the
existing checkpoints.

Repo/path: `sim2claw` (this checkout)

Date: 2026-07-18

Proof class: simulation honest-manipulation evaluation. Physical authority
remained closed. No camera, serial, gateway, network, or robot path was opened.

## Problem

The frozen v1 evaluator (`configs/tasks/chess_rook_lift_v1.json`,
`src/sim2claw/act_evaluator.py`) scores a rook lift from four families of
signal only: target lift, jaw–target contact duration, model-owned actions, and
zero assistance. It never measures what the rest of the arm does to the rest of
the board. A policy that lifts `black_rook_a8` while flinging `black_queen_d8`
off the table is scored a clean success.

Replaying the saved action traces through the simulator and measuring every
free-joint piece confirms this on the local checkpoints. Every checkpoint that
v1 scores as a success disturbs three to five non-target pieces past 6 mm:

| Checkpoint | v1 | worst non-target | rook tilt (end) |
|---|---|---|---|
| `seed20260717_upd8000` | pass | `black_queen_d8` 1209 mm | 26° |
| `seed7_upd8000` | pass | `black_bishop_c8` 288 mm | 27° |
| `seed99_upd8000` | pass | `black_bishop_c8` 316 mm | 27° |
| `seed55_upd8000` | pass | `black_queen_d8` 85 mm | 20° |
| frozen 2400 baseline | fail (hold) | `black_queen_d8` 1037 mm | 96° |

The eight synthetic training experts are the source: each moves three to five
non-target pieces past 6 mm, worst-case 52 mm to 1.25 m. ACT is faithfully
imitating a destructive teacher.

## What this change adds

A new task contract and evaluator that leave v1 frozen and untouched:

- `configs/tasks/chess_manipulation_v2.json` — derived from v1 (same scene,
  episode, observation, action, and ACT blocks), adding collateral and grasp
  gates to the evaluator block:
  - `maximum_nontarget_displacement_m` = 0.006
  - `nontarget_ejection_displacement_m` = 0.05 (required count: 0)
  - `require_no_nontarget_arm_contact` = true
  - `minimum_target_clearance_m` = 0.04
  - `maximum_target_tilt_deg` = 15.0
  - `maximum_target_settle_speed_mps` = 0.05
  - `require_bilateral_pad_grasp` = true
- `src/sim2claw/manipulation_v2.py` — `evaluate_manipulation(checkpoint)`.

## Method: score the exact accepted trajectory

The evaluator does **not** re-run inference. ACT inference is deterministic (the
CVAE latent is fixed to zero at inference), but these policies are chaotically
sensitive: a ~1e-6 perturbation in the first action chunk compounds through the
contact dynamics and flips a clean 99 mm lift into a toppled 15 mm nudge. To
stay comparable to the frozen scorer, `evaluate_manipulation` calls the frozen
`evaluate_act` as the single source of truth for the trajectory and the v1
gates, then replays that exact recorded action trace to measure:

- per-non-target-piece maximum 3-D displacement from the settled start,
- board ejection of any non-target piece,
- any arm-body contact with any non-target piece,
- target board clearance,
- target final tilt (angle of the piece's local +z from world +z),
- target final settle speed (free-joint linear velocity),
- bilateral grasp (fixed and moving jaw pads both contacting the target).

`success_v2` requires the frozen v1 success **and** every new gate.

## Result

All five local checkpoints fail v2. The four that v1 accepts fail on
`max_nontarget_displacement`, `nontarget_ejections`, `no_nontarget_arm_contact`,
and `target_upright` — i.e. they eject a piece, drag the arm through the board,
and hold the rook tilted. Receipts under
`outputs/polycam_chess_table/manipulation_v2/`.

## Current truth

- The honest evaluator is implemented and reproducible; v1 remains frozen.
- No policy or expert demonstration currently passes v2.
- The collision-aware oracle rebuild (elevated top-down corridor plus an
  orientation-aware grasp so the approach is collision-free *and* the rook is
  lifted upright) is diagnosed but not yet implemented. A position-only elevated
  approach cuts worst-case collateral from ~1.25 m to ~33 mm but drops the
  grasp; orientation-aware grasp IK is the next step.
- No NVIDIA/GR00T lane exists in this checkout; those depend on external Cosmos
  access and are out of scope here.

The dependency order remains: honest evaluator and clean oracle, then accepted
datasets, then ACT/GR00T training, then independent hidden evaluation.
