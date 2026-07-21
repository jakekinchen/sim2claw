# Hardware-Free B-G Fidelity Advancement Plan

> **For agentic workers:** execute experiments in lane order unless a
> dependency note says otherwise; every experiment must land with a frozen
> contract or receipt, focused tests, a ledger row, and no promotion claim.
> Checkboxes track completion.

**Goal:** Close the remaining sim-to-real gap for the B-G pawn benchmark —
grasp retention, transport, and placement in command-driven replay, then a
sim-trained goal-conditioned policy — using only evidence already on disk and
local CPU/MPS compute.

**Architecture:** Three measurement lanes turn existing recordings into new
observables (object trajectories from overhead video, grasp-state from the
wrist camera, refined board/camera registration); those observables feed a
v2 workcell refit, a deadband-capable actuator model, and a contact fit;
on top sits the sim-only training and evaluation lane plus a standing
uncertainty/identifiability program.

**Tech stack:** Python 3.12, MuJoCo 3.10.0, OpenCV/ffmpeg (already used for
review renders), SciPy 1.18.0, PyTorch 2.11.0 on MPS (precedent: the
957,350-parameter rook-lift ACT was trained locally).

## Global constraints

- No robot motion, no serial bus, no camera capture, no paid compute
  (Brev or otherwise). Local CPU/MPS only.
- Frozen contracts stay frozen: new work creates v2 artifacts; nothing
  rescores or relabels committed receipts.
- The sysid split (`configs/sysid/physical_pawn_sysid_split_v1.json`) remains
  the split authority. Its held-out **joint rows are already opened** by the
  workcell lane and may never again serve as fresh validation for joint-space
  fits. Its held-out **videos are still sealed**
  (`d1-to-d2__20260719T031518Z-34bff0dd`, `g1-to-g2-redo__20260719T032810Z-9e623c5e`,
  and the lateral `c1-to-d2__20260719T035317Z-2a332ab7`): they are the one
  remaining untouched validation resource. Every video-derived fit below
  trains on the 11 train-episode videos and opens held-out videos exactly
  once, at its declared validation step, and never for tuning afterward.
- Every fitted parameter ships with bounds declared before fitting, a
  train/validation protocol declared before the first optimizer run, and an
  explicit claim boundary (no physical-calibration, policy, or promotion
  claims from simulator-frame evidence).
- Evidence base this plan builds on:
  `outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v1/` (workcell candidate,
  held-out kinematic admission 23.5 mm),
  `outputs/pawn_bg_act_v1/pawn_bg_actuator_sysid_v1/` (latency 50.6 ms,
  held-out tracking 2.132 to 1.640 deg),
  `docs/run-logs/2026-07-20-pawn-bg-dynamics-grasp-observability.md`
  (sag attribution, aperture validation, retention metrics),
  `docs/run-logs/2026-07-19-simulator-progression-ledger.md` (metric rules).

---

## Lane A — Measurement from existing video (the unlock)

The single reason contact and sag parameters are weakly identifiable today is
that no measured object trajectory exists. The 13 product episodes each carry
a hash-bound `overhead_c922.mp4`, 26 owner-accepted image-space markers
(`configs/evaluations/pawn_rank12_owner_visual_review_20260719_v1.json`), and
a proposal B1 board homography with 1.94 px corner RMS. That is enough to
produce planar pawn trajectories without any new capture.

### A1. Per-episode board homography and uncertainty

- [ ] **Files:** create `src/sim2claw/overhead_board_registration.py`,
  `configs/vision/overhead_board_registration_v1.json`,
  `tests/test_overhead_board_registration.py`.
- [ ] Detect the printed fiducial sheet and board corners per episode video
  (first/last frames plus every 2 s), fit a per-episode homography
  board-plane-to-pixels, and report reprojection RMS per episode.
- [ ] Validate against the 26 owner markers: predicted square centers versus
  accepted fiducial centers, reported in px and mm.
- [ ] **Acceptance:** homography exists for 11/11 train videos with corner
  RMS <= 3 px (~2.5 mm at board scale); owner-marker disagreement <= 6 px.
  Failures are recorded per episode, not silently dropped.
- [ ] Receipt with per-episode homography hashes; ledger row; commit.

### A2. Pawn trajectory extraction (train videos)

- [ ] **Files:** create `src/sim2claw/overhead_pawn_tracking.py`,
  `configs/vision/overhead_pawn_tracking_v1.json` (frozen tracker settings),
  `tests/test_overhead_pawn_tracking.py` (synthetic-frame fixtures).
- [ ] Track the selected brown pawn per frame (color/template tracking is
  sufficient: brown pawn on beige/brown squares, static camera). Output per
  frame: board-plane (x, y), visibility flag, occlusion-by-arm flag.
  Timestamps aligned to `overhead_video_time_seconds` already present in
  `samples.jsonl`.
- [ ] Derive per-episode event times from the object itself: first sustained
  pawn motion (grasp), lift-off, transport path, settle time, final square
  offset. These are **measured** replacements for the gripper-threshold
  proxy events.
- [ ] **Acceptance:** tracked coverage >= 80% of non-occluded frames on
  11/11 train episodes; final-position estimate within one half-square of
  the owner-reviewed destination for every success-labeled episode.
- [ ] **Cross-check (no fitting):** compare measured grasp times against the
  frozen gripper-close proxy events; publish the proxy's timing bias
  distribution (the workcell fit inferred ~+15 mm reopen bias; this measures
  it directly).

### A3. Wrist-camera grasp-state classifier (retention ground truth)

- [ ] **Files:** create `src/sim2claw/wrist_grasp_state.py`,
  `tests/test_wrist_grasp_state.py`.
- [ ] The single hash-bound D405 wrist release video
  (`19f2d6f8...` per the source-fit contract bindings) shows the gripper and
  pawn during release. Build a per-frame pawn-in-gripper classifier
  (color/edge heuristics; no training data needed at this scale) and emit
  measured grasp-retention intervals.
- [ ] **Scope note:** only one wrist video exists; this yields retention
  ground truth for one episode. Worth it because sim retention (0.6-0.8 s)
  versus real retention is currently inferred, not measured; one measured
  episode pins the scale.
- [ ] **Acceptance:** classifier agrees with the overhead-derived grasp
  interval on the same episode within 0.2 s at both endpoints.

### A4. End-effector planar track from overhead video (optional, after A2)

- [ ] Track the gripper head in the overhead view (white jaw against dark
  background) to get a measured planar end-effector trajectory. This is the
  only fully independent check of the joint-to-world map during *motion*
  (event fits only constrain two instants per episode).
- [ ] **Acceptance:** report agreement between measured planar EE track and
  candidate-FK planar track; no fitting in this step.

---

## Lane B — Workcell calibration v2 against measured trajectories

### B1. Refit board and lift-zero against pawn-anchored events

- [ ] **Files:** create `configs/optimization/pawn_bg_workcell_fit_v2.json`,
  extend `src/sim2claw/pawn_bg_workcell_fit.py` with a
  `measured-object-events` mode; extend `tests/test_pawn_bg_workcell_fit.py`.
- [ ] Replace proxy targets with A2-measured grasp/release instants and
  measured pawn positions (not labeled square centers): the pawn was not
  necessarily centered on its square. Refit the stage-B planar board and
  stage-D lift offset with the same bounds and priors as v1; drop the reopen
  timing nuisance (A2 makes it unnecessary).
- [ ] **Validation protocol (declared now):** fit on 11 train episodes.
  Open the two sealed product held-out **videos** exactly once; validation
  metric is predicted-versus-measured pawn pickup/placement position error.
  Admission: held-out mean error <= 15 mm.
- [ ] **Expected effect:** train event residual floor drops below the
  current 17.4 mm (which is inflated by square-center labeling slop and
  proxy timing); the lift-offset estimate gains an error bar independent of
  the proxy.

### B2. Pinch-point convention audit

- [ ] Fit a bounded tool-point offset in the gripper frame (3 params,
  <= 25 mm) *against* the joint-offset explanation using the same events;
  report which parameterization wins on train residual and whether the two
  are separable given the observed wrist-pose diversity. If they are not
  separable, record that as an identifiability boundary (do not ship both).
- [ ] **Files:** extend `pawn_bg_workcell_fit.py` fit stages; add the
  hypothesis comparison to the receipt.

### B3. Event-extractor v2

- [ ] **Files:** create `configs/optimization/pawn_bg_event_extractor_v2.json`;
  extend `src/sim2claw/pawn_bg_source_fit.py` loader tolerance or add a v2
  extractor module.
- [ ] Define grasp/release events from measured pawn motion (A2) with the
  gripper signal as a consistency check only. Publish v1-versus-v2 event
  time deltas per episode as the definitive proxy-bias measurement.

---

## Lane C — Actuator model that can sag (sim-side, independent of Lane A)

### C1. Deadband/current-limit servo emulation in the replay loop

- [ ] **Files:** create `src/sim2claw/so101_servo_model.py`,
  `configs/sysid/so101_servo_model_v1.json`,
  `tests/test_so101_servo_model.py`; wire into
  `pawn_bg_actuator_sysid.simulate_tracking` and
  `pawn_bg_workcell_fit.replay_episode_with_candidate` behind an opt-in
  `servo_model` parameter.
- [ ] Because replay sets `data.ctrl` every step, the firmware behavior can
  be emulated without MuJoCo plugins: per joint, per step, compute the
  commanded target, apply an error deadband `d_j` (no corrective torque
  inside the band) and a torque/current envelope `tau_max_j(qvel)` by
  modulating the actuator gain/forcerange arrays or by writing an
  effective ctrl. Parameters per joint: deadband `d_j` (0 to 3 deg),
  effective torque cap `tau_j` (0.3 to 2.94 Nm), plus the already-identified
  50.6 ms latency held fixed.
- [ ] **Fit protocol (declared now):** train on the 15 train episodes'
  joint tracking; the objective adds a stall-reproduction term (fraction of
  real stall rows the sim reproduces) to the RMS term so the optimizer can
  no longer satisfy one at the expense of the other. Evaluate on the 3
  held-out episodes with the reuse caveat labeled (their joint rows are
  opened; this is regression evidence, not fresh admission).
- [ ] **Acceptance:** train stall reproduction for lift and elbow >= 40%
  (today 9%/6%) **and** overall train tracking RMS <= 1.7 deg (i.e., the
  sag term may not be bought by degrading tracking beyond 5%).
- [ ] **Payoff test:** rerun the consequence replay; the diagnosis predicts
  closure-point error drops from ~46 mm toward ~15-20 mm and grasp streaks
  lengthen. Record whichever way it goes.

### C2. Gripper servo squeeze model

- [ ] Apply the same servo model to the gripper joint; the real close
  command reaches 1.1% (4-5 mm aperture) against a 16 mm neck, so grip
  force in sim is currently whatever the unmodeled 2.94 Nm cap delivers.
  Fit the gripper torque cap so simulated squeeze at 1.1% against a rigid
  neck matches the STS3215 current-limited stall behavior bracket declared
  in the config (bounds, not a point estimate — no direct measurement
  exists without hardware).
- [ ] **Acceptance:** grasp of a settled pawn at measured close commands
  holds under a 1 m/s^2 lateral acceleration sweep in at least the
  mid-friction rubber variant, or the failure mode is documented.

---

## Lane D — Contact fitting against measured retention (after A2/C1)

### D1. Rubber-tip parameter fit within the frozen prior bounds

- [ ] **Files:** create `configs/simulation/rubber_tip_fit_v1.json` (search
  space = the frozen low/high prior bracket from
  `configs/simulation/rubber_tip_contact_sensitivity_v1.json`; nothing
  outside it), extend `src/sim2claw/contact_prior.py` with a bounded
  interpolation constructor, plus tests.
- [ ] Objective: reproduce A2-measured grasp retention intervals and
  transport paths in command-driven replay with the C1 servo model active.
  Fit sleeve thickness and friction (2-3 params). Train on train episodes;
  validate once on held-out videos (shared budget with B1's single opening —
  coordinate so both validations run in the same declared pass).
- [ ] **Acceptance:** mean absolute retention-duration error <= 30% on
  train; held-out episodes reproduce grasp-then-hold (binary) correctly.
- [ ] **Identifiability guard:** publish the near-equivalent ensemble
  (parameter sets within 1% objective) per the sysid framework's pattern;
  if the ensemble spans the whole prior bracket, the honest conclusion is
  "not identifiable open-loop" and the fit is recorded as such.

---

## Lane E — Sim-only training and evaluation (local MPS)

### E1. Calibrated-scene regeneration of the B-G task assets

- [ ] Rebuild the B-G scene binding on the v2 workcell candidate (board
  yaw/center, lift offset, range envelope, latency, servo model) as
  `configs/scenes/operator_updated_chess_workcell_v4_candidate.json` —
  explicitly a candidate scene: the frozen v3 evaluator stays untouched for
  historical comparability.
- [ ] Regenerate Studio posters/assets for the candidate scene so owner
  review sees the corrected board orientation (the current committed scene
  still renders the mirrored labeling).

### E2. Demonstration retargeting into the goal-conditioned frame

- [ ] **Files:** create `src/sim2claw/pawn_bg_demo_retarget.py` plus tests.
- [ ] Per the governing design sentence (teleoperate styles, generate
  instances combinatorially): express the 11 train demonstrations in
  object-relative coordinates (gripper pose relative to selected-pawn pose,
  phase-segmented by A2 events), then synthesize task instances across all
  12 directed B-G skills and continuous within-square placement jitter by
  replaying retargeted trajectories in the calibrated sim.
- [ ] **Acceptance:** >= 70% of synthesized instances pass the frozen hard
  gates in sim (contact, lift, containment, upright, released, collateral)
  before any policy training; below that, the workcell/servo/contact lanes
  above get the residual, not the training lane.

### E3. Train the first B-G pick-place ACT candidate (sim data only)

- [ ] **Files:** reuse `act_pick_place.py` / `goal_act_training.py`
  contracts; create `configs/training/pawn_bg_act_state_v1.json` with a
  frozen train/held-out instance split and a separately invoked CPU/fp32
  evaluator, mirroring the rook-lift discipline.
- [ ] Train locally on MPS with domain randomization over the rubber-tip
  ensemble, the servo-parameter near-equivalent ensemble, and +/-5 mm board
  pose — the calibrated uncertainty *is* the randomization distribution.
- [ ] **Acceptance for the sim claim only:** held-out sim instances pass
  the frozen 12-skill bidirectional evaluator at a pre-declared rate
  (propose >= 8/12 directed skills with both directions passing at
  >= 60%); wording stays "simulated policy on calibrated-candidate scene,"
  never transfer.
- [ ] **Replay cross-check:** the policy's closed-loop sim trajectories are
  compared (DTW distance, phase durations) against the 11 human
  demonstrations for plausibility drift.

### E4. Fidelity regression harness (continuous integration for the ledger)

- [ ] **Files:** create `src/sim2claw/fidelity_regression.py`,
  `tests/test_fidelity_regression.py`, plus a CLI (`sim2claw
  fidelity-regression`).
- [ ] One command reruns the three cheap fidelity metrics (train event RMS,
  train joint-tracking RMS, train replay consequence counts) against any
  scene/parameter revision and appends a machine-readable ledger row to
  `docs/run-logs/2026-07-19-simulator-progression-ledger.json` with commit,
  receipt hashes, and proof state. Every future sim change lands with a row;
  silent fidelity regressions become impossible.

---

## Lane F — Standing uncertainty and identifiability program

### F1. Parameter uncertainty by episode bootstrap

- [ ] Bootstrap the v1/v2 workcell fits over episodes (leave-2-out, 50
  resamples — cheap, minutes) and publish parameter spreads: board center,
  board yaw, lift offset. The lift offset's spread is the number the
  eventual hardware recalibration will be judged against.

### F2. Identifiability ledger

- [ ] **Files:** create `docs/reference/BG_PARAMETER_IDENTIFIABILITY.md`.
- [ ] Freeze the evidence-backed table this lane has accumulated: board
  planar pose (identifiable, ~13 mm), board orientation (categorical),
  lift zero (identifiable as vertical correction; arm-frame vs base-pitch
  resolved by pan-flatness; physical mechanism unresolved), base z versus
  lift zero versus tool point (not separable from events alone; B2 may
  resolve), gripper percent-to-angle map (validated at grasp point),
  command latency (identified, 50.6 ms), per-joint torque/friction
  (not identifiable from tracking RMS alone; C1 adds the stall term),
  contact parameters (outcome-sensitive, identifiability pending D1),
  mass/inertia (not identifiable from any current signal; currents too
  quantized — measured at R^2 <= 0.13).
- [ ] Rule: any future fitting proposal must name its row and either use an
  identifiable signal or add the observable that makes it identifiable.
  This is the guard against another free-sign-adapter incident.

---

## Sequencing

| Order | Experiments | Depends on | Rough local cost |
|---|---|---|---|
| 1 | A1, A2, C1 (parallel) | — | hours of CPU |
| 2 | A3, A4, C2 | A2 / C1 | hours |
| 3 | B1, B2, B3 | A2 | hours |
| 4 | D1 | A2 + C1 | hours-day |
| 5 | E1, E2 | B1 | hours |
| 6 | E3 | E2 | day-scale MPS |
| 7 | E4, F1, F2 | any time; F2 updates as lanes land | hours |

The single declared opening of the sealed held-out videos happens once,
jointly for B1 and D1, after both are frozen.

## Out of scope (requires hardware or owner action)

Recorded here so nobody burns local cycles approximating them: LeRobot
recalibration at a marked fixture pose (settles the lift-zero mechanism),
a per-joint slow sweep with 20 Hz current telemetry (identifies
torque/friction/deadband directly), a ruler measurement of base mount
height and axes from two table edges, a scale measurement of one pawn, and
any physical replay or policy execution. Each is minutes of owner time and
each collapses an uncertainty this plan can only bound.
