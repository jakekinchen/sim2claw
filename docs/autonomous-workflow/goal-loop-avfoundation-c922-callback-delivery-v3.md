# Goal Loop — AVFoundation C922 Callback Delivery v3

## Mission

Test the single remaining mechanism exposed by callback-delivery v2: whether
holding the associated C922 device configuration lock through session commit,
initial session start, and immediate post-start verification prevents
AVFoundation from replacing the frozen `640×480 420v` format at start.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity goal.
2. Reviewed clean `main@56fc242dc0b28af853663cb8b1b7228181db441c`.
3. Callback-delivery v2 terminal-degraded evidence and independent PASS review.
4. The macOS 26.5 SDK `AVCaptureDevice` lock semantics.
5. The sealed format-inventory v2 candidate.
6. `configs/evaluations/avfoundation_c922_callback_delivery_v3.json`.
7. Exact committed v3 observer and independent evaluator.

## Intended Outcome

One C922-only observation repeats the v2 graph and exact format but changes
only the device-lock lifetime. The observer acquires the lock after input and
output association, sets the exact format/durations, keeps the lock through
commit and `startRunning()`, records active format and preset at each stage,
then unlocks before the callback window. Any pre-start or post-start mismatch
stops fail closed without repair.

## Acceptance Criteria

1. Preserve all S2/HIL, format-inventory, callback v1, and callback v2 evidence
   byte-identically.
2. Commit this prompt and v3 contract before implementation or camera use.
3. Keep the same device, format, durations, output request, duration, and
   evaluator thresholds as v2.
4. Change only the lock lifetime; do not assign a session preset or add output
   dimension conversion keys.
5. Use one observation, at most one ten-second C922 session, and no retry.
6. Record lock-held status, active format, durations, and session preset before
   commit, after commit, and after start.
7. Unlock only after post-start recording and before the sustained callback
   window.
8. If format identity fails before start, abstain without starting. If it fails
   after start, stop immediately and report degraded.
9. Observer artifacts remain typed, primitive-only, non-scoring, and unable to
   promote.
10. Evaluator owns validation, thresholds, verdict, aggregation, and
    replay/substitution/mutation rejection.
11. No D405, robot, simulator, provider, training, promotion, metric-depth, or
    task authority.
12. Focused static/synthetic tests plus fresh read-only review are sufficient;
    no broad repository suite.

## Evidence Standard

Report all three lifecycle identities and lock states, preset raw values,
output/drop counts, PTS statistics, delivered formats, exact budgets/hashes,
verdict, failed gates, and unchanged frozen evidence. The proof class remains
`camera_source_callback_delivery`.

## Decision Status

### Confirmed

- V2 associated input/output before setting the exact active format.
- V2 preserved that format through commit.
- V2 unlocked before commit/start and retained preset
  `AVCaptureSessionPresetHigh`.
- `startRunning()` changed the device to `1920×1080 420v` at about 24 Hz.
- V2 is exhausted and cannot be retried.

### Assumptions

- The start-time override may require exclusive device configuration access to
  remain held until the session has fully started.
- The device lock is a distinct mechanism from graph configuration atomicity.

### Recommended Defaults

- Preserve every v2 identity, budget, and evaluation threshold.
- Set no session preset and no output width/height keys.
- Bound the observer process so a blocked start becomes a terminal
  prerequisite abstention, not a retry.

### Open Questions

- Resolved: `startRunning()` preserves the exact device format while the
  configuration lock is held.
- Resolved: the session preset getter remains `.high`; the lock window, not a
  preset change, prevented override.
- Resolved: steady-state cadence is near 30 fps, but the first scored PTS
  interval was 66 ms and failed the unchanged strict maximum.
- Open: whether a separately preregistered warm-up before the scored window
  yields continuous in-gate cadence without hiding later gaps.

## Execution Rhythm

1. Commit prompt/contract.
2. Implement/typecheck/test without camera.
3. Commit exact v3 bytes.
4. Reconfirm frozen evidence and unused output root.
5. Execute one bounded observation, evaluate once, seal, review, stop.

## Progress Ledger

```text
Current state: Terminal degraded on cadence only; one-session budget exhausted.
Completed: Preregistration d6c1a08; exact implementation a779dc5; one observation/evaluation.
Evidence: raw df6aac8d; evaluation b4cc0037; receipt 276611fd / digest 7c596566.
Remaining: Seal state/log and obtain fresh read-only review.
Blockers: First PTS interval 66 ms; remaining 303 intervals passed the 50 ms gate.
Next step: Separately preregister a warm-up-bounded measurement window.
```
