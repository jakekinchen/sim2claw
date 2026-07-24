# Goal Loop — AVFoundation Dual-Camera Common Session v1

## Mission

Test one concrete lifecycle-isolation mechanism: bind the exact D405 and C922
as two inputs/two metadata outputs in one native `AVCaptureSession`, hold both
format locks through start verification, and measure stationary callback
delivery without independent camera open/close transitions.

## Ordered Source of Truth

1. The owner's evaluator-owned Twin-fidelity closure objective.
2. Exact baseline `049c5da55a203780ad20a2ef9711480125702286`.
3. Sealed D405 inventory, C922 callback v4, and nested-lifecycle receipts.
4. `configs/evaluations/avfoundation_dual_camera_common_session_v1.json`.
5. Exact committed observer/evaluator/runtime identities.
6. `GOAL.md`, project state, orchestration ledger, and run logs.

## Intended Outcome

One stationary metadata-only native common session either verifies exact-format
bounded callbacks from both cameras or seals the precise admission/delivery
failure. No container, robot, simulator, provider, or task authority is opened.
No result is called synchronized exposure or motion reliability.

## Acceptance Criteria

1. Preserve all frozen S2/HIL/camera outputs byte-identically.
2. Commit prompt/contract before observer/evaluator implementation or session.
3. Use exactly one `AVCaptureSession`, two exact device inputs, and two
   `AVCaptureVideoDataOutput`s. No separate per-camera session/lifecycle.
4. Freeze D405 format 0/range 4, 424×240 `2vuy` at 5 fps and C922 format
   16/range 0, 640×480 `420v` at 30.00003000003 fps.
5. Hold both device locks through input/output association, commit, start, and
   immediate post-start format verification.
6. Emit typed callback/drop/lifecycle metadata only. Do not encode video.
7. The independent evaluator owns identity, admission, exact-format, window,
   callback, PTS, drop, interval, budget, and verdict checks.
8. Keep the first source-PTS second visible as warm-up per stream; score the
   frozen remaining window. Require at least 285 C922 and 48 D405 measurement
   callbacks, 9.5 seconds common host span, zero drops, and maximum intervals
   0.049999950000049996 and 0.3 seconds respectively.
9. Add adversarial tests for device/output substitution, missing second input,
   independent-session use, lifecycle/format mutation, malformed callbacks,
   method/self-score injection, threshold/budget mutation, replayed roots, and
   byte-identical evaluation.
10. Commit exact implementation before one session. No retry, replacement,
    threshold change, robot motion, simulator replay, or provider call.
11. Seal hashes/state/review. A failure routes to an isolated camera host; a
    pass routes to production writer integration before motion qualification.

## Evidence Standard

Report exact commits/trees and all contract/source/evaluator/compiler/binary,
prelaunch, attempt, raw, evaluation, and receipt hashes; admission stages;
per-stream callback/drop/count/span/interval metrics; budget; tests; frozen
evidence; verdict; and closed authority.

## Decision Status

### Confirmed

- The D405 has an evaluator-selected exact 424×240 `2vuy` 5-fps candidate.
- The C922 has verified exact-format steady callbacks after one-second warm-up.
- Independent FFmpeg lifecycles still produced a D405 gap near the reverse
  boundary; that family is exhausted.

### Assumptions

- Standard macOS `AVCaptureSession` may admit two external video inputs and
  outputs. The observer must ask `canAddInput`/`canAddOutput`; this is not yet
  evidence.

### Recommended Default

- Attempt the single native common session. If the second input/output cannot
  be admitted, seal prerequisite abstention and switch to an isolated host.

### Open Questions

- Whether one standard session admits both exact external inputs/outputs.
- Whether both active formats survive start simultaneously.
- Whether source callback cadence remains bounded for both streams.

## Execution Rhythm

1. Commit preregistration.
2. Implement/test without device access.
3. Commit exact bytes and obtain pre-session review.
4. Execute one stationary callback session.
5. Evaluate once, seal, and choose production integration or isolated host.

## Progress Ledger

```text
Current state: Preregistered before implementation or session.
Completed: D405 and C922 format/cadence inputs are frozen.
Evidence: D405 receipt fb4e76d9; C922 receipt 7354ce1d; baseline 049c5da.
Remaining: Implement observer/evaluator, review, execute once, seal.
Blockers: Common-session two-input/two-output admission is unverified.
Next step: Implement the typed observer and independent evaluator.
```
