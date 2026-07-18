# Slice Brief 002: Goal-Conditioned ACT Contract

**Date:** 2026-07-18

**Milestone:** M6 - Frozen State/Goal ACT Contract

## Objective

Create and freeze `configs/tasks/chess_pick_place_act_state_v1.json` plus the
smallest loader/schema and deterministic fixture surface needed to prove that
the new continuous-goal ACT contract is coherent and leakage-resistant. Do not
generate a training dataset or train a policy in this slice.

The owner-confirmed current scene layout is two-sided and sparse: brown pawns
at A2, B1, C2, D1, E2, F1, G2, H1 and mirrored tan pawns at A8, B7, C8, D7,
E8, F7, G8, H7. The standard full-chess scene remains a legacy proof layout.

## Product / Project value

This replaces the combinatorial "one demonstration/checkpoint per
piece-square pair" framing with one explicit state/goal contract. It also
prevents the object/target retargeting generator from defining or leaking into
its own held-outs after data generation begins.

## Acceptance criteria

- Add a new versioned contract without modifying the frozen
  `chess_rook_lift_v1` or `chess_pick_place_groot_v1` contract bytes.
- Freeze the exact observation order, dimensions, units, coordinate frames, and
  observability rules for joints/velocities, end-effector, gripper,
  selected-piece pose, continuous target pose, relative transforms, object
  descriptor, and optional observable skill/contact data.
- Explicitly reject episode progress, timed phase progress, square one-hots,
  raw language, privileged future state, and unavailable sensor placeholders.
- Keep six clipped absolute SO-101 joint-position targets as actions.
- Freeze consequence-based transition predicates and tolerances for pregrasp,
  grasp/lift, transport, place/release, and retreat. Distinguish planner-owned,
  ACT-owned, and state-machine-owned behavior.
- Freeze an extensible grasp-family descriptor with pawn-like as the first
  supported family and rook-like, large king/queen/bishop, and asymmetric
  knight as declared later families.
- Reuse the GR00T evaluator semantics for destination, height, uprightness,
  settling, gripper clearance, non-target displacement, final jaw contact,
  action ownership, and assistance. Training and diagnostic reward have no
  promotion authority.
- Freeze source/target continuous pose cells, seeds, object/destination pair
  holdouts, distractor layouts, generator identity, and candidate-lineage
  fields before any rows are admitted.
- Add deterministic positive schema fixtures and negative fixtures for timing
  leakage, split leakage, frame/unit errors, wrong piece, collision/spill, lost
  grasp, bad placement, non-clear release, assistance, and non-model-owned
  actions.
- Preserve simulation-only authority and keep every generated artifact out of
  Git.

## Expected files

- `configs/tasks/chess_pick_place_act_state_v1.json`
- `src/sim2claw/act_pick_place.py` or one equivalently scoped repo-native
  contract module
- `tests/test_act_pick_place.py`
- a concise run/session log recording the frozen config and test identities
- updates to the decision/goal/state only if implementation proves a documented
  contradiction; never silently revise the owner directive

## Test plan

Test deterministic load/round-trip behavior, exact feature ordering and
dimensions, legal SE(3) frames/units, continuous-goal encoding, action bounds,
transition observability, train/held-out disjointness, generator-lineage
completeness, evaluator ownership, and every declared negative fixture.

Record SHA-256 before and after for both frozen predecessor task files and fail
the slice if either changes.

## Validation commands

```bash
uv run pytest -q
uv run python -c 'from sim2claw.act_pick_place import load_act_pick_place_task_contract; load_act_pick_place_task_contract()'
git diff --check
```

The module/import name may be changed once during implementation if repo
conventions require it; update this brief and the validation command before
claiming the contract frozen.

## Evidence to record

- new contract SHA-256 and schema version;
- unchanged SHA-256 values for both frozen predecessor contracts;
- exact observation/action dimensions, order, frames, and units;
- exact transition predicates and which component owns each action interval;
- split census proving zero overlap and zero held-out training rows;
- generator and lineage schema identity, even though generation is deferred;
- positive and negative fixture results; and
- explicit statement that no dataset, checkpoint, policy result, or physical
  authority was created by this slice.

## Reachability / demo proof

Construct a deterministic fixture in which the planner resolves
`brown_pawn_a2` and `board.square_pose("c3")` to structured poses. Show that the
contract can encode this state and a second continuous destination using the
same observation schema, with no square class or policy identity change. Show
that timed phase/progress input is rejected.

This is contract reachability only, not a learned pick-and-place demo.

## Cross-doc impact

On completion, mark M6 with the exact contract/test evidence, update
`project_state.json` to M7, and author the next bounded retarget-and-validate
brief. Do not mark ACT-1 or a dataset milestone complete.

## Out of scope

Trajectory segmentation, motion planning, IK implementation, bulk episode
generation, teleoperation collection, ACT training, shared skill-token models,
GR00T retraining, full-board evaluation, gateway work, calibration, camera,
serial, robot motion, and physical data.

## Stop conditions

Stop if a required input is not observable in the declared runtime, coordinate
frames cannot be made unambiguous, the held-out partition leaks through the
generator plan, a frozen predecessor contract would need mutation, or work
would cross into data generation/training. Preserve the contradiction and route
it to Decision 0004 and the owner rather than guessing.
