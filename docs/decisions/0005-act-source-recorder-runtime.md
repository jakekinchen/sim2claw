# Decision 0005: Loopback ACT Source Recorder Runtime

Status: accepted boundary for simulated and operator-gated physical source collection

Date: 2026-07-18 America/Chicago

## Decision

Add one local recording surface to the browser Studio. A physical SO-101 leader
can drive the MuJoCo follower while the recorder retains leader targets,
follower commands, follower state, selected-piece pose, continuous target pose,
timestamps, and leader/follower error. Stopping the recording opens an explicit
label step for skill, observed outcome, and notes.

Recordings are written under ignored storage:

```text
datasets/act_source_recordings/<label>__<recording-id>/
  samples.jsonl
  recording_receipt.json
```

These are raw source episodes. The receipt fixes `is_training_data: false` and
`training_admission: pending_deterministic_replay_and_separate_evaluator`.
Correct, incorrect, and corrective episodes may all be retained; only the
later M7 generator/replay/evaluator pipeline can admit derived strict-success
rows into an ACT training dataset.

## Control boundary

- Recorder POST endpoints operate only when Studio binds to a loopback address.
- Simulator mode opens only the expected leader bus and leaves leader torque
  disabled. The physical follower is not opened or commanded.
- Physical follower mode is routed only through
  `sim2claw.so101_physical_gateway.v1`. It requires a torque-off bus check,
  workcell acknowledgement, a bounded Sync with no more than 20 degrees of
  initial body mismatch, and a three-second warning before paired relative-zero
  registration. Sync ramps the follower to the nearby leader pose and always
  finishes torque-off.
- Physical recording permits 90 degrees of relative body travel and 180
  degrees of wrist-roll travel, clipped again to the follower's saved
  calibration. Four-degree command steps smooth the follower without imposing
  the prior 20-degree total workspace.
- Rate limiting is recorded, but stall enforcement is time-based and releases
  torque only after five seconds without at least 0.5 degrees of measurable
  progress. USB/bus errors still stop immediately.
- Physical Start owns Sync and the countdown; the separate Sync and Check
  controls are optional operator surfaces. Fault drafts move to ignored
  `failed_attempts/` diagnostics and the recorder returns to ready without a
  reset dialog.
- Physical recordings remain unqualified until authoritative object/target pose
  sensing and physical consequence evaluation exist.
- Server shutdown stops an active recorder and requests backend torque-off
  before closing.

Decision 0004 and milestone M13 remain the governing physical-proof boundary.
Owner direction advanced gateway and raw-source infrastructure; it did not
promote a physical episode or a sim-plus-real result.

## Adopted public dependency

| Dependency | Source | Version | Reason |
| --- | --- | --- | --- |
| `lerobot[feetech]` | Hugging Face `lerobot`, official SO-101 and teleoperation runtime | `0.6.0` | Reviewed public API for calibrated SO-101 leader/follower buses and Feetech transport |
| `numpy` | NumPy project through the existing Python runtime | `2.2.6` | Satisfies LeRobot 0.6.0's `<2.3` constraint while preserving the repo's existing array runtime |

The implementation was written against the official LeRobot 0.6.0 API and
documentation. No source, calibration, script, or artifact was copied from the
prior-project archive.

## Evidence boundary

A successful device preflight proves only that the expected USB buses,
calibration files, runtime, and frozen task contract are present. A saved
simulated recording proves only that the leader-to-MuJoCo collection path ran
and produced a checksummed raw source artifact. A physical recording proves
only that the reviewed gateway captured the commanded and observed joint trace;
replaying that trace in MuJoCo compares joint-space response, not object or
contact dynamics. None of these results proves a learned policy, a
strict-success training row, physical task success, or simulator accuracy for
the task.
