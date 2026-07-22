# 2026-07-20 B--G contact sensitivity and publication gate

Commands:

```text
uv run --offline python scripts/run_pawn_bg_contact_sensitivity.py
uv run --offline python scripts/run_pawn_bg_publication_gate.py
```

The previously frozen rubber-tip prior ensemble was replayed after the selected
timing and deadband mechanisms. All four variants retain exact source actions,
reach 11/11 simulated contact, and remain 0/11 strict success. Lift spans only
2--3/11. The high prior improves mean final target distance to 30.5 mm, but no
variant is selected because the retained videos do not authoritatively label
physical grasp, lift, retention, force, or transport.

The composite receipt binds nine evidence artifacts, their SHA-256 values and
regeneration commands, a deterministic 10,000-replicate whole-episode bootstrap,
and the publication summary figure. It accepts timestamp alignment/110 ms and
the 2-degree deadband as diagnostics, rules out reset semantics as the primary
gap, and emits:

`TERMINAL_NEGATIVE_CONTACT_RETENTION_AND_TRANSPORT_UNDERIDENTIFIED`

Simulator composite promotion, training admission, physical accuracy, policy
promotion, and physical transfer all remain false.

Artifacts:

- `outputs/pawn_bg_contact_sensitivity_v1/contact_sensitivity_receipt.json`
- `outputs/pawn_bg_publication_gate_v1/publication_gate_receipt.json`
- `outputs/pawn_bg_publication_gate_v1/publication_summary.png`
