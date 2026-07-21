# Brief 011: Inspect Corrective-Repair Benchmark

Decision: `COMPLETE`

## Objective

Add a hardware-free Inspect task that measures whether an agent can infer and
submit a bounded task-space correction from transfer-observable failure
evidence. Codex CLI and Claude Code must receive identical cases, skills,
tools, budgets, sandbox constraints, and deterministic evaluator logic.

## Deliverables

1. A pure deterministic benchmark core with frozen public evidence, sealed
   centering targets, budget enforcement, typed-proposal validation, terminal
   single-use scoring, and cryptographic receipts.
2. Four deterministic controls: unchanged, seeded random nudge, bounded grid
   search, and fixture oracle.
3. Inspect dataset, bridged tools, scorer, task entrypoint, and shared agent
   adapters using the existing networkless Docker image.
4. Focused tests proving harness parity, packet hygiene, single-use scoring,
   deterministic metrics, baseline ordering, and no provider, robot, network,
   host mount, or paid-compute side effects.

## Frozen benchmark semantics

- Cases are synthetic pregrasp-centering repairs and remain a benchmark proof
  class, never calibration or transfer evidence.
- The proposal is the existing `corrective_intervention_proposal.v1`; raw joint
  commands, held-out bytes, privileged integration state, and direct control
  remain forbidden.
- Public evaluation uses development perturbations. The terminal scorer uses a
  disjoint sealed perturbation set exactly once.
- Primary metrics are sealed robustness, correction error, gain over unchanged,
  intervention cost, safety/contract compliance, evidence discipline, and an
  aggregate score. No LLM judge is used.
- Control algorithms receive the same proposal and simulator-call budgets.
- The oracle is an instrumentation ceiling, not a deployable baseline.

## Acceptance checks

- Both harness tasks instantiate with identical sample identities and limits
  without making a model call.
- Public packets contain no sealed target, hidden perturbations, credentials,
  host-home path, Docker socket, or hardware authority.
- Repeated seeds produce byte-identical control summaries and score receipts.
- Oracle exceeds bounded search, bounded search exceeds unchanged in aggregate,
  and random is reported without assuming it must beat unchanged case-by-case.
- Terminal submissions are single-use and cannot admit training data or promote
  a policy.

## Proof boundary

Passing this brief establishes benchmark and harness infrastructure plus
synthetic repair-task behavior. It does not establish provider-model quality,
learned-policy improvement, B--G success, posterior calibration, or physical
transfer.

## Verification outcome

- Eight focused benchmark/Inspect tests pass.
- Repeated control runs are byte-identical. Mean aggregate scores are 0.360
  unchanged, 0.516 seeded random, 0.944 bounded search, and 0.954 oracle.
- One mock sample completed through each real Inspect SWE harness in the pinned
  networkless image. Each scored zero because the deterministic mock returned
  prose and made no terminal proposal; this is expected infrastructure proof.
- The full repository suite passes with 532 tests and 328 subtests.
