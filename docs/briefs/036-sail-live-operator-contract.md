# Brief 036 — Generic SAIL live-operator contract

Decision: `CONTINUE` (anchor `100`: the effectiveness audit proved the live C2
campaign bypassed SAIL's causal operator surfaces).

## Outcome

Create one config-driven, typed live-campaign contract and executable operator
that accepts arbitrary campaign, mechanism, intervention, observable, factor,
and evaluator identifiers. The C2 retained case must bind through that public
contract; Python must not enumerate C2 campaign IDs or schema versions.

## Frozen boundaries

- Do not execute or finish B2-02X and do not open a new C2 replay.
- Keep action SHA-256
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
- Keep evaluator sources, release index 401, trace guards, task thresholds, and
  proof wording immutable.
- Maximum live-operator budget is one intervention and eighteen C2 anchor
  replays; the budget is global, not per family.
- Training, robot, physical-capture, and self-promotion authority remain false.

## Verification gate

- Generic IDs load and execute without a Python allow-list.
- Invalid bindings, action/evaluator drift, post-result expansion, budget
  escape, invalid posterior likelihoods, unaffected-factor mutation, and
  unauthorized promotion fail closed.
- The retained C2 config composes residual verification, structural surprise,
  mechanism availability, acquisition, belief graph, posterior, influence,
  sparse loop closure, invariance, and consequence gates into one trace.
- No C2 result is opened before the operator and manual ablation exist.

## Completion evidence

Changed files, focused tests, generated operator artifacts, source/action/
evaluator hashes, budget use, posterior/factor before-and-after records, and the
terminal evaluator-owned verdict must be recorded in the executor log and final
receipt.
