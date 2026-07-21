# Pawn B--G force-retention diagnosis and fixed-pad sensitivity

Date: 2026-07-21

## Outcome

The action-frozen simulator now records source-frame and transition-aligned
grasp-retention traces containing per-jaw contact counts, MuJoCo normal and
tangential contact-force magnitudes, contact span, opposing-normal score, pawn
pose and velocity, target distance, pinch offset, simulated gripper state, and
the corresponding source commanded and measured gripper positions.

Those traces reject a generic "insufficient friction" explanation. The four
lifted baseline episodes exhibit at least two mechanisms:

- E2 -> E1 loses the moving-jaw contact while the fixed jaw still carries
  5.59 N of simulated normal force. The pawn falls below the 40 mm lift gate
  6.75 ms later. This is a direct premature-slip case.
- C2 -> C1 also ends by losing the moving jaw, but only after the action-frozen
  trajectory has already descended below the lift gate.
- D2 -> D1 and F2 -> F1 descend below the lift gate while bilateral contact is
  still present. Their first qualified-contact loss is therefore not the cause
  of the initial descent.

The force values are MuJoCo constraint-space diagnostics. They are not physical
force measurements and do not add physical authority.

## One-coordinate result

Reducing only the fixed rubber-pad thickness multiplier from 1.0 to 0.9 was
selected from the three adaptive sentinel episodes and then replayed on the
already-opened 11-episode regression set. Every source action array remained
byte-identical.

| metric | V3 baseline | fixed pad 0.9 | delta |
| --- | ---: | ---: | ---: |
| lifts | 4 / 11 | 4 / 11 | 0 |
| lift + transport | 1 / 11 | 1 / 11 | 0 |
| strict successes | 0 / 11 | 0 / 11 | 0 |
| mean final target distance | 106.19 mm | 60.15 mm | -46.03 mm (-43.4%) |
| mean final distance, lifted episodes only | 115.32 mm | 78.55 mm | -36.77 mm (-31.9%) |
| overall joint RMS | 1.21378 deg | 1.21244 deg | -0.00134 deg |
| EE RMS | 11.4168 mm | 11.3984 mm | -0.0184 mm |

The strongest consequence-aligned change is F2 -> F1: final target distance
falls from 170.72 mm to 23.63 mm, the pawn remains upright and settled, and the
action hash is unchanged. Three repeat replays produced byte-identical public
episode payloads and the same 23.6283 mm result.

The candidate passes the frozen one-percent trace limits (joint RMS at most
1.22397 degrees and EE RMS at most 11.4571 mm). It is nevertheless a
**diagnostic candidate, not a promoted composite**, because task counts do not
increase.

## Robustness and rejected branches

- Occluding the original rigid anchors behind the rubber sleeve reduced lift
  retention or violated the trace guard; the underlying rigid collider is not
  the premature-release cause.
- Increasing moving-pad thickness from 1.05 through 1.75 reduced the sentinel
  consequence metrics.
- Combining fixed-pad 0.9 with sliding friction 2.0 preserved only one
  lift-and-transport result and severely worsened sentinel terminal distance.
- Moving-pad longitudinal placement by +/-1 mm was unstable and did not reach
  a destination gate.
- A 61-point fixed-pad map over 0.880--0.940 found 30 results below 25 mm but
  only two whole-base destination crossings and no strict success. The best
  upright crossing was 7.66 mm at 0.910, missing the 6 mm composable-center
  gate; adjacent values did not preserve it. It is a solver-sensitive point,
  not a physical calibration claim.

## Frozen-metric interpretation

The existing `maximum_transport_progress_after_lift` metric updates only while
the pawn is currently at least 40 mm above its initial height. D2 and F2 both
move into the target region while still bilaterally grasped after first
crossing 40 mm, but the frozen transport metric stops observing that progress
once the arm carries lower. The evaluator was not changed. This is recorded as
a publication caveat and a candidate secondary diagnostic for a future,
separately frozen evaluator revision.

## Evidence

- Baseline full receipt:
  `outputs/pawn_bg_grasp_group_probes/frozen_v3_timestep045_all.json`
  (SHA-256 `5763e0be1f1ff6d1e535f13af36289eabb07f219220ac2c95b7c8bdf4158eb29`)
- Fixed-pad full receipt:
  `outputs/pawn_bg_grasp_group_probes/v3_fixed_tip_thickness_0p9_all.json`
  (SHA-256 `2c066c0d2565290fda37e0badd781f636e1876427de6d5027051ba736e9a2860`)
- Baseline retention traces:
  `outputs/pawn_bg_retention_traces_v1/`
- Fixed-pad F2 retention trace:
  `outputs/pawn_bg_retention_traces_v1/20260719T032620Z-0c7e3d86__fixed0p9.json`
  (SHA-256 `7ff1947fcacea9732fc28808efd7d3303f683fa8c8e59a8f3f3a1f9df5f01ec1`)
- Diagnostic parameters:
  `configs/experiments/pawn_bg_v3_fixed_pad_0p9_diagnostic_parameters.json`

No robot, camera, wrist stream, Brev resource, or paid compute was used. The
result is retained action-frozen simulator diagnostic evidence only.
