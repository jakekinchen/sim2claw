# SAIL/ClawLoop Phase 1 Reproduction Map

## Canonical build

```bash
uv sync --frozen
uv run sim2claw sail-compile-publication \
  --config configs/sail/publication_campaign_v1.json \
  --output outputs/sail/publication-v1
```

The command verifies all 25 exact source bindings and every upstream receipt
before compiling. It does not invoke a provider, open a device, train a policy,
or access hardware. Owner-local ignored evidence must be present at the hashes
in the publication config. In a clean checkout without those bytes, the
retained-evidence path must skip or fail closed; it must not substitute fixture
zeros.

## Verification

```bash
uv run pytest tests/test_sail_publication.py tests/test_sail_cli.py -q
uv run pytest tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py -q
uv run pytest tests/test_sail_mechanisms.py tests/test_sail_belief_graph.py tests/test_sail_influence.py tests/test_sail_invariance.py tests/test_sail_acquisition.py tests/test_sail_loop_closure.py tests/test_sail_benchmark.py -q
uv run pytest tests/test_sail_agent_campaign.py tests/test_sail_capability_campaign.py tests/test_sail_policy_flywheel_campaign.py tests/test_learning_factory.py tests/test_sail_cli.py tests/test_studio.py tests/test_sail_studio_observatory.py tests/test_sail_publication.py -q
uv run pytest
git diff --check
```

Provider and hardware tiers remain manual, budgeted or separately authorized,
and are not needed to reproduce Phase 1. Their absence is a result boundary,
not an invitation to bypass the gate.

## Receipt roots

| Result lane | Canonical ignored artifact |
|---|---|
| seeded public/sealed benchmark | `outputs/sail/seeded-benchmark-v1/` |
| governed agent campaign | `outputs/sail/inspect-campaign-v1/` |
| retained retrospective case | `outputs/sail/retired-workcell-case-v1/` |
| prospective simulator experiment | `outputs/sail/prospective-sim-v1/` |
| TwinWorthiness capabilities | `outputs/sail/twin-capability-v1/` |
| policy flywheel | `outputs/sail/policy-flywheel-v1/` |
| Studio observatory | `outputs/sail/studio-observatory-v1/` |
| publication package | `outputs/sail/publication-v1/` |

The machine-readable `reproduction_map.json` records each source path, digest,
tracked/ignored status, automatic CI command, sealed-data boundary, and the
canonical regeneration command. `receipt.json` binds all 24 generated package
outputs plus the config, compiler, and source inventory.

## Determinism and statistics

- Eight seeded cases are paired by exact case ID.
- Ten thousand bootstrap replicates use the frozen seed `2026072217`.
- Retained data are resampled only by whole episode.
- Effect sizes are paired risk difference and matched rank-biserial effect.
- Secondary comparisons use Holm-Bonferroni correction.
- Missing provider, physical, policy-rank, or invariance results remain
  `not_evaluable` or unavailable; they are never converted to zero successes.
- Public and sealed bytes remain disjoint, sealed labels remain evaluator-only,
  and method actions/evaluator state remain unchanged.
