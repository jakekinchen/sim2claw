# Executor session 029: modular live operator and trusted fixture adapter

Date: 2026-07-22

Milestones: `D4`, `D5`

## Implemented

- Reduced `live_operator.py` from 1,843 lines to a 50-line public facade.
- Extracted typed contracts, pure decisions, canonical state, receipt
  verification, runtime orchestration, and trusted adapters into dedicated
  modules.
- Removed the disabled public simulator-receipt parameter and added a
  result-free trusted-adapter request.
- Added a fail-closed immutable registry with one deterministic fixture
  adapter. Campaign, mechanism, and intervention IDs remain data-driven.
- Bound execution to config/action/evaluator/intervention/source identities,
  canonical repository fixture paths, global budgets, signature separation,
  replay state, and all-false external authority.
- Recomputed mutation, response, likelihoods, factor updates, and consequence
  both during execution and during receipt verification.
- Added frozen request/fixture/adapter-contract schemas and one generic raw
  fixture.
- Added locking, interrupted-write, generated-state cleanup, schema-alignment,
  pre-execution abstention, replay, and resealed-evidence negative tests.

## Compatibility and proof

The retained C2 operator was rerun only to its already-authorized deterministic
measurement-acquisition abstention; no simulator family was launched. All 14
non-receipt artifacts are byte-identical to the v2 retained output. Migration
receipt `61ff4e4a697cf80c30d0bb8a65bec4b6463def4b7e1bfc12710a76c078efc172`
accounts for the v3 compiler/evaluator identity, receipt digest/schema, and two
intentional API changes.

The separate generic development fixture proof admitted one locally derived
adapter result with one intervention and one anchor replay. Its operator
receipt SHA-256 is
`5eb07d5a746465b4c3d9264ec4d1d4fec57ac143f57f4a0d4bd79f2de492da1f`;
the adapter receipt SHA-256 is
`bc5c36ecb721c06f114155fc89490ad7276bfe7fb7013affb3e31427c70ffe09`.
It is not C2, simulator-promotion, training, provider, or physical evidence.

## Verification

- Final focused suite: 47 passed in 4.12 seconds.
- `git diff --check`: passed.
- Fresh test run left no undeclared test campaign or state directories.
- Reviewer 033: `PASS`, zero blocking findings, zero edits.

## Boundaries

Generic caller-authored simulator evidence remains disabled. The retained C2
outcome remains the sealed measurement-acquisition abstention. Training,
provider/spend, simulator campaign/promotion, capture, gateway, camera/serial,
and robot motion authority remain false.
