# LLM Corrective-Intervention Goal Loop Run Log

## Run identity

- Started: 2026-07-20 America/Chicago
- Repository: `/Users/kelly/Developer/sim2claw`
- Active goal thread: `019f7ce1-f912-7793-8c2e-4583c6a55563`
- Goal contract: `docs/autonomous-workflow/goal-loop-llm-corrective-intervention.md`
- Current brief: `docs/briefs/011-inspect-corrective-repair-benchmark.md`
- Proof class: hardware-free infrastructure; later fixtures remain synthetic or
  simulation evidence unless separately admitted
- Status: complete for the hardware-free implementation objective

## Initial audit

- The checkout is `main`, two commits behind `origin/main`, with existing dirty
  and untracked work. Those paths are treated as user/other-thread owned.
- `GOAL.md` already contains unrelated physical-source GR00T diagnostic edits;
  this loop will not overwrite it.
- The repo-local autonomous workflow and wrapper scripts already exist, so the
  workflow bootstrap was intentionally not rerun.
- LF-12 already persists trace-native counterexamples and independently checks
  corrective branch artifacts.
- Corrective admission already matches exact pre-failure integration state,
  independently replays the full episode, excludes failed-prefix rows, rejects
  held-out corrections, and routes admitted suffixes to LF-09.
- The geometric pawn expert already uses deterministic damped least-squares IK,
  a 3 mm residual ceiling, six absolute joint targets, and 20 Hz execution.
- The completed Inspect GapBench already provides isolated Codex/Claude
  adapters, shared skills, bounded tools, deterministic scoring, and sealed
  single-use submissions.

## Missing components at start

1. Typed LLM task-space intervention and transfer-observable failure packet.
2. General bounded waypoint compiler with proposal provenance.
3. Exact branch runner that materializes a corrective source episode.
4. Proposal score separated from policy reward and evaluator admission.
5. Evidence-grounded posterior schema, sampler, and robustness receipt.
6. LF-12-to-LF-09 wiring for LLM-proposed/geometric-expert-owned corrections.
7. Retraining mixture and checkpoint lineage proof.
8. Repair-specific Inspect task, controls, metrics, and model campaign contract.

## Progress

| Slice | Decision | Evidence | Next |
|---|---|---|---|
| Authority and workflow audit | CONTINUE | Existing workflow, LF recursion, source contract, IK expert, and GapBench inspected | Freeze contracts and tests |
| Frozen contracts | CONTINUE | `llm_corrective_intervention_v1.json`; fail-closed proposal, packet, compiled trajectory, posterior, and score validators | Build executable path |
| Packet and compiler | CONTINUE | Transfer-observable LF-12 packet builder; real MuJoCo translation-only pregrasp compiler; no raw joints or clipping | Execute exact branch |
| Branch and robustness runtime | CONTINUE | Exact integration-state restoration, 20 Hz branch execution, deterministic posterior runner, development/sealed separation | Connect LF evidence |
| LF evidence adapter | CONTINUE | Failed-prefix zero-row evidence; sealed branch; proposal and compiler lineage; geometric-expert action owner; existing correction envelope builder | Produce full corrective source episode and independent verdict |
| Canonical correction and admission | CONTINUE | A full C8-to-A6 episode preserves the nominal prefix, inserts five exact compiled actions, passes the unchanged strict evaluator, and admits 561 suffix rows with zero failed-prefix rows | Prove retraining consumption |
| Correction mixture and retraining | CONTINUE | A byte-bound dataset adds only admitted suffix rows; a two-update local CPU ACT checkpoint binds that exact dataset and passes an independent finite-action runtime smoke | Benchmark agent repair quality fairly |
| Corrective Inspect task | CONTINUE | Four matched cases, five repair skills, six bridged tools, disjoint public/sealed perturbations, typed proposals, deterministic scorer, and single-use terminal receipts | Establish controls and harness startup |
| Controls and harness proof | CONTINUE | Byte-identical unchanged/random/search/oracle summaries; mock Codex and Claude runs complete through the pinned image | Run broad verification |
| Final audit | STOP | 532 tests and 328 subtests pass; lock, build, compile, diff, task enumeration, Docker cleanup, and authority audit pass | Preserve remaining scientific work as explicit non-claims |

## Validation ledger

- `uv run pytest -q tests/test_corrective_intervention_contracts.py`: PASS as
  part of the focused suites.
- New corrective contract/runtime/LF tests: 34 PASS.
- New tests plus existing LF goal-loop, LF component, and source-episode tests:
  48 PASS and 2 subtests PASS in 105.49 seconds before the LF adapter addition.
- `uv run pytest -q tests/test_corrective_intervention_end_to_end.py`: 1 PASS
  in 90.95 seconds after adding suffix admission, correction-mixture lineage,
  two-update CPU training, and independent checkpoint runtime smoke.
- The end-to-end fixture produced 561 admitted correction rows and zero
  failed-prefix or held-out rows. Its checkpoint smoke is structural/runtime
  evidence only; `behavioral_evaluation` and physical-transfer proof are false.
- Corrective benchmark/Inspect focused tests: 8 PASS in 1.07 seconds.
- Deterministic control mean aggregate scores: unchanged 0.359790,
  seeded-random 0.515570, bounded search 0.943603, oracle 0.954103. Repeated
  runs produced identical summaries and receipts.
- `inspect list tasks` enumerated `sim2claw_corrective_repair` without a model
  call. One mock sample completed through each real Inspect SWE adapter:
  - Codex log: `runs/corrective-repair/mock-inspect-codex/2026-07-20T14-29-58-00-00_sim2claw-corrective-repair_hJqGvb73j7CqD8hdGCQqmn.eval`
  - Claude log: `runs/corrective-repair/mock-inspect-claude/2026-07-20T14-30-27-00-00_sim2claw-corrective-repair_NDXYdBdJYDJrSmVSYs47Yq.eval`
  Both scored 0.0 because the mock returned prose and made no terminal repair.
- `uv run --group inspect pytest -q`: 532 PASS and 328 subtests PASS in
  240.96 seconds.
- `uv lock --check`, `uv build`, Python compileall, and `git diff --check`:
  PASS. The source distribution and wheel built successfully.
- `docker compose -f evals/inspect_gapbench/compose.yaml ps --all`: empty; no
  benchmark container remains.
- No hardware, provider model, network campaign, Brev resource, or paid compute
  was used.

## Current limitation

The canonical fixture proves the generator, admission, dataset, and local
trainer/runtime mechanisms, but it is synthetic/off-product and does not prove
B--G policy behavior, a learned correction advantage, real posterior quality,
or sim-to-real transfer. The active slice is an agent-neutral Inspect benchmark
with deterministic non-LLM controls; provider-backed runs remain separately
authorized.

The hardware-free loop and benchmark implementation are now complete. The
remaining work is scientific evidence acquisition rather than missing loop
machinery: evaluator-owned real anchors for posterior identification; frozen
provider/model campaign runs; independent learned-policy held-out comparison;
and reviewed physical gateway validation.

## Safety and cost

- Physical authority: false.
- Provider-backed model calls: not authorized by this run.
- Brev or other paid compute: not used or required for the active slice.
- Generated outputs will remain under ignored or temporary paths.

## Accountability closeout

- Task ledger: T00--T11 complete.
- Provider-backed model calls: zero.
- Physical actions and hardware authority: zero/false.
- Brev or other paid compute: not used.
- Training admission remains evaluator-owned; Inspect and proposal scores have
  no admission or promotion authority.
- The checkout retains pre-existing dirty/untracked work and was not committed,
  pushed, rebased, or merged.
