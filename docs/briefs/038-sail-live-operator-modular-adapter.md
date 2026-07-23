# Brief 038: modular SAIL live operator and trusted fixture adapter

## Milestones

Advance D4 and D5 from
`docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md`.

## Required outcome

Extract the retained SAIL live operator into reviewable contract, decision,
state, receipt, runtime, and adapter modules without changing its retained C2
abstention artifacts. Remove the disabled simulator-receipt public parameter.
Add one registered, deterministic fixture adapter whose request contains no
result or consequence and whose reviewed code derives and revalidates the
mutation, response, likelihoods, factor updates, and consequence.

## Allowed paths

- `src/sim2claw/sail/live_*.py`
- `src/sim2claw/cli.py`
- `configs/sail/schemas/trusted_*.json`
- `configs/sail/migrations/live_operator_modularization_v3.json`
- `tests/test_sail_live_operator.py`
- `tests/fixtures/sail/trusted_adapter_fixture_v1.json`
- current goal/state/ledger and this slice's session/reviewer records

## Frozen boundaries

- The retained C2 action, evaluator, intervention set, and consequence gates
  stay unchanged.
- Generic caller-authored simulator receipts remain disabled.
- The adapter registry contains no campaign, mechanism, or intervention ID
  whitelist. Only reviewed adapter implementations are registered.
- A request may bind raw fixture input but cannot supply a result, mutation,
  factor update, likelihood, or consequence.
- The fixture adapter is development evidence only. It does not authorize a C2
  family, simulator promotion, training, provider use, capture, gateway access,
  or robot motion.
- Canonical campaign state remains global, locked, append-only, budgeted, and
  independent of output directories.

## Acceptance evidence

- `live_operator.py` is a small public facade over extracted modules.
- Retained v2 and v3 runs have byte-identical hashes for all 14 non-receipt
  artifacts; the versioned migration receipt names the four intentionally
  changed receipt fields and both API changes.
- Frozen JSON schemas cover the result-free request, raw fixture, and fixture
  adapter contract with additional properties rejected.
- Execution and read-time verification independently recompute the trusted
  result from the frozen contract and raw fixture.
- Focused tests cover no-request abstention, one-use budget accounting,
  caller-result injection, changed mutation/evaluator/config/action/source
  identity, fixture and adapter substitution, authority widening, stale
  implementation receipts, state replay, locking, interrupted writes, and
  cleanup.

## Stop conditions

Stop for retained-output drift without an exact migration account, an
unrecomputed consequence, a path or authority escape, an unexpected branch or
remote divergence, or any request to open C2/provider/training/physical work.
