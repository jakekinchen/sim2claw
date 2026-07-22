# Pawn workcell fit V3: board-pitch trace reduction

Date: 2026-07-20

Scope: offline analysis of the retained physical B--G traces and MuJoCo
source replay. No robot, provider API, training, Brev, or physical motion was
used.

> Superseding evidence note (2026-07-20): Stage F jointly refit joint zero
> offsets and therefore is not an action-frozen simulator comparison. Its
> geometry hypothesis remains useful, but the clean causal result is the
> geometry-only, byte-identical-action audit in
> `docs/run-logs/2026-07-20-pawn-action-frozen-gap.md`. The assisted aligned
> GR00T smoke is also excluded from fixed-policy evidence.

## Outcome

The train residuals had a monotonic file-axis structure: Stage-D errors were
negative at file B and positive at file G. That pattern motivated one new
physical scene parameter, the isotropic chessboard playing-side dimension.
The frozen simulator used a 355.6 mm playing area (44.45 mm squares). The
train-only Stage-F fit produced:

- playing side: 300.738 mm;
- square side: 37.592 mm;
- train event RMS: 17.414 to 12.906 mm, a 25.885% reduction;
- train XY RMS: 14.049 to 7.876 mm, a 43.937% reduction;
- no command clipping.

The two evaluator episodes had already been opened by the earlier Stage-D
study, so their results are transparent confirmation rather than untouched
model-selection evidence:

- event RMS: 23.549 to 16.097 mm, a 31.645% reduction;
- command-driven mean source-approach error: 17.276 to 9.222 mm;
- mean final target distance: 185.845 to 29.337 mm;
- selected-piece contact remained 2/2;
- lifts and task successes remained 0/2.

This is the requested lower-error result. It is a simulator-geometry and trace
comparison result, not a measured board calibration or transfer proof.

## Encoder-to-simulator trace comparison

The receipt now evaluates every sample in two modes against the static source
pawn-neck target:

1. mapped follower encoder state through simulator forward kinematics;
2. command-driven MuJoCo state under the same recorded command stream.

On the 11 train episodes:

| Metric | Stage D | Stage F |
| --- | ---: | ---: |
| Mean mapped-encoder minimum approach error | 8.224 mm | 4.071 mm |
| Encoder episodes within 10 mm | 7/11 | 11/11 |
| Mean command-sim minimum approach error | 14.117 mm | 11.126 mm |
| Command-sim episodes within 10 mm | 4/11 | 6/11 |
| Command-sim joint tracking RMS | 2.572 deg | 2.582 deg |

The board-pitch candidate halves mapped-encoder geometric error without
improving joint tracking. The remaining command-versus-encoder approach delta
is about 7.055 mm under Stage F, which localizes the next gap to
command-to-motion tracking and gripper/contact timing rather than board pose.

## Split decision

Stage F is the lower-error geometry/trace candidate, but it is not the global
physics-replay replacement:

| Train consequence | Stage D | Stage F |
| --- | ---: | ---: |
| Selected-piece contact | 9/11 | 6/11 |
| Lift | 1/11 | 0/11 |
| Mean final target distance | 60.468 mm | 35.374 mm |
| Success | 0/11 | 0/11 |

The predeclared contact and lift retention gates therefore failed. The receipt
records `kinematic_error_candidate: stage_f_board_pitch` and
`physics_replay_candidate: stage_d_lift` rather than conflating the two proof
surfaces. A train-only rubber-tip sensitivity rerun did not repair this:
nominal/low/midpoint produced 6/11 contact and high produced 7/11, with 0 lifts
and 0 successes for every variant.

## Reproduction and artifacts

Command:

```bash
uv run python scripts/run_pawn_bg_workcell_fit_v3.py
```

Tracked inputs and implementation:

- `configs/optimization/pawn_bg_workcell_fit_v3.json`
- `src/sim2claw/pawn_bg_workcell_fit_v3.py`
- `scripts/run_pawn_bg_workcell_fit_v3.py`
- `tests/test_pawn_bg_workcell_fit_v3.py`

Ignored, hash-bound outputs:

- `runs/pawn-bg-workcell-fit-v3/train_fit.json`
  - SHA-256 `abe9d2f6566b0193cb60ea1cafd0954eea0c2e628c0efcbbf0533d09aaaf0a0f`
- `runs/pawn-bg-workcell-fit-v3/confirmation.json`
  - SHA-256 `ea36ee7b6cc04d0734b8a8ec3e3579bd94c163c36d71f95895055093a8695f64`

The contract discloses that the B--G train residual gradient motivated this
parameter family and that an exploratory train-only kinematic fit preceded the
full consequence gate. The evaluator confirmation did not select or tune the
candidate.

Verification completed with 25 focused tests passing, followed by the full
repository suite: 565 tests and 328 subtests passed in 336.78 seconds. JSON
parsing, `uv lock --check`, `git diff --check`, and the historical `scene.py`
source hash also passed. The board-scale override is isolated to the workcell
fit layer so prior Studio and replay-audit artifacts retain their original
source binding.

## Claim boundary and next mechanism

The inferred 300.738 mm playing side is a trace-derived hypothesis. It should
be checked with a ruler if a similar physical scene is rebuilt. Until then it
must not be described as a measured physical board dimension.

Stage F reduces the geometry error while leaving a 2.58-degree joint-tracking
RMS and a command-driven approach gap. The next bounded mechanism is therefore
gripper aperture/contact timing or per-joint control tracking, not more board
warping, base tilt, or rubber friction. No compatible B--G ACT checkpoint was
introduced, and no policy or physical success claim follows.
