# Autonomous Milestones

This file defines invariant milestones for autonomous work on this project.

Milestones are required outcomes, not detailed subtasks. The Executor and Reviewer choose the implementation slices needed to satisfy the next milestone.

## Overall Goal

Prove a clean-room hierarchical manipulation system that moves a selected chess
piece to a continuous destination pose. The primary reliable lane is explicit
state/goal ACT trained from a small source set expanded by object/target-relative
retargeting and strict simulation validation. GR00T remains the separate
RGB/language generalization challenger. Both lanes preserve evaluator-owned
promotion, bounded paid compute, and simulation-only authority.

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

**Completion evidence:**

- NVIDIA's loader at the frozen source commit accepted 24 episodes and the
  declared language, state, action, and front-video modalities on A100-80GB.

**Status:** PASS

## M2 - Pinned N1.7 Policy-Server Preflight

**Required outcome:** One Brev A100 worker runs the exact NVIDIA N1.7 source,
loads `nvidia/GR00T-N1.7-3B`, accepts the repo-native modality config and
dataset, and starts a policy server without opening a physical path.

**Verification gate:** Preserve CUDA/GPU/source/model identities, loader output,
and one finite policy response.

**Evidence:** The exact source, A100/CUDA/Torch environment, dataset loader, and
base-model revision passed. A finite custom policy response was not reached
because model construction required gated `nvidia/Cosmos-Reason2-2B` access.

**Status:** PARTIAL; policy response remains open behind the gated dependency.

## M3 - Bounded Post-Training Candidate

**Required outcome:** One declared post-training campaign completes from the
clean base, saves fixed checkpoints, and obtains an open-loop result on held-out
data. Training never sets promotion.

**Verification gate:** Immutable run receipt plus fixed-checkpoint evaluator
artifacts and exact optimizer/data identities.

**Evidence:** The fixed 250-step command was launched, but Hugging Face denied
the Cosmos dependency before optimizer step zero. No checkpoint was created.

**Status:** BLOCKED on human acceptance/access for the gated NVIDIA model.

## M4 - Closed-Loop Chess Consequence

**Required outcome:** The policy server owns every action in held-out simulated
episodes for unseen piece/target combinations. Results are classified as pass,
partial, or terminal negative by the frozen consequence evaluator.

**Verification gate:** Action traces, RGB evidence, per-gate results, and zero
assistance frames.

**Status:** NOT RUN; there is no learned checkpoint to evaluate.

## M5 - Evidence Preservation and Paid-Compute Teardown

**Required outcome:** Preserve selected artifacts and exact spend, delete the
non-stoppable Brev worker, and poll authenticated inventory until empty.

**Verification gate:** Recomputed artifact hashes, spend ledger, deletion
receipt, and final `brev --no-check-latest ls --json` showing no workspaces.

**Completion evidence:** Workspace deletion was requested at 01:06:47 CDT.
Authenticated inventory at 01:15:57 CDT returned `workspaces: null`. Estimated
spend is approximately `$0.30`, with a conservative bound of `$0.40`.

**Status:** PASS

## Strategic program after the bounded GR00T campaign

M0--M5 above preserve the first GR00T challenger campaign exactly as it ran:
local data/evaluator success, a gated dependency before optimizer step zero,
and verified paid-resource teardown. They are not rewritten as ACT evidence.
The active next program begins at M6 and is governed by
`docs/decisions/0004-goal-conditioned-act-pick-place.md` and
`docs/goals/GOAL_CONDITIONED_ACT_PICK_PLACE.md`.

## M6 - Frozen State/Goal ACT Contract

**Required outcome:** A new `chess_pick_place_act_state_v1` contract freezes
continuous object/target pose inputs, robot and relative state, object-family
descriptors, six absolute joint targets, observable skill transitions,
generator lineage, train/held-out pose cells and object/destination pairs, and
the GR00T-derived consequence gates before any training rows exist.

**Why this is invariant:** Retargeting can create leakage at combinatorial scale.
The evaluator, generator behavior, coordinate frames, and splits must therefore
be fixed before either the data generator or learner can optimize against them.

**Verification gate:** Contract/schema tests plus deterministic negative
fixtures reject fixed progress clocks, invalid frames/units, held-out rows,
wrong-piece motion, collision/spill, bad placement, non-clear release,
assistance, and non-model-owned actions. The frozen rook ACT and GR00T v1 files
remain unchanged.

**Status:** NEXT; planning accepted, config and tests not yet implemented.

## M7 - Retargeted Strict-Success Dataset

**Required outcome:** Repo-native constructive and simulated-teleoperation
sources are segmented into object/target-relative contact trajectories,
retargeted across continuous source/goal poses, stitched through collision-free
motion, solved through SO-101 IK, and fully replayed in MuJoCo. Only strict
successes enter the ACT dataset.

**Verification gate:** Exact source/segment/transform/planner/IK/simulator/
repair/evaluator lineage for every candidate; accepted/rejected counts and
rejection histogram; deterministic replay; dataset receipt and zero held-out
training rows. The practical first recipe is 10--20 diverse simulated source
episodes plus constructive experts expanded into 500--2,000 accepted episodes
for one grasp family.

**Status:** NOT STARTED.

## M8 - ACT-1 Variable-Pose Grasp and Lift

**Required outcome:** One grasp family is grasped and lifted from withheld
continuous source-pose cells without episode progress or timed phase progress.
ACT owns the learned contact actions; planned free-space actions remain labeled.

**Verification gate:** Valid grasp, frozen minimum lift, stable unsupported hold,
no board/distractor collision, model-owned learned actions, zero assistance,
action traces, and CPU/fp32 evaluator receipts.

**Status:** NOT STARTED.

## M9 - ACT-2 Variable-Target Placement

**Required outcome:** From an already-grasped reset, one goal-conditioned ACT
placement skill reaches continuously sampled destinations, releases, and clears
the piece on withheld target-pose cells.

**Verification gate:** Destination XY and height error, uprightness, settled
velocity, no final jaw contact, gripper/retreat clearance, zero assistance, and
model-owned learned actions all pass the separate evaluator.

**Status:** NOT STARTED.

## M10 - ACT-3/4 Sparse Pick-and-Place Composition

**Required outcome:** The hierarchical system composes grasp and placement on a
sparse board for zero-row object/destination-pair and continuous-pose-cell
held-outs. Planner, state-machine, and ACT action ownership remain explicit.

**Verification gate:** Full pick/place gates pass for every required held-out;
pair, pose-cell, and aggregate results are reported separately; no stage clock,
square one-hot, task-specific checkpoint, or training-row leakage exists.

**Status:** NOT STARTED.

## M11 - ACT-5 Distractors and Collision Avoidance

**Required outcome:** Evidence progresses through target-only, distant
distractor, nearby distractor, sparse-board, and full-board layouts without
moving non-target pieces beyond the frozen limit.

**Verification gate:** Per-piece displacement, wrong-contact, spill, placement,
release, ownership, and assistance results pass. The known queen-sweep
counterexample remains a mandatory rejection fixture.

**Status:** NOT STARTED.

## M12 - ACT-6 Correction and Recovery

**Required outcome:** A versioned correction mixture teaches recovery from
frozen object-pose error, delayed gripper response, joint offsets, partial
contact, and object motion. Human/constructive takeovers retain exact branch and
corrective-suffix lineage.

**Verification gate:** Held-out perturbation consequences pass without
undeclared assistance; correction and nominal strata are reported separately.

**Status:** NOT STARTED.

## M13 - Separately Authorized Physical Anchoring

**Required outcome:** Only after simulation and gateway gates pass, collect a
small physical teleoperation anchor set and evaluate a versioned sim-plus-real
candidate under a separately frozen physical proof contract.

**Verification gate:** Every physical episode records leader target, follower
command, actual follower state, timestamps, pose sensing, available
current/effort, and outcome. The training action is the follower command;
actual state and leader/follower difference remain observable evidence. Any
physical rollout requires explicit owner authority and the one reviewed
gateway. Published sim-plus-real gains are rationale, not a local success gate.

**Status:** DEFERRED; not authorized by this roadmap.
