# Native D405 pose-plane capture orchestrator

Date: 2026-07-25

Proof class:
`physical_calibration_setup_pose_plane_observations_only`

Implementation status: hardware-free synthetic verification passed; the native
orchestrator was not run against a camera or robot in this lane.

## Bounded behavior

The orchestrator:

1. Requires a previously accepted stationary D405 RGBD receipt and binds its
   exact camera identity, 848x480 depth intrinsics, and depth units.
2. Enumerates the D405 before recording, starts `rs-record` itself, and treats
   native depth-topic appearance in the new database as the readiness event.
   It does not depend on `rs-record`'s carriage-return progress output.
3. Records lower/upper monotonic bounds around recorder start and stop.
4. Runs the existing live-anchored setup-only route executor.
5. Requires the returned route receipt to exactly match its stored receipt,
   requires a successful route and confirmed final torque-off, and consumes
   the route receipt's exact monotonic terminal-hold interval.
6. Stops `rs-record`, re-enumerates the camera, and fails closed on identity
   drift. Recorder startup failure interrupts and waits for the spawned process
   (with a kill fallback), preventing leaked camera ownership.
7. Converts the terminal hold into the conservative bag-time window:

   ```text
   lower = hold_start_monotonic - record_start_lower_monotonic
   upper = hold_end_monotonic   - record_start_upper_monotonic
   ```

   A frame is admitted only when its bag/header timestamp falls wholly inside
   this interval for every possible recorder-start time in the measured bound.
8. Reads native Z16 ROS2 image payloads only within that window, verifies each
   bag timestamp against its image-header timestamp, verifies the database
   identity/calibration against the accepted lineage, and reuses the existing
   robust metric plane fitter.
9. Emits each admitted metric plane with the stationary terminal joint-pose
   mean, standard deviation, range, telemetry hash, and exact terminal-command
   hash for later camera-to-robot extrinsic fitting.

The runtime fails closed for missing/unbounded clocks, route failure, missing
or changed route receipt, unconfirmed torque-off, identity or calibration
change, nonstationary terminal joints, insufficient hold frames, timestamp
disagreement, or failed plane-quality gates.

## Synthetic acceptance

The positive fixture used recorder-start bounds `[100.0, 100.1]` seconds and a
route terminal hold `[101.2, 102.5]` seconds. The resulting conservative bag
window was `[1.2, 2.4]` seconds. Of fixture frames at 0.8, 1.3, 2.0, and 2.6
seconds, only 1.3 and 2.0 seconds were admitted. Both were bound to the same
three-sample stationary six-joint hold observation and passed the reused metric
plane gates.

Negative fixtures cover:

- D405 identity drift after capture;
- route completion without confirmed final torque-off;
- recorder start uncertainty wider than the contract;
- no sufficient depth frames inside the conservative hold;
- native recorder readiness failure releasing the spawned process.

## Authority boundary

The emitted receipt grants no camera-to-robot extrinsic, board origin, replay,
policy, task-success, or physical-task authority. It contains calibration
observations suitable for a later separately evaluated fit; it does not perform
or promote that fit.

## Verification

```text
.venv/bin/pytest -q \
  tests/test_d405_pose_plane_capture.py \
  tests/test_live_anchored_camera_reposition.py \
  tests/test_d405_metric_surface_plane.py \
  tests/test_d405_stationary_rgbd_capture.py
.............................                                            [100%]
29 passed in 1.11s
```
