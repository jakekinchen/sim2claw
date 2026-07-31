# Executor session 115 — OR43 load-side gripper calibration preflight

Date: 2026-07-31
Card: `OR43`
Result: `PASS_PACKET_COMPILED_BLOCKED_METRIC_LOAD_SIDE_SENSOR`

OR43 compiles a deterministic no-object calibration packet without touching
hardware:

- `442` rows at `20 Hz`;
- `22.1 s`;
- three `5°↔30°` task-range cycles;
- one `5°↔60°` diagnostic cycle;
- maximum compiled slew `14.865°/s`;
- requested float64 hash
  `3ab970c0bcb5310e9a3939accce09eb281c9daac939e989749655b91ca8f3aa0`;
- requested, sent, measured, and host-timestamp fields declared separately.

The static capability preflight checks only executable/module presence and
bound source capabilities. It does not enumerate a device, open a camera or
serial bus, enable torque, move the robot, run a pawn attempt, or replay the
simulator.

The Mac has `librealsense 2.58.3` and `rs-enumerate-devices`, but the current
sim2claw native capture stack retains only D405 RGB. It does not retain metric
depth, sensor timestamp, exposure metadata, or frame counter. No metric
fiducial or secondary load-side encoder lane is configured. The packet is
therefore compiled but not admitted for motion.

Five focused tests pass, including deterministic schedule/hash behavior,
slew/trace gates, fail-closed live capability detection, and a synthetic
metric-depth capability pass.
