# Executor Session 003: LLM Corrective Contracts and Runtime

## Scope

Implemented T01--T06 and the evidence-adapter portion of T07 from
`docs/autonomous-workflow/goal-loop-llm-corrective-intervention.md`.

## Changed paths

- `configs/evaluations/llm_corrective_intervention_v1.json`
- `src/sim2claw/corrective_intervention.py`
- `src/sim2claw/corrective_intervention_runtime.py`
- `src/sim2claw/corrective_intervention_lf.py`
- `tests/test_corrective_intervention_contracts.py`
- `tests/test_corrective_intervention_runtime.py`
- `tests/test_corrective_intervention_lf.py`
- scoped goal, brief, run log, and this workflow evidence

## Outcome

- Frozen fail-closed proposal, packet, compiler, posterior, score, budget, and
  authority contracts.
- Transfer-observable LF-12 failure packet builder.
- Translation-only pregrasp Cartesian compiler using the repo's SO-101 damped
  least-squares IK, 3 mm residual ceiling, joint/rate/collision checks, no
  clipping, and geometric-expert action ownership.
- Exact evaluator-only MuJoCo state capture/restoration and branch execution.
- Deterministic development/sealed posterior sampling and callback-based
  robustness runner.
- Proposal score that cannot admit, promote, or claim physical transfer.
- LF evidence materialization that preserves LLM proposal lineage while
  passing only the existing three authenticated artifacts into the unchanged
  correction submission envelope.

## Verification

- New corrective tests: 34 passed.
- New tests plus existing Learning Factory goal-loop/component and canonical
  source-episode tests: 51 passed and 2 subtests passed in 104.28 seconds.
- Scoped `git diff --check`: passed.
- `scripts/audit_autonomous_workflow.sh`: passed; workflow audit clean.

## Proof boundary

This is hardware-free infrastructure and real MuJoCo branch-execution proof.
It is not a full corrective episode, LF-09 dataset admission, trained policy,
sim-to-real result, B--G success, or physical task result.

## Remaining

Produce one canonical corrective source episode whose actions contain the
compiled intervention and a successful geometric continuation. Independently
replay the full prefix plus suffix, admit suffix rows through LF-12/LF-09, and
then build the retraining and Inspect comparison slices.
