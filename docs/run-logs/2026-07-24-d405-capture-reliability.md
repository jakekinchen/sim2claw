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
- Final qualification/recorder/timing/teleop/HIL/Studio/project-binding
  focused gate: `48 passed`.
- Python compilation and `git diff --check`: passed.
- Optional `ruff` was not run because it is not present in the locked project
  environment; no dependency was added.

The sealed multilevel HIL campaign remains six attempts, zero retries, four
admitted packets, and two rejected packets. The earlier four-attempt HIL
campaign and all eleven frozen S2 artifacts remain byte-identical.

## Frozen stationary qualification

The qualification implementation was committed at `c823d63` before live
execution. The committed runner verified the frozen contract and exact
FFmpeg/FFprobe binaries, refused an existing output root, and owned exactly
six sequential no-motion simultaneous captures. A separate evaluator re-probed
the raw videos and owned the verdict.

Budget and authority:

- six of six required trials used;
- zero replacements, retries, robot motions, and provider calls;
- no simulator replay, training, promotion, metric-depth, or task authority;
- FFmpeg SHA-256 `0a96da2735695308d964e25fa6f4a0db2e9d24031390360f4c5ff96a4f8938e`;
- FFprobe SHA-256 `68447e67105534f3f43b95c94983ed56fbdd7125e5724cc56499ad538c2b86a7`.

Every D405 source completed normally through stdin `q`, finalized in
`0.72–0.96 s`, and produced 201–202 frames with monotonic 5 fps container PTS,
zero inferred missing intervals, and no source stall. The macOS log contains
no D405 USB removal during the campaign.

The evaluator nevertheless returned
`reject_stationary_capture_reliability`: all six C922 containers contained
29–30 inferred missing 30 fps intervals. Read-only frame-level PTS inspection
located the gaps at the D405 stream lifecycle boundaries:

| Trial | C922 open-side gap | C922 close-side gap |
| --- | --- | --- |
| 01 | `0.466667 → 0.966667 s` | `41.366667 → 41.933333 s` |
| 02 | `0.433333 → 0.933333 s` | `41.566667 → 42.100000 s` |
| 03 | `0.433333 → 0.933333 s` | `41.366667 → 41.933333 s` |
| 04 | `0.433333 → 0.966667 s` | `41.566667 → 41.733333 s` and `41.766667 → 42.133333 s` |
| 05 | `0.500000 → 1.000000 s` | `41.400000 → 41.966667 s` |
| 06 | `0.466667 → 1.000000 s` | `41.600000 → 42.133333 s` |

The D405 session begins about `1.0 s` after the C922 session. Its action window
ends near C922 PTS `41.02–41.05 s`, and D405 finalization ends during the
second C922 gap. This is evidence of camera-service/lifecycle coupling in the
encoded C922 timeline. It is not a device-clock measurement or proof that the
camera failed to expose those images.

Content-addressed evidence:

- campaign SHA-256
  `57d4983c73543bb6b675447cb9f5c3e0d60a2035ad06806cf79d48437c4cf2cf`;
- evaluation file SHA-256 and canonical digest
  `80ed9ac3608c0f95353a95dd83e3cb87959d273885f4415e483e8074c6828cde`;
- receipt file SHA-256
  `cfc11ff377730c137211ea41758ddd4da150a8b4d108f825a0619c7a7d453733`;
- embedded receipt digest
  `294f30661f4d5967b90b88f3692d5856537e4c7e05aa1801ae9e642d1b84ee58`;
- 36 raw artifacts bound by the receipt.

## Decision

Software-side fail-closed handling is implemented, but the frozen stationary
dual-camera campaign is a terminal negative. It is not retried and its
zero-gap threshold is not changed after results. Before a new motion packet can
address Twin fidelity, the D405 cable/connector path needs physical
reseating/replacement and strain relief, and the host capture path needs a
separately preregistered lifecycle-safe dual-camera qualification. Geometry,
metric depth, force/load, synchronized device timing, and strict held-out task
consequence remain open measurement prerequisites.
