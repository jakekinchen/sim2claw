# GR00T B--G Training Gate

Status: no new paid training authorized by this decision

Date: 2026-07-19 America/Chicago

## Decision

Do not launch another Brev GR00T run yet. Build the current-scope data,
language, simulator-baseline, and identity layers first. A training launch is
worth paying for only when its frozen development result can answer a B--G
product question and its retained evidence can be attributed to the exact
dataset, checkpoint, runtime, and evaluator.

The completed GR00T campaign's worker was deleted and its campaign-specific
inventory was verified empty at teardown. Any current NemoClaw workspace is a
separate owner-reserved deployment lane, not a GR00T training worker. The
completed 1,000-step run is a terminal-negative infrastructure result for one
off-product C8-to-A6
development rollout: zero pawn lift and 125.724 mm final XY error. It is not a
negative result for the GR00T model class or for the B1/B2 through G1/G2 product
surface.

## Work That Proceeds Without Paid Compute

### 1. Freeze the semantic and language layer

Every source episode should bind one canonical structured goal:

- `piece_id`, piece family/color, observed source pose, and source square;
- destination square and continuous target pose;
- direction, board/workcell identity, and named hardware profile;
- one canonical instruction plus provenance-bound paraphrases;
- task outcome, failure/correction tags, and proof class; and
- source action/video/state hashes and the exact observation/action schema.

Paraphrases improve language coverage but do not create independent robot
episodes. Weighted copies, alternate prompts, camera views, or replays of the
same actions count once when measuring data diversity. Evaluation instructions
and semantic combinations freeze separately and never enter training prompt
augmentation.

The first current-scope dataset should cover all 12 directed B--G skills with
accepted current-geometry simulation sources. It should vary initial pawn
offsets, target offsets, distractors, and approach conditions rather than repeat
one nominal trajectory many times. Visual recordings remain context or
physical read-only evidence unless synchronized actions and admission rules make
them valid policy rows.

### 2. Measure the uncalibrated simulator baseline

The first simulator comparison is recorded-action replay, not closed-loop
policy execution. After a reviewed physical-to-simulator joint transform exists:

1. initialize from the measured state;
2. apply the exact recorded command sequence without clipping;
3. retain requested and applied controls separately;
4. compare measured and simulated joints, timing, and gripper signals; and
5. report unavailable EE, pawn, contact, grasp, and release observables as
   unavailable rather than inferred.

This establishes how the nominal simulator responds to the physical commands
before parameters are changed. It does not establish contact fidelity.

Closed-loop ACT or GR00T replay is a post-calibration test, after staged
calibration improves frozen held-out recorded-action replay. It also requires a
compatible B--G checkpoint and frozen preprocessing/runtime identity. The
accepted ACT checkpoint implements only `chess_rook_lift_v1`; running it on
this pawn task would not measure B--G sim-to-real agreement.

### 3. Calibrate in identifiable stages

Geometry, timing/control, and contact/object parameters remain separate. Each
parameter needs both a supporting observable and nontrivial sensitivity, and a
calibrated model must improve a frozen held-out episode set.

The physical gripper has an owner-reported rubber-band wrap at each claw tip,
approximately four to five wraps per side. This likely changes effective tip
geometry, friction, compliance, grip force, and release behavior. The durable
configuration observation is
`docs/reference/PHYSICAL_GRIPPER_TIP_MODIFICATION_20260719.json`. Until it is
measured and bound to acquisition sessions, the simulator should treat contact
parameters as uncertain priors, not as calibrated hardware constants.

### 4. Launch only after the paid-run gate passes

A new Brev campaign requires all of the following before instance creation:

- a hash-bound B--G dataset with unique-source and weighted-row counts;
- all 12 directed skills represented by accepted current-geometry sources;
- frozen canonical task semantics, prompt augmentation rules, and held-outs;
- an exact observation/action/preprocessing contract supported by the model;
- a retained base-checkpoint and processor inventory;
- server self-attestation and pre-query checkpoint/runtime verification;
- a separately owned frozen CPU/fp32 evaluator;
- one bounded development case inside product scope;
- a dollar/hour limit, wall-clock cap, artifact-retention plan, and automatic
  teardown path; and
- a written stop rule with no automatic retry.

If any item fails, improve the dataset or infrastructure locally rather than
spending GPU time.

## Claim Ladder

The repository can currently claim implementation and protocol readiness,
complete endpoint evidence recovery, an off-product terminal-negative GR00T
run, and an empty paid-resource inventory. It cannot claim a working B--G
policy, calibrated contact physics, or sim-to-real transfer.

A future nominal-replay result may claim only the observables it measures. A
held-out-improving joint/timing fit does not imply pawn-contact fidelity. A
simulation policy result is a learned-policy simulation result. A B--G policy
claim requires frozen current-scope held-out evaluation, and a physical or
sim-to-real claim requires separately admitted robot evidence when hardware is
available.
