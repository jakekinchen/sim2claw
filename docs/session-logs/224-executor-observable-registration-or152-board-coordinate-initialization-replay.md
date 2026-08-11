# OR152 Executor log — board-coordinate initialization replay

Date: 2026-08-11

## Scope

OR152 consumed one write-once observation-conditioned simulator replay. It
preserved OR34's exact 531 raw measured robot rows, timestamps, row order,
native-timestep interpolation, OR18 model and solver, range union, contact and
object parameters, settled support Z, upright quaternion, post-action settle,
and task evaluator. The sole changed factor was selected-pawn initial XY,
transported through OR18 board geometry after OR151 Reviewer `PASS`.

No temporary or prototype dynamics replay was run. Preflight tested only the
contract and frozen metric-comparison logic; post-run tests read the canonical
receipt and trace without rerunning dynamics.

## Frozen result

The result is `TERMINAL_NO_TASK_OUTCOME_METRIC_ADVANCEMENT`:

- initial XY changed by `13.978176 mm`;
- selected-pawn contact remained present, but first contact moved from OR34
  sample `230` to `259` and first 1 mm motion from `232` to `263`;
- signed D2 progress changed from `+86.164735 mm` to `-4.854555 mm`;
- final D2 planar error regressed from `33.946221 mm` to `68.927982 mm`;
- final tilt changed only `0.000795 deg` better and remained `102.104198 deg`;
- final height error changed by less than `0.00001 mm` and remained
  `14.538801 mm`;
- no frozen task gate flipped false-to-true; numeric task success remains
  false.

The replay falsifies pawn-XY-only correction as a sufficient task mechanism.
It suggests the retained board coordinate cannot be transported independently
of the robot-to-board gauge, but OR152 alone does not identify which robot,
board, wrist, jaw, or dynamic parameter is causal.

## Verification

```text
uv run --locked pytest -q tests/test_observable_registration_or34_board_coordinate_initialization_replay.py
3 passed

uv run --locked sim2claw check --profile agent
pass
```

Receipt SHA-256:
`684ee5a2c15e189392fcffeec4275d8c86c58894d2287c1e3485f08315c1610d`.

Trace SHA-256:
`110c5bc104ef70fd44d97a13ffff65ac386300ac5cc0413e1621d25df1fd2bf2`.

This is a terminal negative for the single frozen factor, not action-only
transfer, physical task evidence, physics fidelity, task success, promotion,
or transfer proof. The run may not be retried or searched for a favorable
outcome.
