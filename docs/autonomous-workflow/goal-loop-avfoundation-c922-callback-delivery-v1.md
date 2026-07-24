# Goal Loop — AVFoundation C922 Callback Delivery v1

## Mission

Measure whether the exact C922 AVFoundation candidate selected by the sealed
format-inventory v2 evidence actually produces native source callbacks with
the declared format and bounded cadence. Keep this camera-only measurement
separate from D405 lifecycle, container timing, physical exposure,
cross-camera synchronization, robot, simulator, and task evidence.

## Ordered Source of Truth

1. The owner's request to advance Twin fidelity using evaluator-owned
   measurement rather than additional ungated simulator search.
2. Clean local `main` at
   `7ad9757fb7d23d52f24635b4d4d234b1fe2983e0`.
3. The sealed AVFoundation format-inventory v2 raw observation, evaluation,
   and receipt.
4. `configs/evaluations/avfoundation_c922_callback_delivery_v1.json`.
5. Apple AVFoundation/CoreMedia APIs and the exact committed Swift observer
   and Python evaluator.
6. `GOAL.md`, project state, orchestration ledger, and run logs.

## Intended Outcome

One exact-name C922 capture session requests format index `16`, range index
`0`, `640×480`, subtype `420v`, and frame duration
`0.03333330000003333 s`. A typed observer records session state, the applied
format, output/drop callbacks, sample PTS/duration, callback host time, and
delivered format. A separate evaluator verifies identities and reports either
verified callback delivery, degraded callback delivery, or prerequisite
abstention. A result does not reclassify any sealed D405/container result.

## Acceptance Criteria

1. Preserve all eleven S2 files and both HIL campaign states byte-identically.
2. Commit this prompt and contract before implementing or opening a capture
   session.
3. Bind the sealed v2 inventory candidate, raw/evaluation/receipt hashes,
   exact device name, unique ID, model ID, format/range indices, dimensions,
   subtype, supported FPS, and frame duration.
4. Use exactly one observation attempt and at most one ten-second C922-only
   capture session; no retry or replacement observation.
5. Do not open or reset the D405, invoke the robot gateway, move a robot, run
   the simulator, call a provider, train, or promote.
6. The observer emits Codable primitive-only artifacts and never scores,
   promotes, or changes thresholds.
7. The evaluator alone owns validation, continuity thresholds, verdict, and
   aggregation. It rejects identity drift, malformed/non-finite fields,
   noncontiguous sequences, duplicate/replayed events, format substitution,
   budget drift, and evaluator/source/binary mutation.
8. Verified delivery requires at least `240` output callbacks, zero dropped
   callbacks, exact delivered dimensions and subtype on every output,
   strictly increasing numeric PTS, and no PTS interval above `1.5` times the
   frozen nominal interval.
9. A valid session with samples that misses a continuity gate is
   `callback_delivery_degraded`, not fabricated success. Missing identity,
   authorization, session startup, raw evidence, or all samples is
   `prerequisite_abstention`.
10. Bind the committed contract, source, evaluator, compiler, binary,
    prelaunch manifest, raw observation, evaluation, and receipt by SHA-256.
11. Repeated evaluation materialization is byte-identical; generated outputs
    remain ignored.
12. Run only focused static/unit proof plus the one live observation and fresh
    read-only review. A broad repository suite is not required for this
    isolated measurement transaction.

## Evidence Standard

Report exact commits/trees; source/evaluator/compiler/binary hashes; device and
active-format identity; session count and duration; output/drop counts; PTS
interval statistics; delivered dimensions/subtypes; verdict and failed gates;
receipt digest; unchanged frozen evidence; and closed authorities. Call this
`camera_source_callback_delivery`, never physical-exposure continuity,
cross-camera synchronization, metric calibration, simulator fidelity, or task
success.

## Decision Status

### Confirmed

- Format-inventory v2 observed 33 formats and 209 ranges in one exhausted
  read-only observation.
- Its evaluator selected format index `16`, range index `0`, `640×480`,
  subtype `420v`, at `30.00003000003 fps`.
- The earlier 12-attempt source-localization family delivered zero samples
  because its integer-30 request could not select this fractional-rate format;
  that family remains exhausted and is not reused.

### Assumptions

- The exact C922 device and selected native format remain present.
- A ten-second session is sufficient to distinguish callback delivery from
  the former pre-session format-selection failure.

### Recommended Defaults

- One attempt, one ten-second session, no retry.
- `240` minimum outputs and `1.5×` nominal maximum PTS interval.
- Preserve degraded measurements rather than tuning gates after observation.

### Open Questions

- Whether the selected candidate can be applied and the session started.
- Whether delivered callbacks retain `640×480` `420v`.
- Whether source PTS is continuous under C922-only operation.

## Execution Rhythm

1. Freeze and commit prompt plus contract.
2. Implement typed observer and independent evaluator without opening camera.
3. Run focused synthetic/static tests and commit exact implementation.
4. Reconfirm identities and frozen evidence.
5. Execute the sole bounded observation once.
6. Evaluate once, freeze receipt/state, obtain read-only review, and stop.

## Progress Ledger

```text
Current state: Preregistration drafted before implementation and camera access.
Completed: Frozen v2 candidate and prior exhausted-family boundaries reconciled.
Evidence: v2 inventory raw 3754a62f; evaluation 3c59915c; receipt 14c8f821.
Remaining: Commit preregistration; implement/test; commit exact identities; execute one observation; evaluate and close.
Blockers: None before implementation. Any identity or authorization drift forces abstention without retry.
Next step: Commit this prompt and contract before authoring the observer.
```
