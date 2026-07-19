# Studio Task Orchestrator AI build run log

Request: Complete `docs/briefs/006-studio-task-orchestrator.md` and test the exact OpenAI adapter with the repository `.env` credential.
Repo/path: `/Users/kelly/Developer/sim2claw`
Started: 2026-07-19
Completed: 2026-07-19. Core implementation, deterministic proof, exact OpenAI provider proof, integration, browser polish, full-suite verification, and local packaging are complete. Silicon live connectivity is intentionally not claimed because the camera feed/token was unavailable.
Owner constraints: Preserve clean-room proof classes; do not treat synthetic fixtures as learned, simulation, or physical proof; keep credentials server-side; do not grant physical authority; do not relabel rook, GR00T, scripted, or raw-motion behavior as promoted B--G ACT skills.

## Acceptance Criteria

- Provide the loopback-controlled **Task Orchestrator** Studio tab without changing existing Replay, Library, Calibration, Robots, Record, Live, or Learning Factory routes.
- Freeze exact B--G rank-1/rank-2 occupancy, Silicon snapshot, model, skill, event, result, fixture, and physical-canary contracts.
- Keep whole-image `>= 0.97` similarity as a model-input deduplication gate, separate from square-level base-case classification.
- Make Start/Resume, user chat, explicit Refresh, source recovery, and skill completion/failure force an accepted observation.
- Keep user and world/action inactivity timers independent, visible, and defaulted to 300 seconds.
- Bind user-facing `5.6 luna` to catalog-resolved provider ID `gpt-5.6-luna`, medium reasoning, strict structured output, one attempt, and no silent substitution.
- Expose all 12 intended B--G ACT moves, but leave each unavailable until separately evaluated checkpoint, evaluator, and promotion identities exist.
- Serialize execution, require a fresh observation and deterministic postcondition check after every fixture-only simulated move, and let the deterministic checker own completion.
- Keep observe-only, simulation, and physical-shadow surfaces at `physical_authority: false`; leave the physical canary disabled pending its separate evaluator and per-action operator approval.
- Retain credential-free, hash-linked session receipts under ignored `runs/task_orchestrator/<session-id>/` and release source, model, and skill resources on Stop/fault.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Implementation | Codex | Implement and integrate the bounded runtime, contracts, server routes, UI, tests, and documentation | Brief 006 and current repository contracts | Repository changes and this run log |
| Runtime planner | OpenAI Responses adapter, exact `gpt-5.6-luna`, medium | Produce one schema-valid bounded proposal from an accepted frame and receipt-linked context | Synthetic B-file mismatch, frozen reference frame, exact contracts, and unavailable production skill registry | Live schema-valid `ask_user` decision plus model/latency/usage lineage; no substitution or physical authority |
| Perception | OpenCV square classifier | Classify each managed square independently of whole-image similarity | Registered 512x512 synthetic board fixtures | Structured occupancy, confidence, mismatches, blockers, and suggested same-file move |
| Deduplication | Normalized-luminance global SSIM | Suppress visually redundant model inputs only | Consecutive registered ROIs | Similarity, accepted/ignored lineage, and suppression count |
| UI proof | Codex in-app browser | Audit layout, control state, tab isolation, overflow, and browser console | Loopback Studio server at the Task Orchestrator route | Two ignored PNG screenshots and zero observed console errors |
| Verification | `pytest`, Node syntax check, `jq`, `uv lock`, `uv build` | Exercise contracts, failure paths, fixture restoration, HTTP integration, packaging, and syntax | Current worktree | Passing local proof listed below |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Synthetic board fixtures | Deterministic in-repo generator | `uv run python scripts/generate_orchestrator_fixtures.py` | `tests/fixtures/orchestrator/*.png` and `configs/orchestrator/fixtures/pawn_bg_base_case_v1.png` | Fresh synthetic fixture proof only; no prior-project artifact copied; grants no learned, simulator, or physical authority |
| Frozen fixture manifest | Brief 006 requirements | Manually authored contract | `configs/orchestrator/fixtures/fixture_manifest_v1.json` | Enumerates positive, every single-file, multi-file, stale, drift, ambiguity, model, unavailable-skill, and timeout cases |
| Physical canary gate | Brief 006 TO-6 boundary | Manually authored contract | `configs/orchestrator/physical_canary_gate_v1.json` | Disabled; defines shadow comparison, new evaluator, per-action approval, and one-action canary prerequisites only |
| Physical canary evaluator | Brief 006 TO-6 boundary | Manually authored independent evaluator contract | `configs/orchestrator/physical_pawn_bg_canary_evaluator_v1.json` | Frozen but inactive; binds scene/workcell/calibration, fresh evidence, exclusive leases, approval, tracking/stall sources, postcondition, collateral, safe-stop, and torque-off gates |
| Studio visual proof | Loopback Studio runtime | Browser viewport and full-page screenshots | `outputs/task_orchestrator/studio-task-orchestrator-completion-viewport.png`, `outputs/task_orchestrator/studio-task-orchestrator-completion-full.png` | Ignored evidence captured from the final worktree; no remote camera or hardware was opened |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Fixture generation | `uv run python scripts/generate_orchestrator_fixtures.py` | Passed and reproduced the frozen fixture set | `tests/fixtures/orchestrator/` |
| Focused orchestrator suite | `uv run pytest -q tests/test_task_orchestrator.py` | 31 passed, 22 subtests passed | Test output from 2026-07-19 |
| Full repository suite | `uv run pytest -q` | 435 passed, 328 subtests passed | Test output from 2026-07-19 |
| Dependency lock | `uv lock --check` | Passed; 94 packages resolved with no lock change required | `uv.lock` |
| JavaScript syntax | `node --check src/sim2claw/studio_web/studio.js` | Passed | `src/sim2claw/studio_web/studio.js` |
| Frozen JSON parse | `jq empty configs/orchestrator/**/*.json configs/orchestrator/*.json` | Passed | `configs/orchestrator/` |
| Package build | `uv build` | Passed; source distribution and wheel built | `dist/sim2claw-0.1.0.tar.gz`, `dist/sim2claw-0.1.0-py3-none-any.whl` |
| Studio HTTP integration | Focused HTTP tests plus `http://127.0.0.1:4173/#/orchestrator` | Passed; only the orchestrator panel was visible at 1280px, all seven Studio destinations remained intact, no horizontal overflow, 12 unavailable skill rows showed receipt/mode/readiness/result state, exact-model credential was reported configured, only the unavailable Silicon credential was requested, shadow review remained gated, physical gated was disabled, and there were zero console errors; one existing Three.js deprecation warning remained | `outputs/task_orchestrator/studio-task-orchestrator-completion-viewport.png` |
| Exact OpenAI catalog | Authenticated `GET /v1/models` with redacted output | Passed; the requested label resolved to `gpt-5.6-luna`; the prior guessed `gpt-5.6` ID returned `model_not_found` and was not retained | Safe terminal catalog receipt from 2026-07-19 |
| Exact OpenAI turn | `uv run python scripts/smoke_task_orchestrator_openai.py` | Passed; exact `gpt-5.6-luna`, medium reasoning, schema-valid `ask_user`, 5,300 input / 164 output / 78 reasoning tokens, 2,540.19 ms; secret not printed and no fallback attempted | Safe JSON terminal receipt from 2026-07-19 |
| Full service plus real model | `uv run python scripts/smoke_task_orchestrator_service_openai.py` | Passed; synthetic registered B-mismatch frame traversed session start, accepted-frame receipt, exact live model decision, user-help pause, and clean Stop; no skill execution or hardware command | `runs/task_orchestrator/20260719T111337.977536Z-97bf8f4b/` |
| Receipt privacy and lineage | Redacted receipt audit | Passed; 11 contract/reference digests, contiguous 8-event sequence, retained accepted-frame hash, terminal result, no API key bytes, `physical_authority: false`, and torque-off not applicable | `runs/task_orchestrator/20260719T111337.977536Z-97bf8f4b/` |
| Silicon live snapshot | Frozen HTTPS endpoint and adapter fixture tests | **Not live-verified:** the camera feed/token was unavailable; connection is assumed compatible with the repository overhead-webcam boundary, but the adapter still fails closed until its exact endpoint contract passes | `configs/orchestrator/silicon_overhead_snapshot_v1.json` |
| Skill execution | Injected promoted-fixture adapters only | Passed every one-file mismatch and two three-move combinations, one dispatch at a time with forced postcondition observations; pause/stop races, failed-skill observations, source recovery, and resource release also passed; **not** evidence of a promoted ACT checkpoint or MuJoCo/physical capability | `tests/test_task_orchestrator.py` |
| Physical shadow | Injected promoted-fixture shadow registry | Passed supervised operator-choice receipt with frame/state/proposal/operator/digest/exact-match lineage, zero adapter calls, and `hardware_command_issued: false` | `tests/test_task_orchestrator.py` |

## Completion Audit By Slice

| Slice | Result | Authoritative Evidence |
| --- | --- | --- |
| TO-0 contracts and fixtures | Complete | Frozen base, orchestrator, Silicon, skill, decision/event/result, fixture-manifest, canary, and physical-evaluator JSON; required negative fixtures and tests pass |
| TO-1 observe-only Studio | Complete | Loopback APIs, background worker, controls, adjustable polling, dual timers, source health, frame display, ledger, read-only rejection, and browser proof pass |
| TO-2 deduplication and perception | Complete | Frozen normalized-luminance SSIM suppresses `>= 0.97`; a B-file move remains above that threshold yet the independent square classifier detects it; stale/drift/malformed/ambiguous cases fail closed |
| TO-3 model dry run | Complete | Authenticated exact-model preflight and one real strict Responses turn pass with `gpt-5.6-luna`, medium reasoning, one attempt, bounded images/context, and no substitution |
| TO-4 simulation skill execution | Complete at the available capability boundary | Registry admits only digest-bound ACT entries; production is correctly 0/12, while injected promoted-fixture adapters prove serialization, every one-file restoration, multi-file sequences, timeout, safe-stop, and forced verification without claiming policy/MuJoCo evidence |
| TO-5 continuous restoration | Complete | Deterministic checker owns completion; bounded serial restoration passes every single-file case and two three-move sequences; ambiguous/obstructed states request user intervention without a model dispatch |
| TO-6 shadow and canary | Complete at the non-authorizing boundary | Supervised physical-shadow comparison receipts are implemented and tested with no hardware command; independent physical evaluator and single-use approval contracts are frozen; canary and unattended physical execution remain disabled as required |

## Known Gaps

- No Silicon feed or server-side snapshot token was available. The endpoint, freshness, registration, redirect, size, encoding, and credential boundaries are frozen and fixture-tested, but live connectivity is not claimed.
- Production readiness is 0/12 skills. Simulation and physical shadow remain unavailable because no compatible B--G ACT checkpoint has separate evaluator and promotion receipts.
- The fixture-only dispatcher proves orchestrator serialization and verification logic, not an evaluated ACT policy, MuJoCo task success, learned generalization, or physical behavior.
- Physical gated mode and the canary remain disabled. The independent evaluator and approval contracts now exist, but their physical runtime, current tracking/stall thresholds from a promoted receipt, gateway lease proof, and torque-off evidence do not; Brief 006 intentionally grants none of that authority.

## Follow-Up Queue

- At a workcell with the Silicon service available, set `SIM2CLAW_SILICON_SNAPSHOT_TOKEN` server-side and verify one live registered snapshot against the frozen contract without exposing the token or endpoint path to the browser.
- Admit any future B--G ACT adapter only after its checkpoint, CPU/fp32 evaluator, promotion receipt, observation/action schema, scene, workcell, and calibration identities pass the independent registry checks.
- After a compatible promoted skill exists, complete the frozen minimum five supervised shadow comparisons per skill and the independent physical evaluator before seeking explicit authorization for one bounded canary.
