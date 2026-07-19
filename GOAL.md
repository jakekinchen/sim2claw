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

The final owner-selected product benchmark is frozen separately in
[`configs/evaluations/pawn_rank12_bidirectional_v2.json`](configs/evaluations/pawn_rank12_bidirectional_v2.json):
move the near-side brown pawns between ranks 1 and 2 in both directions for
files B through G. It contains 12 directed skills. The earlier A--H v1 contract
is immutable historical evidence and no longer defines current product scope.
Exact evaluator realizations never enter training. Safe pushing and
pick/lift/place are both valid only when the same strict board-consequence and
collateral gates pass. ACT and GR00T use the same scorecard, while simulation,
learned-policy, physical read-only, and physical task evidence remain separate.

The v2 evaluator measures base-center endpoint grades, bias/covariance,
initial-to-final offset sensitivity, measured input support, geometric path
repeatability, and affine alternating-move diagnostics. The 18 recovered,
hash-bound physical recordings provide 36 visual review panels and folder-label
coverage of all 12 skills. The owner reviewed the 26 product-scope image-space
markers covering 13 recordings and all 12 skills; the five out-of-scope rows
remain excluded. No marker is admitted as a metric pose, so no self-centering,
drift, or policy result is admitted. Research-level
interpretation is further governed by the separate protocol-only
[`configs/evaluations/pawn_transition_inference_readiness_v1.json`](configs/evaluations/pawn_transition_inference_readiness_v1.json);
it does not change v2 engineering outputs or promote a checkpoint. Its
claim-eligible tier is disabled until a new protocol version is justified by a
frozen small-cluster coverage study.

Those 18 recordings were produced by leader/follower teleoperation. Their
receipts identify `human_teleoperator` as the action owner, carry no model or
checkpoint identity, and mark the corresponding policy candidates as
non-callable. They are source trajectories for the B--G benchmark and future
ACT training, not executions of learned B--G ACT policies. No compatible B--G
ACT checkpoint is present in the current project storage. The only retained
learned ACT weights are for the separate fixed rook-lift proof and must never be
substituted for the B--G benchmark.

## Immediate mission

1. Preserve the frozen `configs/tasks/chess_pick_place_act_state_v1.json`
   observation/action schema, consequence-driven skill transitions, evaluator
   gates, object-family descriptors, and train/held-out pose/composition splits
   while implementing its still-missing data and policy milestones.
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
4. Preserve all 11 folder/receipt conflicts. Seven product rows now have
   append-only owner-reviewed folder-label corrections for qualitative routing;
   those corrections do not rewrite replay or training provenance. Obtain
   independently reviewed, uncertainty-bearing metric pawn base centers plus a
   held-out-validated board calibration. Do not infer `A`, `b`, support, or
   drift from catalog labels, nominal square centers, or qualitative markers.
5. Review and freeze the physical-to-simulator joint transform, then replay
   exact requested actions without clipping. Fit geometry, timing/control, and
   contact/object parameters only when each stage has identifying observables
   and improves a frozen held-out split. Bind the owner-reported rubber-band
   fingertip wraps to a named physical hardware profile before treating
   gripper contact geometry, friction, compliance, or release behavior as
   calibrated. The current fail-closed preflight is itself the uncalibrated
   B--G baseline boundary: all 54 assets verify, but 0/18 episodes are replay
   eligible because the transform is provisional and recorded values exceed
   current simulator limits.
6. Build current-scope B--G simulation sources and evaluate ACT or GR00T only
   with a compatible checkpoint, frozen preprocessing/runtime identity, and the
   separate evaluator. The completed 1,000-step C8→A6 GR00T campaign is an
   off-product terminal negative, not B--G evidence. Do not launch another
   paid GR00T training run until a newly bounded task, admitted B--G source
   groups, and cap exist. The owner-reserved 20-hour NemoClaw deployment lane
   is separate and remains under its originating thread's compute authority.

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
- PASS: the earlier paid GR00T training worker was torn down and authenticated
  inventory for that campaign was verified empty. A later, separate NemoClaw
  workspace is owner-reserved for a 20-hour deployment lane and must not be
  mistaken for an idle GR00T worker.
- PASS: the owner-selected B1↔B2 through G1↔G2 product benchmark, 12 directed
  skills, endpoint grades, fail-closed pose admission, and scorecard are frozen.
- PASS: all 18 current recording directories and 54 catalog-bound assets are
  recovered and hash-verified; 36 proposal panels are preserved with zero
  admitted poses.
- PASS: a separate research inference protocol and reproducible replay-limit
  audit are frozen. Current claim eligibility is disabled, and the legacy
  physical mapping is explicitly not exact-replay or calibration-ready.
- PASS: recorded-action replay and staged system-ID contracts require measured
  initial velocity and units, exact unclipped controls, immutable episode
  splits, object-state provenance, observable residuals, and sensitivity. The
  canonical report admits 0/18 episodes, so no project parameter was fit.
- PASS: the exact 12-semantic B--G language surface, deterministic prompt
  provenance, group-before-prompt split rule, and evidence-count accounting are
  frozen. Current coverage is zero admitted source groups and zero training
  rows; generated prompt strings are not behavioral evidence.
- TERMINAL NEGATIVE: one bounded 1,000-step GR00T challenger completed, but its
  sole off-product C8→A6 development rollout produced 0 mm lift and 125.724 mm
  final XY error. Held-outs stayed sealed and the paid worker was deleted.
- PENDING: goal-conditioned ACT data generation and training, the
  retarget/validation pipeline, ACT-1 through ACT-6 evidence, reviewed endpoint
  poses, exact replay, held-out-improving calibration, and any later
  sim-plus-real anchoring evidence. The contract itself is already frozen and
  tested.
- BLOCKED PRODUCT CHALLENGER: no compatible B--G learned checkpoint or admitted
  current-scope training dataset exists.
- ACCEPTED ANCILLARY DIAGNOSTIC: the unmeasured rook-lift rubber-wrap run is not
  B--G evidence. Its first result was rejected because checkpoint snapshot
  bytes were not rehashed before deserialization. That bypass is repaired and
  covered by a forged-snapshot regression; a fresh authenticated rerun accepts
  only the narrow conclusion that this rook policy's simulated outcome changes
  across the declared mass-neutral contact-prior ensemble.

The robot geometry/composition slice, one narrow frozen ACT simulation task,
and the local GR00T data/evaluator foundation are complete. The goal-conditioned
ACT contract is implemented, but its dataset, trained policy, and milestone
evidence are not. This does not claim a working pick/place policy, working
GR00T policy, broad policy robustness, full-board manipulation, calibration,
gateway, sim-to-real transfer, or a physical workcell gate.
