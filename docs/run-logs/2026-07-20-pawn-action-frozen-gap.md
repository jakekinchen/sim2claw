# Pawn B--G action-frozen simulator-gap audit

Date: 2026-07-20

Scope: offline MuJoCo analysis of retained physical telemetry and retained
unassisted GR00T action arrays. No policy inference, IK, corrective action,
provider API, robot, Brev, training, or physical motion was used.

## Correction to the earlier approach

The earlier Stage-F board-pitch experiment was not a clean fixed-controller
comparison. It jointly refit physical-to-simulator joint zero offsets. The
earlier source-aligned GR00T smoke also applied a post-policy fixed-offset bridge
and declared assistance. Those results remain diagnostic, but they are excluded
from action-frozen evidence.

This audit enforces two immutable-control lanes:

1. Each physical teleoperation command sequence is mapped exactly once with the
   reconstructed Stage-D adapter. The resulting contiguous `float64` array is
   passed unchanged to both simulator variants.
2. Each retained GR00T `applied_actions` array is passed directly to both
   simulator variants. No adapter is invoked and the policy is not called.

Every variant must receive the same shape, dtype, byte sequence, and SHA-256.
Any clipping, IK correction, post-policy offset, corrective suffix, assistance,
or candidate-specific mapping fails the experiment.

## Geometry-only result

Only board center, board yaw, and playing-side length were optimized. The
Stage-D joint offsets, measured joint envelope, and reopen-timing nuisance term
were frozen. The resulting train-only candidate was:

- board center: `[-10.223, -45.851] mm` in the table frame;
- board yaw: `184.908 deg` relative to the table;
- playing side: `301.338 mm` (`37.667 mm` squares);
- train event RMS: `17.414 -> 12.954 mm`, a `25.614%` reduction;
- already-open confirmation RMS: `23.549 -> 15.944 mm`, a `32.295%` reduction.

The 11 train command matrices have 11 distinct hashes, and each hash is
identical between Stage D and the geometry-only simulator. The two
already-open confirmation matrices pass the same invariant. Confirmation did
not tune or select the candidate.

## Full trace observability

For every one of the 4,743 train samples and 819 confirmation samples, the
audit persists:

- timestamp and phase;
- requested, commanded, and measured physical joint positions;
- measured joint velocity and available motor current;
- the exact applied simulator action;
- mapped-encoder and command-driven simulator joint states;
- mapped-encoder and simulator end-effector XYZ;
- time-aligned end-effector error;
- end-effector distance to source and destination pawn-neck targets.

Each episode also has a source-distance overlay and an end-effector XY-path
plot. The visual inspection shows the expected result: geometry moves the
target relative to the same arm trajectory; it does not repair the trajectory.

| Train metric | Stage D | Geometry only |
| --- | ---: | ---: |
| Mean mapped-encoder minimum source distance | 8.224 mm | 3.983 mm |
| Mean command-sim minimum source distance | 14.510 mm | 12.310 mm |
| Time-aligned command-sim vs encoder EE RMS | 20.792 mm | 20.874 mm |

The nearly unchanged end-effector tracking RMS is the key conceptual result.
Board geometry improves target registration, but not command-to-motion
dynamics or tracking.

## Frozen GR00T action replay

All 12 retained unassisted `(317, 6) float64` action arrays match the SHA-256
values in the frozen report. They were replayed byte-identically under the
original geometry and the geometry-only candidate. The policy was not invoked,
no action adapter ran, and no action was clipped.

| Open-loop consequence | Original geometry | Geometry only |
| --- | ---: | ---: |
| Mean minimum EE-to-source-neck distance | 187.063 mm | 87.392 mm |
| Selected-piece contact | 0/12 | 0/12 |
| Task consequence success | 0/12 | 0/12 |
| Mean final distance in square sides | 1.000 | 1.853 |

One candidate case crossed the reward's height-only lift threshold without jaw
contact. That is a collision/dynamics artifact, not a grasp, and provides no
policy-success evidence.

The geometry hypothesis therefore explains a substantial target-registration
component of the gap, but it does not close the interaction gap. Under exactly
the same model-produced controls, the gripper never contacts the selected pawn
and no task succeeds. The next simulator-only hypotheses should target reset
alignment, actuator response/latency, gripper aperture mapping, and contact
geometry/timing, one bounded family at a time. They must retain this same
action-invariance gate.

## Reproduction and artifacts

Command:

```bash
uv run python scripts/run_pawn_bg_action_frozen_gap.py
```

Tracked implementation:

- `configs/optimization/pawn_bg_action_frozen_gap_v1.json`
- `src/sim2claw/pawn_bg_action_frozen_gap.py`
- `scripts/run_pawn_bg_action_frozen_gap.py`
- `tests/test_pawn_bg_action_frozen_gap.py`

Ignored, hash-bound outputs:

- `runs/pawn-bg-action-frozen-gap-v1/train_fit.json`
  - SHA-256 `4f111fdcb0328394b6f98fa77f4a23418b8bf0cbb47096d392fdc96d262fac80`
- `runs/pawn-bg-action-frozen-gap-v1/confirmation.json`
  - SHA-256 `4fccbb23da6a7df142245419f56a638468746d00fd47fad323877bd315ecf0ec`
- `runs/pawn-bg-action-frozen-gap-v1/policy_action_replay.json`
  - SHA-256 `9a5b3d62e19802c5df74d578e3f58834f5760a059ccccee93e3c136f9a5a4fde`

All three receipts bind implementation SHA-256
`e9b883b715a2b8f4290b774cc98e8395c999e1faf9f9fd1ef197bcaf85fe5827`.

Focused verification passed: `3 passed`. The repository-wide suite completed
with exit status 0; 568 tests were collected. JSON parsing, the dependency-lock
check, and `git diff --check` also passed.

## Claim boundary

This is a geometry and open-loop gap-attribution result. The inferred board
dimensions are trace-derived, not physically measured. A frozen open-loop
action comparison is the correct causal test for simulator parameters; it is
not a new closed-loop policy evaluation. In a later closed-loop test, the
checkpoint, code, prompts, seed, and preprocessing should remain unchanged,
but actions may legitimately differ because a changed simulator produces
different observations.
