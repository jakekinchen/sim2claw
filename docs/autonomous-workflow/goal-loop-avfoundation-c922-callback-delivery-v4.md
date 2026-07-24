# Goal Loop — AVFoundation C922 Callback Delivery v4

## Mission

Determine whether the sole v3 cadence failure is confined to startup by
scoring an unchanged ten-second callback window after a fixed one-second
source-PTS warm-up, while retaining and reporting every callback, format, and
drop from the full session.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity goal.
2. Exact `main@1ff887e`.
3. Callback-delivery v3 sealed evidence and fresh independent PASS review.
4. The byte-identical v3 lock-through-start Swift observer.
5. The sealed format-inventory v2 candidate.
6. `configs/evaluations/avfoundation_c922_callback_delivery_v4.json`.
7. Exact committed v4 evaluator/runtime binding.

## Intended Outcome

Reuse the proven v3 observer bytes for one eleven-second C922-only session.
The evaluator defines the first source-PTS second as warm-up before observation
and scores cadence only among callbacks at or after that frozen boundary. It
still requires exact format, numeric/strict PTS, and zero reported drops across
the entire session.

## Acceptance Criteria

1. Preserve S2/HIL, inventory, and callback v1-v3 evidence byte-identically.
2. Commit this prompt/contract before v4 evaluator implementation or camera use.
3. Reuse v3 Swift source byte-identically; do not change its lock mechanism.
4. Freeze one source-PTS second of warm-up and a ten-second target measurement
   window before observation.
5. Report warm-up and measured intervals separately; never erase warm-up data.
6. Keep the unchanged 1.5× nominal maximum interval gate in the measurement
   window.
7. Require exact `640×480 420v`, numeric/strict PTS, and zero Apple drop
   callbacks across the full session.
8. Use one observation, one session, eleven seconds maximum, and no retry.
9. Evaluator alone owns the boundary, thresholds, verdict, and aggregation.
10. No D405, robot, simulator, provider, training, promotion, task, or transfer
    authority.
11. Focused static/synthetic tests and fresh read-only review are sufficient.

## Evidence Standard

Report full-session and measured counts, spans, warm-up and measured interval
statistics, exact formats, drops, lifecycle identities, budgets, hashes,
verdict, failed gates, and frozen evidence. This can verify a production
pre-roll callback window, not exposure continuity or simulator fidelity.

## Decision Status

### Confirmed

- V3 repaired the start-time format override.
- All 305 v3 callbacks were exact `640×480 420v`.
- Exactly one PTS interval failed, at interval index zero.
- The remaining 303 intervals passed the unchanged maximum.
- V3 is exhausted and cannot be retried.

### Assumptions

- A one-second source-PTS pre-roll is a deployable recording behavior, not an
  evaluator-only exception.
- If gaps recur after warm-up, source cadence remains degraded.

### Recommended Defaults

- One-second source-PTS warm-up.
- Ten-second target measurement window.
- Preserve all v3 thresholds and format/authority gates.

### Open Questions

- Whether all measurement-window intervals satisfy the 50 ms maximum.
- Whether the full session remains exact format with zero reported drops.

## Execution Rhythm

1. Commit prompt/contract.
2. Implement/test evaluator and runtime binding without camera.
3. Commit exact bytes.
4. Gate on v3 review PASS, frozen evidence, and unused output root.
5. Execute/evaluate one observation, seal, review, stop.

## Progress Ledger

```text
Current state: Preregistered design pending commit; no v4 evaluator or session.
Completed: V3 exact-format delivery with one startup cadence gap.
Evidence: v3 raw df6aac8d; evaluation b4cc0037; receipt 276611fd / digest 7c596566.
Remaining: Commit; implement/test/commit; v3 review gate; one observation; close.
Blockers: Any frozen-evidence drift forces abstention.
Next step: Commit this prompt and contract.
```
