# Decision 0004: Goal-Conditioned ACT Pick-and-Place

Status: accepted owner direction for the primary interpretable manipulation lane

Date: 2026-07-18 America/Chicago

## Decision

Build one goal-conditioned state ACT system that can compose selected-piece and
continuous destination poses. Do not teleoperate, label, or train a separate
policy for every piece-to-square pair.

The governing design sentence is:

> Teleoperate grasp styles and corrections, not every task instance; generate
> the task instances combinatorially in simulation using object- and
> target-relative trajectory retargeting.

The task planner translates language such as "move the black rook to c6" into
structured inputs:

```text
piece_id = black_rook_a8
piece_pose = current observed pose
target_pose = board.square_pose("c6")
```

The ACT policy receives state, object, and target geometry. It does not receive
or interpret the phrase `c6`, use a one-hot destination square, or require a
checkpoint for each object/destination combination.

## Frozen baseline boundary

`chess_rook_lift_v1` and its accepted 957,350-parameter ACT checkpoint remain
immutable narrow proof of the clean-room ACT implementation. Its 31-value
observation includes fixed episode progress, a five-phase one-hot, and timed
phase progress. Those inputs were legitimate for the fixed rook-lift proof but
effectively disclose position within a scripted episode. The checkpoint must
not be evolved into or relabeled as the general pick-and-place policy.

The next contract is a new file and identity:

`configs/tasks/chess_pick_place_act_state_v1.json`

The contract must be frozen before training and must not modify
`configs/tasks/chess_rook_lift_v1.json` or
`configs/tasks/chess_pick_place_groot_v1.json`.

## Policy contract

Required observation families:

- robot joint positions and velocities;
- end-effector pose;
- gripper position or aperture;
- selected-piece pose;
- continuous destination pose;
- end-effector pose relative to the selected piece;
- selected-piece pose relative to the destination;
- piece geometry/type or grasp-family descriptor;
- optional observable contact, current, or effort values when the declared
  runtime actually provides them; and
- an optional externally derived `skill_id` whose transitions depend only on
  observable consequences.

Fixed episode progress, elapsed-time phase progress, privileged future state,
and square-class one-hots are prohibited. The action remains six absolute
SO-101 joint-position targets clipped to the actuator control range.

The initial object descriptor should support at least these grasp families:

1. rook-like cylindrical base;
2. pawn-like small base;
3. large king/queen/bishop; and
4. asymmetric knight.

One family may establish the first proof, but materially different grasp modes
need their own source demonstrations. Geometry metadata cannot substitute for
an unrepresented grasp strategy.

## Hierarchical execution boundary

Begin with a task planner, an observable skill-state machine, and learned ACT
contact skills:

1. `pregrasp`: move to a grasp pose relative to the selected piece;
2. `grasp_lift`: establish contact and lift clear of the board;
3. `transport`: move the grasped piece above the target;
4. `place_release`: lower, establish support, release, and clear contact; and
5. `retreat`: leave the board safely.

Transitions must be consequence-based:

- pregrasp to grasp: end effector within the frozen grasp-pose tolerance;
- grasp to lift: valid contact or declared closure consequence;
- lift to transport: selected piece clears the board;
- transport to place: piece reaches the target stand-off tolerance;
- place to release: piece is supported and within target tolerance; and
- release to retreat: jaw contact is clear.

For the first reliable demo, repo-native motion planning or the constructive
controller owns free-space stand-off, transit, and retreat. ACT owns the
contact-sensitive grasp/lift and place/release segments. The resulting claim is
"hierarchical learned manipulation," not "entirely end-to-end learned policy."

Separate per-skill ACT policies are the debugging-first implementation. After
the individual skill gates pass, one shared ACT model conditioned on a skill
token is the preferred consolidation experiment. Consolidation receives a new
recipe identity and cannot erase the separate-policy evidence.

## Object- and target-relative data generation

Every source episode retains the full follower trajectory and its provenance.
For a picking segment, encode the end-effector trajectory in the selected
object frame:

```text
T_object_ee(t) = inverse(T_world_object) * T_world_ee(t)
```

For a placement segment, encode it in the target frame:

```text
T_target_ee(t) = inverse(T_world_target) * T_world_ee(t)
```

Retarget into a new scene with:

```text
T_world_ee_pick_new(t) = T_world_object_new * T_object_ee(t)
T_world_ee_place_new(t) = T_world_target_new * T_target_ee(t)
```

Each candidate then passes this pipeline:

1. join local manipulation segments with collision-free lift/transit motion;
2. solve inverse kinematics for the SO-101;
3. execute the entire candidate in MuJoCo;
4. reject collision, lost grasp, wrong-piece contact, non-target displacement,
   failed placement, invalid release, or any other frozen gate failure; and
5. retain only strict evaluator successes as training episodes.

Repairs are allowed only as new, lineage-linked candidates that are replayed
and revalidated from their exact initial state. A generated episode proves only
that the data generator produced an accepted demonstration; it does not prove
learned-policy generalization.

One source trajectory may deliberately fan out across object perturbations,
destination poses, and timing/trajectory perturbations. A representative
planning calculation is `10 * 20 * 5 = 1,000` candidates before validation;
the strict-success yield, rejection reasons, and source lineage must be
reported rather than assumed.

## Teleoperation and data mixture

Use simulated leader-to-follower teleoperation first. Collect source episodes
that span the important modes rather than all board squares:

- near and far transport;
- leftward and rightward transport;
- central and edge targets;
- distinct comfortable approach/grasp choices;
- slow and fast placement; and
- recoveries from intentional small offsets.

Do not collect human teleoperation merely to prove that a geometric path
exists; the constructive expert already serves that purpose. Use teleoperation
to capture comfortable approaches, natural wrist/gripper coordination, grasp
closure and near-contact placement timing, alternative valid styles,
misalignment corrections, and realistic follower dynamics.

The first practical dataset target is 10--20 good simulated teleoperation
episodes plus existing repo-native constructive-expert trajectories, expanded
and validated into 500--2,000 successful episodes for one grasp family. Mix
validated generated nominal data, teleoperation-derived trajectories, and a
deliberately oversampled minority of correction/recovery data. Exact ratios are
experimental, but rare contact, release, avoidance, and recovery frames must
not be drowned out by free-space transit.

Physical teleoperation is a later, separately authorized proof class. Record
leader targets, follower commands, actual follower joint positions/velocities,
camera or fiducial pose inputs, available motor current/effort, timestamps,
object/target poses, and consequence success. Train against the follower
commanded target while retaining actual follower state and leader/follower
difference in observations or diagnostics. Real demonstrations anchor rather
than replace the large simulation dataset.

## Evaluator and held-outs

Reuse the consequence semantics from `chess_pick_place_groot_v1` while replacing
RGB/language conditioning with explicit state and goal poses:

- destination XY error;
- final height error;
- upright orientation;
- settled final velocity;
- gripper clearance;
- displacement of every non-target piece;
- no final jaw contact;
- model-owned actions; and
- no assistance.

Freeze evaluator behavior, generator behavior, scene cells, seeds, and split
membership before training. Training must include each object and destination
region somewhere while withholding specific object/destination pairs, entire
continuous source/target pose cells, and nearby-distractor layouts. A pair
holdout such as training on `rook -> b6,d6` and `king -> c6,e6` while evaluating
`rook -> c6` and `king -> d6` tests composition without claiming unseen object
geometry.

## Ordered curriculum

1. **ACT-1, variable-pose grasp/lift:** one grasp family, source offsets and
   yaw; require valid grasp, minimum lift, stable unsupported hold, and no board
   collision, with no progress/phase-clock inputs.
2. **ACT-2, variable-target placement:** begin already grasped and condition on
   a continuous target; require placement error, uprightness, settling, clear
   release, and clear retreat.
3. **ACT-3, sparse-board full pick/place:** join ACT-1 and ACT-2 with only one
   or two visible pieces. This is the first full pick-and-place claim.
4. **ACT-4, combinatorial held-outs:** evaluate withheld object/target pairs and
   full continuous pose cells.
5. **ACT-5, distractors/collision avoidance:** progress from target only to a
   distant distractor, nearby distractor, sparse board, and finally full board.
6. **ACT-6, recovery:** inject bounded object-pose error, delayed gripper
   response, joint offsets, partial contact, and object motion; save human or
   constructive-expert corrective suffixes with exact intervention lineage.

No later rung may retroactively broaden an earlier claim.

## Lane relationship

ACT is the reliable, explicit state/goal manipulation path. GR00T remains the
RGB/language and wider-generalization challenger. The planner provides
structured piece and target poses to ACT and raw language/RGB to GR00T. Both
lanes use evaluator-owned consequence gates; neither policy, training loss,
reward, source demonstrator, or data generator can promote itself.

## Research rationale, not project proof

The owner adopted these research results as rationale for the program; they do
not prove that this repository has reproduced them:

- [MimicGen](https://arxiv.org/abs/2310.17596) reported more than 50,000
  generated demonstrations across 18 tasks from roughly 200 human
  demonstrations, including 1,000 demonstrations for new reset distributions
  from ten source demonstrations.
- [SkillMimicGen](https://proceedings.mlr.press/v270/garrett25a.html) separates
  local manipulation skills from free-space motion and reported more than
  24,000 demonstrations from 60 human demonstrations.
- [ACT](https://arxiv.org/abs/2304.13705) uses conditional-VAE action chunks to
  reduce effective horizon and demonstrated difficult real tasks with about 50
  demonstrations/ten minutes per task; that scale is not assumed to transfer.
- [Sim-and-Real Co-Training](https://arxiv.org/abs/2503.24361) reported an
  average 38% benefit from adding simulation data across its studied tasks;
  this motivates later mixed-data experiments but is not a guarantee here.

No new implementation dependency is adopted by this planning decision.

## Consequences and claim limits

- Dataset generation replaces combinatorial manual teleoperation; it does not
  replace strict simulation replay or held-out policy evaluation.
- Destination retargeting is expected to transfer more readily than grasp
  geometry; grasp families and material mode coverage remain explicit.
- Timed stage inputs are removed. An externally computed observable stage is
  permitted only with the hierarchical claim boundary.
- Full-board evidence remains closed until the full-board distractor rung
  passes. The existing queen-sweep counterexample remains binding.
- Physical camera, gateway, serial, servo, calibration, and motion authority
  remain closed until their separately frozen phases and owner gates pass.
