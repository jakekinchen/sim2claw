# Reviewer decision 039: Q00 board-side diagnosis

Date: 2026-07-27

Decision: `CONTINUE`

Evidence anchor: `100`

## Independent check

The review rebuilt `CURRENT_TASK_PIECE_LAYOUT` directly, applied every
per-joint manifest transform entry with the scalar formula
`sign * source * scale + zero_offset`, and asserted the resulting site/base
and pinch/neck minima to `1e-9 mm` absolute tolerance without calling the
executor's vector transform helper.

Observed:

```text
site_base c2=265.275519@434 c8=80.897091@242 c7=100.783880@270
pinch_neck28 c2=257.506340@435 c8=64.673854@242 c7=85.525518@270
independent_transform_formula_check=PASS
```

## Acceptance audit

- Immutable C2 tensor and hashes identified: pass.
- Current compiled task scene and candidate manifest identified: pass.
- Perfect-tracking FK used without dynamics, clipping, or action mutation:
  pass.
- C2, C8, and C7 minima reported with explicit observable definitions: pass.
- Approximately six-rank categorical error assessed: confirmed.
- Exact code/config source identified: pass.
- No robot motion or non-document mutation: pass.

The accepted conclusion is deliberately narrower than “the entire
registration is fixed.” A categorical rank-side correction is necessary, but
the `52-65 mm` best corrected-side residual shows that it is insufficient.
Q01 may freeze the zero-motion registration split. Q02 may not inspect Q01
held-out evidence before freezing its candidate family.
