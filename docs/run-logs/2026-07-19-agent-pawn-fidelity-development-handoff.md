# Agent B-G Pawn Fidelity Development Handoff

Date: 2026-07-19 America/Chicago

## Purpose

This document reconstructs the work performed by our agent in an isolated
worktree, explains how each diagnostic led to the next change, and records the
unfinished improvement lane visible when the work paused.

This is a read-only handoff assembled from the worktree's commit history,
tracked run logs, uncommitted source, and ignored receipts. It is not an
integration decision. The current checkout, frozen contracts, evaluator-owned
admission, and reproducible receipts remain authoritative.

## Snapshot and proof state

- Work surface: isolated agent worktree and branch
- Last committed revision: `fa5746153180ef4d2a4824645bb38df1436efbb5`
- Last commit time: 2026-07-19 06:42:29 -05:00
- Last observed uncommitted write: 2026-07-19 07:37:52 -05:00
- Remote state at inspection: no branch with this name on `origin`
- Process state at inspection: the agent process still had the isolated
  worktree as its working directory, but the files had not changed since the
  times above
- Unique committed slice relative to current `main`: 14 patch-unique commits,
  20 files, approximately 4,443 added lines and 6 removed lines

Committed evidence and unfinished work must be treated separately:

1. The committed source-fit result is terminal-negative and rejects the fitted
   adapter.
2. The later ignored receipts show a substantial kinematic-only gain from a
   different parameterization.
3. The code that produced the later receipts is uncommitted, lacks a committed
   closeout, and grants no training, policy, physical-calibration, or promotion
   authority.

## The progression

### 1. Freeze a task-specific B-G evaluator before changing the fit

Commits:

- `b72a943` — freeze B-G pawn simulation reward gates
- `7bc41a1` — evaluate B-G demonstrations in simulation
- `3e137e2` — document the terminal-negative result

The work began by making the B1-G2 rank-1/rank-2 question executable rather
than judging it visually. It added:

- `configs/evaluations/pawn_bg_sim_reward_v1.json`
- `src/sim2claw/pawn_bg_reward.py`
- `src/sim2claw/pawn_bg_demo_sim.py`
- focused reward and replay tests

The evaluator separated shaped diagnostic reward from hard task gates. The
hard gates included lift, whole-base target containment, composable and
precision centering, uprightness, settled state, selected-piece contact and
release, absence of wrong-piece contact, collateral-motion bounds, and finite
state. Source-command replay was explicitly prevented from claiming learned
policy success.

The first replay used 13 owner-reviewed physical teleoperation recordings,
5,562 rows, and four contact variants. All 52 episode/variant runs failed
before meaningful pawn interaction:

- selected-piece contacts: 0
- lifts: 0
- task successes: 0
- mean final target error: approximately 44.45 mm
- maximum rise: approximately 0.00014 mm
- all 13 recordings required command clipping in every variant

This ruled out rubber-tip friction as the first-order explanation: the
simulated tips never reached the selected pawn. The actionable problem became
command/frame/workcell compatibility before contact modeling.

### 2. Fit the recorded joint source convention, then reject it honestly

Commits:

- `6245c9c` — fit a bounded B-G source joint adapter
- `849499e` — render the comparison history
- `b7e29ed` — document the source-fit terminal negative

The next approach fitted joint signs and zero offsets using a deterministic
gripper-close/reopen event proxy. It compared forward-kinematic pinch points
against labeled source and destination square centers while enforcing command
range constraints.

Measured gain:

- provisional adapter event RMS: 309.55 mm
- best bounded candidate event RMS: 118.42 mm
- relative RMS reduction: 61.74%
- clipping under the candidate: eliminated for the permitted rows

The gain was not accepted because task consequences became no better:

- contacts: 0/11
- lifts: 0/11
- successes: 0/11
- maximum selected-pawn rise: effectively zero

The candidate also required multi-radian offsets and sign changes that were a
poor physical explanation for a supposedly near-identity SO-101 joint
convention. The frozen admission rule therefore selected no adapter and
recorded `terminal_negative_no_source_fit_adapter_accepted`.

This phase's main value was diagnostic. It demonstrated that an unconstrained
joint-frame explanation could reduce point error without producing contact or
a credible calibration.

### 3. Correct the comparison camera and board presentation

Commits:

- `86bcb72` — match the comparison to the C922 angle
- `2453f13` — document the rerender
- `a5dff97` — correct C922 camera corner mapping
- `0b93770` — document the corrected mapping
- `58899e1` — correct the B-G visual board layout

The agent then improved the diagnostic surface so physical and simulated
motion could be compared from the same approximate viewpoint. It fitted a
visual-only C922 perspective transfer and corrected the checkerboard-symmetric
corner ambiguity. The final board-corner reprojection residual was reported as
1.94 px RMS and 3.00 px maximum.

Owner review then corrected four display facts:

- beige and brown square colors had been exchanged;
- the two sides' pawn colors had been exchanged;
- the robot-side sparse row was B1, C2, D1, E2, F1, G2;
- robot-side A/H pawns were absent from the reviewed scene.

These changes were isolated to the review renderer. They did not rescore the
frozen evaluator or convert the visual transfer into camera calibration.

The key diagnosis exposed by this phase was that the simulated board labeling
appeared rotated 180 degrees relative to the physical, owner-reviewed board.
That observation later became the first categorical step of the unfinished
workcell fit.

### 4. Separate encoder-state agreement from dynamic command following

Commits:

- `9ce21f0` — add measured joint-state comparison replay
- `ade3fff` — isolate B-G appearance from the frozen scene
- `fa57461` — document joint-state replay evidence

The comparison was split into two distinct modes:

1. `measured_actual_state` places simulator joints at the mapped follower
   encoder state and calls `mj_forward`. This is a kinematic visualization and
   has zero simulator-minus-mapped-encoder error by construction.
2. `command_driven_physics` sends the source commands through the MuJoCo
   actuators. This is the relevant motion-model diagnostic.

For the 368-sample B1 recording, command-driven joint RMS errors relative to
the mapped measured state ranged from 1.83 degrees at shoulder pan to 3.33
degrees at elbow flex. The analysis found tracking-error stalls/holds, but did
not establish a mechanical stop or fit joint limits, gains, damping, or action
semantics.

This decomposition prevented a visually aligned encoder replay from being
mistaken for a good actuator model. It also pointed to two independent gaps:
workcell/frame alignment and command-following dynamics.

## Uncommitted work after `fa57461`

The worktree then began a replacement workcell-fit lane. The following files
were uncommitted at inspection:

- `configs/optimization/pawn_bg_workcell_fit_v1.json`
- `src/sim2claw/pawn_bg_workcell_fit.py`
- `src/sim2claw/pawn_bg_actuator_sysid.py`
- modifications to `src/sim2claw/scene.py`
- modifications to `docs/reference/PHYSICAL_REPLAY_JOINT_LIMIT_AUDIT_20260719.json`

Ignored receipts existed under:

- `outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v1/`
- `outputs/pawn_bg_act_v1/pawn_bg_actuator_sysid_v1/`

### Revised hypothesis

The new approach replaced free joint signs and large offsets with a staged,
more physically interpretable explanation:

1. Rotate the board labels 180 degrees as a categorical correction.
2. Fit a bounded planar board-center and board-yaw correction.
3. Keep all joint signs at identity and fit bounded joint zero offsets.
4. Compare a general small-offset model, a model with base-height/reopen-timing
   nuisance terms, and a lift-dominant model allowing a larger shoulder-lift
   offset.
5. Select among the candidates by training-side selected-piece contact count,
   breaking ties by lower event RMS.
6. Open the two frozen held-out episodes once after candidate selection.

The selected `stage_d_lift` candidate used:

- board yaw relative to table: 184.91 degrees
- board center in table frame: approximately (-10.63 mm, -66.31 mm)
- shoulder-lift zero offset: 18.70 degrees
- other fitted zero offsets: near zero
- joint signs: all identity
- command clipping: none in candidate replays

### Preliminary gains from the revised fit

Training-side kinematic progression:

| Stage | Event RMS |
|---|---:|
| Frozen baseline | 309.55 mm |
| 180-degree relabel | 106.71 mm |
| Planar board fit | 89.41 mm |
| Small joint offsets | 39.70 mm |
| Height/timing nuisance model | 26.14 mm |
| Selected lift-dominant candidate | 17.41 mm |

Training-side task consequences for the selected candidate:

- episodes with selected-piece contact: 9/11
- episodes with a lift: 1/11
- task successes: 0/11
- mean maximum rise: 6.36 mm
- mean final target distance: 60.47 mm

The once-opened held-out receipt reported:

- held-out candidate event RMS: 23.55 mm
- held-out frozen-baseline event RMS: 327.53 mm
- declared kinematic admission threshold: 60 mm
- clipping: none
- kinematic-only admission: true
- selected-piece contact: observed in both held-out episodes
- lifts: 0/2
- task successes: 0/2

This is a real gain in the worktree's own frozen kinematic metric, and it moves
the replay from no contact to repeatable contact. It is not task success,
physical calibration, or sim-to-real validation. In particular, one held-out
episode ended 326.10 mm from its target.

### Actuator system-identification attempt

After improving workcell alignment, the agent began fitting four bounded global
actuator parameters on joint tracking:

- command latency
- actuator gain scale
- joint damping scale
- actuator force-range scale

The fitted candidate was close to nominal:

- latency: effectively 0 seconds
- gain scale: 0.9976
- damping scale: 1.0917
- force-range scale: 1.0529

The improvement was small but repeated on held-out data:

| Split | Nominal simulator RMS | Fitted simulator RMS | Absolute gain |
|---|---:|---:|---:|
| Train | 2.0408 degrees | 2.0316 degrees | 0.0093 degrees |
| Held out | 2.1322 degrees | 2.1234 degrees | 0.0088 degrees |

This suggests that global actuator tuning was not the main remaining error
source. The receipt correctly limits the result to joint-space evidence.

## What it was trying to improve next

The unfinished code and receipts indicate the next objective was to turn the
newly recovered contact into reliable lift and placement while determining
whether contact priors or actuator dynamics explained the remaining failures.
The intended path appears to have been:

1. Preserve the 180-degree board correction and the selected bounded workcell
   candidate that reduced event RMS and removed clipping.
2. Re-run the rubber-tip ensemble now that 9/11 training episodes reach the
   selected pawn, making contact sensitivity observable rather than dormant.
3. Use command-versus-encoder tracking to decide whether actuator latency,
   damping, gain, or torque saturation materially improves replay.
4. Diagnose why contact rarely becomes lift and why no trajectory completes a
   one-square placement.

The generated contact-sensitivity summary shows why this remained unfinished:

| Variant | Episodes with contact | Episodes with lift | Mean rise | Mean final distance |
|---|---:|---:|---:|---:|
| Nominal | 9 | 1 | 6.36 mm | 60.5 mm |
| Rubber low | 9 | 1 | 8.65 mm | 69.8 mm |
| Rubber midpoint | 9 | 0 | 5.18 mm | 60.9 mm |
| Rubber high | 9 | 0 | 10.12 mm | 62.8 mm |

No variant demonstrated task success. Contact modeling had finally become
relevant, but it had not produced a stable grasp, useful transport, release,
or centering result.

## Required closeout before integration

The uncommitted lane should not be merged as-is. A reviewer or continuing agent
should require at least the following:

1. Freeze the current ignored receipts and hashes in a tracked run log without
   upgrading kinematic admission into a task or physical claim.
2. Add focused tests for the new workcell-fit and actuator-sysid modules,
   including split isolation, one-time held-out use, candidate-selection order,
   clipping rejection, and unchanged defaults in `scene.py`.
3. Re-run the full suite, lock check, package build, and `git diff --check` from
   the exact candidate commit.
4. Audit whether the 18.70-degree shoulder-lift offset has independent physical
   support. It is bounded, but much larger than the other fitted offsets and
   could be compensating for an unmodeled geometry or event-timing error.
5. Treat the held-out set as opened. Do not tune further against those two
   episodes and then reuse their 23.55 mm result as fresh held-out evidence.
6. Keep the actuator fit diagnostic unless a separately frozen rule shows a
   meaningful improvement. The current gain is only about 0.009 degrees RMS.
7. Require task-level lift, transport, release, and centering evidence before
   admitting demonstrations for training or broadening pawn capability claims.

## Integration preparation

Before publishing this handoff and the paused implementation, the integrating
agent added seven focused regression tests covering the non-authorizing
contract, frozen 13-recording scope, identity joint signs, opt-in scene-yaw
override, actuator parameter scaling, and candidate receipt loading. The
intentional `scene.py` source change also required refreshing the bound Studio
source hash and deterministic scene-revision expectation; no default scene
behavior was changed.

Verification on the exact pending tree:

- focused workcell-fit tests: 7 passed;
- full suite: 411 passed and 306 subtests passed in 21.79 seconds;
- `uv lock --check`: passed with 94 packages resolved;
- source distribution and wheel: built successfully;
- `git diff --check`: passed.

## Bottom line

The agent's most important contribution was not a solved pawn move. It changed
the diagnosis from "the recorded commands never approach the pawn" to "a
specific board-frame correction and bounded workcell candidate recover
kinematic proximity and repeated contact." It did so while preserving the
negative task result: there are still zero complete moves, the physical
calibration is not established, and no training or promotion authority follows.

The promising unfinished hypothesis is that the original 180-degree board
labeling mismatch dominated the source-fit failure. The remaining work is no
longer gross frame alignment; it is explaining and validating grasp/lift and
transport behavior without overfitting the already-opened held-out episodes.
