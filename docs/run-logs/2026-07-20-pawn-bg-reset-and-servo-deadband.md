# 2026-07-20 B--G reset and servo-deadband ablations

Commands:

```text
uv run --offline python scripts/run_pawn_bg_reset_reference.py
uv run --offline python scripts/run_pawn_bg_servo_deadband.py
```

The first commanded and first measured states differ by only 0.068 degrees
overall RMS, with a 0.264-degree maximum on shoulder lift. First-commanded reset
wins every fold numerically but improves only 0.002% over first-measured, below
the frozen 0.5% materiality threshold. Model-default reset reaches 8.890 degrees
RMS. Reset/reference semantics are therefore ruled out as the primary gap and
the physically grounded first-measured reset is retained.

At the selected 110 ms timing, a constrained shared lift/elbow deadband grid
from 0 to 3 degrees selects 2 degrees in all four whole-episode folds. Pooled CV
joint RMS improves from 1.461 to 1.296 degrees (11.3%); EE RMS improves from
16.417 to 12.936 mm. Lift/elbow flat-response reproduction rises from
14.7%/9.9% to 69.6%/58.9%.

Unchanged-action consequence improves from 9/11 to 11/11 contact and from 0/11
to 2/11 lift, but remains 0/11 strict success. The 2-degree value is an accepted
simulator model-class diagnostic for deadband/compliance/gravity sag, not a
measured physical firmware parameter or composite promotion.

Receipts:

- `outputs/pawn_bg_reset_reference_v1/reset_reference_receipt.json`
- `outputs/pawn_bg_servo_deadband_v1/servo_deadband_receipt.json`
