# D405 Capture Reliability

Date: 2026-07-24

Proof class: `camera_transport_diagnostic_and_fail_closed_capture_infrastructure`

## Scope

This transaction diagnoses the two rejected D405 captures from the sealed
six-attempt multilevel HIL campaign and hardens future capture failure
handling. It does not retry either packet, move the robot, run the simulator,
claim metric depth, recalibrate the twin, or change the strict task score.

The frozen contract is
`configs/evaluations/d405_capture_reliability_v1.json`, SHA-256
`e8232fd76044e5458030fe7392eb0b69d8b0f1bebf96706a96c68642d011b942`,
committed before implementation at
`0e4d57836ba6ddda9f2e6fb1d5357f14881737a2`.

## Root-cause evidence

Both rejected reports recorded a live FFmpeg process whose lossless source
stopped advancing:

- shoulder lift: last container PTS `13.6 s`, report SHA-256
  `911d3363dd962b2a34dcb0e34efdd618e2290bbcc20a914a505725bd1aef7ec4`;
- wrist flex: last container PTS `22.8 s`, report SHA-256
  `10d28805c19a48428db01156a6a855c55ef71204ac1ec531a06da7cdf5963bc7`.

The macOS unified log independently shows that these were whole USB-device
removals, not merely stalled encoders:

- `2026-07-24 09:04:50.908-05:00`: the host reported the SuperSpeed device
  removed; `UVCAssistant` could not abort I/O or select alternate setting zero,
  invalidated the D405, and re-enumerated it at `09:04:53.448`;
- `2026-07-24 09:08:25.254-05:00`: the same removal signature occurred and the
  D405 re-enumerated at `09:08:25.785`.

The D405 is directly attached at location `0x00200000`, reports operational
SuperSpeed, and uses USB host controller protocol 3.1. The rejected overhead
frames show the wrist-camera cable under changing tension while the arm is
moving.

Two bounded stationary diagnostics then separated the software and physical
paths:

| Diagnostic | D405 result | C922 result | USB removal |
| --- | --- | --- | --- |
| D405 isolated | 200 frames / 40.000 s / clean exit | not open | none |
| Production-order C922 then D405 | 200 frames / 40.000 s / clean exit | 1,229 frames / 42.000 s / clean exit | none |

These temporary diagnostics are not qualification artifacts. Together with the
two motion-time USB removals, they support a motion-correlated
cable/connector/strain-relief fault. They do not identify which physical cable
segment or connector is defective, and a stationary pass does not prove
capture reliability under motion.

Intel's current RealSense release notes also state that macOS builds are
compilable but not validated. That platform limitation remains relevant, but
the locally observed whole-device removal and motion correlation are the
direct evidence for this classification.

## Recorder hardening

`WristVideoRecorder` now:

- monitors FFV1 Matroska byte growth separately from process liveness;
- allows the frozen `3.0 s` startup grace, then fails after more than `3.0 s`
  without growth;
- labels the heartbeat as transport progress, not exposure time, frame-drop
  proof, or a synchronized device clock;
- records source bytes, last-growth offset, stall state and elapsed time;
- escalates shutdown through stdin `q` (`1.0 s`), process-group `SIGINT`
  (`3.0 s`), terminate (`2.0 s`), and kill (`2.0 s`);
- records every attempted stage, the terminal stage, and bounded signal
  errors;
- keeps a detected source stall failed even when the partial Matroska container
  is readable.

A live class-level smoke completed 65 D405 frames over 13.000 seconds, reported
continuous source progress, stopped through stdin `q`, produced the browser
derivative, and did not trigger the watchdog.

## Verification

- Recorder/timing/teleop/HIL focused tests: `29 passed`.
- Recorder/timing/teleop/HIL plus Studio project-map and Learning Factory
  binding tests: `41 passed`.
- Python compilation and `git diff --check`: passed.
- Optional `ruff` was not run because it is not present in the locked project
  environment; no dependency was added.

The sealed multilevel HIL campaign remains six attempts, zero retries, four
admitted packets, and two rejected packets. The earlier four-attempt HIL
campaign and all eleven frozen S2 artifacts remain byte-identical.

## Decision

Software-side fail-closed handling is implemented. The separately frozen six
by 40-second no-motion qualification remains pending and may establish only
stationary dual-camera acquisition health. Before a new motion packet can
address Twin fidelity, the D405 cable/connector path needs physical
reseating/replacement and strain relief, followed by a newly preregistered
motion-qualified capture check. Geometry, metric depth, force/load, synchronized
device timing, and strict held-out task consequence remain open measurement
prerequisites.
