# Autonomous Milestones

This file defines invariant milestones for autonomous work on this project.

Milestones are required outcomes, not detailed subtasks. The Executor and Reviewer choose the implementation slices needed to satisfy the next milestone.

## Overall Goal

Prove a clean-room, language-conditioned GR00T N1.7 policy-server path that
observes the simulated chess workcell and moves a named piece to a named square.
The path must preserve evaluator-owned promotion, bounded paid compute, and
simulation-only authority.

## Milestone Rules

- Milestones are invariant outcomes, not task lists.
- Agents choose implementation slices needed to satisfy the next milestone.
- The Reviewer may not mark a milestone complete without running or recording its verification gate.
- The Manager challenges work that optimizes beyond the current milestone before the gate is satisfied.
- If a milestone gate proves wrong or incomplete, update this file.

## M0 - Frozen Campaign Boundary

**Required outcome:** The model/source identity, task split, consequence gates,
diagnostic reward boundary, Brev price, spend ceiling, and teardown rule are
frozen before paid training.

**Why this is invariant:** A learned policy or reward cannot be allowed to
rewrite the test that promotes it, and paid compute cannot begin with ambiguous
scope or cost.

**Verification gate:**

```bash
uv run python -c 'from sim2claw.groot_chess import load_groot_task_contract; load_groot_task_contract()'
brev --no-check-latest ls --json
```

**Completion evidence:**

- `configs/tasks/chess_pick_place_groot_v1.json` binds NVIDIA source commit
  `23ace64f...`, disjoint cases/seeds, reward non-authority, and frozen gates.
- One A100-80GB is capped at the earlier of 08:30 CDT or $50; projected eight
  hour spend at the quoted `$1.656/hour` is `$13.248`.
- Initial authenticated Brev inventory was empty.

**Status:** PASS

## M1 - Accepted Dynamic Demonstration Dataset

**Required outcome:** At least two named piece types and multiple target-square
instructions produce GR00T LeRobot v2 demonstrations; every included episode
passes the frozen consequence evaluator, while held-out cases contribute zero
training rows.

**Why this is invariant:** GR00T post-training requires synchronized RGB,
language, proprioception, and action data. A failed scripted trajectory is a
counterexample, not an imitation target.

**Verification gate:**

```bash
uv run pytest -q
uv run sim2claw groot-expert-eval --split held_out --episode-index 0
uv run sim2claw groot-expert-eval --split held_out --episode-index 2
uv run sim2claw groot-export --output datasets/chess_pick_place_groot_v1
```

**Completion evidence:**

- Twenty-four training and four held-out scripted consequences passed locally.
- Dataset receipt, metadata, parquet, RGB videos, stats, and file hashes exist
  under ignored `datasets/chess_pick_place_groot_v1/`.

**Status:** IN PROGRESS until the pinned NVIDIA loader accepts the export.

## M2 - Pinned N1.7 Policy-Server Preflight

**Required outcome:** One Brev A100 worker runs the exact NVIDIA N1.7 source,
loads `nvidia/GR00T-N1.7-3B`, accepts the repo-native modality config and
dataset, and starts a policy server without opening a physical path.

**Verification gate:** Preserve CUDA/GPU/source/model identities, loader output,
and one finite policy response.

**Status:** PENDING

## M3 - Bounded Post-Training Candidate

**Required outcome:** One declared post-training campaign completes from the
clean base, saves fixed checkpoints, and obtains an open-loop result on held-out
data. Training never sets promotion.

**Verification gate:** Immutable run receipt plus fixed-checkpoint evaluator
artifacts and exact optimizer/data identities.

**Status:** PENDING

## M4 - Closed-Loop Chess Consequence

**Required outcome:** The policy server owns every action in held-out simulated
episodes for unseen piece/target combinations. Results are classified as pass,
partial, or terminal negative by the frozen consequence evaluator.

**Verification gate:** Action traces, RGB evidence, per-gate results, and zero
assistance frames.

**Status:** PENDING

## M5 - Evidence Preservation and Paid-Compute Teardown

**Required outcome:** Preserve selected artifacts and exact spend, delete the
non-stoppable Brev worker, and poll authenticated inventory until empty.

**Verification gate:** Recomputed artifact hashes, spend ledger, deletion
receipt, and final `brev --no-check-latest ls --json` showing no workspaces.

**Status:** PENDING
