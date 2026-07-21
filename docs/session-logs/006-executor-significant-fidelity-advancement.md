# Executor Session 006: Significant Fidelity Advancement

## Scope

Continued the approved hardware-free, action-frozen campaign until one frozen
goal-loop stop condition passed: at least 5% grouped-CV joint-RMS improvement
without EE regression, or material target-piece consequence advancement.

## Residual diagnosis

The selected 110 ms timing plus 2-degree deadband baseline had 1.2955577
degrees body-joint RMS and 12.9364 mm EE RMS. Elbow flex dominated at 2.3338
degrees RMS with -1.6394 degrees signed bias. Its error was larger in
stationary/load-bearing rows and pose-dependent. Independent deadbands alone
could not cross the frozen 5% threshold while retaining the lift/elbow stall
constraint; residual holding-gain probes were negative.

## Frozen continuation

The formal 63-candidate experiment varied shoulder-lift deadband, elbow-flex
deadband, and one simulator-side elbow load-bias coefficient. The coefficient
multiplies MuJoCo's bias-force term only while the elbow servo is inside its
deadband. Source action arrays remain contiguous float64, byte-identical,
unclipped, unassisted, and in their original order.

Four whole-episode folds selected a 1.5-degree lift deadband, 2.0--2.5-degree
elbow deadbands, and coefficient -1.5. The coefficient equals the frozen lower
grid boundary in every fold. This supports the bounded response family but does
not identify its magnitude or a physical motor/firmware/torque mechanism.

## Evaluator result

- pooled body-joint RMS: 1.2955577 to 1.2118497 degrees, 6.461% lower;
- pooled EE RMS: 12.9364 to 11.3437 mm, 12.312% lower;
- every validation fold improves: 7.010%, 4.298%, 10.350%, and 2.984%;
- paired 10,000-replicate episode-bootstrap joint-improvement 95% interval:
  4.398--8.540%;
- bootstrap probability of positive improvement: 1.0;
- bootstrap probability of at least 5% improvement: 0.9162; and
- already-opened two-episode confirmation: 1.3285 to 1.2806 degrees, consistent
  direction only and never used for selection.

The 11 validation episodes originate from one retained acquisition session.
The bootstrap interval is conditional on those episodes and must not be read as
independent-session or physical-population generalization.

## Consequence boundary

The strict unchanged-action target-piece replay remains mixed: contact 11/11 to
11/11, lift 2/11 to 1/11, whole-base-inside-destination 0/11 to 2/11, strict
success 0/11 to 0/11, and mean final target distance 76.884 to 47.310 mm.
Therefore the accepted result is trace fidelity only. Grasp advancement,
contact identification, composite simulator promotion, training admission,
policy promotion, and physical transfer remain false.

## Artifacts

- `configs/sysid/pawn_bg_servo_load_bias_v1.json`
- `outputs/pawn_bg_servo_load_bias_v1/servo_load_bias_receipt.json`
- `configs/evaluations/pawn_bg_fidelity_advancement_v1.json`
- `outputs/pawn_bg_fidelity_advancement_v1/advancement_receipt.json`
- `outputs/pawn_bg_fidelity_advancement_v1/fidelity_advancement_summary.png`

## Final verification

```text
uv run --offline pytest -q tests/test_pawn_bg_servo_load_bias.py::test_load_bias_contract_is_bounded_action_frozen_and_non_authoritative tests/test_pawn_bg_fidelity_advancement.py
```

Result: 4 passed in 9.25 seconds. Targeted `compileall`, JSON parsing, and
`git diff --check` also pass. Ruff is not installed in the locked runtime, so
no Ruff result is claimed.
