# Goal Loop: Fixed-Data Multimodal Reality-Gap Pipeline

## Mission

Extract the maximum scientifically defensible value from the immutable 18-
episode physical teleoperation corpus. Compile deterministic interaction-phase
proposals, synchronized visual evidence, event-conditioned physical metrics,
and a fail-closed real-versus-simulator comparison surface; expose the evidence
to matched Codex and Claude Inspect harnesses; define a phase-balanced training
ablation; and prepare a separately gated similar-hardware revalidation protocol.

The result must never turn inferred events into measured contact, duplicate
rows into independent episodes, provisional replay into calibration, or a
future similar scene into evidence for the retired workcell.

## Source of truth

Use this authority order whenever sources disagree:

1. The latest user instruction and repository `AGENTS.md`.
2. Immutable source bytes and hashes in
   `configs/data/physical_pawn_move_catalog_20260719.json`.
3. `configs/sysid/physical_pawn_sysid_split_v1.json`; whole-episode split and
   evaluator ownership are unchanged.
4. The retrospective publication and telemetry contracts under
   `configs/evaluations/`.
5. Exact replay, task, evaluator, Learning Factory, and promotion contracts.
6. `GOAL.md` and `docs/autonomous-workflow/project_state.json`.
7. This goal loop and its dated run log. They record execution but cannot
   promote evidence or overrule frozen contracts.

## Intended outcome

One offline command materializes, for every requested partition:

- exact gripper-phase/event proposals with immutable source lineage;
- per-row phase labels without changing the original dataset;
- event-conditioned command-tracking, velocity, timing, and raw-current
  summaries;
- synchronized visual evidence strips around closure and release proposals;
- a bounded multimodal annotation schema that retains ambiguity and model
  disagreement;
- an event-conditioned real-versus-simulator comparison receipt when, and only
  when, an exact unclipped replay trace with an approved transform exists;
- a phase-balanced sampling manifest that changes sampling probability but
  never episode count, row identity, action bytes, or training admission; and
- a future similar-scene protocol with explicit old/new workcell identities.

## Acceptance criteria

- [x] All 18 sample, receipt, and video hashes verify before extraction.
- [x] The frozen 15-train/3-held-out split remains whole-episode disjoint.
- [x] Development materialization defaults to train only; held-out access is a
      separate evaluator-owned invocation.
- [x] Every row receives exactly one deterministic phase label.
- [x] Closure/release outputs are named candidates or proxies, never measured
      contact, grasp force, or metric contact points.
- [x] Current evidence records its 5 Hz cached/raw semantics.
- [x] Visual strips bind source video hash, exact requested timestamps, decoded
      timestamps/frame indices, and generated artifact hash.
- [x] VLM annotations use finite enums, preserve occlusion/ambiguity, omit the
      receipt outcome from the prompt, and have zero promotion authority.
- [x] Event-conditioned physical metrics are descriptive at row level and use
      whole episode as the independent unit.
- [x] Real-versus-simulator comparison fails closed on provisional transforms,
      clipping, repaired rows, missing canonical velocity, or row misalignment.
- [x] Phase-balanced manifests preserve 18 source episodes and 7,741 unique rows
      across the frozen partitions;
      weighted draws are not reported as new data.
- [x] The similar-scene protocol requires a new workcell identity unless the
      board, environment, camera, transforms, and hardware identities are
      independently proven identical.
- [x] Focused and full tests, deterministic reruns, generated artifacts,
      limitations, and blockers are recorded.

## Evidence vocabulary

Observed evidence:

- requested, commanded, and measured joint positions;
- measured joint velocity;
- cached raw present-current proxy;
- monotonic/control/video timestamps;
- hash-bound video and endpoint images; and
- human-teleoperation receipt context.

Derived candidates:

- open-reference peak;
- closure onset and near-closed crossing;
- mechanically loaded closure candidate;
- closed/transport candidate interval;
- release onset and destination-open peak;
- visual source occupancy, overlap, co-motion, destination occupancy, and
  visible release annotations; and
- apparent response lag, explicitly not command-to-actuation latency.

Unavailable without new instrumentation or calibration:

- exact physical contact time or point;
- calibrated contact force, torque, or grasp force;
- metric 3D object trajectory;
- camera-capture or command-to-actuation latency;
- contact/friction system identification; and
- physical policy-transfer proof.

## Milestones and task ledger

Status values: `pending`, `in_progress`, `complete`, `blocked`.

| ID | Task | Status | Required evidence |
|---|---|---|---|
| T00 | Audit live authority, corpus, split, repeated moves, and dirty worktree | complete | 18 episodes, 7,741 rows, 15/3 split, nine move IDs recorded in run log |
| T01 | Freeze this mission, vocabulary, acceptance gates, and execution ledger | complete | This file and dated AI-build run log |
| T02 | Freeze event, visual-annotation, comparison, and sampling contracts | complete | Hash-bound config plus rejection tests |
| T03 | Implement deterministic event/phase compiler | complete | Every one of 7,741 rows receives exactly one phase in the combined evaluator inventory |
| T04 | Implement synchronized visual evidence strips | complete | 18 deterministic 1920 x 1560 strips with requested/decoded timestamps and hashes |
| T05 | Implement event-conditioned physical summaries | complete | Per-phase and independent-episode distributions with cached-current semantics |
| T06 | Add matched Inspect Codex/Claude annotation/audit task | complete | Skill, six bounded tools, approval policy, scorer, and task-load tests |
| T07 | Add agent-output consensus/disagreement compiler | complete | Signed raw attempts, deterministic agreement, no model judge |
| T08 | Add exact-replay-gated real-versus-simulator comparison | blocked | Interface and positive/rejection fixtures pass; 0/18 live traces are eligible |
| T09 | Add phase-balanced training-ablation manifest | complete | 6,486 unique train rows, frozen weights, no admission/promotion |
| T10 | Materialize train outputs and evaluator-owned held-out receipt | complete | Two matching train digests plus three-scenario held-out aggregate |
| T11 | Add similar-hardware/new-scene revalidation protocol | complete | Identity decision tree, empty-close baseline, timestamp and sensor checklist |
| T12 | Run provider/system campaign | blocked | CLIs are installed; exact event campaign/model settings and provider-use authority are not frozen |
| T13 | Run policy-training ablation | blocked | Source remains unadmitted and there is no evaluator/physical-validation authority |
| T14 | Full verification and publication closeout | complete | 557 tests and 328 subtests pass; deterministic artifacts, paper-facing analysis, and blockers recorded |

## Decision status

Confirmed:

- The original data cannot be recollected and remains immutable.
- The same SO-101 hardware may be available later, but the same board and
  environment are not guaranteed.
- The current corpus contains 18 independent episodes and 7,741 rows; all
  receipt outcomes belong to human teleoperation.
- The existing whole-episode split contains 15 train and three held-out
  episodes.
- Exact replay is currently 0/18 because the transform is provisional and
  current simulator ranges would clip recorded values.

Recommended defaults:

- Develop deterministic extraction and visual prompts on train episodes only.
- Preserve the existing gripper event threshold and do not tune it from
  held-out results.
- Use telemetry to propose short visual windows; never ask a VLM to search an
  entire video or infer hidden metric geometry.
- Treat trace-only, trace-plus-vision, and agentic multimodal methods as
  explicit ablations against the nominal simulator.
- Prioritize event-conditioned simulator fidelity before policy retraining,
  because no current physical policy evaluation can be performed.

Open questions that must remain explicit:

- Whether the physical-to-simulator transform can be approved from retained
  records without new calibration motion.
- Whether future physical revalidation recreates the old workcell or defines a
  new related workcell.
- Which provider/system campaign is authorized and affordable.
- Whether any event-weighted physical rows can satisfy the separate training-
  admission contract; this pipeline does not admit them itself.

## Execution rhythm

1. Re-read authority, this ledger, live Git status, and the latest receipt.
2. Select the smallest incomplete task that advances a testable gate.
3. Add deterministic acceptance and rejection tests first when practical.
4. Implement only within the task's evidence and authority boundary.
5. Materialize ignored outputs and inspect visual artifacts when applicable.
6. Run focused tests, deterministic reruns, then proportionate broad tests.
7. Update this ledger and the run log with exact evidence and blockers.
8. Continue until T14 passes; never convert a partial or blocked result into a
   completed simulator, training, or physical-transfer claim.

## Progress ledger

```text
Current milestone: offline fixed-data pipeline complete
Completed: T00-T07, T09-T11, T14
Evidence: 557 tests plus 328 subtests; two identical 15-episode train corpus digests; evaluator-owned three-episode held-out corpus; inspected full-resolution strip
Remaining: T08, T12, and T13 remain typed blockers outside the completed offline build
Blockers: exact real-versus-sim execution is blocked by 0/18 replay eligibility; provider calls lack a frozen event campaign; policy training lacks admission/evaluator authority
Next step: approve exact replay from retained calibration evidence if possible, then freeze a three-case subscription campaign before any model call or training run
```
