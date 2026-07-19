# Learning Factory Buildout Gap Audit

**Status:** hardware-free buildout and clean-clone acceptance complete;
selected physical B--G campaign truthfully blocked at LF-05 on external
evidence prerequisites

**Audit date:** 2026-07-19

**Accepted implementation:** `416eb77` on
`codex/task-orchestrator-plan`; original audit was performed against the
uncommitted slice based on `13999e9`

## 2026-07-19 buildout disposition

The gap findings below describe the first scaffold and remain useful historical
critique. They are superseded for current implementation status by the buildout
completed after this audit. Every hardware-free card P0 through P8 now has an
executable component, negative contract, and focused test. The live physical
project still stops correctly at LF-05; implementation completion does not
manufacture missing physical replay evidence or a successful B--G policy.

| Card | Current disposition | Evidence boundary |
| --- | --- | --- |
| P0 | `passed` | Fixture claims corrected; false-lineage local ACT profile quarantined |
| P1 | `passed` | Typed adapters, stage-specific identities, content-addressed outputs, terminal attempts, heartbeat leases, campaign generations |
| P2 | `passed` | Real 3DGS reuse/run, twin compilation/render/trace, source parsing, replay/split adapters; live source stops on exact defects |
| P3 | `passed` | Real sysid fit plus separate-process held-out calibration evaluator exercised on synthetic system-identification fixtures |
| P4 | `passed` | Training-only curriculum, verified planner/IK lineage, real exact pawn replay/evaluation, 61-D ACT plus GR00T payloads, immutable rejection artifacts |
| P5 | `passed` | Dataset-consuming ACT trainer and separate CPU/fp32 consequence evaluator; real component campaign produced an honest terminal-negative |
| P6 | `passed` | Trace-native registry; independently replayed, byte-bound corrective suffixes; executable child generations; parent evidence inheritance; declared LF-12 routes |
| P7 | `passed` | Independent promotion/rejection process, hash-guarded simulation skill package, typed runtime counterexample return |
| P8 | `passed` | Fresh locked `git clone --no-local` at `416eb77`: 446 tests and 328 subtests, source/wheel build, lock, compile, JSON, Bash, ignore, and diff checks passed |

Current real-component mechanism evidence is recorded in
[`../run-logs/2026-07-19-learning-factory-buildout.md`](../run-logs/2026-07-19-learning-factory-buildout.md).
It includes one 562-row strict source admission, one exact LF-09 dataset, one
dataset-bound checkpoint, one separate held-out terminal-negative evaluation,
one trace-native counterexample, and one independent promotion rejection. The
upper-side `tan_pawn_c8 -> a6` source proves the generic LF-09 mechanism only;
it is not relabelled as B--G evidence.

**Governing task:**
[`../autonomous-workflow/goal-loop-learning-factory.md`](../autonomous-workflow/goal-loop-learning-factory.md)

## Original audit verdict (superseded by the buildout disposition above)

The learning factory is not fully built. It has a useful navigation and receipt
control plane, a 14-stage graph, a read-only Studio rail, and contract-helper
functions. It does not yet execute the real LF-01-through-LF-13 learning
pipeline.

The end-to-end deterministic fixture is a mechanism test: most stage outputs
are literals, caller-supplied booleans, or caller-supplied metrics. It proves
that the controller can advance, persist receipts, preserve a blocker, and
render status. It does not prove reconstruction, source normalization, replay,
system identification, cousin generation, dataset construction, policy
training, independent evaluation, recursion, or promotion.

Current completion estimate:

| Surface | Estimated completion | Meaning |
| --- | ---: | --- |
| Operator navigation and control plane | 75% | CLI, graph, receipts, statuses, resume, leases, and Studio exist, with reliability gaps |
| Real deterministic stage chaining | 25% | LF-00 has meaningful inspection and LF-03 has a shallow compile check; most real component APIs are not invoked |
| Full task-document outcome | 40% | contracts and helpers exist, but both scientific critical paths remain largely unimplemented |

The two unfinished critical paths are:

```text
demonstrations -> exact replay -> frozen split -> system identification
  -> independent before/after fidelity verdict

calibrated twin -> cousin generation -> strict replay/admission -> immutable dataset
  -> goal-conditioned ACT training -> independent evaluation -> counterexamples
  -> versioned retry -> promotion -> runtime skill package
```

## What is actually built

- Exact LF-00-through-LF-13 graph validation and project-declared profiles.
- CLI navigation for inspect, status, next, bounded range, resume, and explain.
- Project-scoped attempt directories, atomic JSON writes, stage result digests,
  dependency checks, basic exclusive leases, and hash-based passed-stage reuse.
- A useful distinction among `blocked`, `failed`, `terminal_negative`, and
  downstream `not_ready` states.
- A read-only Studio stage rail with evidence, blockers, next action, and a
  copyable resume command.
- Schema-level helpers for calibration comparison, bounded cousin proposals,
  dataset admission, checkpoint capture, candidate scorecards,
  counterexamples, correction candidates, and promotion state.
- A real physical-project blocker at LF-05 that preserves the current evidence
  boundary instead of opening training.

These components should be retained and hardened. They are the factory shell,
not the factory's working machinery.

## Stage-by-stage gap map

| Stage | Existing real owner/API | Current factory behavior | Remaining build |
| --- | --- | --- | --- |
| LF-00 Project intake | `project_bundle.inspect_project`, `doctor.run_doctor` | Real project inspection and doctor, without render probe | Hash all declared artifacts, git revision, dependency/runtime identities, tool versions, and target-specific probes; emit typed missing-input repairs |
| LF-01 Visual reconstruction | `iphone_3dgs.run_iphone_3dgs`, `probe_video`, `inspect_gaussian_ply` | Passes when reconstruction is optional; fixture returns a literal ID | Add run/reuse adapter, bind video/config/tool identities and receipt, validate output manifests, retain relative-scale-only authority |
| LF-02 Twin authoring | Codex-authored scene patch plus project contracts | Hashes an existing capture config and mass profile | Define typed scene proposal, uncertainty and measured-versus-estimated fields, bounded Codex work request, patch/dependency/provenance manifest, and candidate validator |
| LF-03 Twin validation | MuJoCo scene, render, trace, grasp, contact-sensitivity components | Compiles, takes four steps, checks finite `qpos` and scene ID | Join settle/stability, geometry, articulation, collision, cameras, task fixtures, traces/renders, sensitivity, provenance, and authority checks into one admission receipt |
| LF-04 Demonstration normalization | `source_episode.load_source_episode`, `adapt_source_episode`, `tree_manifest`; source evaluator | Counts catalog episodes and hashes the catalog | Load and hash every payload, validate units/clocks/device/task identity, produce immutable canonical episodes, record conflicts and missing observables, and preserve raw-to-canonical lineage |
| LF-05 Replay and split freeze | `recorded_replay` validators/replayer; `inspect_recording_catalog_inputs`; `freeze_episode_split` | Reads readiness summary fields from `project_state.json` | Run the actual input report and exact replay, persist receipts, then freeze evaluator-owned whole-episode roles; reconcile calibration/validation/debug/sealed-heldout roles with the existing sysid split |
| LF-06 System identification | `system_identification.run_system_identification`; `contact_sensitivity.run_contact_sensitivity` | Physical profile returns a generic blocker; fixture returns a literal experiment | Compile an agent proposal into reviewed bounds, execute the existing fitter on calibration episodes, bind sensitivities and candidate twin bytes, and persist fit/terminal-negative receipts |
| LF-07 Before/after comparison | Sysid held-out evaluation and consequence evaluators | Compares fabricated metric dictionaries in the fixture | Independently run baseline and candidate on one frozen validation cohort, join real residuals and optional policy probes, and admit only from fidelity/identifiability evidence |
| LF-08 Cousin curriculum | Goal-conditioned task contract in `chess_pick_place_act_state_v1.json` | Bounds JSON offsets, distractors, and roles | Implement coverage accounting, pose/layout selection, task/scene compilation, versioning, and explicit train/debug/sealed role allocation; do not mutate held-outs |
| LF-09 Replay and dataset admission | source evaluator/adapters; pawn and multisource GR00T export/preflight | Trusts caller booleans and hashes candidate dictionaries | Generate candidates with planner/IK lineage, fully replay each, execute the strict evaluator, preserve rejection artifacts, adapt accepted rows, and export/preflight immutable ACT/GR00T datasets |
| LF-10 Candidate training | `act_train.train_act` for frozen rook only; bounded GR00T campaign code | Writes fake weights, or trains a separate internally generated rook dataset | Build a trainer that consumes the exact LF-09 dataset receipt; bind recipe/runtime/log/budget identities; checkpoint atomically; enforce local/Brev leases and cleanup |
| LF-11 Independent evaluation | `act_evaluator.evaluate_act` for frozen rook only; frozen goal-conditioned evaluator contract | Trusts supplied success rates; local profile reduces one rook episode to 0/1 and adds a synthetic candidate | Implement a CPU/fp32 evaluator for the goal-conditioned contact skills and B--G scorecard, run every immutable checkpoint on identical frozen cohorts, and emit consequences plus rankings |
| LF-12 Counterexamples and repairs | Trace producers plus registry helper | Normalizes one synthetic failure batch without persisting it | Persist the common registry, attach actual traces/identities, classify mechanism and destination, validate failed-prefix/intervention/corrective-suffix artifacts, and create versioned repair candidates |
| LF-13 Promotion and handoff | Promotion contract; downstream orchestrator skill registry | Computes state from caller-supplied IDs and a boolean scope flag | Independently revalidate joined project/twin/dataset/checkpoint/evaluator IDs, issue promotion/rejection receipts, publish the exact runtime skill package, and accept typed runtime counterexamples back |

## Cross-cutting correctness gaps

1. **Implementation identity is incomplete.** The reuse key hashes only
   `learning_factory.py`, `learning_factory_artifacts.py`, and Python version.
   A change to replay, sysid, ACT, MuJoCo inputs, dependencies, or external
   binaries can incorrectly reuse an old result.
2. **Artifacts are digest-labelled, not content-addressed.** Attempt outputs
   live below timestamp/UUID paths. There is no immutable object store keyed by
   digest or verified artifact-reference schema.
3. **Lease recovery is incomplete.** Exclusive creation prevents two writers,
   but there is no heartbeat, process/host validation, expiry, or safe stale
   lease recovery.
4. **Attempt lifecycle is incomplete.** `attempt.json` remains `running`; only
   `stage_result.json` records the terminal state. Exceptions write a failed
   receipt and then re-raise, so the CLI can expose a traceback instead of a
   consistently structured failed result.
5. **Resume is retry, not recursive orchestration.** Recursive graph edges are
   metadata only. LF-12 cannot create a new campaign/dataset version and reopen
   LF-06, LF-08, or LF-09 while retaining prior immutable evidence.
6. **Verdict helpers trust their caller.** Replay pass flags, evaluator pass
   flags, success rates, trace hashes, correction artifacts, and scope
   compatibility are not joined to verified producer receipts.
7. **The local ACT profile has false lineage.** LF-09 creates one cousin
   dataset receipt, but `train_act()` generates and trains its own frozen
   rook-lift dataset. LF-10 then records the LF-09 dataset digest against that
   unrelated checkpoint. This path must not count as acceptance evidence.
8. **No goal-conditioned ACT implementation exists.** The 61-dimensional
   observation, source/target pose splits, planner/ACT ownership, lineage, and
   evaluator gates are frozen as a contract, but there is no generator,
   dataset loader, trainer, or evaluator implementing it.

## Task milestone reassessment

| Milestone | Honest state | Reason |
| --- | --- | --- |
| M0 Contracts/navigation | Partial | graph and UI schemas exist; artifact reference and blocker contracts are not fully enforced |
| M1 Controller/receipts/resume | Partial | basic loop works; identity, content addressing, lease recovery, terminal attempt state, and structured failure behavior remain |
| M2 Source-to-dataset path | Not implemented | current physical adapter stops at catalog/readiness summaries; fixture does not call real source/replay/export components |
| M3 Local training/evaluation | Not accepted | local ACT run has a dataset/checkpoint lineage mismatch and does not exercise the intended goal-conditioned task |
| M4 Calibration comparison | Helper only | comparison arithmetic exists; there is no real bounded runner or before/after evaluator adapter |
| M5 Counterexamples | Helper only | schema/deduplication exist; the controller does not persist, route, or validate real correction evidence |
| M6 Cousin recursion | Not implemented | JSON bounds are not a cousin compiler, and recursive edges do not execute |
| M7 Studio navigation | Substantially implemented | read-only rail exists; artifact drilldown and version/campaign history remain |
| M8 Clean-clone closeout | Not accepted | prior verification proves the scaffold; it cannot close acceptance criteria for unimplemented real stages |

The current task document and automation-map status lines should therefore be
corrected from “implemented” to “control-plane scaffold; integration open.”

## Dependency-ordered build cards

### P0 — Correct the proof boundary

- Relabel fixture evidence as mechanism-only and remove M0-through-M8 closeout
  claims.
- Disable or clearly quarantine `local_act_fixture` until its lineage is fixed.
- Record an acceptance-criterion checklist in the ledger with `passed`,
  `partial`, `open`, `terminal_negative`, or `external_blocker` states.

**Acceptance:** no document, Studio label, or receipt implies that a literal
fixture output executed a real component or that the rook checkpoint used the
LF-09 dataset.

### P1 — Harden the controller and adapter contract

- Introduce a typed `StageAdapter` interface with declared inputs, produced
  artifact references, verdict owner, proof class, blockers, and cleanup.
- Bind git revision, dirty-file identities in scope, invoked module hashes,
  dependency/runtime versions, project artifacts, and tool identities.
- Add immutable content-addressed outputs, terminal attempt updates, structured
  CLI error/exit behavior, lease heartbeat/stale recovery, and campaign/version
  IDs for recursive reruns.

**Acceptance:** changing any invoked implementation or input supersedes the
stage; interrupted work recovers safely; a failed adapter yields an inspectable
terminal result without losing the diagnostic.

### P2 — Wire real LF-00-through-LF-05 intake and replay

- Invoke the existing reconstruction, canonical source, input-report, exact
  replay, and split APIs directly.
- Build a full twin-admission validator instead of the four-step smoke check.
- Use existing source/replay/sysid fixtures for a hardware-free integration
  campaign; let the live physical campaign stop on its genuine data blocker.

**Acceptance:** a fixture with real payload files produces verified source and
replay receipts and a frozen split; corrupt units, timing, transforms, payload
hashes, or scene artifacts stop the correct stage.

### P3 — Wire real LF-06 and LF-07 calibration

- Add the bounded calibration experiment compiler.
- Call `run_system_identification` and sensitivity analysis on the frozen
  calibration cohort.
- Invoke a separate evaluator process for baseline/candidate validation and
  optional policy probes.

**Acceptance:** the existing synthetic sysid fixture is fitted and compared
through factory adapters; the calibrated candidate can lose simulated policy
success yet pass only when frozen real-to-sim fidelity improves.

### P4 — Build real LF-08 and LF-09 cousin/data production

- Implement goal-conditioned pose/layout coverage and bounded curriculum
  selection.
- Add planner/IK-based object- and target-relative candidate generation with
  complete lineage.
- Compile, replay, strictly evaluate, adapt, export, and preflight every
  candidate; keep a rejection ledger and sealed-split proof.

**Acceptance:** an accepted dataset contains only fully replayed,
evaluator-admitted training episodes; one invalid cousin retains its exact
rejection reason; no held-out row appears in train output.

### P5 — Build real LF-10 and LF-11 goal-conditioned ACT

- Refactor or replace the narrow ACT trainer so it accepts the exact LF-09
  immutable dataset rather than generating data internally.
- Implement the frozen 61-dimensional observation and consequence-driven
  grasp/place skills.
- Add the separate CPU/fp32 evaluator for the continuous source/target pose
  splits and B--G scorecard.
- Bind checkpoints to dataset, recipe, runtime, logs, and resource closeout.

**Acceptance:** one checkpoint can be traced byte-for-byte to one LF-09 dataset
and is evaluated on an unopened frozen cohort by a separate owner; fabricated
score fields cannot enter LF-11.

### P6 — Make LF-12 recursion executable

- Persist trace-native counterexamples and typed routing.
- Validate correction branches from actual artifacts.
- Version datasets/campaigns and execute LF-12-to-LF-06/LF-08/LF-09 edges
  without overwriting the parent evidence.

**Acceptance:** one evaluator failure creates a deduplicated regression record,
one separately admitted repair creates a new dataset version, and a second
candidate verdict is produced without changing held-outs or prior receipts.

### P7 — Build LF-13 promotion and runtime handoff

- Rejoin and revalidate all producer receipts in an independent promotion
  process.
- Publish the orchestrator-facing allowlisted skill package only for an exact
  eligible task/scope/runtime identity.
- Define and validate the typed counterexample return path from the runtime.

**Acceptance:** deleting, changing, or mismatching any required receipt makes
the skill unavailable; neither Codex, trainer, Studio, nor runtime can forge
promotion.

### P8 — Product acceptance

- Run a true clean Git clone after the scoped changes are committed; do not use
  a copied dirty source snapshot as clean-clone proof.
- Run real-component integration campaigns for LF-00-through-LF-07 and
  LF-08-through-LF-13, plus focused/full tests, build, lock, schema, link,
  ignore, credential, and resource audits.
- Add Studio artifact drilldown and campaign/version history.

**Acceptance:** each task-document criterion has current evidence or one
precise external prerequisite, and no hardware-free implementation item is
misclassified as a physical blocker.

## Recommended first shippable vertical slice

Do P0 and P1, then implement LF-04-through-LF-07 against the existing source,
replay, and synthetic sysid fixtures. This slice exercises the real scientific
spine without requiring new physical capture, a GPU, or a new policy model. It
also establishes the adapter and receipt pattern needed by every later stage.

After that, the next vertical slice should be one exact LF-09 dataset through a
dataset-consuming LF-10 trainer and real LF-11 evaluator. Do not continue from
the current `local_act_fixture`; fix the lineage at the trainer boundary first.

## External physical prerequisites

These block the active physical campaign, but not the hardware-free build cards
above:

- approve or replace the provisional physical-to-simulator joint transform;
- repair or recollect the 18 episodes whose current readiness is 0/18;
- resolve 2,255 measured and 2,231 commanded out-of-range rows among 7,741
  rows, with maximum exceedances of about 0.1235 and 0.1158 simulator units;
- capture metric end-effector, pawn, contact, grasp, and release observables;
- physically qualify the current 100 mm workspace and reconcile the frozen
  evaluator's 72 mm board-pose dependency; and
- collect and admit compatible B--G training data before claiming a promoted
  B--G checkpoint.

Until those inputs change, the correct live campaign outcome remains LF-05
`blocked`: zero exact replay, zero parameter fit, zero held-out calibration
evaluation, and no compatible B--G learned checkpoint.

## Working-tree and publication note

The learning-factory implementation is currently uncommitted and partially
staged. The checkout also contains concurrent Task Orchestrator changes. Any
future commit must separate the learning-factory slice from those unrelated
changes and should not present the current task-document closeout as accepted
proof.
