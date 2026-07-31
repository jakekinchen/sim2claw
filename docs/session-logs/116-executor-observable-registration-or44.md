# Executor session 116 — OR44 D405 metric-depth sidecar

Date: 2026-07-31
Card: `OR44`
Result: `PASS_COMPILED_D405_METRIC_SIDECAR_NO_DEVICE_ACCESS`

OR44 implements the smallest instrumentation capability selected from the
GPT Pro failure branch after OR40 and OR41:

- a native C++17 D405 recorder linked against `librealsense 2.58.3`;
- raw frame-ordered `Z16` output;
- a manifest with metric depth scale and calibrated intrinsics;
- per-frame sensor timestamp and timestamp domain;
- host steady-clock arrival;
- frame number, dimensions, stride, bit depth, and raw byte offset;
- frame counter, exposure, gain, and actual FPS when the device reports them.

The source makes `--help` return before `rs2::context` construction. The
deterministic build evaluator compiled and linked the native binary, ran only
that help path, and verified all frozen schema tokens. The binary hash is
`7a53f8d02d02e7d457ed0d5ee3e7662a34ffa3786d870d9ba3d08981db2d9736`.

OR44 did not invoke `rs-enumerate-devices`, create a RealSense context, inspect
device presence, open a camera, start a stream, open serial, enable torque,
move the robot, attempt a pawn task, or replay the simulator. Metric depth and
the load-side gripper mapping therefore remain unacquired. Nine focused OR43
and OR44 tests pass.
