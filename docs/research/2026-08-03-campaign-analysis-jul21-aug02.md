# What Jake Built: July 21 → August 2, 2026 — An In-Depth Campaign Analysis

Status: retrospective analysis compiled from committed evidence on `origin/main`
(742 commits, 2,309 files, ~853K insertions, `d9fcf9c..88361af`); grants no new
authority; every number below is sourced from a tracked brief, run-log,
closeout, or receipt.

Date: 2026-08-03 · Author: analysis for Aishwarya Badlani, compiled from
briefs 009–114, run-logs, `GOAL.md`, and the SAIL/OR campaign graphs.

---

## 0. TL;DR

In thirteen days the project went from "we have retained teleoperation data we
can't use" to a complete, honest, receipt-backed answer to the question **"why
doesn't the simulator reproduce what the real robot did?"** — ending in the
repository's single most striking result: an exact-episode physics replay of a
real D1→D2 pawn transfer that **passes all seven terminal task gates with
4.26 mm placement error**, achieved by adjusting exactly one simulator
coordinate (the fixed-jaw contact-skin position) found by a 0.01 mm-resolution
sweep — and then **deliberately quarantining that success** as an
outcome-informed diagnostic rather than promoting it as transfer evidence.

The campaign's honest ledger: physical task attempts **0/10**, REAL→SIM
transfer **0/1**, SIM→REAL **0/0**, simulator promotion **none** — and at the
same time, a calibrated camera model (1.02 px), a twice-held-out-validated
actuator backlash model (55% joint / 61% EE error reduction), a measured
physical contact chronology, and a simulator that now reproduces the task
outcome numerically. The campaign is currently **paused at an external-input
boundary**: every authority (camera, serial, motion, training, paid compute)
is switched off, waiting on owner-provided hardware access.

---

## 1. Where the repo stands right now

- **Latest commit**: `88361af` (Aug 2) "Close exact-episode physics replay
  outcome gap" — closes cards OR49+OR50 of the observable-registration
  campaign.
- **`GOAL.md` status**: `OR50_PASS_QUARANTINED_NUMERIC_TASK_REPLAY_EVENT_MISMATCH_REMAINS`
- **Current card**: `none` — the campaign is at an external-input boundary.
- **All external authorities false**: `camera_open, gateway, heldout_open,
  paid_compute, physical_motion, serial, simulator_promotion, task_attempt,
  training, transfer_claim`. Only `simulator_replay` remains true.
- **Two new tags**: `phase-a-real-to-sim-d1-d2-20260727` (public Phase A
  evidence package) and `workspace-data-20260728-v1` (V04 paused handoff).

---

## 2. The five arcs, in order

### Arc 1 — SAIL: the calibration algorithm and its governance (Jul 21–23)

**SAIL = Structure-Adaptive Interventional Loop Closure**, the algorithmic
core of "ClawLoop," an evidence-gated digital-twin and policy-learning
factory. Its claim to novelty is the update operator: detect *compensating
explanations* (parameters that fit for the wrong reason) via
intervention-specific invariance, introduce candidate physical mechanisms as
typed plugins, reopen only their historical influence set, and reallocate
explanatory credit — instead of refitting everything from scratch.

What exists in code (`src/sim2claw/sail/`, 45 modules):

- **Five frozen contracts** (CalibrationEvidence, ResidualField,
  PhysicalMechanism, Intervention, TwinWorthinessCertificate), all sealed with
  canonical digests and role-gated access.
- **25 golden oracle cases** (immutable behavioral specs, e.g. "sparse closure
  matches full-batch fit with less recomputation").
- **A mechanism-plugin ABI** with ten registered physical mechanisms (timing
  delay 0.11 s, servo deadband 2.0°, load compliance, metric geometry,
  gripper aperture…), each declaring observables, non-identifiabilities,
  priors, and invalidation rules.
- **Twin-worthiness kill switches**: five gates (replay integrity → trace
  fidelity → interaction fidelity → policy concordance → structural
  robustness) mapping to capability levels from TW-DIAGNOSTIC up to
  TW-PHYSICAL-CANARY. Nothing trains or transfers unless the certificate
  level allows it.
- **A six-stage policy flywheel** whose admission matrix assigns **zero
  training rows** to any failed evaluation — run once end-to-end and
  honestly reported as terminal-negative (ACT trained, evaluation failed,
  promotion published a rejection).

Phase 1 (no new physical data, everything from retained evidence + synthetic
runs) closed with a publication freeze: 10,000-episode bootstrap analyses,
787-test broad gate, and an explicit disclaimer that it "does not claim a
policy win, physical mechanism identification, simulator promotion, physical
transfer, or robot capability." A brutal detail worth knowing: in the v2
executed benchmark, plain `sequential_no_revisit` scored 1.000 top-1 vs
SAIL's 0.625 — and the benchmark records that rather than reframing it.
Phase 2 (P2-00…P2-07) is fully specified and **blocked_external**.

### Arc 2 — Metrology: making one camera and one arm trustworthy (Jul 26–27)

The physical calibration chain, brief by brief:

- **Pi IMX708 intrinsics**: printed AprilTag sheet (16 mm effective tag),
  leave-one-tag-out model selection chose the zero-distortion model at
  **1.021 px mean validation RMSE** (radial model rejected at 6.13 px).
- **AprilTag→link registration**: tags bound to `left_shoulder`,
  `left_upper_arm`, `left_wrist`; the winning `shoulder_upper` family passed a
  **fresh untouched pose at 5.76 px RMSE** against a frozen 8 px gate — after
  the training-only selection had picked a family that blew up at 42.3 px on
  held-out, a live lesson in why the repo insists on untouched validation.
- **Joint play / hysteresis**: three failed models (memoryless deadband,
  stateful load-sign play — the latter improving joint RMS while *worsening*
  EE RMS 83% on held-out) before the **direction-conditioned reverse-play
  model** passed two independent fresh held-outs: joint RMS 0.654°→0.294°
  (−55%), EE RMS 5.43→2.13 mm (−61%). Accepted as diagnostic; deliberately
  **not promoted** into the simulator.
- **The blocking discovery**: torque-off gravity sag. The elbow sags 19–48°
  after torque release — past its calibrated envelope — and this, not servo
  identity, comms, thermal, or voltage, is what kills autonomous replay
  attempts.

### Arc 3 — Phase A real-to-sim + the exact-action attempts (Jul 27)

**Phase A D1→D2** (brief 054, tag `phase-a-real-to-sim-d1-d2-20260727`): a
human-teleoperated pawn transfer from D1 to D2, packaged as the project's
first *public, hash-bound* physical task artifact — a 531-frame side-by-side
comparison video, poster, kinematic trace, and receipt, all published to a
GitHub release and byte-verified after unauthenticated re-download. Crucially
its outcome string is `phase_a_visual_artifact_passed_physics_ineligible_fail_closed`:
the physics-replay lane failed closed (0/531 rows exact: rate-limiting, safety
clamps, float32/float64 mismatch, out-of-range targets), so it is a *visual
kinematic* artifact, explicitly not physics replay or task transfer.

Five autonomous exact-action attempts followed (briefs 055–060), **all
terminal negatives on real hardware**, each one localizing the failure more
precisely: elbow no-progress plateaus at 97.2°/82.8°, a 609-of-1041-row stall
before pawn contact, and the C2→C1 attempt (701 clean rows) that toppled the
pawn physically while the identical bytes in MuJoCo produced zero jaw contact
— the double failure that motivated everything after.

### Arc 4 — The C-lane: canonical registration and the immutable C6 (Jul 28–29)

With hardware closed, the campaign turned fully retrospective, building the
"realized-action" chain C0→C9 on the immutable 531×6 gateway-sent tensor of
the successful teleoperated episode:

- **C2**: board/task-plane registration accepted at **4.742 mm RMS**; initial
  pawn XY accepted at **3.101 mm** from D1 center (global mapping still
  unapproved).
- **C4 "effective plant"**: a three-sample command-hold model beat both direct
  targets and 0.11 s ZOH — validation joint RMS **+55.5%**, EE RMS +58.5%.
- **C5 contact identifiability**: fail-closed **0/5** — no contact/object
  dimension has a non-sealed witness, so nothing was fit. MuJoCo contact
  stays an unvalidated diagnostic.
- **C6 mission replay** — the campaign's central negative: one write-once
  natural-contact replay of the exact 531 rows through C4. **No jaw carry
  formed; final error 69.148 mm; tilt 179.99° (pawn on its head); the sim
  first disturbs the pawn at sample 386 and launches it at 388**, while the
  physical robot demonstrably enclosed the pawn by sample 232. Immutable 0/1.
- **C8**: a Studio `#/proof` page synchronizing all 531 rows, video,
  residuals, and the sample-386/388 failure marker.
- **C9**: deferred at the follower-elbow service boundary; ledger preserved at
  physical attempts 0/10.

### Arc 5 — Observable Registration OR0→OR50: closing the 154-sample gap (Jul 29–Aug 2)

The OR lane opened on exactly C6's residuals: physical contact happens at
sample ~230, simulated contact at 386 — a **154-sample / 7.7 s causality
gap**. Method: one card active at a time, each card a frozen 6-file contract
(contract → implementation → test → receipt → closeout → session log), each
changing at most one thing:

- **OR3** bounded the *physical* contact chronology from retained video:
  contact 228–232, carry 260–390, release 400–407.
- **OR6** fit a jaw-aperture offset (0.0495 rad) that fixed projection error
  21.3→1.8 px — but **OR7** re-ran the exact C6 bytes and reproduced the same
  69.148 mm failure: aperture alone rejected.
- **OR12→OR19** closed the fixed-jaw geometric gap 61.7→3.2 mm; OR19 achieved
  first named contact at sample 231 (matching physical!) and reached 9.9 mm
  from D2 — but the pawn tipped (102.1° tilt).
- **OR38** found the knife-edge: two contact-skin positions 5 mm apart
  produce either transport-with-topple or upright-without-transport.
- **OR49** swept 19 candidates at 0.25 mm: terminal negative for event
  matching, but discovered a deterministic *upright basin* at −0.113 m
  (final tilt 0.0017°, but 14.6 mm planar error — 8.6 mm outside the 6 mm
  gate).
- **OR50** swept 25 candidates at **0.01 mm** resolution inside the basin and
  selected **−0.11298 m**: `numeric_task_replay_pass: true`, all 7 terminal
  gates, final planar error **4.260 mm**, final tilt **0.0039°**, byte-identical
  digests across selection and verification runs.

**And then the discipline**: OR50's own closeout lists the four event
residuals that still mismatch (pawn motion starts 3 samples early, support
loss 4 samples early, no bilateral named-jaw contact, 26.1° transient tilt at
sample 260 vs a 10° gate), sets `complete_event_and_numeric_task_replay_pass:
false`, and stamps every claim-limit false: not canonical geometry, not
held-out validated, not approved mapping, not simulator promotion, not
transfer evidence. The queue was amended to make OR49/OR50 an explicit,
permanent quarantine exception.

---

## 3. How the work was approached — the method behind the 742 commits

Six patterns repeat everywhere and explain both the volume and the
credibility:

1. **One card at a time, one variable at a time.** Every experiment is a
   frozen contract with an acceptance gate declared *before* running. OR50
   changed literally one number (a contact-skin Z coordinate) at 0.01 mm
   steps.
2. **Fail-closed by default.** C5 fit *nothing* because its witnesses were
   sealed. The Phase A physics lane refused to retime rows it couldn't
   reproduce. Preflights (e.g. the OR48 packet) enumerate every capability
   they may NOT use.
3. **Untouched held-outs decide; training metrics never do.** The AprilTag
   family that won training-only selection failed 42 px on held-out; the
   stateful joint-play model improved joint RMS while worsening EE RMS 83%.
   Both were rejected on exactly that basis.
4. **Negatives are immutable and load-bearing.** C6's 0/1 is never re-rolled;
   every OR card cites it. Terminal-negative briefs outnumber passes and are
   written with the same care.
5. **Outcome-informed results are quarantined.** The OR50 success used the
   known physical outcome to select a simulator parameter — so it is
   permanently barred from mapping/promotion/transfer claims, by a rule
   written into the queue the same day it was needed.
6. **Receipts, hashes, byte-verification.** Public release assets re-downloaded
   unauthenticated and byte-matched; action tensors carried by SHA-256 through
   every lane; determinism proven by digest-identical repeat runs.

The volume (180 commits on the busiest day) is an artifact of the 6-file
card pattern plus an autonomous executor loop (brief 037's dev-loop control
plane) running under these constraints — not of churn.

---

## 4. Proven vs. not proven (the honest scoreboard)

| Claim | Status | Evidence |
| --- | --- | --- |
| Pi camera intrinsics | **Proven** (1.02 px LOO validation) | brief 048 run-log |
| Tag→link registration | **Proven** (5.76 px on fresh pose) | brief 048 |
| Direction-conditioned backlash model | **Validated twice, unpromoted** (−55% joint / −61% EE) | 07-27 run-logs |
| Physical contact chronology of the D1→D2 episode | **Bounded** (contact 228–232, carry 260–390) | OR3 |
| Sim reproduces task *outcome* on exact replay | **Yes, quarantined** (4.26 mm, 7/7 gates, OR50) | `88361af` closeout |
| Sim reproduces contact *events* | **No** (4 residuals, 26.1° transient tilt) | OR50 `event_residual` |
| Effective plant (3-sample hold) | **Proven on validation** (+55% RMS) | C4 |
| Contact parameters identified | **No — 0/5, fail-closed** | C5 |
| Autonomous physical task success | **No — 0/10 attempts** | C9 ledger |
| REAL→SIM transfer | **No — 0/1 (C6 immutable)** | C6 |
| SIM→REAL transfer | **Never attempted — forbidden until paired passes** | briefs 056/059/060 |
| Any simulator promotion | **None** | all closeouts |
| SAIL beats baselines on its own benchmark | **No (0.625 vs 1.000 top-1), reported as such** | executed benchmark v2 |

---

## 5. The blockers — why the campaign is paused

Everything now waits on physical-world inputs that only the owner can grant:

1. **The elbow torque-off sag** (19–48°, past the calibrated envelope) is the
   named mechanical blocker for any new autonomous motion; CC03E localized a
   mechanical-resistance signature (elbow moves 1.6–1.8° for a 5° request
   while wrist moves 4.8°) without proving a broken part. Service at the
   follower-elbow boundary is the deferred fix (C9/PS0–PS8).
2. **The D405 metric capture** (OR43–OR48): the compiled external-metric
   pad-surface packet needs a working RealSense D405 (the one-shot camera
   lease found no device, exit code 2, and by contract cannot be retried) and
   two jaw-bound metric landmarks. This is the *evidence-safe promotable*
   path to real contact-skin calibration.
3. **Global mapping approval**: C922 intrinsics/distortion and the
   robot/jaw/support mapping remain unapproved, so all pixel-space fits stay
   diagnostic.
4. **Hardware authority**: every capability flag is off; nothing moves, opens,
   trains, or spends until the owner grants it.

---

## 6. Next steps

As named by `GOAL.md` (`next_transition`) and the successor queue, in order of
evidence value:

**Owner-gated (the real unlocks):**
1. Service or accept the follower elbow (ID-3) — reopens physical motion.
2. Provide a working D405 + two jaw landmark markers → execute the frozen
   OR48 metric packet (byte-identical 442-row motion, fit gates ≤0.75 mm
   validation RMS, ≥30% improvement, fail-closed preflight already written).
   This converts the quarantined OR50 geometry into *promotable*
   contact-skin calibration.
3. Approve (or reject) the global camera/robot mapping so pixel-space
   validation can become metric.

**Agent-doable now (diagnostic lane, no new authority):**
4. Freeze a new quarantined card around the four OR50 event residuals
   (early motion, early support loss, missing bilateral contact, transient
   tilt) without touching the successful terminal evaluator or trajectory.
5. Preserve OR50 exactly as-is (its determinism digests make it a permanent
   regression anchor).

**Strategic (from the SAIL plan):** Phase 2 (P2-00…P2-07) — live workcell
identity measurements and interaction probes — is fully specified and waiting
on the same hardware authority.

---

## 7. How this connects to the Honest Evaluation paper

The two workstreams are converging on the same thesis from opposite ends:

- The paper documents that **outcome-only grading lies** (v1 vs v2, 0/5
  checkpoints, collateral inheritance). Jake's campaign spent two weeks
  proving the converse discipline in practice: **OR50 achieves the outcome
  and refuses to claim the behavior**, because the contact *events* still
  mismatch — that is §5's replay philosophy and §10's threat model, lived.
- Our replay-stability probe (modeA/modeB, `docs/paper-evidence/`) supplies
  the quantitative backbone for the campaign's determinism discipline:
  bitwise-identical graded replays vs. 1e-6 perturbations flipping 5/7 gates
  — directly citable next to OR50's digest-identical verification runs.
- The H2 sweep's "loss improves, behavior doesn't" (12 runs) parallels the
  C-lane's "fit improves, contact doesn't" (C4 +55% RMS while C6 stays 0/1)
  — the same proxy/competence divergence at the calibration layer.
- The paper's §6.3 "damage is inherited from the teacher" now has a physical
  sibling: the campaign's only task success is a *human* teleoperation
  episode, and every autonomous imitation of it failed on unmodeled
  mechanism (sag, backlash) — data quality, not optimization, is the
  binding constraint in both.

Worth proposing to Jake: a short §8-style corroboration paragraph citing the
OR50 quarantine as independent evidence that outcome-passing ≠
behavior-matching, with the numbers above.

---

## Claim boundary

This document aggregates existing committed evidence and grants no authority.
It admits no episode, promotes no simulator parameter, and makes no physical
claim beyond what the cited receipts state.
