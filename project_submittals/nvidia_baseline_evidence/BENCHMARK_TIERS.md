# Benchmark tiers — two tracks, one shared discipline

**Status: drafted locally, not yet committed or pushed pending review.**

Both tracks below reuse the same reference evidence and the same rule: a
policy or orchestrator is never graded by itself. Track 1 is buildable now
against data already in this repo. Track 2 depends on an overnight run and
existing but not-yet-executed infrastructure; it is upside, not the fallback.

## Shared ground truth (not a benchmark subject — the fixed reference)

- `configs/tasks/chess_rook_lift_v1.json` — frozen ACT task, held-out seed
  `9101`, CPU/fp32 evaluator. Result on record: 94.88mm max lift, 94.01mm
  final rise, 1,083 consecutive jaw-contact steps.
- `configs/tasks/chess_pick_place_groot_v1.json` — frozen GR00T task,
  language+RGB conditioned, sparse-board curriculum.
- `physical-replay-evidence-20260719` GitHub Release — camera-verified
  physical command-trace replay (see `BASELINE_SUMMARY.md`), proof class
  `physical_teleoperation_source_unqualified`.

Nothing below is allowed to upgrade the evidentiary weight of these — a
benchmark result can *cite* them, never *promote* them.

---

## Track 1 — LLM orchestration benchmark ("in the bag")

**Question it answers:** given a scene state and an instruction, which LLM
picks the correct skill and target, and does that decision hold up across
a full task, not just one step?

| Tier | What's tested | Ground truth | Scoring |
|---|---|---|---|
| **1 — Single-decision accuracy** | Orchestrator output `{piece_id, target_pose}` for one instruction + observed state | The actual piece/target choices recorded in existing teleop/ACT episodes | Exact match against the recorded choice, per episode |
| **2 — Closed-loop task completion** | Full skill sequence to reach a goal state (e.g. a complete chess move) | Same frozen evaluator already gating ACT/GR00T (pass/fail + margin) | Same evaluator, same held-out set — no new metric invented |
| **3 — Cross-model leaderboard** | Tiers 1–2 run identically across orchestrators | N/A — this tier only aggregates | Table: model × (Tier 1 accuracy, Tier 2 pass rate, Tier 2 margin) |

Orchestrators to run through Tier 3, in priority order:

1. **Claude** — already working live against the physical arm; this run is
   the receipted version of what's already demoed.
2. **Nemotron (vanilla)** — baseline, no fine-tuning, same input/output
   schema as Claude's.
3. **Nemotron (NeMo-Aligner DPO fine-tuned)** — trained on preference pairs
   extracted from accepted vs rejected/corrected episode receipts, per the
   plan scoped earlier this session.

This entire track runs on data and evaluators that already exist in this
repo. The only new work is the orchestrator-swap harness (Tier 1/2 runner)
and the DPO data-prep step for item 3 — nothing here is blocked on new
hardware time.

---

## Track 2 — GR00T fine-tune benchmark (overnight, upside not fallback)

**Question it answers:** does fine-tuning on our data measurably raise
GR00T's capability, including on cases the current model documented as
failing.

Existing infrastructure this reuses directly (already in `scripts/brev/`):

- `run_groot_n17_chess_finetune.sh` — fine-tune run against
  `chess_pick_place_groot_v1`, 250 steps, saves every 125.
- `evaluate_groot_n17_chess_checkpoints.sh` — checkpoint sweep evaluator,
  already parameterized for steps `1000 2000 3000 4000 5000`, reports
  Average MSE/MAE per checkpoint via `open_loop_eval.py` against a held-out
  split.

| Tier | What's tested | Method | Status |
|---|---|---|---|
| **0 — Baseline** | Pretrained GR00T-N1.7-3B, no fine-tuning | `evaluate_groot_n17_chess_checkpoints.sh` at step 0 / pinned base snapshot | Runnable now |
| **1 — Fine-tuned checkpoint sweep** | Same held-out set, checkpoints 1000–5000 | Same script, post-finetune | Needs the overnight `run_groot_n17_chess_finetune.sh` job to finish |
| **2 — Capability-expansion regression** | Does fine-tuning fix a *specific, already-documented* failure — the full-board expert that "moved the target but swept a queen off the board" (per `README.md`) | Re-run that exact failing case through the fine-tuned checkpoint | Needs Tier 1's checkpoints |
| **3 — Before/after comparison** | Baseline vs best fine-tuned checkpoint, matched held-out cases | Paired comparison, MSE/MAE delta plus Tier 2's pass/fail | Needs Tiers 0–2 |

Tier 2 is the tier worth highlighting to NVIDIA specifically — it's not a
generic "the loss went down" claim, it's "here is a failure we already
published in our own README, and here is whether fine-tuning resolved it."
That is a much stronger claim than an aggregate metric and costs nothing
extra to compute once Tier 1 exists.

---

## Why two tracks instead of one script with a coin flip

Track 1 has no dependency on tonight's compute succeeding. Track 2 depends
on a job that "there's no guarantee will be working by tomorrow." Keeping
them as two distinctly-scoped benchmark tracks — not two versions of the
same script — means Track 1's results are final and presentable regardless
of Track 2's outcome, and Track 2 only ever adds to the presentation, never
gates it. The single shared script this maps to is the *presentation
script* with a marked branch point (see prior discussion); this document is
the benchmark spec that script's two branches draw from.

## External reference data (Hugging Face) — three uses, kept distinct

Public LeRobot-format SO-101 datasets on the Hugging Face Hub
(`lerobot/svla_so101_pickplace` and community equivalents) share this
project's exact embodiment and format, so they plug into existing tooling
without a conversion step. They are external reference data, not captured
evidence — tag anything derived from them with a distinct proof class,
same discipline as everything else in this repo. Verify each dataset's
license/card before use.

1. **Track 2, new Tier 2.5 — generalization check.** Run the chess-tuned
   GR00T checkpoint against a held-out external SO-101 dataset (different
   task, same embodiment). Tests whether chess fine-tuning caused
   catastrophic forgetting on unrelated manipulation — a materially
   stronger "enhancement" claim than an aggregate in-domain metric alone.
2. **Run-configuration check, before spending overnight compute.** NVIDIA's
   own official "Post-Training Isaac GR00T N1.5 for LeRobot SO-101 Arm"
   reference run reports loss plateauing around step 1,500–2,000 (0.080 at
   step 500 → 0.040 at step 1,500) and MSE 0.017 at convergence — the same
   metric `evaluate_groot_n17_chess_checkpoints.sh` already reports.
   `run_groot_n17_chess_finetune.sh` currently defaults to `MAX_STEPS=250`,
   roughly 6-8x short of NVIDIA's own published convergence point. Confirm
   this is intentional before tonight's run, or Tier 1 risks an
   undertrained checkpoint regardless of data quality.
3. **Track 1, second task family.** Train/validate one additional ACT skill
   against a public SO-101 dataset so the Tier 3 orchestrator leaderboard
   isn't scored on a single chess task alone — an orchestrator × skill-family
   matrix is a stronger comparison than orchestrator × one task.

External reference numbers worth citing directly when presenting (not
sim2claw results, context only): NVIDIA's own MSE 0.017 convergence point,
and GR00T N1.5 vs N1 base success rate (38.3% vs 13.1% across 12 DreamGen
tasks) as a realistic-magnitude anchor for any fine-tune delta claimed here.

## Open dependencies before either track produces a citable number

- Track 1 needs the orchestrator-swap harness (Tier 1/2 runner) built —
  not yet started.
- Track 1's DPO fine-tune (leaderboard item 3) needs the receipt-to-
  preference-pairs converter — not yet started.
- Track 2 needs the overnight fine-tune job kicked off with enough lead
  time to finish before it's needed.
- Both tracks' results, once produced, should publish through the same
  GitHub Release evidence pattern as `physical-replay-evidence-20260719` —
  see the open item in that release's automation gap noted earlier this
  session.
