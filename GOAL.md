# Clean-Room Build Goal

Build sim2claw manually from the available design and research documents,
starting from a documentation-only repository and producing fresh,
repo-native implementation and evidence for every capability.

## Current achieved slice

- Python 3.12, MuJoCo 3.10.0, Pillow 12.3.0, and PyTorch 2.11.0 are directly
  pinned; `uv.lock` freezes the transitive environment.
- A fresh bootstrap and fail-closed Mac/NVIDIA doctor are implemented.
- Capture `8873B66C-774C-48B1-B51D-338645867009` is fetched with exact
  SHA-256 verification into ignored storage and converted by repo-native code.
- A new MuJoCo scene builds the measured table, a configurable chessboard, and
  32 dynamic pieces plus two articulated SO-101 arms; it compiles, steps, and
  renders on this Apple Silicon Mac.
- The chess scene now applies an owner-measured SO-101 mass profile in memory:
  `907 g` bare and `1,006 g` for the left arm with its D405 payload, with a
  conservative `965--1,047 g` bound while hardware, mount, and cable masses
  remain estimated. CAD centers and scaled inertia tensors remain priors.
- The scene is compositionally aligned to the owner-provided photo with the
  fiducial sheet, tripod, rear window/blinds, and portrait viewpoint. Estimated
  mounts and poses remain distinct from measured geometry.
- The scan can render as a non-colliding reference overlay. Physical authority
  remains closed.
- A frozen `chess_rook_lift_v1` task now separates eight training seeds from a
  zero-training-row held-out seed and binds a separately invoked CPU/fp32
  evaluator before policy selection.
- A fresh 957,350-parameter state-based ACT policy trained locally on MPS and
  passed one held-out simulation episode: 94.88 mm maximum rook lift, 94.01 mm
  final rise, 1,083 consecutive jaw-contact steps, and no assistance.
- A separate frozen GR00T N1.7 task now binds RGB, language, six-joint state,
  six-joint targets, two named pieces, disjoint destination cases, a diagnostic
  reward with no promotion authority, and evaluator-owned placement gates.
- Twenty-four sparse-board training experts and four zero-training-row held-out
  experts passed. Their ignored GR00T LeRobot v2.1 export contains 8,712 frames
  with parquet/video/meta/stats identities bound by a dataset receipt.

## Governing long-term direction

The primary interpretable manipulation lane is now a new goal-conditioned,
state-based ACT program. The governing design sentence is:

> Teleoperate grasp styles and corrections, not every task instance; generate
> the task instances combinatorially in simulation using object- and
> target-relative trajectory retargeting.

`chess_rook_lift_v1` and its accepted checkpoint remain frozen as narrow proof
that the clean-room ACT implementation can learn one fixed rook-lift task. They
must not be revised into, relabeled as, or used to claim the general policy.
That receipt predates the owner-measured mass profile and is not evidence that
the checkpoint passes under the heavier current dynamics; requalification must
be separately invoked and recorded.
The replacement contract will be `chess_pick_place_act_state_v1`: continuous
selected-piece and destination poses, relative transforms, robot state, object
geometry, and observable skill state in; six absolute SO-101 joint targets out.
Fixed episode progress, timed phase progress, and square-specific policies are
not part of that contract.

The first reliable system is hierarchical. A task planner resolves language to
`piece_id`, measured/simulated `piece_pose`, and continuous `target_pose`; an
observable consequence-driven skill state machine sequences manipulation; ACT
learns the contact-sensitive grasp/lift and place/release skills. Ordinary
motion planning or the constructive controller owns initial free-space
stand-off, transit, and retreat. Any such result is claimed as hierarchical
learned manipulation, not end-to-end policy control.

GR00T remains a separate RGB/language generalization challenger. It reuses the
same evaluator semantics but does not displace the state/goal ACT lane, and ACT
does not consume raw chess language or require a checkpoint per piece-square
pair. The accepted architecture and long-horizon execution contract are in
[`docs/decisions/0004-goal-conditioned-act-pick-place.md`](docs/decisions/0004-goal-conditioned-act-pick-place.md)
and
[`docs/goals/GOAL_CONDITIONED_ACT_PICK_PLACE.md`](docs/goals/GOAL_CONDITIONED_ACT_PICK_PLACE.md).

## Immediate mission

1. Freeze `configs/tasks/chess_pick_place_act_state_v1.json`, its observation
   and action schema, consequence-driven skill transitions, evaluator gates,
   object-family descriptors, and train/held-out pose/composition splits before
   generating training rows.
2. Build a repo-native simulator data path that ingests constructive-expert and
   simulated-teleoperation source episodes, converts contact segments to
   object/target-relative trajectories, retargets them across continuous poses,
   plans collision-free connecting motion, solves IK, replays every candidate
   in MuJoCo, and admits strict successes only.
3. Execute the ACT curriculum in order: variable-pose grasp/lift, variable-goal
   placement from an already-held piece, sparse-board full pick/place,
   combinatorial held-outs, distractors/collision avoidance, then corrective
   recovery data. The first practical dataset target is 10--20 good simulated
   source episodes plus constructive experts expanded into 500--2,000 accepted
   episodes for one grasp family.
4. Keep the gated GR00T campaign preserved as a challenger and external-access
   blocker; do not spend more Brev money until its access preflight passes and a
   separately bounded task is authorized.

## Non-goals at this boundary

- Do not copy source code, scripts, configurations, receipts, outputs,
  checkpoints, datasets, caches, or runtime environments from the archive.
- Do not treat imported documents as live authority or current proof.
- Do not claim Mac, NVIDIA, simulator, policy, gateway, camera, serial, or robot
  readiness before fresh repo-native verification exists.
- Do not manually teleoperate every piece-square combination, encode squares as
  policy classes, or train one checkpoint per pair.
- Do not present retargeted demonstrations as proof that a policy generalized;
  only frozen held-out consequence evaluation can establish that claim.
- Do not claim an externally staged or planned hierarchy is an entirely
  end-to-end learned policy.

## First milestone acceptance status

- PASS: a documented dependency lock and host support matrix exist.
- PASS: a new bootstrap creates the runtime from declared upstream sources.
- PASS: one new table-and-chess simulator workcell compiles and renders in
  process on a Mac.
- PASS: the same doctor contract has a fail-closed NVIDIA/EGL preflight.
- PASS: fresh tests and a run log are tracked; the ACT source implementation is
  recorded in commit `361e042`.
- PASS: no physical hardware path is opened.
- PASS: the first task, split, ACT recipe, and CPU/fp32 evaluator are frozen in
  repo-native code/configuration; one model-owned held-out episode passed.
- PASS: a dynamic language/RGB chess contract, accepted sparse-board expert
  dataset, disjoint held-out cases, and consequence evaluator are frozen.
- PASS: the earlier paid GR00T worker was torn down and authenticated Brev
  inventory was verified empty.
- PENDING: the new goal-conditioned ACT contract, retarget/validation pipeline,
  ACT-1 through ACT-6 evidence, and any later sim-plus-real anchoring evidence.
- BLOCKED CHALLENGER: GR00T optimizer steps and learned closed-loop consequences
  remain blocked on gated `nvidia/Cosmos-Reason2-2B` access.

The robot geometry/composition slice, one narrow frozen ACT simulation task,
and the local GR00T data/evaluator foundation are complete. The goal-conditioned
ACT program is planned but not yet implemented or proven. This does not claim a
working pick/place policy, working GR00T policy, broad policy robustness,
full-board manipulation, calibration, gateway, sim-to-real transfer, or a
physical workcell gate.
