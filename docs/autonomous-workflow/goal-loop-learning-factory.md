# Goal Loop: Build the Codex-Driven Sim2Claw Learning Factory

**Status:** hardware-free implementation complete; clean-clone closeout in
progress; selected physical campaign remains externally blocked at LF-05

**Executor:** Codex operating directly in the Sim2Claw repository

**Companion architecture map:**
[`../briefs/007-learning-factory-automation-map.md`](../briefs/007-learning-factory-automation-map.md)

## Mission

Build a navigable, resumable Sim2Claw learning factory that Codex can run from
project inspection through twin construction, demonstration intake, calibration,
dataset creation, policy training, independent evaluation, counterexample
handling, cousin expansion, and promotion. Codex is the only reasoning and
authoring agent required by this workflow. Do not add a secondary LLM provider,
model-adapter product requirement, or user-supplied LLM credential.

The factory must make the correct next step obvious, execute deterministic work
automatically, invoke Codex judgment only where authored proposals or repairs
are required, preserve every proof boundary, and stop at precise blockers
instead of silently weakening a gate.

## Source of truth

Read these in order at the beginning of every execution turn. Later items may
clarify but may not silently override earlier authority.

1. The current user direction, including:
   - Codex runs the entire learning factory;
   - the product does not require the user to provide an LLM;
   - the primary product need is easy navigation and a clear flow at every
     step;
   - the workcell, cameras, calibration, video, and demonstrations are project
     inputs unless a stage proves one is missing or stale; and
   - the runtime Task Orchestrator is separate from the learning factory.
2. Repository `AGENTS.md`, including the clean-room and Brev cost-control
   requirements.
3. [`../../GOAL.md`](../../GOAL.md) and
   [`project_state.json`](./project_state.json), read from the live checkout.
4. The selected `configs/projects/*.json` project manifest and every contract
   it hash-binds, especially the frozen evaluator and workcell identities.
5. Frozen task, source, calibration, evaluator, and authority contracts under
   `configs/` and `calibration/`.
6. Accepted decisions:
   - [`../decisions/0004-goal-conditioned-act-pick-place.md`](../decisions/0004-goal-conditioned-act-pick-place.md);
   - [`../decisions/0007-canonical-manipulation-source-episodes.md`](../decisions/0007-canonical-manipulation-source-episodes.md); and
   - [`../decisions/0010-recorded-action-replay-and-staged-sysid.md`](../decisions/0010-recorded-action-replay-and-staged-sysid.md).
7. The live implementation, tests, ignored run receipts, and exact artifact
   bytes in the selected checkout.
8. Current run logs and research notes. These explain evidence but do not
   supersede live contracts or artifact identities.
9. Read-only archive references. They are historical requirements and lessons,
   never implementation or current proof.

When prose and live artifacts disagree, stop and reconcile the correct authority
instead of choosing the more convenient result. A receipt proves what happened;
it does not redefine the task or evaluator.

## Intended outcome

A normal operator or future Codex task can open one project, see the full
learning-factory stage rail, understand what is ready or blocked, run the next
eligible stage, resume after interruption, and inspect all inputs, outputs,
owners, verdicts, and next actions without reconstructing the workflow from
dozens of commands or prior agent conversations.

The finished implementation provides:

- one project-declared learning-factory graph;
- one Codex-operated CLI flow for run, resume, status, and explanation;
- read-only Studio navigation over the same graph and receipts;
- deterministic adapters around existing repo components;
- typed Codex-authored proposal artifacts for scene construction, calibration
  experiments, cousins, counterexample diagnosis, and repairs;
- evaluator-owned calibration and policy verdicts;
- a recursive but bounded counterexample/cousin/data loop;
- an optional promoted-skill package for the separate runtime orchestrator; and
- no secondary LLM service, raw LLM-to-hardware path, or self-promotion route.

The factory implementation can be complete even when a particular robotics
campaign ends `blocked`, `partial`, or `terminal_negative`. Successful learned
behavior is an evidence outcome, not a prerequisite for truthful workflow
completion.

## Scaffold verification and buildout correction

The first implementation pass created these scaffold surfaces:

- `configs/learning_factory/graph_v1.json` — exact LF-00 through LF-13 graph;
- `src/sim2claw/learning_factory.py` — controller, leases, receipts, status,
  ranges, next, resume, and explanations;
- `src/sim2claw/learning_factory_artifacts.py` — calibration, cousins, dataset
  admission, training capture, evaluation, counterexamples, correction, narrow
  ACT binding, and promotion contracts;
- `src/sim2claw/learning_factory_studio.py` plus
  `studio_web/learning-factory.*` — read-only operator navigation;
- `scripts/run_learning_factory_fixture.py` — synthetic LF-00-through-LF-13
  controller mechanism proof; and
- `tests/test_learning_factory.py` — authority, split, identity, lease, resume,
  calibration, cousin, admission, ACT, counterexample, CLI, and Studio negative
  and positive cases.

The selected physical project ran LF-00 through LF-04 and emitted a structured
LF-05 blocker. It did not run calibration or training. The synthetic fixture
advanced through all fourteen controller states, but most outputs were literal
or caller-supplied values. It is not reconstruction, replay, calibration,
dataset, training, evaluation, recursion, or promotion proof. The removed
`local_act_fixture` path associated an LF-09 dataset digest with a checkpoint
trained on a separately generated rook dataset and therefore was invalid
lineage, not acceptance evidence.

The first-pass verification results below remain evidence for the scaffold
only:

- focused learning-factory and project tests: 87 passed;
- full suite: 412 passed and 324 subtests passed;
- isolated source snapshot with a fresh locked virtual environment: 16 focused
  controller tests passed and all 14 synthetic fixture states advanced;
- source and wheel builds passed;
- lock, compile, JSON, Bash syntax, documentation link, generated-artifact
  ignore, credential-pattern, and diff/whitespace checks passed; and
- no paid or Brev-backed resource was created, started, or used.

The stage-by-stage buildout gaps and corrected priorities are recorded in
[`../briefs/008-learning-factory-buildout-gap-audit.md`](../briefs/008-learning-factory-buildout-gap-audit.md).
Historical scaffold execution hashes are recorded in
[`../../.factory/learning-factory-ledger.md`](../../.factory/learning-factory-ledger.md).

## Current implementation result

The post-audit buildout now provides the real machinery that the first scaffold
did not:

- stage-specific code/tool/runtime identity, immutable content-addressed
  outputs, recoverable leases, terminal attempts, and explicit generations;
- direct LF-01-through-LF-07 adapters for reconstruction, twin validation,
  source inspection, exact replay/splits, bounded sysid, and a separate
  calibration evaluator process;
- a training-only pose/layout curriculum and LF-09 admission path that reruns
  the strict source evaluator, independently recomputes scene/reset/transform
  lineage, retains exact rejections, and writes immutable 61-D ACT and GR00T
  payloads;
- an ACT trainer that consumes exactly the LF-09 receipt instead of generating
  another dataset, plus a separate CPU/fp32 online consequence evaluator over
  a cohort provably frozen before training;
- trace-native counterexample persistence, validated corrective-suffix intake,
  and executable LF-12 child generations that inherit parent receipts without
  overwriting them;
- an independent promotion process and a simulation-only runtime package whose
  skills become unavailable when checkpoint, evaluator, or promotion bytes are
  missing or changed; and
- Studio campaign history and read-only immutable-artifact drilldown.

The real-component mechanism run is documented at
[`../run-logs/2026-07-19-learning-factory-buildout.md`](../run-logs/2026-07-19-learning-factory-buildout.md).
Its learned-policy result is terminal-negative, which is expected evidence that
the evaluator remains authoritative. The selected physical project remains at
LF-05 because it still has zero exact replay-ready episodes and an unapproved
joint transform.

## Confirmed requirements

1. **Codex is the workflow driver.** Codex reads the project, authors candidate
   code and proposals, invokes deterministic tools, interprets results, repairs
   implementation, records evidence, and advances the stage graph.
2. **No user-provided LLM.** Do not build provider selection, an LLM API-key
   onboarding flow, or a second autonomous model service into the learning
   factory.
3. **Deterministic gates own truth.** Codex may propose; the compiler, replay
   engine, system-identification evaluator, frozen consequence evaluator, and
   promotion engine decide their declared gates.
4. **Navigation is a product feature.** Every stage exposes purpose, required
   inputs, current status, latest evidence, exact blocker, available action,
   and next stage.
5. **Workcell evidence is input-first.** Calibration and demonstration
   collection are optional repair/acquisition paths when project inspection
   finds missing evidence, not mandatory onboarding steps for every project.
6. **Training never promotes itself.** Trainer outputs are candidates only.
7. **Generated cousins never admit themselves.** Every generated episode is
   replayed and separately evaluated before dataset admission.
8. **Calibration is not simulated success maximization.** Accept a calibrated
   twin only from held-out fidelity improvement and sensitivity/identifiability
   evidence. A lower simulated ACT success rate may be more accurate when it
   better matches physical behavior.
9. **Runtime orchestration stays downstream.** The learning factory publishes
   promoted skill packages; the runtime may return execution counterexamples.
   It cannot train, evaluate, admit, or promote.
10. **Paid compute is bounded and cleaned up.** Every Brev-backed stage has a
    task, budget, timeout, artifact-recovery plan, and verified stop/delete
    closeout unless a newer explicit owner reservation applies to that exact
    workspace.

## Non-goals

- Requiring a separately configured LLM, foundation-model endpoint, or model
  provider for the learning-factory UI or controller.
- Allowing Codex prose to count as calibration, task success, evaluation, or
  promotion evidence.
- Replacing existing deterministic Python components with a giant shell script.
- Letting the runtime Task Orchestrator mutate datasets, training recipes,
  evaluators, checkpoints, or promotion state.
- Treating the 3DGS or scene hierarchy as metric or collision authority.
- Training on held-out rows, retrospective failures, unreviewed proposals, or
  raw counterexamples.
- Clipping requested physical actions to make replay appear valid.
- Automatically deploying a policy to hardware because it passed simulation.
- Copying implementation, data, checkpoints, outputs, or environments from the
  archive repository.

## Operator navigation model

Present the factory as one ordered rail. Each stage card or CLI status block
must show:

```text
Stage:
Purpose:
Status:
Required inputs:
Latest inputs and hashes:
Output contract:
Verdict owner:
Latest evidence:
Blockers:
Available Codex action:
Next stage when passed:
```

Use these states consistently:

- `not_ready`: a dependency has not produced an eligible output;
- `ready`: all declared inputs are present and verified;
- `running`: one lease-owning attempt is active;
- `passed`: the stage's declared gate passed;
- `partial`: useful bounded evidence exists but the full gate did not pass;
- `blocked`: a precise unmet prerequisite prevents execution;
- `failed`: the attempt malfunctioned or violated its execution contract;
- `terminal_negative`: the attempt completed correctly and the candidate failed
  the frozen scientific/product gate;
- `superseded`: a newer immutable candidate or contract replaced this result.

`blocked` and `terminal_negative` are successful workflow outcomes when they are
truthfully evidenced. They are not generic exceptions.

## User-facing command target

Implement a coherent command family, reusing Python functions directly when
possible:

```text
uv run sim2claw factory-inspect --project <project.json>
uv run sim2claw factory-status --project <project.json>
uv run sim2claw factory-run --project <project.json> --next
uv run sim2claw factory-run --project <project.json> --from <stage> --through <stage>
uv run sim2claw factory-run --project <project.json> --resume
uv run sim2claw factory-explain --project <project.json> --stage <stage>
```

Exact naming may change once against existing CLI conventions, but the behavior
must remain: inspect, understand, run next, run a bounded range, resume, and
explain. Do not require users to remember the individual low-level commands.

## Learning-factory flow

The stage input/output contracts are defined in Brief 007. The execution flow
below tells Codex what to do, what permits advancement, and what to record.

### LF-00 — Inspect the project and workcell package

Codex actions:

1. Resolve the project manifest inside the live repo.
2. Verify the project, evaluator, workcell, calibration, task, source catalog,
   authority, and Git/runtime identities.
3. Run the target-appropriate doctor without opening physical authority.
4. Produce a content-addressed input inventory and exact blocker list.

Advance when: the project inspection passes and every required input is either
present or explicitly declared optional for the selected path.

Output: `factory_project_inspection.v1` plus a resolved stage graph.

If blocked: name the missing or inconsistent artifact and the smallest action
that could resolve it. Do not continue into a dependent stage.

### LF-01 — Reconstruct visual context

Codex actions:

1. Verify the source video identity and explicit reconstruction executables.
2. Run or reuse a hash-matching `iphone-3dgs` result.
3. Preserve the pre-fit holdout and reconstruction receipt.
4. Register the output as visual context only.

Advance when: the 3DGS and receipt pass format/inventory checks. This does not
make them metric or collision authority.

Output: relative-scale 3DGS package, reconstruction receipt, frames/cameras, and
visual proof class.

### LF-02 — Author a twin candidate

Codex actions:

1. Read the workcell measurements, robot models, video/3DGS evidence, task
   requirements, and any typed scene proposal.
2. Author or repair repo-native MuJoCo scene code, assets, configuration, and
   tests in a bounded checkout.
3. Record every adopted public dependency and provenance decision.
4. Treat inferred geometry and physics as versioned candidates with uncertainty.

Advance when: a candidate implementation and dependency/provenance manifest
exist and are ready for deterministic validation.

Output: immutable twin candidate identity and patch/asset manifest.

Codex owns authorship, not acceptance.

### LF-03 — Compile and validate the baseline twin

Codex actions:

1. Compile, settle, render, and step the scene.
2. Run geometry, articulation, collision, stability, camera, trace, and task
   fixture checks applicable to the candidate.
3. Compare measured versus estimated fields and reject authority inflation.
4. Package all failures into structured diagnostics for LF-02 repair.

Advance when: the Twin Validator emits a passed baseline candidate receipt.

Output: scene manifest, validation receipt, renders/traces, and baseline twin ID.

### LF-04 — Import and normalize demonstrations

Codex actions:

1. Hash and inventory every episode payload.
2. Normalize only fields whose units, clocks, frames, devices, and provenance
   are explicit.
3. Preserve raw data immutably and record label or metadata conflicts.
4. Request human review only for truly ambiguous physical annotations or
   missing external measurements.

Advance when: canonical source episodes exist with no silent repair.

Output: canonical episode catalog, conflict queue, and missing-observable report.

### LF-05 — Establish replay readiness and freeze splits

Codex actions:

1. Verify joint transforms, units, initial position/velocity, action timing,
   object state, and required observables.
2. Audit exact controls against the simulator without clipping.
3. Freeze whole-episode calibration, validation, debug, and sealed held-out
   roles before fitting.
4. Emit `blocked` when the data cannot identify the requested calibration.

Advance when: at least the minimum declared cohort is exact-replay eligible and
the evaluator-owned split is immutable.

Output: replay-readiness receipt and frozen split manifest.

### LF-06 — Fit calibrated twin candidates

Codex actions:

1. Propose bounded parameter families, priors, stages, and fitting techniques.
2. Convert the proposal into a reviewed machine-readable experiment spec.
3. Run staged system identification only on calibration episodes.
4. Require sensitivity and identifying observables for every fitted stage.
5. Preserve baseline, candidate, optimizer, and residual identities.

Advance when: a calibrated candidate improves the declared validation metrics
and has an evaluator-ready comparison package.

Output: calibrated twin candidate, fit receipt, stage residuals, and sensitivity
report.

### LF-07 — Compare fidelity and frozen policy probes

Codex actions:

1. Evaluate baseline and calibrated twins on the same frozen validation and
   policy-probe cohorts.
2. Measure trajectory/contact/outcome fidelity, ACT success, sim/real gap,
   failure agreement, and ranking agreement where data supports them.
3. Keep calibration selection independent from training loss and simulated
   success maximization.
4. Ask the independent evaluator to admit, reject, or leave the candidate
   partial.

Advance when: the Calibration Evaluator admits one twin version for the next
curriculum tier.

Output: before/after comparison and evaluator-owned calibration verdict.

### LF-08 — Propose and compile the next cousin curriculum

Codex actions:

1. Read admitted twin uncertainty, coverage gaps, prior counterexamples, and
   allowed variation envelopes.
2. Propose the smallest informative cousin batch.
3. Start with continuous source/target pose cells and known distractor layouts;
   defer broad object/task cousins until these pass.
4. Compile proposals into deterministic candidate scenes/tasks with lineage.
5. Keep training, debug, and sealed evaluation cousins disjoint.

Advance when: a bounded cousin batch is compiled and ready for replay.

Output: curriculum batch manifest, coverage map, and candidate lineage.

### LF-09 — Replay candidates and admit a dataset

Codex actions:

1. Solve/planner-generate every candidate using frozen implementations.
2. Replay the complete trajectory in the bound twin.
3. Apply the separate strict-success evaluator.
4. Retain accepted and rejected candidates with explicit reasons.
5. Adapt accepted sources to ACT and/or GR00T formats.
6. Run local loader/preflight checks and prove zero held-out training rows.

Advance when: one immutable dataset receipt passes every admission and loader
gate for the selected trainer.

Output: admitted dataset, rejection ledger, lineage manifest, and preflight
receipt.

### LF-10 — Train policy candidates

Codex actions:

1. Bind the dataset, recipe, code, model/runtime, budget, and resource lease.
2. Run local ACT first when it can answer the question; use paid compute only
   for a bounded admitted campaign.
3. Capture scheduled checkpoints atomically with byte-derived identities.
4. Record terminal status, logs, runtime, and cost without evaluating promotion.
5. Recover required artifacts and clean up paid resources immediately when the
   bounded task ends.

Advance when: immutable checkpoint manifests exist and no paid worker is left
outside an explicit current reservation.

Output: candidate checkpoints, manifests, training receipt, and compute closeout.

### LF-11 — Independently evaluate and compare candidates

Codex actions:

1. Reverify checkpoint, evaluator, runtime, task, and held-out identities.
2. Run the separate CPU/fp32 consequence evaluator.
3. Produce per-gate, per-case, and aggregate results.
4. Compare candidates only on the same frozen scorecard.
5. Preserve `terminal_negative` results and do not select from training loss.

Advance when: the evaluator produces a complete eligible/rejected/partial
candidate comparison.

Output: candidate scorecard and evaluator-owned ranking/eligibility result.

### LF-12 — Turn failures into counterexamples and repair work

Codex actions:

1. Normalize failed replay, ACT, GR00T, and later runtime traces into one
   content-addressed counterexample envelope.
2. Deduplicate by source/candidate/evaluator/failure identity.
3. Diagnose the likely mechanism and route it to calibration, cousin coverage,
   data repair, implementation repair, or regression-only storage.
4. When a correction exists, preserve the failed prefix, intervention point,
   exact branch state, and successful corrective suffix.
5. Admit repair data only after complete replay and separate evaluation.

Advance when: each counterexample has an evidence-backed disposition and any
repair candidate is linked without overwriting the original failure.

Output: counterexample registry, repair queue, regression fixtures, and admitted
correction candidates.

### LF-13 — Publish evidence and promotion state

Codex actions:

1. Join the project, twin, dataset, checkpoint, runtime, evaluator, calibration,
   and authority identities by candidate ID.
2. Ask the independent Promotion Engine to emit promotion, rejection, partial,
   or terminal-negative state.
3. Publish a read-only Studio view and concise evidence summary.
4. If eligible, package a promoted skill artifact for the separate runtime
   orchestrator with preconditions, effects, supported workcell/twin IDs, known
   failure regions, and safe-stop behavior.

Advance when: the final state and all evidence are hash-bound and inspectable.

Output: promotion/rejection receipt, candidate registry record, Studio evidence,
and optional promoted skill package.

## Milestones and implementation order

### M0 — Freeze factory contracts and navigation

- Define the factory run, stage result, artifact reference, attempt, blocker,
  and status schemas.
- Add the project-declared stage graph without changing frozen task/evaluator
  contracts.
- Define the CLI navigation and Studio read-only stage-card model.
- Add negative fixtures for authority, split, identity, and state confusion.

Gate: the graph resolves deterministically and invalid contracts fail closed.

### M1 — Implement controller, receipts, status, and resume

- Add a Python controller that invokes stage adapters.
- Persist atomic receipts below ignored run roots.
- Add dependency-aware `--next`, bounded ranges, and hash-aware `--resume`.
- Prevent concurrent ownership of the same stage attempt.
- Surface precise blockers as results rather than generic exceptions.

Gate: an inspect/readiness run can be interrupted and resumed without rerunning
unchanged passed stages.

### M2 — Wire the source-to-dataset deterministic path

- Adapt existing project inspection, source inventory, replay readiness, split,
  source evaluator, adapters, export, and preflight functions.
- Stop at the first non-admitted dependency.
- Prove accepted/rejected lineage and zero held-out rows.

Gate: a synthetic/frozen fixture completes end to end while the current physical
B--G project truthfully stops at its current readiness blocker.

### M3 — Wire local candidate training and independent evaluation

- Run the frozen narrow ACT fixture through dataset, training, immutable
  checkpoint capture, evaluation, and candidate result receipts.
- Preserve its narrow claim and prevent relabeling as a B--G policy.

Gate: training cannot write or forge evaluator/promotion state.

### M4 — Implement calibration before/after comparison

- Add a calibration experiment schema and bounded runner.
- Join baseline and calibrated twin identities to residual and policy-probe
  cohorts.
- Add sensitivity, held-out improvement, and sim/real-gap reporting.

Gate: synthetic or eligible data proves the mechanism; current physical data
remains blocked until its missing inputs are actually repaired.

### M5 — Implement counterexample registry and repair routing

- Add one cross-lane counterexample schema, deduplication, and disposition.
- Route failures without automatically admitting them to training.
- Add validated correction-episode lineage.

Gate: identical failures cannot silently enter multiple pools, and held-out
counterexamples cannot become training data.

### M6 — Implement the first constrained cousin loop

- Compile continuous pose and known distractor cousins.
- Select a bounded batch from coverage gaps and counterexamples.
- Replay, evaluate, admit, train, and independently compare.

Gate: at least one full recursive fixture run produces a new immutable dataset
version and a new candidate verdict without changing held-outs.

### M7 — Add Studio navigation and operator handoff

- Show the same stage graph, statuses, attempts, evidence, blockers, and next
  Codex action in Studio.
- Keep Studio read-only with respect to proof and promotion.
- Add one copyable resume command for every actionable stage.

Gate: a new operator can identify the current state and next action without
reading implementation source or prior chat history.

### M8 — Clean-clone acceptance and closeout

- Reproduce the deterministic fixture path from a clean clone/runtime.
- Run focused and full tests, build artifacts, JSON/schema checks, Bash checks,
  and documentation/link verification.
- Verify generated data and credentials remain ignored.
- Verify Brev inventory for any campaign used by this task and clean up idle
  paid resources.
- Publish the final evidence map and unresolved external blockers.

Gate: every acceptance criterion below is evidenced, terminal-negative, or
reduced to a precise external prerequisite without authority inflation.

## Acceptance criteria

The task is complete only when all applicable items are evidenced:

1. One selected project manifest resolves one deterministic LF-00 through LF-13
   graph with exact contract and artifact identities.
2. `inspect`, `status`, `run next`, bounded `from/through`, `resume`, and
   `explain` behaviors exist through a coherent CLI.
3. Stage outputs are atomic, content-addressed, project-scoped, and bound to
   code/runtime/evaluator identity.
4. A blocked or terminal-negative stage prevents dependent execution while
   remaining inspectable and resumable.
5. Codex can run the complete workflow without a secondary LLM configuration,
   provider key, or model-selection UI.
6. The source-to-dataset chain is automated and proves no held-out or rejected
   episode enters training.
7. A local ACT fixture proves training, immutable checkpoint capture, separate
   evaluation, and non-self-promotion.
8. Baseline-versus-calibrated comparison reports fidelity and policy-probe
   metrics without optimizing merely for higher simulated success.
9. The calibration evaluator alone admits or rejects calibrated twins.
10. Counterexamples have one common schema, stable identity, disposition,
    regression lineage, and guarded correction admission.
11. The first cousin compiler generates only bounded declared variations,
    retains rejection reasons, and keeps train/debug/held-out roles disjoint.
12. The recursive fixture loop can produce a new dataset candidate and policy
    verdict without mutating prior evidence.
13. The Promotion Engine, not Codex or the trainer, owns promotion decisions.
14. Studio shows the graph, current status, evidence, blockers, and next Codex
    action without gaining training, evaluator, gateway, or physical authority.
15. The only runtime-orchestrator interfaces are promoted skill packages out
    and typed execution counterexamples back.
16. Relevant focused tests, the full suite, build/lock checks, schema/JSON
    validation, and diff/whitespace checks pass.
17. Generated artifacts, datasets, checkpoints, caches, credentials, outputs,
    and run state remain outside Git unless a tracked contract/index explicitly
    belongs in source.
18. Any explicitly Brev-backed work has bounded receipts, recovered evidence,
    and final authenticated inventory/teardown proof consistent with the latest
    owner instruction for that exact workspace.

## Evidence standard

Do not claim a milestone or the task complete from prose alone. Record:

- exact changed files and commit(s), if publication is authorized;
- project, stage, attempt, code, runtime, dataset, twin, checkpoint, evaluator,
  and receipt hashes;
- commands and exit status;
- focused and full test results;
- an example successful fixture run;
- an example blocked physical-project run;
- an example terminal-negative candidate result;
- before/after calibration comparison artifacts;
- counterexample and correction lineage fixtures;
- Studio screenshots or browser evidence when navigation changes;
- generated-artifact and Git-ignore audit;
- paid-resource inventory and teardown proof when applicable; and
- every unresolved blocker with the smallest exact owner action.

Keep proof classes separate: fixture, synthetic, simulation, replay,
learned-policy, physical read-only, and physical task evidence are not
interchangeable.

## Decision status

### Confirmed

- Codex is the sole required reasoning/execution agent.
- No user-provided LLM or provider integration is required.
- The learning factory and runtime Task Orchestrator are separate systems.
- The workcell/video/demonstrations are project inputs by default.
- Calibration, cousins, counterexamples, training, evaluation, and promotion
  form the core recursive learning loop.
- Evaluators and promotion remain independent from Codex authorship and
  training.

### Recommended defaults

- Implement Python stage adapters around existing functions rather than shell
  output scraping.
- Start with one local deterministic fixture and the frozen narrow ACT proof.
- Represent current B--G physical readiness as a blocked example until its
  actual input defects are resolved.
- Build pose/layout cousins before broad object or task cousins.
- Make the CLI authoritative for execution and Studio the read-only navigation
  surface.
- Keep one writer per checkout and preserve unrelated dirty work.

### Assumptions to reverify

- The active project remains the B--G rank-1/rank-2 project.
- Current project/evaluator hashes and stage blockers may change before
  implementation reaches them.
- Existing low-level commands remain the preferred component APIs; refactor to
  direct Python calls where necessary.
- Physical measurements or corrected demonstrations may arrive independently.

### Open questions that do not block M0--M3

- Final public naming of the learning-factory CLI.
- Whether long-running run control eventually moves from the local Codex task
  to a packaged background service.
- Which policy cohort should own the first physical calibration-correlation
  study after eligible data exists.
- When object and task cousins become justified beyond pose/layout cousins.

## Execution rhythm

Repeat until all acceptance criteria are resolved:

1. Read the ordered source of truth and the latest ledger.
2. Inspect the exact checkout, branch, diff, artifacts, processes, devices, and
   paid-resource state relevant to the next stage.
3. Resolve the current factory graph and select the smallest dependency-ready
   milestone slice.
4. Implement one bounded change while preserving unrelated work.
5. Run focused verification immediately.
6. Write the stage/milestone evidence and update the ledger.
7. Re-read the acceptance criteria and choose the next slice.
8. Run broader regressions before integration or publication.
9. Continue through blockers when safe work remains; stop for user input only
   when an external choice or authorization materially changes the result.
10. Never end while an unreserved paid resource created or used by this task is
    still running.

## Progress ledger

Maintain `.factory/learning-factory-ledger.md` as the live execution surface.
Do not overwrite the existing orchestration ledger or unrelated task state.

Use this compact format:

```text
Updated at:
Branch / HEAD:
Selected project:
Current milestone:
Current factory stage:
Stage status:
Completed:
Evidence:
Tests:
Artifacts / receipts:
Remaining:
Blockers:
External owner action:
Paid resources:
Next step:
```

Append important campaign decisions and terminal-negative outcomes. Do not
rewrite history to make the current state appear cleaner.

## Completion and blocked-state rule

Complete the task only when the acceptance criteria are evidenced and the
factory is navigable from a clean environment. A specific robotics lane may
remain blocked or terminal-negative without blocking workflow completion if:

- the implementation needed to represent and resume that state is complete;
- the evidence is preserved;
- no claim is inflated;
- the smallest external prerequisite is recorded; and
- all other safe dependency-independent work is finished.

Do not declare the overall task blocked merely because calibration data, a
compatible B--G checkpoint, physical access, authentication, or paid compute is
currently unavailable. First finish every hardware-free and credential-free
factory component that can be implemented and proven against fixtures.
