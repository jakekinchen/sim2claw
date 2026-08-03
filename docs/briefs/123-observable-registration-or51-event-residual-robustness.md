# OR51 — Outcome-success robustness and event-residual audit

Decision: `CONTINUE`

Evidence anchor: `100` — OR50 has a byte-reproduced numeric task success, but
the selected trace fails four event-shape requirements and has no bilateral jaw
contact.

## Required outcome

Audit the already-generated OR50 candidate surface and selected rerun trace to
decide whether the numeric success is locally continuous and event-causally
compatible. Do not execute MuJoCo, fit or select a parameter, open held-out
evidence, or alter the OR50 evaluator.

## Frozen gates

- The OR50 selected coordinate and both immediate `0.01 mm` neighbors must each
  retain numeric task success and the same seven-element terminal gate vector.
- The selected trace must contain named contact from both jaw surfaces.
- All five OR50 preterminal gates must pass: contact timing, no early motion,
  support-loss timing, bilateral-contact timing, and sample-260 uprightness.
- OR50 selection and verification result digests must remain identical.
- The audit must use zero simulator replays, zero hardware actions, and zero
  parameter changes.

## Terminal rule

If any gate fails, emit a deterministic terminal receipt that preserves OR50 as
an isolated outcome-informed diagnostic and routes the promotable path back to
OR48's independently metric load-side observation packet.
