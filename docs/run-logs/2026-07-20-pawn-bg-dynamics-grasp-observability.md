# B-G dynamics and grasp observability expansion

Date: 2026-07-20 America/Chicago

Outcome: **diagnostic evidence only; no promotion, training, policy, or
physical claim.** This log extends the frozen workcell-fit lane
(`configs/optimization/pawn_bg_workcell_fit_v1.json`, receipt under
`outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v1/`) with independent audits and
dynamics/grasp instrumentation on the frozen train split. Held-out episodes
were not reused for any fitting; where an already-opened held-out number is
mentioned it is labeled as such.

## 1. Independent audits of the +18.70 degree shoulder-lift zero offset

The integration handoff required an independent physical audit of the fitted
lift offset before treating it as calibration. Three local audits ran; none
used any quantity that entered the kinematic fit.

### 1a. Motor-current versus gravity-torque regression (inconclusive)

The recordings carry 5 Hz `available_motor_current_raw` telemetry never used
by any fit. Quasi-static rows (all joint speeds below 20 deg/s, deduplicated
5 Hz readings, 678 rows) were regressed against the simulator's gravity torque
at the mapped measured pose under both zero hypotheses:

| Joint | R^2 identity | R^2 candidate |
|---|---:|---:|
| shoulder_lift | 0.055 | 0.067 |
| elbow_flex | 0.125 | 0.018 |
| wrist_flex | 0.006 | 0.004 |

Currents are quantized (13 distinct lift values, mostly zero); static friction
lets the servo hold with zero current. All R^2 are noise-level, so this audit
neither supports nor refutes the offset. Shoulder-pan gravity torque is zero
under both hypotheses, as expected for a vertical axis.

### 1b. Stall-torque clustering (inconclusive, mild elbow preference for identity)

Real stall rows (joint stationary while command-minus-measured exceeds
2 degrees) should cluster at high gravity torque. AUC of separating stall rows
by |gravity torque|: lift 0.690 identity vs 0.684 candidate; elbow 0.638
identity vs 0.512 candidate. Again weak; the elbow direction mildly prefers
identity, which is noted, not suppressed.

### 1c. Pan-dependence of the vertical residual (supports arm-frame lift offset)

A base-pitch error (unobservable in the overhead photo) would make the
vertical event residual pan-dependent; a shoulder-lift zero offset would not.
Regression of the stage-D per-event z residual on shoulder-pan angle over the
22 train events: slope +0.054 mm/degree, R^2 0.005, implied 2.3 mm variation
across the observed 42-degree pan span against 10.3 mm residual scatter.
**The vertical correction is flat in pan, favoring the arm-frame shoulder-lift
zero interpretation over base pitch.**

The strongest evidence for the offset remains consequence-level: with small
offsets the replayed arm never touches the selected pawn (0/11); with the
lift-dominant candidate it touches in 9/11 train and 2/2 already-opened
held-out episodes, matching the videos in which every real demonstration
grasped the pawn. Physical verification still requires a hardware datum
(re-run LeRobot calibration at a marked pose, or a single measured
base/shoulder height).

## 2. Joint-tracking dynamics decomposition (train split, nominal dynamics)

Per-joint decomposition of the command-driven tracking error under the frozen
workcell candidate (metrics receipt:
`outputs/pawn_bg_act_v1/pawn_bg_actuator_sysid_v1/receipt.json`; global-scale
fit already recorded there was near-null: 2.041 to 2.032 degrees train RMS).

| Joint | Real lag | Sim lag | Real stall rows | Sim reproduces | RMS moving | RMS holding | Direction bias |
|---|---:|---:|---:|---:|---:|---:|---:|
| shoulder_pan | 100 ms | 50 ms | 80 | 31% | 2.22 deg | 0.51 deg | +0.64 deg |
| shoulder_lift | 103 ms | 50 ms | 860 | 3% | 3.62 deg | 1.52 deg | +1.78 deg |
| elbow_flex | 100 ms | 50 ms | 1755 | 1% | 3.26 deg | 3.09 deg | +1.59 deg |
| wrist_flex | 100 ms | 50 ms | 86 | 48% | 2.98 deg | 0.42 deg | +2.77 deg |
| wrist_roll | 100 ms | 50 ms | 113 | 42% | 3.03 deg | 0.56 deg | +0.99 deg |

Reading: the real chain lags ~100 ms versus ~50 ms simulated; the real lift
and elbow park degrees away from the command under gravity (sag) and the
nominal simulator reproduces almost none of those stalls because the vendored
2.94 Nm force range with kp 998 always wins against the ~0.8 Nm gravity load.
The positive direction bias on every joint is a deadband/static-friction
signature. A manual probe capping lift/elbow force range at 0.3x overshoots
(13.7 degree lift RMS): a constant torque cap trades static sag against
dynamic droop, so the bounded per-joint fit (force range, Coulomb friction,
damping, latency) must find the compromise, and the constant-cap model class
itself is a recorded limitation.

## 3. Grasp aperture validation and retention instrumentation

- Simulated jaw aperture at the observed mean close command (9.1 percent)
  is 16.5 mm, matching the 16 mm pawn neck diameter. **The linear
  percent-to-ctrlrange gripper mapping is independently validated at the
  grasp point** (the teleoperator closed to just-neck width and the simulator
  reproduces that width at the same percent). Real closes continue to
  1.1 percent (~4-5 mm aperture), i.e. several millimeters of commanded
  interference that rubber compliance absorbs physically.
- New replay metrics (`longest_contact_streak_rows`,
  `maximum_rise_while_in_contact_m`) quantify retention. Under the frozen
  candidate with nominal dynamics, grasps hold 11-16 rows (0.6-0.8 s) versus
  multi-second real transport; carried rise reaches 40.8 mm in the best
  episode. The four frozen rubber-tip variants now produce different outcomes
  (mean carried rise 3.2-6.7 mm; lift gate 1/11 nominal and low, 0/11 mid and
  high), confirming contact parameters moved from outcome-invisible to
  identifiable-in-principle, but rubber alone does not fix retention.
- Slip postmortems (holder `c2-to-c1..bf91502b`, slipper `b2-to-b1`): at
  closure the pinch point sits 44-55 mm from the pawn center (a proper neck
  pinch is ~12 mm). The simulated arm closes high because it tracks the
  command exactly while the real arm sags below it; the resulting grip is an
  accidental edge contact that slips at lift-off. **Grasp retention is
  therefore gated primarily by the per-joint sag/tracking gap, ahead of
  rubber compliance.**

## 4. Per-joint bounded identification result

Receipt: `outputs/pawn_bg_act_v1/pawn_bg_actuator_sysid_v1/per_joint_receipt.json`
(fitted on the first 8 train episodes, evaluated on all 15 train and the 3
held-out episodes; bounds latency [0, 0.15] s, force-range scale [0.15, 1.5],
Coulomb friction [0, 0.6] Nm, damping scale [0.25, 4]).

- Identified: **command latency 50.6 ms** (one 20 Hz sample), matching the
  100 ms real versus 50 ms simulated lag measured in section 2.
- Not identified: per-joint force-range, friction, and damping all stayed at
  nominal. The optimizer correctly refused the constant-torque-cap sag
  explanation because capping torque near the gravity load wrecks
  moving-phase tracking (manual probe: lift RMS 13.7 degrees at 0.3x).
- Joint tracking RMS: train 2.041 to 1.622 degrees (-20.5%); held-out 2.132
  to 1.640 degrees (-23.1%). The held-out episodes were already opened by the
  workcell lane; this reuse is labeled, not fresh admission evidence.
- Stall reproduction stayed low (held-out lift 0.27, elbow 0.03): the
  hold-sag behavior needs an actuator model with an error deadband or
  current-limited torque profile, which the vendored position servo cannot
  express. This is a recorded model-class limitation, not a fitting failure.

Combined consequence replay (fitted latency plus the frozen candidate,
`outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v1/combined_dynamics_eval.json`):
contact stays 9/11, mean final target distance improves 60.5 to 54.2 mm
(46.4 mm under rubber-high), and grasp retention is unchanged — as expected,
since uniform latency does not move the closure point relative to the sagged
real arm. The grasp-retention gap is now attributed specifically to the
unmodeled gravity sag at closure.

## 5. Claim boundary

Everything here is simulator-frame diagnostic evidence on the frozen train
split. The held-out episodes remain opened-once by the workcell lane; the
per-joint dynamics receipt labels its held-out reuse explicitly and grants no
fresh admission. No physical calibration, task success, policy, training, or
promotion claim is made or implied.
