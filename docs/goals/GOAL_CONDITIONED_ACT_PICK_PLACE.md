# Goal: Goal-Conditioned ACT Pick-and-Place

Use this file as the durable prompt for the primary interpretable manipulation
program. Continue until the next frozen milestone is evidenced or a genuine
external blocker is the sole remaining condition. Do not skip proof rungs.

## Mission

Build and evaluate a hierarchical, goal-conditioned state ACT system that moves
a selected chess piece to a continuous destination pose without one policy or
manual teleoperation demonstration per piece-square pair. Create the training
set from a small, diverse source set through object/target-relative retargeting,
collision-free stitching, IK, complete MuJoCo replay, and strict evaluator
admission.

## Source of truth

Use these sources in authority order:

1. The owner's governing directive embedded in this goal: "Teleoperate grasp
   styles and corrections, not every task instance; generate the task instances
   combinatorially in simulation using object- and target-relative trajectory
   retargeting."
2. `AGENTS.md` and its clean-room, evidence-class, evaluator-ownership, gateway,
   paid-compute, and generated-artifact boundaries.
3. `docs/decisions/0004-goal-conditioned-act-pick-place.md` for architecture,
   representations, data generation, curriculum, and claim limits.
4. The future frozen `configs/tasks/chess_pick_place_act_state_v1.json`; once
   reviewed and frozen, its exact gates/splits outrank prose defaults here.
5. `configs/tasks/chess_pick_place_groot_v1.json` for consequence-evaluator
   semantics only, not policy modality or training data.
6. `configs/tasks/chess_rook_lift_v1.json` and its run log as immutable narrow
   ACT evidence, never as the new task contract.
7. Current repo-native receipts, action traces, datasets, session logs, and
   `docs/autonomous-workflow/project_state.json` for live evidence state.
8. The cited public research papers as design rationale only. The read-only
   archive may provide lessons but no source, data, artifact, or authority.

## Intended outcome

One frozen state/goal task accepts a structured piece pose and continuous target
pose, then uses observable consequence-driven skill transitions to execute a
hierarchical pick-and-place. A few simulated teleoperation and constructive
expert trajectories become a large, lineage-complete set of strict-success
training episodes across source/target poses. A separately invoked CPU/fp32
evaluator demonstrates performance on unseen pose cells, unseen
object/destination combinations, and progressively harder distractor/recovery
conditions. GR00T remains the RGB/language challenger; physical authority
remains closed. Separate skill policies are the debuggable interim system; after
their gates pass, a versioned shared ACT model conditioned on observable
`skill_id` is the desired long-term consolidation candidate.

## Confirmed requirements

- Preserve `chess_rook_lift_v1` and its checkpoint unchanged as narrow proof.
- Create a new `chess_pick_place_act_state_v1` contract; never silently mutate a
  frozen task, evaluator, split, or accepted receipt.
- Express goals as continuous poses. The planner, not ACT, resolves language or
  board-square names into `piece_id`, `piece_pose`, and `target_pose`.
- Observe joints/velocities, end-effector pose, gripper state, piece/target
  poses, relative transforms, and object geometry/family. Optional contact or
  current values must be genuinely observable and declared.
- Remove episode progress, elapsed-time phase progress, and fixed timed phase
  one-hots from the new policy input.
- Keep six absolute SO-101 joint-position targets as actions.
- Use consequence-driven `pregrasp`, `grasp_lift`, `transport`,
  `place_release`, and `retreat` transitions.
- Initially plan or construct free-space stand-off, transit, and retreat; learn
  contact-sensitive grasp/lift and place/release. Label the result hierarchical.
- Retarget source manipulation segments in object and target frames, stitch
  them with collision-free motion, solve IK, execute the complete candidate in
  MuJoCo, and admit strict successes only.
- Preserve source episode, segment, transform, planner, IK, simulator, repair,
  and evaluator lineage for every generated candidate and accepted row.
- Reuse GR00T placement consequence semantics under the separately owned
  CPU/fp32 evaluator. Training, reward, source expert, generator, and policy
  never promote themselves.
- Freeze generator behavior, seeds, pose cells, object/destination pairs,
  distractor layouts, splits, and evaluator gates before training.
- Keep generated data, checkpoints, credentials, caches, observations,
  `outputs/`, and `runs/` out of Git.
- Keep camera, serial, gateway, robot motion, calibration, sim-to-real, and
  physical claims closed until separately authorized and evidenced.

## Recommended defaults

These are the starting recipe, not permission to weaken an invariant when a
number proves infeasible:

- debug separate skill ACT policies first; test a shared model with `skill_id`
  only after the individual gates pass;
- collect 10--20 diverse simulated teleoperation source episodes for one grasp
  family and include repo-native constructive-expert sources;
- generate 500--2,000 strict-success training episodes across broad continuous
  source and destination poses;
- include near/far, left/right, central/edge, multiple approach styles, slow/fast
  placement, and intentional small-offset recoveries;
- mix mostly validated nominal generated data with teleoperation-derived data
  and an oversampled minority of correction/recovery episodes; select exact
  ratios by frozen experiments;
- expand grasp families in this order unless geometry evidence says otherwise:
  rook-like, pawn-like, large king/queen/bishop, asymmetric knight.

Record any departure and its evidence before generating a replacement dataset.

## Milestones and acceptance criteria

### ACT-0: frozen contract and negative fixtures

Complete when the new config and loader/schema tests freeze:

- exact observation ordering, frames, units, and dimensions;
- six-target action representation and limits;
- observable skill-transition predicates and tolerances;
- object/grasp-family descriptor schema;
- generator version and lineage schema;
- source/target pose cells, object/pair holdouts, distractor layouts, and seeds;
- GR00T-derived consequence gates; and
- deterministic negative fixtures for timing leakage, split leakage, wrong
  piece, collision, spill, loss, bad placement, non-clear release, assistance,
  and non-model-owned actions.

No training rows may be generated before this gate passes.

### ACT-1: variable-pose grasp and lift

One grasp family, random source offsets and yaw, no destination. Pass requires
valid grasp, frozen minimum lift, stable unsupported hold, no board/distractor
collision, model-owned learned contact actions, and no progress clock.

### ACT-2: variable-target placement

Begin with the object already held and supply a continuously sampled target
pose. Pass requires target XY/height tolerance, uprightness, settled velocity,
clear release, and clear retreat on withheld target pose cells.

### ACT-3: sparse-board full pick-and-place

Join grasp and placement with one or two visible pieces. Every action owner and
planner/ACT handoff must be explicit. This is the earliest rung that can claim
full pick-and-place, and only for its frozen sparse-board distribution.

### ACT-4: combinatorial composition

Train with every object and destination region represented somewhere while
withholding declared object/destination pairs and complete continuous pose
cells. Pass only on zero-row held-outs. Report pair, pose-cell, and aggregate
results separately.

### ACT-5: distractors and collision avoidance

Progress through target only, one distant distractor, one nearby distractor,
sparse board, and full board. Preserve the existing queen-sweep failure as a
required counterexample class. Do not skip directly to a full-board claim.

### ACT-6: correction and recovery

Inject frozen small pose errors, delayed gripper response, joint offsets,
partial contact, and object motion. Allow a human or constructive expert to
take over, save the exact corrective suffix and intervention state, and train a
versioned recovery mixture. Pass on held-out perturbations without undeclared
assistance.

### ACT-7: physical anchoring, later and separately authorized

Only after simulation gates and gateway prerequisites pass, collect physical
leader/follower teleoperation with synchronized commands, actual state,
timestamps, pose sensing, available current/effort, and outcomes. Co-train a
versioned sim-plus-real candidate; never treat published average improvements
as a promised local result. This milestone grants no authority by its presence
in the roadmap.

## Evidence standard

Before claiming a milestone, surface:

- changed config/code/docs and exact Git identity;
- source episode count and provenance by human, teleoperation, constructive,
  generated, repaired, and corrective class;
- candidate/accepted/rejected generation counts and rejection-reason histogram;
- dataset receipt, split audit, lineage hashes, observation/action statistics,
  and held-out zero-row proof;
- exact training recipe, checkpoint hashes, environment, and accelerator;
- separately owned evaluator command/output, per-gate results, action ownership,
  assistance/intervention frames, traces, and replayable media;
- comparison to the previous rung without changing its gate;
- remaining blockers and claim limits; and
- authenticated paid-resource inventory/teardown proof whenever Brev was used.

Training loss, generated-episode yield, a good-looking video, or one successful
training-distribution rollout is diagnostic evidence only.

## Locked final product benchmark

`configs/evaluations/pawn_rank12_bidirectional_v1.json` is the final
owner-selected task-coverage scorecard. It asks for A1→A2 and A2→A1, repeated
through H, for 16 directed cases. Three exact simulation realizations per case
produce 48 zero-training-row episodes. The exact seeds, initial-state
perturbations, reset rules, gates, and rollouts never enter training.

This benchmark is consequence-based: safe pushing and safe pick/lift/place are
both valid if the pawn finishes upright, settled, and inside the requested
square while the robot clears contact and non-target pieces remain undisturbed.
It does not replace the compositional/continuous-pose held-outs above; those
measure generalization, while this scorecard measures complete coverage of the
owner's concrete product task.

Every fixed ACT checkpoint must report 48-row simulation results by file and
direction. The later physical run is a separate 16-trial scorecard and requires
the same checkpoint plus separately authorized pose sensing and consequence
evaluation. The five recorded physical episodes may become training sources
after admission but can never be recycled as benchmark trials.

## Execution rhythm

1. Inspect `GOAL.md`, this file, Decision 0004, current project state, the exact
   frozen contracts, recent receipts, current branch, and worktree dirt.
2. Choose the smallest slice that advances the current ACT milestone without
   opening a later proof class.
3. Freeze or version its contract before data generation or training.
4. Implement and run the smallest relevant deterministic tests.
5. Record exact evidence and counterexamples in ignored outputs plus a concise
   tracked run/session log.
6. Invoke the separate evaluator and compare against the milestone criteria.
7. Update the project-state ledger; continue until the milestone passes or a
   true external blocker is isolated.

Do not spend paid compute to discover a contract, dataset, loader, or auth issue
that can be proven locally. If Brev is used, stop/delete it immediately after
the bounded task and verify authenticated inventory before ending.

## Progress ledger

```text
Current milestone: M7 retargeted strict-success dataset foundation
Contract/config identity: chess_pick_place_act_state_v1 @ 3f1fcdbb...
Current state: five saved physical source episodes reviewed; final 16-case product benchmark frozen; zero training rows admitted
Completed: source hash audit, video review, joint-response-only MuJoCo replay, intake ledger, bidirectional rank-1/rank-2 eval contract
Evidence: configs/data/physical_teleop_episode_intake_20260718.json; configs/evaluations/pawn_rank12_bidirectional_v1.json
Counterexamples: one push-only strategy; one laggy-start episode; three move-metadata conflicts
Dataset counts and lineage: 5 physical sources / 2,186 samples / 0 admitted rows
Evaluator result: no physical consequence evaluator result; all formal outcomes unreviewed
Paid resources: none opened for intake
Remaining: implement benchmark reset/evaluator, reconcile coordinates/outcomes, annotate pose and skill segments, run versioned admission gate
Blockers: benchmark evaluator implementation plus authoritative physical piece/target pose and strict physical consequence verdict are absent
Next smallest step: implement deterministic reset fixtures for all 16 cases without generating training or eval rows
Claim boundary: physical teleoperation source evidence only; no ACT, GR00T, or task-success claim
```

## Stop conditions

Stop the current run when the current milestone is evidenced, an external owner
action is the sole blocker, a frozen identity mismatch is detected, continuing
would cross into a later authority class, or an authorized paid-compute bound
is reached. Preserve partial and terminal-negative evidence; never change gates
to convert it into a pass.
