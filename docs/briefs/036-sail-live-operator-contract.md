# Brief 036 — Generic SAIL decision/evidence control-plane contract

Decision: `CORRECTED` (the first implementation selected the right abstention,
but its result trust and proof language were not merge-reviewable).

## Outcome

Create one config-driven, typed live-campaign contract and decision/evidence control plane
that accepts arbitrary campaign, mechanism, intervention, observable, factor,
and evaluator identifiers. The C2 retained case must bind through that public
contract; Python must not enumerate C2 campaign IDs or schema versions.

## Frozen boundaries

- Do not execute or finish B2-02X and do not open a new C2 replay.
- Keep action SHA-256
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
- Keep evaluator sources, release index 401, trace guards, task thresholds, and
  proof wording immutable.
- Maximum decision-plane budget is one intervention, eighteen C2 anchor
  replays, and six separately counted synthetic measurement trials; the budget
  is persistent and global, not per process or family.
- Training, robot, physical-capture, and self-promotion authority remain false.

## Verification gate

- Generic IDs load without a Python allow-list. This component does not execute
  interventions. Generic simulator-result admission is disabled until a
  trusted deterministic adapter recomputes concrete mutations and consequence
  from raw artifacts; internally consistent files are not evaluator authority.
- Invalid bindings, action/evaluator/code/config/source drift, post-result
  expansion, receipt/result/raw-artifact tampering, duplicate execution/replay/
  trial IDs, budget escape, invalid posterior likelihoods, unaffected-factor
  mutation, and supplied promotion fields fail closed.
- The retained C2 config composes residual verification, structural surprise,
  mechanism availability, acquisition, belief graph, posterior, influence,
  sparse loop closure, invariance, and consequence gates into one trace.
- A strictly offline measurement lane accepts synthetic fixtures only when the
  acquisition packet, common clock, sampling, skew, calibration, phases, raw
  hashes, result hash, evaluator identity, and all-false authority verify.
- Campaign state resolves to one ignored, repository-relative path keyed by the
  campaign and canonical config digest, never beneath caller-selected output.
  All semantic artifacts and the receipt are verified before the append-only
  state transition is committed as the final mutation.
- `verify_live_operator_receipt` rechecks the receipt digest, config, source,
  compiler and output hashes, canonical state chain, action/evaluator/
  intervention identity, budget, and all-false authority at read time.
- Missing source-bound invariance vectors are not imputed.
- The metric rename is scoped to this new control-plane contract. The
  receipt-bound Phase 1 acquisition compiler, config, intervention schema, and
  fixture retain their frozen byte identities; migrating that historical
  schema would require a separately versioned campaign and receipt re-freeze.

## Completion evidence

Changed files, focused tests, generated decision artifacts, source/action/
evaluator hashes, persistent state-chain identity, budget use, posterior/factor
before-and-after records, and the terminal derived verdict must be recorded in
the session log and final receipt.
