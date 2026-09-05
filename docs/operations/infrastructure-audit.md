# Operations infrastructure audit

Audit date: 2026-09-05. Baseline: `main` at `9a91ba850149270685076ceade762bb367808f31`. Scope: software operations, historical evidence discovery, and human interpretation. This report does not activate a successor to the closed OR156 campaign.

Code line references below describe that audited baseline. The accompanying operations implementation changes some line numbers and closes the initial CLI import/retrieval gap; its remaining roadmap items are still proposals.

The repository already contains most of the difficult safety and reproducibility primitives. The missing layer is a small, shared way to find historical evidence, distinguish what it actually proves, connect failures to reusable techniques, and see current work without rereading hundreds of documents. Build this layer around existing contracts; do not create another autonomous campaign controller.

## Current authority and audit method

Both required entry checks passed: `uv run --locked sim2claw check --profile agent` and `uv run --locked sim2claw agent-context --role reviewer`. They reported no active campaign card, all external authority false, and OR156 at its external-input boundary. The historical development loop is closed by its terminal packet. Software operations improvements are a separate user-authorized scope.

The audit read the current implementations below, their relevant tests, CLI registration, Studio browser/server projection, and existing schemas. It also performed a read-only subprocess import probe. It did not run simulations, touch cameras or serial devices, start paid resources, or treat an old plan as current authority.

## Components to reuse

| Component | Concrete source | Existing behavior | Operations use |
|---|---|---|---|
| Current role packet | `src/sim2claw/agent_context.py:399`, `:459`, `:518`, `:569` | Binds repository identity and authority sources, detects drift, limits context bytes | Include a freshly compiled status packet alongside retrieved historical context; failure stays visible |
| Current campaign graph | `src/sim2claw/sail/current_campaign_graph.py:122`, `:193` | Typed source-bound graph with explicit revision history | Link historical cases to their declared campaign; do not infer the active card from filename order |
| Canonical artifact identity | `src/sim2claw/learning_factory_artifacts.py:22`, `:27`, `:35` | Canonical JSON hashes, streaming file hashes, atomic JSON replacement | Bind each indexed source and extracted span to original bytes; keep index rebuildable |
| Exact test identity | `src/sim2claw/dev_loop/lifecycle.py:403`, `:447`, `:493` | Binds HEAD, tree, branch, command, relevant path bytes/diff, dependencies and Python runtime; only exact passing receipts are reusable | Avoid redundant verification when the evidence identity still matches; state the scope of reuse |
| Bounded test runner | `src/sim2claw/dev_loop/runner.py:78`, `:98`, `:139`, `:177`, `:190` | File lock, task contract, child lease before release, timeout and process-group termination, durable receipt | Future software job execution should call this runner rather than invent a subprocess lifecycle |
| Process ownership | `src/sim2claw/dev_loop/lifecycle.py:535`, `:558`, `:619`, `:684` | Process identity, owned leases, guarded cleanup, orphan classification | Show owned/live/orphaned/unknown process states separately; never kill a PID discovered only by name |
| Review and merge proof | `src/sim2claw/dev_loop/lifecycle.py:205`, `:253`, `:932`, `:1062` | Independent review receipts, canonical artifact binding and merge-readiness verification | Operations findings can point to completed proof; an indexed paragraph cannot replace it |
| Transactional evidence admission | `src/sim2claw/sail/live_evidence.py:456`, `:524`, `:618` | Validates append-only digest chain, unique execution/result identities, budget deltas, locking and state equality before commit | Reuse these semantics when a future operations workflow needs durable decisions; do not write campaign state from search or lessons |
| Studio project projection | `src/sim2claw/studio_project_map.py:362`, `:410`; `src/sim2claw/studio_server.py:437` | Human/agent view over catalog, SAIL and factory evidence with explicit authority fields | Keep Studio as another presentation client of the same operations snapshot |
| Studio heartbeat | `src/sim2claw/studio_events.py:29`, `:71`, `:117`, `:139` | Per-process status, phase, metrics and atomic replacement | Read as current activity; optionally publish operations progress using an adapter |
| Orchestrator event format | `src/sim2claw/task_orchestrator.py:728` | Sequence, session ID, timestamp, event, structured payload and append-only JSONL | Borrow the event envelope shape without constructing the hardware-capable orchestrator service |

## Gaps and their implications

1. **Retrieval and cross-run learning lack a shared contract.** Current authority compilation is deliberately small and campaign-specific. Studio aggregates run evidence, but neither `agent_context.py` nor `studio_project_map.py` provides a searchable, source-spanned history of operational decisions. Agents repeatedly rediscover conventions and repeat broad searches. A local, incremental evidence index is the first useful addition.

2. **The current project map is a fixed workflow presentation.** `studio_project_map.py:30` fixes eight stage IDs, and `:75` requires exactly that count and order. `build_project_map` loads an existing factory project and observations from the catalog. Preserve this work for its existing purpose; a general operations graph needs extensible node types and explicit edges rather than more stage-specific branches in this function.

3. **Heartbeats cannot recover phase history.** `studio_events.py:139` replaces the same activity JSON on every update. A finished heartbeat preserves final state but not every attempted step, prior blocker, review revision, or recovery action. Keep a separate append-only operations journal for new activity; imported heartbeats must be labeled snapshots rather than reconstructed complete histories.

4. **Browser visibility is polling-based and fragmented.** `studio_web/studio.js:4906` starts separate catalog, recorder, workspace and orchestrator polling loops. The project map has its own fetch at `:724`. A small terminal `watch` and an exportable operations report can share one read model immediately. A later live web view should consume the same snapshot/event cursor rather than compute independent truth.

5. **CLI dependency exposure exceeds log-query needs.** `cli.py:8` imports alignment, while `alignment.py:9` imports MuJoCo and `:10` NumPy; `render.py:9` also imports MuJoCo. The read-only probe observed both modules loaded just by importing `sim2claw.cli`. One warm local sample took 0.1146 seconds for the import and 0.1247 seconds for module help; this is a dependency-boundary finding, not a measured user-visible performance problem. A stdlib operations module plus lazy CLI dispatch makes log retrieval usable without starting simulation imports.

6. **Verification reuse depends on a complete declared input set.** `dev_loop/lifecycle.py:412` hashes caller-specified relevant paths. The system cannot infer an omitted configuration, data manifest or imported module. Initially preserve the exact contract; later derive suggested relevant paths from dependency metadata and show that suggestion for review. Do not silently weaken identity to improve cache-hit rate.

7. **The runner serializes all runs sharing one receipt root.** `dev_loop/runner.py:98` holds the root lock across execution. This prevents duplicate work, but also serializes unrelated identities under that root. Do not rewrite the proven lifecycle as part of indexing. Measure queue wait before adding per-identity locks plus an explicit resource scheduler.

8. **The existing benchmark is not an efficiency measurement.** `dev_loop/bench.py:112` scores whether configured control labels cover seeded defect requirements. Its claim boundary at `:174` explicitly excludes general coding quality, research effectiveness and physical capability. Keep it as a deterministic fixture check; measure new operations gains using retrieval correctness, repeated-work avoidance and time-to-evidence on frozen tasks.

9. **Atomic replacement is not a complete multiwriter journal.** `learning_factory_artifacts.py:35` prevents partially written JSON reads, but the helper itself does not provide compare-and-swap or locking. SAIL supplies those semantics around it. A new index should use SQLite transactions, and a future decision journal needs explicit sequence/expected-version validation.

10. **Missing and stale evidence must be observable.** Studio already catches unavailable SAIL/factory bindings and preserves proof lanes (`tests/test_studio_project_map.py:141`, `:207`). An operations index should likewise report skipped oversized files, unsupported schemas, unresolved references, changed source hashes and deleted sources. A corpus count alone is not proof every claim was inspected or every outcome independently verified.

## Target structure and data flow

```text
Repository files and explicitly scoped local receipts
  ├─ canonical authority adapter ───────────────────────────────┐
  ├─ documentation adapter: session/reviewer/manager/run logs   │
  ├─ structured adapter: decisions, evaluations, leases        │
  └─ process/activity adapter: current snapshots                │
         ↓ read-only, bounded, source-hashed ingestion          │
  Rebuildable local SQLite index                               │
    source identity → extracted spans → references → case links│
         ↓                                                     │
  Query + coverage + candidate lesson read model ←──────────────┘
    ├─ terminal index/status/search/show/lessons/map
    ├─ append-only user notes and operations events
    ├─ bounded watch with visible refresh state
    └─ self-contained HTML snapshot → later Studio API client
         ↓ separate, reviewed proposal path
  Measurable workflow changes and scoped software milestones
         ↓ existing execution/test/review contracts
  New verified outcomes → append evidence → update lessons
```

The index is derived state under `outputs/operations/`; it can be deleted and rebuilt without losing source evidence. New user notes/events should be durable and exported so a rebuild does not discard interaction history. The existing campaign manifest, queue and evaluator remain authority sources. A historical log is data even when it contains imperative language.

Suggested package responsibilities:

| Module | Responsibility | Must not do |
|---|---|---|
| `ops/core.py` | Source allowlist, bounded ingestion, hashing, SQLite transactions, queries, coverage, current authority adapter | Execute commands found in logs or silently promote narrative claims |
| `ops/cli.py` | Arguments, readable terminal output, bounded watch, JSON projection | Reimplement authority decisions or swallow scan errors |
| `ops/view.py` | Escaped self-contained HTML snapshot with filtering and drilldown | Present old snapshot as live, execute source strings, load remote assets |
| Future `ops/adapters/` | Typed source parsers and receipt verification dispatch | Treat every JSON `status: pass` as physical task success |
| Future `ops/cases.py` | Link attempt → change → check → review → result → lesson with evidence | Invent causal links from temporal proximity |
| Future `ops/proposals.py` | Versioned improvement proposals, priority, bounded acceptance criteria | Activate training, hardware, paid compute or campaign successors |
| Future `ops/metrics.py` | Measured retrieval and workflow evaluation over frozen cases | Use successful test counts as a proxy for research progress |

## Contracts to build toward

**Source record:** stable source ID; canonical repository-relative path; byte digest; file size; source kind/schema; indexing time; source timestamp when actually supplied; bounded extracted text; completeness/skip/error reason. Modification time is a cache hint, not chronology authority.

**Evidence span:** source ID and digest; exact line or JSON pointer; excerpt; link targets; claimed outcome; proof class; verification state (`narrative`, `schema_checked`, `receipt_verified`, `stale`, `missing`, `unsupported`). Extraction never upgrades verification state by keyword alone.

**Case:** explicit task/campaign/run identity; intended result; observed outcome; hypothesis; attempted technique; inputs and environment identity; checks and review; rejected alternatives; terminal status; remaining prerequisite. Link confidence must distinguish explicit identifiers from inferred associations.

**Lesson candidate:** a concrete trigger, recommended behavior, reason, supporting and contradicting spans, applicability boundaries, unknowns and a falsifiable acceptance test. States progress through `candidate → reviewed → adopted → superseded`; adoption concerns software procedure, not simulation or physical proof.

**Operations event:** stable event ID, monotonic sequence, timestamp, actor/source, task/case ID, event kind, concise message, optional related artifact hashes, and expected revision for mutations. `note` is human/agent commentary, never an evaluator receipt.

**Capability graph:** typed nodes for workflow stage, component, interface, tool, technique, artifact, evaluator, proof class, prerequisite, failure mode and improvement. Typed edges include `consumes`, `produces`, `validated_by`, `blocked_by`, `supersedes`, `contradicts`, and `supported_by`. Human-facing nodes need purpose, current readiness, source links and next acceptance criterion.

## Small feasible CLI slice

Commands should have human-readable defaults and consistent `--json` output, accept an explicit repository root, and return nonzero on operational failure.

```text
sim2claw ops index                         # inventory/refresh local sources
sim2claw ops status                        # current authority + corpus coverage
sim2claw ops search "duplicate process"    # source spans with hashes
sim2claw ops brief "duplicate process"     # bounded context for the next agent
sim2claw ops show docs/session-logs/...md   # inspect exact retained source
sim2claw ops lessons                       # evidence-linked procedure candidates
sim2claw ops map                           # structure and implementation readiness
sim2claw ops note "Review complete"        # local interaction journal
sim2claw ops events                        # recent operations events
sim2claw ops watch --count 3 --interval 5   # bounded visible refresh
sim2claw ops report                        # portable interactive HTML snapshot
```

The implemented CLI accepts global `--root` and `--json` before the command, for example `sim2claw ops --json status`. `brief --max-bytes` bounds the actual emitted JSON packet. `note --kind` can distinguish notes, hypotheses, decisions, feedback and milestones; all remain annotations. Reports are written only to ignored HTML paths under `outputs/operations/`.

`watch` uses scoped file metadata, including change time, to decide whether a full index refresh is needed. This is a change hint; an explicit `index` always verifies source bytes. Documents and decisions remain fully searchable, while runtime JSON indexes narrative words rather than raw numeric arrays. `show` retains exact source spans, including numbers.

This slice can improve discovery and interpretation without needing an LLM service, vector database, web server, new paid dependency, or a new campaign. It does not claim complete causal synthesis, optimal agent policies or automatic continuous improvement.

## Prioritized roadmap and acceptance gates

| Priority | Deliverable | Acceptance evidence |
|---|---|---|
| P0 | Reproducible corpus inventory and literal source search | Every admitted source has a digest; excluded/skipped/error sources are counted; changed/deleted sources are reconciled; hostile text and malformed files cannot execute or break the report |
| P0 | Current authority plus historical scope in every surface | Closed OR156 remains explicit; broken authority compilation is visible; source text cannot grant authority |
| P0 | Terminal watch and inspectable HTML report | Watch terminates on count/interrupt; report shows generation time and refresh command; search/filter/drilldown work offline; all source text is escaped |
| P1 | Typed receipt adapters and case graph | Representative success, terminal negative, partial, rejected, missing and stale cases retain their proof classes; exact links resolve; inference is labeled |
| P1 | Reviewed lesson registry | Each candidate has supporting and contradicting evidence, applicability boundary, acceptance test and revision trail; no keyword-based automatic adoption |
| P1 | Frozen retrieval evaluation | Held-out questions with gold source spans; measure relevant-evidence recall, false attribution, time-to-evidence, bytes read and stale-source detection |
| P2 | Bounded execution observations | Adapt existing leases/test runner; measure duplicate launch avoidance, test reuse with exact identity, wall time and recovery from interrupted parent/child processes |
| P2 | Human steering and shared live projection | Notes, proposal review and pause requests have durable acknowledgement; CLI and Studio display one snapshot/event cursor; control requests cannot bypass existing gateways |
| P2 | Simulation capability DAG | Explicit frozen scenario/evaluator identity, candidate-prefix/full-chain runs, baseline/oracle controls, artifact provenance and consequence gates; software plumbing is not a task-success claim |
| P3 | Technique optimization from controlled trials | Compare candidate workflow against frozen baseline across multiple independent cases; report first-pass and iterative outcomes separately with failures retained |
| P3 | Resource-aware scheduling | Measured bottleneck justifies concurrency changes; per-resource leases, bounded budgets and owned-process cleanup proven by adversarial interruption tests |

Useful metrics are median time to the right source, missed/incorrect citations, repeated failed approach rate, exact-identity verification reuse, reviewer rework rate, completed acceptance gates per wall-clock hour, and time between a human steering note and acknowledgement. Track compute cost only where receipts actually expose it. Log count, tokens spent, number of tool calls and attractive dashboards are not outcome metrics.

The target is an auditable feedback loop whose improvements can be measured. No finite audit can establish a perfectly ideal system in every respect; the roadmap makes remaining work explicit and testable.
