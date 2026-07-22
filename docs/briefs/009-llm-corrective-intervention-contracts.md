# Brief 009: LLM Corrective-Intervention Contracts

Decision: `CONTINUE`

Slice result: `complete` on 2026-07-20; successor work is T07 full corrective
episode materialization and independent LF-12/LF-09 admission.

Evidence anchor: `100` — the repository has exact corrective-suffix admission
and a completed Inspect harness, but no typed task-space proposal or posterior
robustness contract connects them.

## Slice objective

Complete T01 of
`docs/autonomous-workflow/goal-loop-llm-corrective-intervention.md`: freeze and
test the typed proposal, failure packet, posterior, compiled trajectory, and
proposal-score contracts without yet generating an admitted source episode.

## Required behavior

- Accept only training/development counterexamples.
- Require transfer-observable evidence and reject evaluator-only payloads.
- Represent interventions as one to three Cartesian delta waypoints in a
  declared object or target frame; raw joint proposals are forbidden.
- Bind every proposal to its parent counterexample, branch state, scene,
  evaluator, prompt/skill/tool identities, and budget.
- Cap translation, rotation, gripper delta, duration, and compiled action count.
- Represent posterior parameters as bounded distributions with immutable seeds,
  source evidence, and explicit unsupported-parameter rejection.
- Keep policy consequence reward, proposal score, and promotion decision as
  separate artifacts.
- Use canonical digests for every artifact.

## Tests first

Add focused tests for valid normalization and rejection of:

- held-out or physical-source correction intake;
- privileged/evaluator-only proposer observations;
- unknown keys or identities;
- raw joint deltas;
- non-finite, over-bound, or excessive waypoints;
- unsupported posterior families, missing evidence, broad bounds, and seed
  overlap; and
- proposal scores that relabel nominal success as robustness or promotion.

## Scope boundary

Do not modify the dirty global `GOAL.md`, dependency files, physical replay
audit, Brev scripts, existing GapBench files, or provider configuration in this
slice. No hardware, model API, network campaign, or paid compute is authorized.

## Verification

Run the focused new tests, existing LF recursion/source-episode tests, and
`git diff --check`. Update the goal-loop ledger and run log only after the
focused gate passes.
