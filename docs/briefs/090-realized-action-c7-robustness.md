# Brief 090 — Realized-Action C7 Robustness

Decision: `CONTINUE`

Evidence anchor: `109`

## Active card

C7 from the realized-action outcome calibration queue.

## Required slice

Preserve the immutable C6 `0/1` result and evaluate only declared deterministic
challengers:

- direct gateway-sent target path;
- diagnostic `0.11 s` ZOH path;
- the already-consumed C6 identified path.

Use the same source, initialization, natural current-MuJoCo contact, and frozen
evaluator. Do not rerun C6's identified path. Do not create geometry/contact
distributions where C2/C5 supplied no identified bounds.

## Verification gate

- C6 receipt and implementation remain byte-unchanged.
- Challenger action tensors are hash-bound and source actions remain exact.
- Nominal and challenger results are separate.
- Unknown geometry/contact dimensions are reported unavailable, not randomized.
- Robust success cannot alter the C6 result.
- A deterministic generated receipt and tracked closeout exist.

## Handoff

Activate C8 causal proof packaging after the robustness result.
