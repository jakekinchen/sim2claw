# Brief 033: actuator-response external validation

Decision: `CONTINUE`

Evidence anchor: `100` — the recovered five-recording cohort is now
hash-complete and the existing sim/real bridge admits its 2,186 rows for
joint-response diagnostics only.

## Required outcome

Evaluate the already-selected action-frozen actuator response model once on
the recovered cohort without reopening model selection. Keep raw execution,
external evaluator aggregation, and the existing strict task consequence
receipt separate.

## Frozen slice

- Selection source: existing 11-episode, four-fold 100 mm load-response
  campaign.
- External evaluation source: exactly five recovered 72 mm recordings.
- Variants: current baseline and selected 110 ms
  delay/deadband/load-response candidate.
- Budget: 10 simulator replays, zero retries.
- External gate: at least 2% pooled joint-RMS improvement, at least 4/5
  episodes improved, positive 95% whole-episode bootstrap lower bound, and no
  pooled EE regression.
- Task gate: read-only verification of the existing independent consequence
  receipt; strict success remains evaluator-owned.

## Stop conditions

- Stop on any source/hash/action/config/evaluator drift.
- Do not repair a failing candidate or widen the family after results.
- Do not use the older board pixels or labels for current spatial, contact, or
  task evidence.
- Do not run physical hardware, capture, training, provider, C2, or another
  simulator family.
