# Goal Loop — AVFoundation C922 Callback Delivery v2

## Mission

Test the single mechanism exposed by callback-delivery v1: whether associating
the C922 input with `AVCaptureSession` before setting the frozen device format
preserves `640×480 420v` through session commit, session start, and delivered
sample buffers.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity goal.
2. Clean reviewed `main` at
   `5d62e15816aa4a1bd7902585a12aeb88ed2d4202`.
3. Callback-delivery v1 terminal-degraded raw evidence, evaluation, receipt,
   and independent PASS review.
4. The sealed format-inventory v2 candidate.
5. `configs/evaluations/avfoundation_c922_callback_delivery_v2.json`.
6. Apple AVFoundation/CoreMedia APIs and exact committed v2 observer/evaluator.

## Intended Outcome

One new C922-only observation configures the session in this frozen order:
begin session configuration; add input and output; lock the now-associated
device; set the exact format and frame durations; unlock; commit; verify active
format; start; verify active format again; observe delivered buffers. The
evaluator distinguishes configuration drift, post-start drift, output
dimension substitution, and cadence degradation.

## Acceptance Criteria

1. Preserve all S2/HIL evidence and callback v1 byte-identically.
2. Commit this prompt and v2 contract before v2 implementation or camera use.
3. Bind the same exact device and format-inventory candidate as v1.
4. Change only the falsified configuration/verification mechanism; do not
   relax v1's output-count, drop, dimension, subtype, or cadence gates.
5. Use one observation attempt, at most one ten-second C922 session, and no
   retry or replacement.
6. Record active device format and session preset raw value after input
   association, after commit, and after start, plus delivered sample format.
7. If exact format identity fails before start, abstain without starting the
   session. If it drifts after start or at output, stop and report degraded.
8. The observer remains typed, primitive-only, non-scoring, and unable to
   promote.
9. The evaluator alone owns validation, thresholds, verdict, aggregation, and
   mutation/replay/substitution rejection.
10. No D405, robot, simulator, provider, training, promotion, metric-depth, or
    task authority.
11. Focused synthetic/static tests and one fresh read-only review are
    sufficient; no broad repository suite.

## Evidence Standard

Report configuration-stage identities, session preset raw values, output/drop
counts, PTS statistics, delivered formats, exact budgets/hashes, verdict,
failed gates, and unchanged frozen evidence. This remains
`camera_source_callback_delivery`, not synchronization, calibration,
simulator fidelity, or task proof.

## Decision Status

### Confirmed

- V1 applied `640×480 420v` before session/input creation.
- Its 243 delivered buffers were all `1920×1080 420v`, with zero drops and
  approximately 24 Hz mean cadence.
- V1 is exhausted and cannot be retried.
- Apple platform headers state that setting `activeFormat` on a device
  associated with a session changes that session to input-priority behavior;
  direct assignment of the input-priority preset is unavailable on macOS.

### Assumptions

- Input association before `activeFormat` is the minimal mechanism that may
  prevent session commit from choosing a different device format.
- Recording format at each lifecycle stage can distinguish device drift from
  output conversion.

### Recommended Defaults

- Preserve the v1 candidate, duration, 240-output minimum, zero-drop gate, and
  1.5× nominal maximum PTS interval.
- Do not set output width/height conversion keys; request only `420v` and treat
  the delivered buffer description as authoritative.

### Open Questions

- Whether post-input `activeFormat` survives commit and start.
- Whether matching device format yields matching delivered dimensions/cadence.
- Whether output conversion remains despite stable device format.

## Execution Rhythm

1. Commit prompt/contract.
2. Implement/test without camera.
3. Commit exact v2 bytes.
4. Reconfirm frozen evidence and unused output root.
5. Execute one observation, evaluate once, seal, review, stop.

## Progress Ledger

```text
Current state: Preregistered design pending commit; no v2 implementation or camera use.
Completed: V1 terminal degraded and independently reviewed PASS.
Evidence: v1 raw 9e3e2d57; evaluation 25827c4d; receipt 2096d836 / digest 558aae78.
Remaining: Commit preregistration; implement/test/commit; one observation; evaluate; close.
Blockers: Any device/candidate drift forces abstention without retry.
Next step: Commit this prompt and contract.
```
