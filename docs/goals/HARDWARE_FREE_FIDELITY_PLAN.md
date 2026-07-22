# Hardware-Free B--G Fidelity Plan v1.2

Status: the v1.1 campaign reached a publication-safe contact/transport terminal
negative on 2026-07-20. A bounded action-frozen continuation on 2026-07-21
verified a significant trace-fidelity advancement. Simulator composite
promotion and training admission still fail closed on grasp/transport.

## Objective

Explain and reduce the simulator-side error exposed when the existing physical
teleoperation action arrays are replayed unchanged. Use only retained data and
local CPU/MPS compute. Produce a publication-grade diagnostic result even if
no candidate passes the composite fidelity gate.

The near-term product is a calibrated *explanation*, not a new action policy.
ACT retargeting or training remains downstream and is disabled until unchanged
human actions replay with materially better consequences.

## Non-negotiable experiment boundary

- The source action array is materialized once as contiguous float64 and its
  shape, dtype, and SHA-256 are bound before a simulator variant runs.
- Every variant receives byte-identical actions. No IK correction, joint
  offset added to actions, clipping, assistance, corrective suffix, or
  candidate-specific action map is allowed.
- Simulator-side reset semantics, application timing, actuator state response,
  geometry, and contacts may vary only as explicitly declared mechanisms.
- A latency candidate may change when the same action is applied, never its
  bytes or ordering. Every replay receipt must prove both properties.
- Lower kinematic residual, simulated reward, contact, lift, or a checkpoint is
  never sufficient alone. Selection uses the frozen vector gate below.
- Training code and an LLM may propose candidates; neither may select or
  promote itself. Deterministic evaluator code owns all verdicts.
- Physical teleoperation, simulation replay, learned-policy simulation, and
  physical policy execution remain separate proof classes.

## Evidence-state correction

The current action-frozen evidence already establishes:

- geometry-only fitting lowered train event RMS from 17.414 to 12.954 mm and
  already-open confirmation RMS from 23.549 to 15.944 mm;
- command-driven versus mapped-encoder end-effector RMS did not improve
  (20.792 to 20.874 mm);
- retained GR00T actions remained 0/12 contact and 0/12 success, while the
  separate human-demonstration lane reached contact in 9/11, lift in 1/11, and
  success in 0/11;
- therefore GR00T action failure and simulator fidelity are separate lanes.

The Stage-F trace optimizer's roughly 301 mm board playing side is now a
rejected/confounded geometry explanation, not a physical board estimate. A
source-bound frame test using visible tag36h11 id 0 gives a 356.2--361.5 mm
mean-side bracket when conditioned on the nominal 80 mm printed black border
and a declared 16--25 mm board/tag plane offset. The registered 355.6 mm board
requires only a 0.2--1.6% nominal tag rescale; the 301.3 mm candidate requires
15.4--16.7%. Because the printed tag was never physically measured, this is
`nominal_print_conditioned_metric_scale_plausibility`, not metric authority.

Operational consequence: freeze playing side at 355.6 mm for the actuator
ablation ladder. Retain the 301 mm result only as evidence that an unconstrained
event fit can compensate for another mechanism. Do not promote either value as
physical metrology until one printed tag edge or the board is measured.

## Frozen composite evaluation vector

Every baseline/candidate result must report, by episode and phase:

1. action shape/dtype/SHA identity and application-time sequence;
2. body-joint tracking RMSE, maximum error, signed bias, and velocity error;
3. gripper command/measured aperture residual and close/open transition time;
4. end-effector position RMSE and source/destination relative-distance curves;
5. closure-point error and source-approach timing;
6. planar pawn trajectory error where video confidence is admitted;
7. contact onset/offset interval error and retention duration;
8. grasp contact, lift, transport, placement, release, collateral motion, and
   strict task success counts;
9. stall-reproduction rate for shoulder lift and elbow; and
10. per-component episode-bootstrap confidence intervals.

The evaluator must preserve curves and phase timing; it may not replace a
trajectory with only its minimum distance.

Candidate admission requires all of the following on grouped train-CV and the
single frozen composite evaluation:

- action invariance passes for every episode and variant;
- overall body-joint tracking RMSE does not regress;
- lift/elbow stall reproduction materially improves;
- end-effector RMSE and closure-point error both improve;
- no already-observable vector component materially regresses;
- at least 6/11 human demonstrations achieve lift and transport in
  action-frozen replay before any retargeting/training lane opens.

If a modality is not observable, report it as missing; do not impute a passing
value. Exact CI thresholds are frozen before the first composite candidate is
evaluated.

## Work packages

### P0 — Evidence reconciliation and scale gate

- [x] Bind IMG_5349 source video, SfM frame, and real 3DGS hashes.
- [x] Detect AprilTag id 0 and fit the visible 9-by-9 board grid in a reviewed
  source frame.
- [x] Publish height sensitivity, edge disagreement, candidate comparison,
  overlay, tests, and false authority flags.
- [x] Regenerate action-frozen v1 train/confirmation/policy receipts in the
  current checkout and bind their code/config/source hashes.
- [x] Build one composite receipt index that never relies on a missing ignored
  output without its hash and regeneration command.

### P1 — Qualified video observability

- [x] Inventory every train/held-out video and freeze its role before decoding
  new frames. The prior fixed-data pipeline already decoded all three
  evaluator-owned held-out videos, so they are already-opened regression
  evidence and cannot provide a fresh admission gate.
- [x] On training videos only, bind owner-reviewed raw-frame source/destination
  endpoint ROIs and compute sustained appearance-loss/appearance-return events.
  Explicitly abstain from a planar trajectory under arm occlusion.
- [x] Validate every endpoint against exact marker-frame, video, and sample
  hashes. Owner markers remain qualitative endpoint checks, never metric labels.
- [x] Publish interval bounds rather than contact labels: source appearance is
  lost a mean 1.386 s before closure onset and destination appearance returns a
  mean 0.832 s after release onset. Do not claim z, lift, force, or metric path.
- [x] Treat the lone wrist video as qualitative gripper-phase corroboration,
  not retention ground truth.
- [x] Compare video intervals with gripper plateau/change-point events and
  publish disagreements rather than forcing one event label.

### P2 — Reset/reference semantics

- [x] Compare reset-to-first-measured-state, reset-to-first-commanded-state,
  and current default reset under identical subsequent actions.
- [x] Record whether the first-second transient explains later EE and joint
  bias. Reject any variant whose reset changes the source action array.
- [x] Audit actuator target units, qpos/ctrl reference conventions, actuator
  limits, and physical-to-simulator joint direction exactly once.

Result: first-commanded reset is the stable numerical CV winner but improves
joint RMS only 0.002% over first-measured, below the frozen 0.5% materiality
threshold. Model-default reset is much worse (8.890 degrees RMS). Retain the
first-measured reset; reset semantics are not the remaining primary gap.

### P3 — Action-frozen actuator ablation ladder

Use grouped cross-validation over whole training episodes. Add one mechanism at
a time and retain all failures:

1. reset/reference correction only;
2. delay-only transport with the existing 50.6 ms diagnostic estimate;
3. per-joint first-order response plus delay;
4. bounded deadband/hysteresis plus delay;
5. bounded current/effort proxy conditioning only if it improves held-in CV
   beyond a model without current;
6. gripper aperture/contact range, never a calibrated force point.

Deadband, gain, and force-range changes must live inside the simulator response
model. Writing a modified effective target is forbidden. Quantized 5 Hz cached
current is a weak proxy and cannot identify torque, friction, or mass by itself.

Executed result:

- timestamp-aligned record-then-ZOH semantics plus a 0--150 ms delay grid
  selected 110 ms on all-train and 100--110 ms across four folds;
- joint RMS fell from 2.563 to 1.461 degrees and EE RMS from 20.843 to
  16.417 mm versus legacy step-then-record;
- a constrained 0--3 degree lift/elbow deadband grid selected 2 degrees in all
  four folds, reducing joint RMS again to 1.296 degrees and EE RMS to 12.936 mm;
- lift/elbow flat-response reproduction rose to 69.6%/58.9%; and
- actions remained float64, byte-identical, unclipped, and unassisted.

The earlier global gain/force/damping fit moved joint RMS only about 0.01
degrees, and quantized nominal-5-Hz current did not identify a better mechanism.

#### P3 continuation — stationary elbow load response

The selected timing-plus-deadband residual was decomposed before opening a new
candidate family. Elbow flex dominated at 2.334 degrees RMS with a -1.639
degree signed mean error. The residual was larger in stationary/load-bearing
rows and correlated with elbow pose, supporting a bounded joint-specific load
response probe rather than another geometry or global-delay fit.

A frozen 63-candidate grid varied lift deadband (1.25/1.5/1.75 degrees), elbow
deadband (2.0/2.25/2.5 degrees), and an elbow load-bias coefficient
(-1.5 through 0.0). The extra simulator torque was active only while the elbow
servo was within its declared deadband. It never changed a source action value,
row, order, application delay, or action hash.

Whole-episode grouped CV selected 1.5 degrees for lift, fold-specific elbow
deadbands of 2.0--2.5 degrees, and coefficient -1.5. Pooled joint RMS fell from
1.2955577 to 1.2118497 degrees (6.461%); EE RMS fell from 12.9364 to
11.3437 mm (12.312%). Every validation fold improved. A deterministic
10,000-replicate paired whole-episode bootstrap gives a 4.398--8.540% 95%
interval for relative joint-RMS improvement, with probability 1.0 of a positive
effect and 0.9162 of at least a 5% effect under that resampling model.
All 11 episodes originate from one retained acquisition session, so this is
conditional episode-level uncertainty rather than independent-session or
physical-population generalization.

The coefficient selected at the frozen grid's lower boundary in every fold.
Therefore the campaign supports only the bounded load-response *model class*;
it does not identify the coefficient magnitude, physical torque, firmware,
gravity compensation, or compliance. The grid is not widened after observing
the result.

### P4 — Contact/object model

- [x] Enter only after video intervals and actuator response are frozen.
- [x] Search inside the existing rubber-tip prior bracket; do not expand it
  post hoc.
- [x] Refuse fitting because retained appearance intervals do not label grasp,
  lift, retention, force, or metric object motion with sufficient authority.
- [x] Publish the full frozen prior ensemble. It spans 2--3 lifts out of 11,
  always 11 contacts and 0 strict successes; no variant is selected.
- [x] If it spans the prior,
  label contact parameters unidentifiable from retained open-loop data.
- [x] Gripper squeeze is reported as a range sensitivity until physical force
  or measured current calibration exists.

### P5 — Composite freeze and evaluator-owned regression

- [x] Freeze geometry (355.6 mm playing-side hypothesis), reset semantics,
  actuator family, gripper range, and contact ensemble together.
- [x] Freeze evaluator code, vector thresholds, episode roles, seeds, and
  bootstrap procedure. No unopened physical video cohort remains.
- [x] Select only by grouped cross-validation on training episodes, then run
  one evaluator-owned comparison on the already-opened held-out episodes.
  Confirmation cannot change selection or be described as fresh validation.
- [x] Publish the full vector, 10,000-replicate whole-episode bootstrap CIs,
  failed components, receipt digests, and the
  exact safe claim even if the decision is terminal negative.

### P6 — Gated simulation training

Disabled until the action-frozen human-demo gate reaches at least 6/11
lift-and-transport episodes without regressed vector components.

Final state: disabled. The selected timing-plus-deadband replay reaches 11/11
contact, 2/11 lift, unobserved transport, and 0/11 strict success. Even the
frozen contact ensemble reaches at most 3/11 lift and 0/11 success.

The 2026-07-21 load-response continuation does not reopen this gate. It retains
11/11 contact, regresses lift from 2/11 to 1/11, produces two destination-inside
endings, and remains 0/11 strict success. Mean final target distance improves
from 76.884 to 47.310 mm, but that mixed vector is not grasp/transport
advancement.

- [ ] Only then build object/target-relative retargeting and admit simulated
  demonstrations through the unchanged strict consequence evaluator.
- [ ] Only then train ACT locally on MPS with uncertainty ensembles derived
  from admitted, identifiable candidates.
- [ ] Compare learned-policy rollouts in a separate proof class. No result in
  this lane retroactively validates simulator fitting or physical transfer.

## Identifiability ledger

| Quantity | Current evidence | Current status |
|---|---|---|
| Board playing side | nominal tag-conditioned frame plus separate photo/Polycam alignment | 355.6 mm physically plausible; no metric authority |
| 301 mm trace fit | event residual optimizer | confounded/rejected as physical scale |
| Board planar pose/yaw | action-frozen event geometry | diagnostic, not physical calibration |
| Lift vertical correction | event z residual and pan-dependence probe | correction identifiable; physical mechanism unresolved |
| Base z vs lift zero vs tool point | same sparse events | not jointly separable |
| Application timing | recorded command/measured trace | 110 ms simulator-side delay accepted by grouped CV; not physical latency calibration |
| Reset/reference | first command, first measured, model default | 0.002% difference; ruled out as primary gap |
| Joint dynamics | command/measured positions and velocities | 2 degree lift/elbow deadband model class accepted by episode CV; not firmware calibration |
| Stationary elbow load response | pose- and phase-conditioned elbow residual under frozen delay/deadband | bounded load-response model class improves CV RMS; coefficient is at search boundary and magnitude is not identified |
| Motor current/effort | cached quantized raw current at nominal 5 Hz | weak proxy; not calibrated torque |
| Gripper contact | aperture plateau plus video intervals | interval hypothesis only |
| Contact/friction | frozen prior consequence sensitivity plus appearance intervals | underidentified: 2--3 lifts, 0 strict successes, no selectable variant |
| Pawn mass/inertia | no direct retained measurement | not identifiable |

Any new fit must name the row it addresses and either use an already
identifying observable or add one. Generic domain randomization is downstream
of this ledger, not a substitute for it.

## Publication-safe stopping outcomes

Any of these is a valid final result:

- a composite candidate improves the full vector under byte-identical actions;
- a terminal-negative result localizes the remaining error to one or more
  unidentifiable mechanisms; or
- the retained data are insufficient and the result names the smallest future
  measurement that would collapse each uncertainty.

The following claims remain prohibited without new physical evidence:
"physically calibrated simulator," "metric 3DGS," "validated sim-to-real
transfer," "working B--G policy," and "measured contact parameters."

The accepted continuation claim is narrower: a predeclared material
action-frozen simulator trace-fidelity advancement with a positive paired
episode-bootstrap interval. It is not a full-vector simulator promotion.

## Out of scope without new owner/hardware work

Robot motion, fresh camera capture, serial access, paid compute, caliper/ruler
measurements, calibrated force/torque measurement, and physical policy replay.
If a similar scene is reconstructed later, one measured tag edge and one board
edge should be captured in the same setup; that small addition would convert
the present scale-plausibility lane into an actual metric-scale test.
