# SAIL Contract Freeze Run Log

Date: 2026-07-21

Milestone: P1-01

Proof class: deterministic fixture and contract infrastructure

## Commands

```bash
uv lock --check
uv run python -m compileall -q src/sim2claw/sail tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py
uv run pytest tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py -q
uv run pytest -q
uv run pytest tests/test_pawn_composability_eval.py::PawnComposabilityEvaluationTest::test_replay_limit_audit_binds_sources_and_internal_arithmetic tests/test_retrospective_publication.py::test_provider_campaign_is_frozen_dry_run_without_secret_values tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py -q
git diff --check
```

## Frozen identities

- `CalibrationEvidence.v1`: `1806dc96b1d14f97d307b41d3247669368b71167387816d162d50f6ef44395b2`
- `ResidualField.v1`: `5e659fb5a5a402f94ba446bb3f6df5b8919ac87aa3926878b50ac44f79f7b6b1`
- `PhysicalMechanism.v1`: `0192cd393cf2a94c91838eb1c8d81c34712b9a562d551aa6ab896db45eff3df5`
- `Intervention.v1`: `b2c8251b99d1ecdf48d5541338c5c549c3f001c81b7d1aec620540c3710d6d40`
- `TwinWorthinessCertificate.v1`: `0cf6abb6472310106ddbe945a2d444994bf2d2d87d733ca077e304f629852c10`
- Benchmark: `fe93329c09c76032a0192ef79d4edea6a989e9c27a825747202a1d5a8079a0cc`
- TwinWorthiness: `0e4828802daa54301779621a8af1ff48e99920a84d594fa12a6c72d5ede7c9e1`
- Proof vocabulary: `53b6889fd0dc5ae04c668869649b0f0aca7ed8eb28d6bc2fedede8529a63a046`
- CI tiers: `fb5edbec8cd7593a7520ac1556a7cea07f5f1b45706668ddadd684f08b01e471`
- Golden registry: `a727a189285703dde745991979f856ca23ed1fa47b8cd08c071e6c8ba09ca514`
- Sealed seed manifest: `4e868d331734cfefa33bd6c195226a187a40fd8bb37bea637c61ddcb83c1eb9d`

## Result

P1-01 accepted. All prospective benchmark and certificate semantics are frozen;
no prospective result has been generated. No external resource was opened.
