# AVFoundation Dual-Camera Common Session v1 Preregistration

Date: 2026-07-24

Baseline: `049c5da55a203780ad20a2ef9711480125702286`

This transaction freezes one native metadata-only common session before
implementation. It uses the evaluator-selected D405 424×240 `2vuy` 5-fps
candidate and verified C922 640×480 `420v` 30.00003000003-fps candidate as two
inputs/two outputs in exactly one `AVCaptureSession`.

Budget is one stationary 11-second session, zero retries/replacements,
independent camera sessions, containers, robot motions, simulator replays, and
provider calls. No observer/evaluator implementation exists and no session has
started. A pass is callback-health evidence only; a failed input/output
admission routes to an isolated camera host.
