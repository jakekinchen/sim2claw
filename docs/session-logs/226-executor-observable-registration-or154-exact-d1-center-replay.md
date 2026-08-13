# OR154 Executor log — exact-D1-center replay

Date: 2026-08-13

## Frozen pre-run materialization

`sim2claw check --profile agent` and the exact Executor context passed with
OR154 active. OR151 through OR153 closeouts, contracts, receipts, and available
531-row traces were read and hash-bound; OR153 is the immutable baseline and is
not rerun.

The sole future factor is selected-pawn initial board coordinate:

- baseline: `[3.568645477294922, 0.48760929703712463]`;
- candidate: exact D1 `[3.5, 0.5]`.

The future implementation preserves OR153's `-88 deg` yaw, support Z, upright
quaternion, 531 raw measured rows, timestamps, row order, native-step
interpolation, model, solver, contact and object parameters, joint-range union,
settle, and evaluator. The contract forbids prototype or temporary replays,
fits, searches, retries, renders, action mutation, retiming, assistance,
hardware, held-out access, and paid compute.

Acceptance is frozen as numeric task success, or contact preserved plus at
least one false-to-true frozen task gate and zero true-to-false gate
regressions. Metric-only improvement fails. A read-only verifier is included
to require a later closeout to hash-bind the contract, implementation, this
log, canonical receipt, and full trace, and to re-evaluate gate acceptance from
the immutable OR153 baseline.

## Pre-run stop boundary

This Executor slice stops after static preflight. It does not invoke the OR154
run entrypoint, compile a MuJoCo model, call `mj_forward` or `mj_step`, create
the output directory, or consume the one authorized replay. Result fields and
post-run hashes intentionally remain absent until a separately authorized
execution crosses the frozen gate.

## Sole canonical replay

After independent Reviewer `PASS_TO_EXECUTE_EXACTLY_ONCE`, the Executor issued
exactly this command once:

```text
uv run --locked python -c 'from sim2claw.observable_registration_or153_exact_d1_center_replay import run_exact_d1_center_replay; run_exact_d1_center_replay()'
```

It exited `0` with no stdout or error. No other dynamics invocation, prototype
or temporary replay, fit, search, retry, render, action mutation, retiming,
hardware action, or paid compute occurred.

## Frozen result

The receipt status is
`PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE`. Selected-pawn contact
remained true with `1049` native contact counts. `settled_height` and `upright`
flipped false-to-true, and no previously true gate flipped false. The pawn
remained outside the composable-center threshold, so numeric task success is
false.

Final task metrics are `45.856146 mm` planar-center error, `0.002665 deg`
upright tilt, and `0.000062941 mm` height error. Against immutable OR153 these
improved by `83.479592 mm`, `97.793428 deg`, and `12.650607 mm`, respectively.
Signed D2 progress remained negative at `-5.171794 mm`; the exact-D1 pawn did
not transfer to the destination square.

The emitted trace has all `531` source timestamps and sample indices in order.
Source hashes remained unchanged. Receipt SHA-256 is
`e8eb180d2e5ad8db5ca695599dc0c77d6aa4c84cfee1df80e43f2fcf75974ca9`;
its artifact digest is
`694eff1a7e9b4e9559eeac9307ade24ef9e986c5f59d22040c4b4328211ddb1c`.
Trace SHA-256 is
`d1491815e682e7cadd7772c50b265e25596661ffd816a2fe6497850ac4562bb4`.

The independent scientific verdict is
`ACCEPT_GATE_LEVEL_ADVANCEMENT_TASK_NEGATIVE`. This closes the exact-centering
factor without retry and admits no automatic successor. It is not numeric task
success, physical measurement, camera, robot, or action calibration, physics
fidelity, physical task evidence, simulator promotion, or transfer proof.
