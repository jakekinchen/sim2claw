# Decision 0006: Bidirectional Rank-1/Rank-2 Pawn Evaluation

Status: historical frozen v1 benchmark; superseded as current product authority

Superseded by:
`configs/evaluations/pawn_rank12_bidirectional_v2.json` and
`docs/decisions/0009-pawn-bidirectional-composability-evaluation.md`

Date: 2026-07-18 America/Chicago

Machine-readable contract:
`configs/evaluations/pawn_rank12_bidirectional_v1.json`

Contract SHA-256:
`f3dac8b86cd7b0252153d25c0d5c09204079003ac9780642992fd10bc08e0d43`

## Supersession note

This file preserves the accepted 2026-07-18 A--H v1 proposal and its campaign
plan without rewriting history. The owner later narrowed the current product
surface to the 12 B--G, rank-1/rank-2 directed skills. Current-facing claims,
training gates, and checkpoint comparisons use v2. Nothing below authorizes an
A/H product claim, a new paid run, or reuse of v1 evaluator rows.

## Decision

The durable product question is now:

> How reliably can the robot move each near-side pawn between ranks 1 and 2 in
> both directions?

The core set has 16 directed cases: A1→A2 and A2→A1, repeated for files B
through H. Each case is an independent board-reset trial. The target pawn
starts on the requested source square, the destination is empty, the other
seven near-side brown pawns stay at their canonical sparse-layout squares, and
the eight far-side tan pawns remain static distractors.

This is the final task-coverage scorecard for comparing progress over time. It
is not an unseen-language benchmark: the same semantic moves may be represented
in training. What stays held out is every exact evaluator realization, seed,
initial-state perturbation, rollout, and physical trial. Evaluation rows always
contribute zero training rows.

## Consequence and strategy boundary

Success is defined by the requested board consequence, not a mandatory motion
style. A safe push and a safe pick/lift/place are both eligible. The evaluator
requires the target pawn to finish upright, settled, and inside the destination
tolerance; the robot must be clear; non-target pieces must remain within the
frozen displacement limit; actions must be model-owned; and assistance is a
failure. Strategy is recorded as a diagnostic breakdown.

This outcome-based benchmark does not weaken or mutate the existing frozen
pick/lift/place task evaluators. Those remain valid for claims specifically
about grasping and lifting. This new contract owns only the broader product
claim that the robot moved the requested pawn safely between the two squares.

## Simulation and physical scorecards

Simulation uses three frozen realizations for every directed case: nominal,
positive pose/joint jitter, and negative pose/joint jitter. The result is 48
zero-training-row episodes. A physical evaluation run uses one standardized
trial for each directed case, or 16 trials, with the same reset and consequence
rules. Simulation and physical results are reported separately.

The primary score is macro success across the 16 directed cases. Every report
also includes both direction rates, each file's two-direction rate, the worst
file, direction parity, time to success, maximum collateral displacement,
assistance count, and strategy. The complete product target is 48/48 frozen
simulation realizations plus 16/16 physical cases for the same checkpoint.

No average may hide a missing file or one-way-only behavior. A physical video
or operator note is not an evaluator verdict, and a simulation result is not a
physical result.

## Relationship to the recorded physical episodes

The five owner-local physical recordings are training-source candidates, not
benchmark trials. After their metadata, outcomes, pose annotations, and segment
lineage are repaired, they can teach contact style, pushing, grasping, release,
and hesitation recovery. Object/target-relative retargeting and the constructive
expert can scale those styles across the rank-1/rank-2 move family with disjoint
training seeds. The original recordings must never be relabeled as frozen eval
rows or replayed as the physical benchmark.

## ACT plan

1. Implement the frozen 16-case reset builder and separate evaluator before
   generating benchmark traces.
2. Reconcile the physical-source metadata and admit only lineage-complete
   segments; preserve push and grasp strategies as explicit classes.
3. Generate broad training variations for all 16 semantic moves using seeds,
   offsets, timings, and trajectories disjoint from the 48 evaluator rows.
4. Evaluate every fixed ACT checkpoint on all 48 simulation rows. Select by
   consequence score, worst-file coverage, collateral, and direction parity,
   never training loss.
5. Run the separately authorized 16-trial physical scorecard only after the
   simulation gate, pose sensing, and physical evaluator exist.

The separate continuous-pose/compositional held-outs in Decision 0004 still
measure generalization. They complement this fixed product-coverage benchmark;
neither replaces the other.

## GR00T and Brev plan

The current `chess_pick_place_groot_v1` rook/king task remains byte-for-byte
frozen. The pawn benchmark requires a new versioned RGB/language/action task and
dataset rather than mutating v1.

Before another paid Brev run:

1. implement and locally test the 48-row evaluator export and official NVIDIA
   loader contract;
2. generate evaluator-disjoint pawn training episodes with all 16 instructions,
   multiple valid strategies, pose jitter, nearby-pawn avoidance, and recovery;
3. preserve exact dataset, modality, simulator, evaluator, model, and source
   identities in the run receipt;
4. train from the declared clean N1.7 base under a new bounded budget, with
   fixed checkpoint intervals;
5. sweep every checkpoint across the same 48 frozen rows and compare ACT and
   GR00T through evaluator receipts only; and
6. turn the largest failure class into new disjoint expert/correction examples,
   never train on a frozen evaluator rollout.

The five C922 recordings cannot enter GR00T until they have reconciled labels,
formal outcomes, synchronized RGB/proprioception/action export, and a new
versioned LeRobot modality receipt. No Brev worker is authorized or opened by
this decision.

## Mutation and claim rule

The case list, reset rules, seeds, gates, and scorecard are frozen. A needed
change creates `pawn_rank12_bidirectional_v2`; it does not rewrite v1. This
decision proves that the benchmark is specified, not that an evaluator,
dataset, policy, simulation pass, or physical pass exists.
