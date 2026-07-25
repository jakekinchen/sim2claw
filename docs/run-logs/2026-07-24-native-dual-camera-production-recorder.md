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

The only camera session used by this task wrote ignored evidence under
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

The exact remaining step is one camera-only production recording through the
post-warm-up implementation, confirming both native and browser outputs from
the current code. This task's one-session limit is exhausted.

## Focused verification

- Swift production helper compiled with `/usr/bin/swiftc`.
- `54 passed, 2 subtests passed`:
  native recorder, teleop recording, Studio catalog/live workspace, container
  timing, and legacy diagnostic video.
- New-module Ruff check passed.

## Proof boundary

This is recorder infrastructure. It does not establish exposure
synchronization, metric depth, calibration, reliable capture under robot
motion, task success, simulator fidelity, training admission, or physical
authority. Twin fidelity remains `0/6` and the strict task score remains
`0/11`.
