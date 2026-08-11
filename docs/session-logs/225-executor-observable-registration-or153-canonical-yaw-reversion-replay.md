# OR153 Executor log — canonical-yaw reversion replay

Date: 2026-08-11

## Frozen scope before dynamics

The agent check and Executor context passed. OR152 is the immutable advancement
baseline. OR18 (`-82 deg`) and OR13 (`-88 deg`) were hash-bound and compared
before dynamics; their sole semantic difference is
`simulation_estimates.robots[0].yaw_relative_to_table_degrees`.

The owner authorization, contract, implementation, tests, brief, and this log
were authored before execution. Preflight exercises only source binding,
semantic-diff isolation, the no-claim boundary, and frozen metric-comparison
logic. The canonical output directory must not exist before the run.

Exactly one replay is admitted. No prototype or temporary dynamics replay,
fit, search, retry, sweep, sign test, assistance, hardware access, held-out
access, paid compute, calibration, promotion, or transfer claim is admitted.

## Frozen acceptance boundary

Against OR152, selected-pawn contact must remain true and at least one of these
must occur: final planar error falls by at least `0.001 m`, upright tilt falls
by at least `5 deg`, final height error falls by at least `0.001 m`, or an
unchanged frozen task gate flips false-to-true. Full simulator task success
still requires every unchanged OR34 gate.

## Result

The single canonical write-once replay returned
`PASS_TASK_OUTCOME_METRIC_ADVANCEMENT` under the prospectively frozen rule:

- selected-pawn contact remained present (`381` native contact counts);
- final height error improved from OR152's `14.538801 mm` to `12.650670 mm`,
  a material `1.888131 mm` reduction;
- final tilt improved by `4.308104 deg`, from `102.104198 deg` to
  `97.796094 deg`, below the frozen `5 deg` material threshold;
- final planar center error regressed materially from `68.927982 mm` to
  `129.335738 mm`;
- signed D2 progress regressed from `-4.854555 mm` to `-54.032948 mm`;
- first contact moved from sample `259` to `260`, and first 1 mm motion from
  sample `263` to `285`;
- no frozen task gate flipped false-to-true; `upright`, `settled_height`, and
  `composable_center` remain false; numeric simulator task success remains
  false.

The exact OR152 pawn pose was preserved (`0.0` maximum absolute change), and
the emitted trace contains all `531` measured rows in order. Source hashes were
unchanged. Execution records exactly one simulator replay, zero fits, searches,
retries, hardware actions, and no paid compute.

Receipt SHA-256:
`9c20c02ca258a1e16eda88d87b4222842b8ebb4463e97275da1f02f2ee177a7e`.

Trace SHA-256:
`f0a688cd3c83304c59e4a1159aeef7fe02200c368bab4b3a96730e09bf6ea283`.

This is a narrow task-outcome metric advancement and a useful yaw-sensitivity
result. It is not a successful square transfer, upright replay, calibration,
physics-fidelity proof, physical task evidence, simulator promotion, or
transfer proof. The bounded replay was not retried or searched.
