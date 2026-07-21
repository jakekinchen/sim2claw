# AI Build Run Log: Fixed-Data Multimodal Reality-Gap Pipeline

Request: Preserve the immutable physical corpus, exploit every defensible
telemetry/video signal, build the event-conditioned real-versus-simulator and
training-ablation pipeline, and prepare a similar-hardware validation lane.

Repo/path: `/Users/kelly/Developer/sim2claw`

Started: 2026-07-20

Completed: offline build complete; provider, exact replay, and training gates blocked

Owner constraints: original data cannot be recollected; same robot hardware
may be available later, but the board/environment may differ; do not invent
contact, force, object-pose, latency, simulator, policy, or transfer evidence.

## Acceptance Criteria

- See `docs/autonomous-workflow/goal-loop-fixed-data-reality-gap.md`.
- The first runnable slice covers deterministic events, visual strips,
  event-conditioned physical metrics, and no-provider Inspect integration.
- Later simulator, provider, training, and physical validation slices remain
  separately gated and retain terminal-negative results.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Contract and implementation | Codex | Author clean-room plan, schemas, extractor, interfaces, and tests | Live repo authority and immutable local corpus | Tracked source/docs and ignored run artifacts |
| Deterministic extraction | Python, NumPy, OpenCV, Pillow | Compile events, metrics, and synchronized strips | Hash-bound sample/video bytes | Event receipts, phase rows, PNG strips |
| Agent harness | Inspect AI and Inspect SWE | Present bounded evidence to matched Codex/Claude systems | Public event cards and host-bridged evidence | Preserved annotations and audits |
| Scientific authority | Deterministic evaluator/Learning Factory | Validate schemas, held-out identities, replay, and admission | Frozen contracts and receipts | Scores, rejections, or typed blockers |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Goal-loop plan | User instruction and live authority | Goal-builder structure | `docs/autonomous-workflow/goal-loop-fixed-data-reality-gap.md` | Tracked execution authority below user/frozen contracts |
| Event corpus | Retained physical recordings | `scripts/materialize_interaction_event_pipeline.py` | `runs/fixed-data-event-pipeline-v1/` | Ignored; retrospective derived evidence only |
| Visual evidence strips | Hash-bound overhead videos | Deterministic frame decode/renderer | `runs/fixed-data-event-pipeline-v1/train-final/episodes/*/interaction_strip.png` | Qualitative image evidence, not metric pose/contact |
| Publication analysis | Generated corpus and retained replay audit | Deterministic aggregation and claim review | `docs/research/2026-07-20-fixed-data-event-analysis.md` | Paper-facing tables and explicit limitations |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Authority/corpus audit | Catalog and split inspection | 18 episodes, 7,741 rows, nine move IDs, 15 train/3 held-out | This log |
| Focused tests | `uv run pytest -q tests/test_interaction_events.py tests/test_inspect_interaction_events.py` | 8 passed in 42.00 s | Test output |
| Deterministic materialization | Two independent train materializations | Matching logical digest `9bae6677fee15968721f7236f23d6a1f01bf524e0e4c6428a282586f9dfd5784` and matching corpus file bytes | `runs/fixed-data-event-pipeline-v1/train-final/` and `train-repeat/` |
| Evaluator-owned held-out | Separate `--partition held_out --evaluator-owned` invocation | 3 episodes, 1,255 rows, 18 candidates, digest `59cf1895bad444d1a1c51c5d83b172e1c02389d742e3ba8a282ce47987b84848` | `runs/fixed-data-event-pipeline-v1/held-out-evaluator-final/` |
| Visual inspection | Original-resolution representative strip | Synchronized 3 x 3 strip is readable at 1920 x 1560; file hash `307f301e0a44db6cf56261d6792e65886bde91ba98ef59c76c11cab5ba7f27ed` | `train-final/episodes/20260719T030059Z-a26f8400/interaction_strip.png` |
| Inspect task discovery | `uv run --group inspect inspect list tasks evals/inspect_gapbench/event_task.py` | `sim2claw_interaction_event_audit` discovered without a provider call | Task module |
| Compile and whitespace | `compileall`; `git diff --check` | Pass | Tracked implementation |
| Full repository suite | `uv run pytest -q` | 557 passed and 328 subtests passed in 289.67 s | Test output |

Final contract SHA-256:
`dd974ce26f3577db7b0eba130e7cf9a829c8b621ff38c08226036a2f262106f6`.
The contract binds the implementation and Inspect artifacts; generated run
artifacts separately bind their own source lineage and logical payloads.

## Known Gaps

- Exact simulator replay is currently ineligible for all 18 episodes.
- Object poses, physical contact, force, calibrated effort, and true latency
  were not recorded.
- Current is a cached 5 Hz raw device proxy.
- Provider/VLM calls and policy training have not been authorized or executed
  by this offline build slice.
- A future similar scene is new evidence unless exact environment identity is
  independently established.

## Follow-Up Queue

- Freeze and authorize any provider/system annotation campaign before calls.
- Resolve exact replay eligibility before reporting real-versus-sim results;
  the legacy 0/18 audit remains binding despite the historical source-fit gain.
- Admit any event-balanced training rows through the existing independent
  dataset evaluator before training.
- Run the similar-scene protocol as a new workcell unless every identity field
  is independently proven unchanged.
