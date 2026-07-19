# GR00T Move-Matrix Data Value Plan

Status: plan; no training launch, physical motion, or promotion is authorized
by this document

Date: 2026-07-19 America/Chicago

## Goal

Produce evidence, from simulation only, that this repository's normalized VLA
dataset improves GR00T N1.7 on commanded chess-piece moves in any direction
and any order, and quantify that improvement as a before/after delta on a
frozen benchmark. "Value to GR00T" is defined as exactly one number family:
the difference between the base checkpoint's and the fine-tuned checkpoint's
results on the same frozen move-matrix evaluation suite, scored by the
separately owned CPU/fp32 consequence evaluator. Nothing else — training
loss, dataset size, or qualitative video — counts as value.

## Input data we are building from

| Asset | Where | State |
| --- | --- | --- |
| 18 physical teleop recordings (13 rank, 3 cross-file, 2 diagonal) | hash-bound catalog + frozen sysid split | quarantined for training (0/18 exact-replay admitted); drives workcell calibration only |
| Workcell fit v1 (17.41 mm train event RMS) + move-suite fit v2 | `pawn_bg_workcell_fit*.py` | v2 awaits a run on the machine holding the recordings |
| Scripted sim expert v10 | `pawn_source_expert.py` | generates evaluator-admitted episodes, hardcoded to C8→A6 |
| Strict source evaluator | `pawn_source_evaluator.py`, contracts v1–v3 | fail-closed admission; owns all episode verdicts |
| GR00T LeRobot export + normalization | `pawn_groot_dataset.py`, `groot_multisource_dataset.py` | 20 Hz float32 sample-hold actions, synchronized RGB, language binding, mean/std/min/max/q01/q99 stats, sealed held-outs |
| Multisource mixture v2 | 73 unique sim episodes, 96 weighted, 41,088 frames | trained once; development rollout terminal negative (C8→A6, off-product) |
| 12-skill endpoint/composability benchmark | `docs/research/2026-07-19-pawn-composability-study.md` | frozen thresholds, awaiting data |
| Paid-run gate | `docs/research/2026-07-19-groot-b-g-training-gate.md` | checklist must pass before any GPU spend |
| Learning factory LF-00–LF-09 | `learning_factory*.py` | automates generate → admit → export → train → promote with receipts |

## Phase 1 — Move-matrix generator: simulated test cases without the arms

The single highest-leverage change: generalize `pawn_source_expert.py` from
its hardcoded C8→A6 into a parameterized generator over (piece, source
square, destination square), producing candidate episodes for a declared
**move matrix**:

1. The 12 directed B–G rank skills (the product surface) — `b1↔b2` … `g1↔g2`.
2. Cross-file moves (`b2→c2`-class) and diagonal moves (`c1→d2`-class),
   mirroring the move classes now first-class in the workcell-fit v2 scope.
3. Multi-square spans (`b1→e2`, `b1→g2`) up to the reachable envelope —
   span coverage currently does not exist in any dataset, physical or
   simulated.
4. Ordered sequences: forward/reverse alternating cycles and two-move
   compositions, feeding the composability study's `delta_final = A *
   delta_initial + b` estimation with controlled initial offsets.

Diversity comes from variation, not repetition (per the training-gate rule
that weighted copies count once): jittered initial pawn offsets, target
offsets, distractor placement, and approach variants, each declared in a
frozen generation contract. Every candidate passes the strict source
evaluator before it may enter any dataset; rejected cousins are counted and
retained as receipts. This is pure MuJoCo + the existing renderer — no
physical arms, runnable on any machine, automatable as a learning-factory
stage.

Two scene lanes, kept separate by contract identity:

- **Frozen-default lane**: the current registered scene, comparable with all
  existing admitted episodes.
- **Physically-grounded lane (opt-in)**: the workcell-fit v2 selected
  candidate (board pose, joint zero offsets), once its fresh diagonal
  held-out admission passes. This lane is what makes "simulation test cases"
  progressively resemble the physical cell without touching the arms.

Concrete target: all 12 rank skills × ≥6 offset seeds, plus ≥4 file, ≥4
diagonal, and ≥4 span cases × ≥3 seeds — roughly 100–200 admitted unique
episodes (40–110k frames at 20 Hz), a genuine order-of-magnitude increase
over the 73 admitted episodes that exist today, with move-class diversity
none of them have.

## Phase 2 — Normalization: making it GR00T-ready

Reuse the existing fail-closed export path; do not invent a new one:

1. Each admitted episode exports through the LeRobot adapter with
   synchronized RGB, state, language, and exact float32 20 Hz sample-hold
   actions; exact-replay verification stays mandatory.
2. A new mixture contract (`chess_manipulation_groot_multisource_v3`)
   composes the move-matrix dataset, binds normalization statistics
   (mean/std/min/max/q01/q99 per state and action dimension) computed over
   the mixture and stored hash-bound so the served model and evaluator
   provably share them.
3. The language layer binds one canonical instruction per episode
   ("move the brown pawn from b1 to b2") plus provenance-bound paraphrases;
   paraphrases never count as new episodes.
4. Unique-source vs weighted-row accounting is reported separately, and every
   held-out split is sealed before the first export.

Held-out design for the generalization claim (declared before generation):

- hold out entire squares (e.g., all moves touching `e2`),
- hold out one move class entirely from a training variant (train
  rank+file only, evaluate diagonal) to measure class extrapolation,
- hold out the longest spans.

## Phase 3 — Before/after: the value measurement

The "before" number does not exist yet and must be measured first:

1. **Freeze the evaluation suite** — 12 rank skills + fixed file/diagonal/
   span cases + the sealed held-outs, one predeclared rollout per case,
   frozen seeds, CPU/fp32 evaluator verdicts, event-RMS and gate-pass
   reporting per case. Freeze before any new training.
2. **Baseline (before)**: run the pinned base `nvidia/GR00T-N1.7-3B` —
   zero-shot, no fine-tune — on the full suite. Every prior rollout in this
   repository was a fine-tuned checkpoint; a base-model receipt is required
   for any honest "before us" claim.
3. **Fine-tune (after)**: only when the paid-run gate checklist passes,
   train on the v3 mixture and run the same frozen suite once. Fix the known
   attribution gap first: the server must rehash the checkpoint directory
   against its manifest and bind PID, command line, port, and digests into a
   client-verified handshake, so results attach to checkpoint bytes rather
   than convention.
4. **Scaling curve**: train at 25% / 50% / 100% of the move-matrix (same
   recipe, same suite). The marginal-value curve is the honest basis for
   extrapolating "how much value more data provides" — extrapolation from
   measured points, not from intuition.

Reporting: a per-case table (skill, move class, span, gates passed, event
metrics) for base vs each fine-tune, appended to the simulator progression
ledger with its receipts. Terminal negatives are recorded, not discarded.

## Phase 4 — Claim ladder for the value story

Can be claimed once measured, in increasing strength:

1. Dataset facts: unique admitted episodes, move-class/span coverage,
   admission rate, normalization identity — receipts only.
2. Simulation before/after: "on the frozen suite, base GR00T passed X/N
   cases; fine-tuned on our normalized dataset it passed Y/N" — the headline
   value number, valid only in simulation.
3. Generalization: performance on held-out squares/classes/spans versus
   trained ones — evidence the dataset teaches structure, not trajectories.
4. Data efficiency: the 25/50/100% curve slope.

Cannot be claimed from this plan: physical transfer, calibrated contact
dynamics, product task success on hardware, or GR00T model-class verdicts.
Those need separately admitted physical evidence and remain outside every
receipt this plan produces.

## Execution order and blockers

| # | Action | Needs arms? | Needs GPU? | Blocked on |
| --- | --- | --- | --- | --- |
| 1 | Run workcell-fit v2 + fresh diagonal holdout | no (needs recording files) | no | machine holding `datasets/manipulation_source_recordings/` |
| 2 | Parameterize the sim expert into the move-matrix generator + generation contract | no | no | nothing |
| 3 | Generate + strict-evaluate the move matrix, both scene lanes | no | no | 2 (lane B also 1) |
| 4 | Mixture v3 export with normalization stats + sealed held-outs | no | no | 3 |
| 5 | Freeze the evaluation suite | no | no | nothing (do early) |
| 6 | Base-model zero-shot baseline on the suite | no | yes (inference) | 5, server handshake fix |
| 7 | Fine-tune + same suite + scaling curve | no | yes (paid gate) | 4, 5, 6, gate checklist |
| 8 | Value report + ledger rows | no | no | 6, 7 |

Items 2–5 are pure local CPU work and can start immediately; they are also
exactly the work the training-gate doc requires before another paid launch.
