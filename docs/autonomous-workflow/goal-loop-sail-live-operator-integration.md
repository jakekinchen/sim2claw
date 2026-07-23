# Goal loop: SAIL decision/evidence control-plane integration and ablation

## Mission

Turn SAIL from a collection of validated fixtures and campaign-specific
guardrails into the causal decision/evidence control plane for the retained C2 twin-error
problem. Replace the manual sequence of hand-authored parameter families with
one compositional operator that updates explicit competing hypotheses, selects
discriminating interventions, reallocates causal credit, validates consequences,
and abstains when the retained evidence is non-identifying.

The prior open-ended C2 search is paused. Do not resume it or start another
parameter family until this operator and its ablation are complete.

## Source of truth

Use these sources in descending authority order:

1. The user-approved objective in Codex task
   `019f8b9d-67ee-7801-9be3-f7cca45e8e3e` (Assess SAIL agent effectiveness).
2. This goal-loop prompt and the live branch
   `codex/sail-live-operator-integration`.
3. The interrupted predecessor task
   `019f87bd-5440-78b2-a74b-c447fe287cbe` (Build Phase 1 SAIL ClawLoop).
   Read its recent turns and receipts for evidence and failure history, but do
   not inherit its instruction to keep searching until a win.
4. `GOAL.md`, `docs/autonomous-workflow/project_state.json`, and
   `docs/goals/SAIL_CLAWLOOP_GRAND_MASTER_PLAN.md`, after reconciling their
   stale B2 active-status text with this pause.
5. Frozen source actions, evaluator-owned task/trace gates, committed contracts,
   and receipt-bound outputs. Generated outputs are evidence, not authority.

Repository and current receipts outrank summaries. Preserve fixture,
retrospective, prospective simulator, training, and physical proof classes.

## Intended outcome

A retained-project SAIL decision follows one auditable path:

`residual evidence -> competing structures -> predicted signatures ->`
`acquisition ranking -> bounded intervention -> posterior/belief update ->`
`sparse affected-factor refit -> invariance/consequence evaluation ->`
`promote or abstain`.

The C2 grasp case must use this path through reusable interfaces. It must not
construct a parallel ad hoc belief graph or require adding another campaign ID
to a Python whitelist. The result may be a simulator gain or a terminal
abstention; passing the evaluator is never required merely to finish the goal.

## Acceptance criteria

1. Reconcile branch, worktree, predecessor task, `GOAL.md`, and
   `project_state.json`; mark the legacy B2 parameter search paused and preserve
   every completed receipt and commit.
2. Define a generic, typed campaign contract that can bind residuals,
   hypotheses, predicted intervention signatures, budgets, observables,
   affected graph factors, evaluators, and proof/authority boundaries without
   enumerating task-specific schema or campaign IDs in Python.
3. Compose the existing `residuals`, `belief_graph`, `structural_surprise`,
   `mechanisms`/`posterior`, `acquisition`, `influence`, `loop_closure`, and
   `invariance` capabilities into a single executable operator. Refactor
   fixture-specific assumptions behind generic interfaces instead of copying
   their logic into another C2-only module.
4. Bind the retained C2 evidence to at least two explicit competing mechanisms.
   Each intervention must declare predicted signatures that could falsify or
   discriminate those mechanisms before any new result is opened.
5. Add a global campaign budget and abstention rule. Before the operator and
   ablation pass, run zero new C2 parameter families. Afterwards, at most one
   SAIL-selected family and at most 18 C2 anchor replays may be opened. Advance
   only actual anchor passes to the existing three sentinels, and do not open
   the all-eleven set unless the frozen gates authorize it.
6. Keep the C2 action array byte-identical and keep evaluator, release index,
   trace guards, task thresholds, and proof language immutable. The operator,
   agent, training code, and simulator implementation cannot promote
   themselves.
7. Produce an ablation against the predecessor's manual search: 32 completed
   campaign receipts, 514 C2 candidate replays, and zero anchor passes at the
   final pause snapshot. B2-02X was interrupted after 17 of 18 anchor artifacts
   and has no complete screen receipt; preserve it but exclude it from completed
   campaign counts. Compare intervention count, simulator evaluations,
   hypotheses eliminated/retained, information gain, task consequences, and
   abstention quality. Do not manufacture an advantage if SAIL does not earn it.
8. If the retained evidence cannot discriminate remaining mechanisms, stop and
   emit a sealed acquisition packet for synchronized jaw force, rubber-cap
   deformation/profile, joint angle/current, and required sampling/calibration.
   Missing measurement is an accepted terminal outcome.
9. Add golden, negative, integration, and end-to-end tests proving action drift,
   evaluator drift, post-result family expansion, budget escape, generic-ID
   handling, invalid posterior updates, unaffected-factor mutation, and
   unauthorized promotion all fail closed.
10. Run focused tests, the SAIL CI tiers, and the complete repository suite.
    Publish a receipt, run log, updated project state, and concise Studio/read-only
    evidence surface. Commit only scoped files on
    `codex/sail-live-operator-integration`.

## Evidence standard

Completion requires:

- exact changed-file and commit inventory;
- source/action/evaluator hashes;
- live operator trace from residual input to terminal verdict;
- hypothesis/posterior and affected-factor before/after records;
- intervention budget and observed-information-gain receipt;
- ablation table with exact inclusion counts;
- focused, CI-tier, and full-suite test results;
- Git status and branch/remote reconciliation;
- Brev and other paid-resource inventory if any such resource is touched;
- explicit remaining blockers and proof class.

Test counts prove implementation integrity, not causal or transfer validity.

## Decision status

Corrective closure (2026-07-22): this component is a decision/evidence control
plane, not an intervention executor. It consumes only independently evaluated,
hash-bound receipts. Persistent generated state enforces unique execution,
anchor-replay, and synthetic measurement-trial identities. The 514 historical
evaluations informed the frozen retrospective decision; SAIL used zero
additional evaluations after the pause. Physical capture and motion remain
separately unauthorized.

Confirmed:

- The old task is interrupted and its open-ended search is superseded.
- Completed commits and negative receipts must be preserved.
- Action assistance, evaluator relaxation, post-hoc success labels, physical
  authority, and training admission are forbidden.
- A correct abstention is preferable to another unbounded parameter sweep.

Recommended defaults:

- Treat the 32-complete-family/514-replay history as retrospective development
  evidence; keep the incomplete 17-artifact B2-02X screen separately labelled.
- Use the three declared sentinels only after a frozen C2 anchor pass.
- Prefer one generic operator and contract version over more C2 schemas.

Open question to resolve from evidence, not assumption:

- Whether any retained simulator-only intervention can discriminate flexural
  rubber behavior from actuator/load-path error without new force/deformation
  measurements.

## Execution rhythm

1. Read both named Codex tasks and inspect the live branch and authority files.
2. Update the compact progress ledger before changing implementation.
3. Choose the smallest operator integration step that satisfies a listed
   acceptance criterion.
4. Implement and test it without running a new physical or C2 search campaign.
5. Record hashes, receipts, and causal decision state.
6. Compare the result with the acceptance criteria and global budget.
7. Continue until the operator and ablation pass, then either execute the one
   authorized selected family or abstain.

## Progress ledger

Maintain this block in `docs/autonomous-workflow/project_state.json` and mirror
the summary in `GOAL.md`:

```text
Current state:
Completed:
Evidence:
Interventions used / budget:
Hypotheses retained:
Hypotheses rejected:
Remaining:
Blockers:
Next step:
```
