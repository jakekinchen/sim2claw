# Goal Loop — Current 100 mm Physical Measurement and Calibration

## Mission

Acquire the missing current-workcell evidence needed to test whether a
mechanism-specific simulator correction improves action-frozen fidelity and
strict pawn-task consequence. Use only the reviewed SO-101 gateway and the
identified C922 camera. Preserve every safety, provenance, action-identity, and
independent-evaluator boundary.

The owner directly authorized bounded camera capture, robot episodes, and new
data collection on 2026-07-23. That authorization opens this transaction; it
does not waive gateway readiness, start-pose, workcell-clear, calibration,
freshness, or evaluator gates.

## Ordered Source of Truth

1. The live checkout, connected device identity, calibration files, camera
   inventory, and torque state.
2. This goal and
   `configs/evaluations/current_100mm_measurement_acquisition_v1.json`.
3. The reviewed `src/sim2claw/physical_gateway.py` and physical replay
   validators.
4. Immutable raw camera, joint, current, command, acknowledgement, and
   consequence artifacts produced by this transaction.
5. Evaluator-owned receipts, `GOAL.md`,
   `docs/autonomous-workflow/project_state.json`, and the orchestration ledger.
6. Historical recordings and simulator results, which remain separate,
   unqualified proof classes unless independently admitted here.

## Intended Outcome

Produce one synchronized, content-addressed current-workcell dataset with
metric registration and explicit missing-channel accounting; use training
episodes to fit only the preregistered factor scopes; freeze one composite
candidate before validation; open held-out episodes once; and report the
independent simulator and physical task consequence honestly.

The acceptable terminal outcomes are:

- a held-out, evaluator-admitted improvement with unchanged action bytes;
- a measured tie or loss with no promotion; or
- a sealed readiness/measurement abstention that names the unmet prerequisite.

## Acceptance Criteria

1. The frozen S2 benchmark/C2 evidence and the closed external-validation
   result remain byte-identical.
2. All hardware access uses the reviewed gateway. No raw joint command,
   direct bus write, IK, offset, clipping, resampling, corrective suffix, or
   action assistance is introduced.
3. Before any motion, the connected identities and calibration hashes match
   the preregistration, follower torque is off, paired-pose/start-envelope
   checks pass, the camera shows a clear intended workcell, and the evaluator
   admits metric board/object registration.
4. A torque-off synchronized baseline records calibrated leader/follower
   position, raw motor current with freshness, camera timestamps, device
   identity, and explicit absence of load/contact/metric-pose channels.
5. Five empty-gripper cycles pass gateway rate, tracking, stall, current
   freshness, camera, and consequence checks before task motion is admitted.
6. Task episodes are frozen as 6 training, 3 validation, and 3 held-out
   episodes. Safety-aborted attempts consume budget and are never silently
   retried or relabelled.
7. Simulator variants replay byte-identical float64 action tensors. Fitting
   uses training only. The one composite candidate and consequence thresholds
   are frozen before validation; held-out data opens once after selection.
8. The independent CPU/fp32 evaluator owns task/EE consequence, admission,
   aggregation, and promotion. Lower joint RMS, visual improvement, current
   change, or contact proxy alone is diagnostic.
9. Physical task score changes only from evaluator-owned, camera-bound,
   metric-consequence evidence. Otherwise the existing strict score remains
   unchanged.
10. Generated observations, credentials, caches, and outputs remain out of
    Git. Versioned contracts, code, tests, goal/state/logs, and content digests
    may be committed.

## Evidence Standard

Keep these proof classes separate:

- `physical_torque_off_read_only_baseline`
- `physical_empty_gripper_safety_baseline`
- `physical_current_workcell_task_observation`
- `action_frozen_simulator_calibration`
- `independent_cpu_fp32_consequence_evaluation`

Every admitted artifact must bind source bytes, device/calibration identity,
timestamps and freshness, camera identity, workcell registration, action hash,
episode split, evaluator version, thresholds, and authority. Unknown or
unmeasured channels remain explicit; they are never converted to zero.

## Decision Status

`DUAL_CAMERA_C2_C1_NEGATIVE_GRASP_MECHANISM_UNRESOLVED_TASK_PIPELINE_STILL_GATED`

Camera and both calibrated SO-101 buses are reachable. The follower remains
torque-off after one bounded positioning move and one camera-recorded
historical replay. The owner clarified that the observed pieces were the
intended task setup and explicitly confirmed the workcell clear. The closest
one-session endpoint was the `b2 to c2` source in reverse; its direct
positioning interpolation had no MuJoCo contact pairs and its complete reverse
trace passed the unchanged replay envelope.

The one admitted torque-off baseline is complete: 30/30 samples include fresh
raw current, the diagnostic video contains 239 frames, and all observations
confirm torque-off/no-motion state. The later replay requested all 566 source
rows but sent only 394 within the exactness tolerance and gateway-clamped 175,
so it remains unqualified command-replay observation. It did not run the
independent metric task evaluator, did not satisfy the five empty-gripper
cycles, and cannot change the strict `0 / 11` task score.

A subsequent owner-requested forward `c2 to c1` replay captured the C922 and
D405 together. Two completed robot attempts are excluded from dual-camera
proof because the D405 stopped after about five seconds. The final unchanged
trace completed 527/527 rows with 501 exact commands and 70 safety-clamped
samples; C922 coverage was 1,049 frames through 34.966667 seconds and D405
coverage was 175 frames through 34.8 seconds. Both cameras and the replay
receipt finalized, and follower torque is off.

The overhead endpoint is unchanged and the wrist view shows the jaws
converging around the pawn without transporting it. During the approach and
closure window, physical tracking lag reached approximately 5-8 degrees on
the shoulder/elbow/wrist chain. The wrist stream has no admitted metric depth
or camera-to-gripper transform, and replay current telemetry was disabled, so
this evidence cannot yet distinguish approach-timing error from inadequate
grasp force/retention. It is a terminal negative for this unmodified trace,
not a score-changing task episode.

## Execution Rhythm

1. Reconfirm device, calibration, camera, torque, repository, and frozen
   evidence identity.
2. Materialize the torque-off synchronized baseline and evaluator receipt.
3. Stop at any pose, workspace, freshness, registration, or sensor failure.
4. After motion readiness passes, run the five frozen empty-gripper cycles.
5. Freeze and collect the 6/3/3 task split without adaptive retries.
6. Fit preregistered factors on training, freeze one candidate, evaluate
   validation, and open held-out once.
7. Publish separate infrastructure, physical-observation, simulator, and task
   consequence receipts; update durable authority and stop.

## Progress Ledger

- 2026-07-23 — Clean `main == origin/main` at
  `694fa5a4372056fa1484711053f2d340e2044232` confirmed.
- 2026-07-23 — C922 AVFoundation camera index `0` captured 1920x1080 frames.
- 2026-07-23 — Leader `/dev/cu.usbmodem5B3D0448141` and follower
  `/dev/cu.usbmodem5B3D0406411` matched the preregistered calibration hashes.
- 2026-07-23 — Two torque-off gateway inspections returned the same unsafe
  paired-pose result; no motion was commanded.
- 2026-07-23 — All 18 retained physical traces failed the unchanged replay
  start-envelope check; no trace was selected or executed.
- 2026-07-23 — One torque-off baseline captured 30/30 fresh-current samples
  and 239 camera frames with zero motion. Receipt digest:
  `4dbb666ab68fa41688b3d346f54797d947fd0771af8f2ec20edc1ac379eb4021`.
- 2026-07-23 — Camera evidence independently rejected the clear-workcell gate;
  motion and task collection remain blocked.
- 2026-07-23 — Owner corrected the camera interpretation and explicitly
  confirmed the intended task setup clear. The leader arm remained unused.
- 2026-07-23 — A first positioning attempt stopped before motion when motor ID
  2 missed the one-attempt torque-enable acknowledgement. Torque-off was
  verified. The gateway now uses the Feetech API's bounded retry window for
  safety-critical enable and disable transitions; 31 focused tests passed.
- 2026-07-23 — A second positioning attempt moved partially, then stopped when
  a duplicate Studio live tab reclaimed the serial port. All competing live
  sessions were closed and torque-off was independently reverified.
- 2026-07-23 — The third positioning attempt completed at 5 degrees/second
  with 0.527/0.615/0.176/1.077/0.352/0.0-degree residuals and released torque.
- 2026-07-23 — The single `b2 to c2` reverse replay completed all 566 rows with
  a 31.066667-second C922 capture. Exact commands were 394/566 and safety
  clamping occurred on 175/566 samples. The proof class is
  `physical_command_replay_observation_unqualified`; task score remains 0/11.
- 2026-07-23 — Owner requested the canonical forward `c2 to c1` trace with
  simultaneous C922 and D405 evidence. The first D405 MP4 was unindexed; the
  second contained only 80 frames through 5.267 seconds. Both robot replays
  completed and are preserved as camera-incomplete evidence, not retried
  successes.
- 2026-07-23 — A torque-off 20 Hz serial-load probe established that the
  D405's supported 424x240-at-5-fps mode sustains 173 frames through 34.4
  seconds while the C922 records at 30 fps.
- 2026-07-23 — The final unchanged `c2 to c1` replay completed 527/527 rows,
  501 exact commands, and 70 safety-clamped samples. Its full dual-camera
  receipt SHA-256 is
  `3fafb113a7b89e0b80640b9c7b4cc2016db16ecafcb9f46cba79a79a1330499f`;
  task score remains 0/11 because the board endpoint did not change.
