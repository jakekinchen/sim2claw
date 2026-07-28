# Native dual-camera production recorder

Date: 2026-07-24

## Outcome

Commit `5515e5d` replaces the default physical Studio/teleop camera lifecycle
with one native `AVCaptureSession`. The process binds the exact C922 and D405
input ports to separate outputs, writes separate H.264 source containers, and
records every callback's stream role, source PTS, duration, format, and
`mach_continuous_time` value in one JSONL ledger. Finalization creates separate
browser MP4 derivatives and the saved recording receipt hashes each source,
derivative, metadata file, callback ledger, native report, source, compiler,
and runtime binary.

Simulation recording still uses the existing single C922 path. The injected
legacy two-recorder path remains available to tests, but it is not the default
physical production path.

## Post-stop gate audit

The frozen common-session result remains
`common_session_callback_delivery_degraded`; no raw artifact, threshold, or
verdict was changed. In raw observation
`f78c363d3e45f4f6a191d8156f047e338d4ee786c9cb47fe10ab58af3b6a44d5`,
both after-stop `format_index` values are `-1`, while both devices retain their
exact identities, dimensions, subtypes, frame durations, and explicit
input/output bindings. The `-1` comes from an object-identity lookup after
`stopRunning()`. It cannot alter already delivered sample buffers or finalized
writers and is therefore not a production acceptance gate.

Production admission instead requires the exact active-session device and
format, exact port binding, first post-warm-up frames from both streams, zero
Apple drop callbacks, zero writer backpressure, increasing source PTS, and
completed independently attributable writers.

## One bounded stationary verification

The initial recorder implementation session wrote ignored evidence under
`runs/native_dual_camera_verification/20260724-production-path`. It constructed
no robot gateway and issued no robot command.

| Fact | C922 | D405 |
| --- | ---: | ---: |
| callbacks | 323 | 56 |
| writer appends | 323 | 56 |
| Apple drops | 0 | 0 |
| writer backpressure | 0 | 0 |
| writer completed | yes | yes |

- Native report:
  `b6c156ecf4017bde9a6a20cee6730fcd3e4bedc570260be1ec26fa9b2b6ee3f1`
- Callback ledger:
  `a9b98b5656c11761700f56e092f27c53cbab44c085a0953d64419a87ea2356f4`
- C922 source:
  `508836b26b5e261611b598ea05d8ee5b46255bfef635ead3dda02c30152471a7`
- D405 source:
  `d88462fd9a588627b88f2968941a6bd222585cf8683683ed82fbde8bf71b2720`
- C922 browser derivative:
  `46ecb6bda68060d868a087d5e73137804d79644a059657f58059f2baedb944ff`

The session reproduced the irrelevant after-stop index reset. It also exposed
an operational issue absent from the metadata-only observer: the D405's first
callback has source PTS `0`, followed by the host-scale PTS sequence. Starting
an `AVAssetWriter` session at that sentinel created a 615,228-second MOV
timeline, so the D405 browser derivative failed.

The committed repair retains every startup callback in the provenance ledger
but excludes the already-established one-source-PTS-second visible warm-up
from both writers. No second camera session was opened. Offline processing of
the captured post-warm-up D405 frames produced 53 source frames and 53 browser
frames over 10.6 seconds:

- post-warm-up source:
  `98da0037fcd761a9c8368a007e974e0ed45b9d0aa4e57aaa433c3fafb74f4bf8`
- browser derivative:
  `e136e3bab825c036b118439325260c1c5268ce0a4b6f2324033830a77c6d362f`

## Post-repair production-path confirmation

One later stationary camera-only attempt exercised the committed warm-up
repair directly through `NativeDualCameraRecorder`. Exact macOS camera
identity matched the frozen C922 and D405 names, model IDs, and unique IDs;
the loopback Studio recorder was idle and no competing capture process was
present. The run constructed no robot gateway, issued no robot command, and
used no retry.

| Fact | C922 | D405 |
| --- | ---: | ---: |
| observed callbacks | 377 | 67 |
| warm-up callbacks retained but not written | 22 | 7 |
| source / browser frames | 355 / 355 | 60 / 60 |
| source duration | 11.833333 s | 12.000000 s |
| maximum written PTS interval | 0.034033 s | 0.200000 s |
| inferred missing intervals / large gaps | 0 / 0 | 0 / 0 |
| Apple drops / writer backpressure | 0 / 0 | 0 / 0 |

The D405 source-PTS `0` sentinel is present in the callback ledger and absent
from the writer. Both written streams are strictly increasing, both source
containers and browser derivatives finalized, and no timeline exceeds 12
seconds. A temporary standard receipt projection over the sealed files was
accepted by the existing Studio catalog as the separate
`overhead_workspace` and `wrist_gripper_upward` feeds with motion and physical
authority false.

- Generated evidence:
  `runs/native_dual_camera_verification/20260724-post-repair-production-path`
- Native report:
  `0fba6b3e2f426649bb05dd111c12344d24e961e316a619ac9e8621b8e846fcf0`
- Callback ledger:
  `662fcbf4aa9be9c38ea2f4bd44635af7632ae4c8cd37939aa259ecd37df03e77`
- C922 source / browser:
  `c819601643d4566a6a31edb9c23fade414e73dffbfd95cf28b3fdd70d53a186a`
  / `155a94a94b7cd520bc79b9473c78489685aca20c076eb1e43cf7c1b0e16a1c6c`
- D405 source / browser:
  `2c0b1b983c948a47a6d7f807cf49043bf87aabc7ecdeab82380cd132e3ea2e91`
  / `2988f6e048c79a06f1d0e1bab006c311110c8c2ce78a9c9304db692891fe947c`
- Acceptance:
  `f4e219265b2e973ec112814d77a6255165086d71cb18a6db4b7703a7ce0465aa`
- Receipt projection:
  `bbef833d50e3a60dbb00a2f34d884282f208cb948add4f48c1ab7946bbbe44b7`

The stationary production recorder capability is verified. Motion reliability
remains blocked on the physical D405 cable/connector/strain-relief repair.

## Next geometry inputs

The repository contains the nominal checkerboard SVG, but the input manifest
still has no printed-grid measurement receipt, focus value, or frames.
Therefore metric fitting is not presently admissible. Human action is required:

1. Print the 9×6-inner-corner target at fixed scale and mount it flat.
2. Measure the actual square pitch and full grid width/height in both axes;
   record the instrument, units, measurement points, and uncertainty. Do not
   substitute the nominal 20 mm and 200×140 mm design values.
3. Disable or otherwise hold C922 focus constant and record the observable
   focus setting used for every frame.
4. Capture at least 18 distinct 640×480 `420v` exact-mode frames with all 54
   corners detected: all five centroid regions, three board-scale bins, at
   least four tilted views, at least three near-frontal views, and all three
   orientation bins.
5. Freeze the accepted frames into 12 fit, 3 validation, and 3 held-out views
   before any model fit.

The exhausted empty-manifest evaluation was not rerun and no calibration model
was fit.

## Focused verification

- Swift production helper compiled with `/usr/bin/swiftc`.
- `54 passed, 2 subtests passed`:
  native recorder, teleop recording, Studio catalog/live workspace, container
  timing, and legacy diagnostic video.
- New-module Ruff check passed.
- Consolidated calibration/recorder/Studio focused bracket:
  `52 passed`.
- Evaluator-owned exact-mode calibration focused bracket:
  `13 passed`.

## Proof boundary

This is recorder infrastructure. It does not establish exposure
synchronization, metric depth, calibration, reliable capture under robot
motion, task success, simulator fidelity, training admission, or physical
authority. Twin fidelity remains `0/6` and the strict task score remains
`0/11`.
