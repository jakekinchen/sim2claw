# sim2claw Goal

Status: `TWIN FIDELITY 0/6; MULTILEVEL HIL TERMINAL PARTIAL; TASK SCORE 0/11`

## Latest contact-free geometric transfer evidence

Two exact geometric B7 hover round trips have now transferred from the current
candidate simulation to the physical follower. The first high hover completed
`481 / 481` motion rows plus `80 / 80` hold rows. The second approached the
same pawn to a frozen `120 mm` hover, stayed there for `7.5 s`, returned to its
fresh anchor, and completed `901 / 901` motion rows plus `80 / 80` hold rows.
Neither trace used clipping, IK repair, offsets, corrective suffixes,
assistance, rate limiting, or a gateway safety clamp. Both closed with torque
off and with the C922, D405, and Pi IMX708 intervals enclosing the action.

The second transfer is the more task-relevant measurement. At its stationary
hover, the physical-vs-commanded candidate-FK residual is `11.195 mm` RMS and
`11.285 mm` maximum; the mean error is
`[+4.531, +2.877, -9.820] mm`. The largest complete-route residual is
`19.997 mm` on retreat. The terminal anchor hold is `0.996 mm` RMS and
`1.046 mm` maximum. This is accepted contact-free physical transfer evidence,
not pawn contact or task success.

The stationary Pi view uniquely decodes current tags `0, 1, 2, 3`; the
complete current body map is now `6 -> left_base`, `3 -> left_shoulder`,
`0 -> left_upper_arm`, `1 -> left_lower_arm`, and `2 -> left_wrist`. The
previous camera-only refresh is prospectively rejected on this new pose:
combined tag-corner RMSE is about `50.81 px`, dominated by tag 1 at
`77.99 px`. A simultaneous camera/tag/joint-zero fit is structurally rank
deficient (`26 / 29`), so the next calibration must anchor one session camera
to fixed-base CAD/tag 6, fit articulated CAD/joint alignment before nuisance
tag mounts, and reserve a roll-separated safe pose as heldout.

Two fresh heldouts for the direction-conditioned joint-play model passed on
2026-07-27. The first preregistered oblique route moved the follower by at most
`6.6214 deg`, returned to its torque-off anchor, and used the exact same
`361 x 6` float64 action bytes in preview and physical execution. C922
(`373` frames), D405 (`62` frames), and Pi IMX708 (`440` frames) recordings
all enclosed the complete action. The executor completed `441 / 441` motion
and hold samples without clamp, rate limit, stall, assistance, intervention,
or action repair, then closed with follower torque off.

The frozen evaluator improved joint RMS from `0.6543 deg` to `0.2936 deg`
(`55.12%`) and end-effector RMS from `5.4303 mm` to `2.1260 mm` (`60.85%`)
against the parent stateful model. The receipt verdict is
`reverse_joint_play_passed_fresh_geometric_heldout`. This is accepted
contact-free physical actuator/kinematic transfer evidence. It is not pawn
contact, task success, global simulator-parameter promotion, or full
six-domain Twin fidelity, so the headline score remains `0 / 6`.

The second heldout repeated the same contact-clean geometric envelope twice,
with four frozen wrist load-sign crossings. It again completed `441 / 441`
exact rows with torque off and all three camera intervals enclosed. The
selected model improved joint RMS from `0.7323 deg` to `0.3258 deg` (`55.51%`)
and end-effector RMS from `5.7681 mm` to `2.2808 mm` (`60.46%`). Its residual
remains dominated by wrist flex (`0.6295 deg` RMS), so the repeated pass
supports the seven-width model while localizing the next bounded mechanism.

The subsequent `0.015 N m` wrist load-sign hysteresis refinement was frozen
before a third, raised-anchor tricam heldout and was rejected. The new packet
completed three separately torque-off-closed stages—clearance/setup, a
four-crossing heldout, and exact-anchor return—with `441 / 441` rows and
C922, D405, and Pi action enclosure in every stage. On the heldout, hysteresis
worsened wrist RMS from `0.6338 deg` to `0.7425 deg`, overall joint RMS from
`0.3685 deg` to `0.4071 deg`, and end-effector RMS from `2.8024 mm` to
`2.8654 mm`. The parameter is not promoted. The surviving no-hysteresis
direction-conditioned model remains bounded on this harder route.

The physical follower returned torque off at
`[-8.8791, -106.2857, 99.2088, -94.3736, -126.3736, 1.6627]` degrees.
Pi tags 1 and 2 returned within `0.494 px` and `1.150 px` respectively;
the negative evaluator result is therefore not a physical non-return.

The next zero-continuous-parameter wrist hypothesis fixed the asymmetric wrist
play corridor to its positive branch instead of switching on simulated
`qfrc_bias`. A retrospective three-trace screen favored that branch, but the
first opposite-bias route exposed a real torque-off gravity-sag failure before
its second triangle. The arm was recovered under a separately reviewed,
all-three-camera route. That recovery now starts C922, D405, and Pi before any
bounded setup clamp and packet-binds an `81`-state joint-progress
hyperrectangle plus the full path back to the stable anchor.

A replacement heldout kept the already stable positive-bias shoulder/lift/
elbow configuration and changed only wrist flex by exactly `+10 deg`, flipping
simulated wrist bias from `+0.019895 N m` to `-0.022116 N m`. Its normalized
`361 x 6` triangle action was byte-identical to the positive trace
(`32834e50...de40`). On positive bias, the fixed branch and dynamic parent were
exactly equal. On negative bias, the fixed branch improved wrist RMS from
`0.752302 deg` to `0.258030 deg` (`65.70%`), joint RMS from `0.338919 deg`
to `0.122422 deg` (`63.88%`), and end-effector RMS from `2.199393 mm` to
`0.715679 mm` (`67.46%`).

The frozen aggregate evaluator still rejected: it required strict improvement
rather than equality on both signs, and the positive/negative wrist return
errors were `0.906939 deg` and `0.797049 deg`, both above the `0.75 deg`
gate. No parameter is promoted. The result nevertheless supports fixed
positive branching as the simplest next simulator mechanism and localizes the
remaining actuator error to sub-degree wrist return/compliance. The final
tricam return reached the stable anchor within `0.087912 deg` lift and
`0.175824 deg` wrist, with follower torque off.

The active queue is now:

1. retain the fixed-positive wrist branch as supported but non-promoted and
   retain the measured `~11 mm` stationary B7 transfer residual as the current
   physical geometric baseline;
2. freeze the corrected five-tag body map and one session-wide Pi
   camera-from-base transform using fixed-base CAD plus tag 6;
3. fit articulated CAD/joint alignment before tag mounts, keeping focal,
   distortion, link meshes, action bytes, and per-frame camera warps frozen;
4. compile one separately reviewed roll-separated high-clearance hover as a
   fresh heldout, with exact surface-distance checks rather than contact masks;
5. require C922, D405, and Pi action-enclosing recordings on every physical
   trial and torque off on every close;
6. admit pawn contact only after the composite heldout passes; do not inherit
   contact or task authority from either successful hover.

## Ordered sim-to-real transfer queue

The active dependency order is:

1. exact action and replay identity;
2. metric geometry and frame registration;
3. synchronized timing and actuation;
4. calibrated contact and load observability;
5. one frozen composite held-out evaluation;
6. one deterministic geometric physical canary;
7. ACT only after the canary is evaluator-admitted;
8. a VLA or LLM challenger only after the ACT baseline is independently
   admitted.

Current entry conditions remain fail closed: Twin fidelity is `0 / 6`, strict
task score is `0 / 11`, and exact-replay eligibility is `0 / 18`. The native
dual-camera recorder is verified only for stationary camera capture. Inspect
Robots is an optional synthetic replay harness and grants neither evaluator
admission nor physical authority.

The current wide Pi view now has a provisional shared-camera three-link result:
zero-distortion intrinsics validate at `1.021 px` mean RMSE, and the corrected
tag-to-body map passed one fresh all-three-tag follower pose at `5.756 px`
corner RMSE and `9.282 px` maximum without per-frame alignment. The full
SO-101 visual tree, including `left_base`, is rendered in the same frame. This
is static camera/kinematic evidence only; the fixed base has no independent
silhouette gate, and none of the six evaluator-owned Twin fidelity domains is
promoted by this result.

The owner-supplied IMG_5349 Gaussian splat is now automatically registered to
that same complete MuJoCo scene instead of opening at an arbitrary relative
pose. A board-plane/lattice fit used only the coherent early SfM camera
component; an exact two-base SO-101 CAD comparison selected the otherwise
ambiguous board symmetry. Four held-out early-component frames score
`3.759 px` weighted corner RMS over `166` corners. Studio applies the resulting
Sim(3) to all `334,537` splats and shows the complete `45`-body reviewed scene
overlay by default. Camera segments `40-49` and `59-77` are explicitly
quarantined after global projection inconsistency, and the earlier broad
all-segment claim is retracted. This is a concrete visual/geometry diagnostic,
not metric, collision, contact, dynamics, task, or physical-control authority;
Twin fidelity therefore remains `0 / 6`.

The registered calibration overlay now also applies a visual-only palette
correction proven by the existing 3DGS and today's H/I/D C922 captures: all
`64 / 64` shared checker colors were inverted, and all `16 / 16` shared pawn
display colors were on the wrong physical side. The correction changes no
body ID, pose, physics, shared scene, or frozen evaluator render. Historical
AprilTags cannot bridge the old splat to the newly mounted link tags: old ID 0
triangulates cleanly at `2.961 px` RMS but is a board-adjacent datum, ID 1 has
one view, and IDs 2/3 are absent, leaving zero legitimate cross-capture link
correspondences.

A complete-CAD retrospective fit identifies the arm visible in IMG_5349 as
the simulator right arm and reduces held-out half-resolution contour median
error from `37.39 px` to `25.38 px`. Distal CAD-to-splat medians improve to
approximately `10-21 mm`, but the shoulder worsens, two joints saturate their
MuJoCo limits, and no independent left-arm silhouette exists. The candidate
is retained only as a historic-pose hypothesis. The active autonomous lane
therefore uses today's H/I/D C922 silhouettes, Pi tags, exact joint receipts,
and full CAD to seek a current-scene multiview signal without new motion.

Future finalized physical recorder outputs can now be converted directly into
the existing exact-replay v1 audit. Its legacy `applied` field is explicitly a
gateway-sent command, not actuator acknowledgement. This operationalizes the
gate but does not reclassify the existing 18 episodes or open physical,
evaluator, timing-identification, or task authority.

An eligible future output can also enter the existing MuJoCo zero-order-hold
replay with its canonical gateway-sent float64 action tensor byte-identical.
This creates replay-class joint residual diagnostics only: it fits no
parameters and leaves geometry, timing, actuation, contact, and task
consequence blocked.

Until the relevant earlier gate opens, defer broad SAIL work, paid GR00T,
large ACT data generation, isolated-host camera infrastructure, new evaluator
families, and additional simulator-only contact sweeps. None is a substitute
for missing action identity, physical measurement, or held-out consequence.

The new versioned P8/P13 metrology transaction is now the single read-only
control layer for the next geometry/scale attempt. It binds the existing C922
acquisition/evaluator and stationary workcell-registration acquisition/evaluator
to the same exact C922 mode, observable constant focus, current workspace and
board pose identities, printed-grid and direct playing-side measurement
requirements, fixed-board/no-motion boundary, 18-view `12 / 3 / 3` split,
eight-point/two-annotator plan, and existing `1.5 mm / 1.5 mm / 2 px`
residual gates. Its readiness command does not open cameras, capture frames,
construct a gateway, or claim metric authority; the current result remains
blocked on human physical inputs.

## Active evaluator-owned Twin fidelity closure

“Perfect” is now an explicit six-domain evaluator verdict, not a visual
impression or an unweighted percentage. Geometry/scale, kinematics,
action/timing, contact/compliance, actuator/load path, and task/EE consequence
must all pass frozen, receipt-bound gates on the same workcell and action
identity. The authoritative prompt is
[`docs/autonomous-workflow/goal-loop-twin-fidelity-closure.md`](docs/autonomous-workflow/goal-loop-twin-fidelity-closure.md).

The first bounded slice now has deterministic camera container-timing
observability and a fail-closed `0 / 6` closure matrix shared by Studio and
agents. The matrix keeps missing, partial, failed, and passed states distinct;
it publishes no weighted percentage. The separately committed and pushed
preregistration authorized exactly six one-attempt unloaded packets, one per
gateway joint, with multiple fixed levels and slow/fast traversals, exact
returns, dual-camera coverage, and container-timing admission.

That campaign is terminal at `6 / 6` attempts, `0` retries, and `0` provider
calls. Every trajectory and controlled return completed with the same
preregistered hardware/calibration identities and follower torque off after
execution. Four packets were admitted. Shoulder lift and wrist flex were
rejected because the D405 stream failed the frozen completion and frame
coverage gates; their robot telemetry remains diagnostic and cannot be fit.
No retry or replacement packet is allowed under this contract.

The D405 failure has now been localized below FFmpeg and the Studio UI. In
both rejected packets macOS recorded a whole USB-device removal while the arm
was moving, invalidated the D405 for every camera client, and re-enumerated it.
The device is directly attached at SuperSpeed, and controlled stationary tests
passed both in isolation and alongside the production C922 path at exactly
`200 / 200` D405 frames over `40.000 s`. The evidence therefore supports a
motion-correlated cable/connector/strain-relief fault, not an encoder,
dual-camera bandwidth, or camera-ownership failure. It does not identify which
physical connector or cable segment is defective.

The preregistered recorder hardening now treats FFV1 Matroska byte growth as a
transport heartbeat, detects an alive-process/no-growth condition after the
frozen three-second grace and timeout, and escalates shutdown through stdin
`q`, process-group `SIGINT`, terminate, and kill. A readable partial container
cannot turn a detected stall into admitted evidence. This is acquisition
infrastructure only: stationary qualification remains separate from reliable
capture under motion, metric depth, calibration, and task proof.

The one authorized stationary qualification is now sealed. It used six of six
40-second dual-camera trials, zero replacements, zero robot motions, and zero
provider calls. The D405 completed all six sources with 201–202 frames,
monotonic 5 fps container PTS, zero inferred missing intervals, and no source
stall. The independent evaluator still rejected all six trials because the
C922 container had 29–30 inferred missing 30 fps intervals at D405 stream-open
and stream-close/finalization boundaries. No USB-device removal occurred in
this stationary campaign. The result is therefore a terminal negative for the
current dual-camera lifecycle, not a D405 motion-reliability pass, and it is not
eligible for retry or post-hoc threshold relaxation.

The bounded AVFoundation source-localization transaction is now a sealed
prerequisite abstention. Its implementation was committed before live use and
the frozen campaign consumed all 12 one-attempt slots—six control-labelled and
six treatment-labelled—with zero replacements, robot motions, or provider
calls. Every attempt failed before session startup because the exact
preregistered C922 `640 × 480 @ 30 fps` AVFoundation format was unavailable.
The campaign therefore contains zero source samples or drops, zero completed
AVFoundation session starts, and zero D405 lifecycle executions.

An independently committed fail-closed sealer verified the original
source/runner/binary identities and all raw artifact hashes, then emitted
`prerequisite_abstention`. No source-continuity comparison is available and no
container gap was reclassified. The immediate software prerequisite is an
evaluator-frozen mapping from the C922's actually enumerated AVFoundation
formats to a supported exact source-probe request; a later campaign would
require new authority because this 12-attempt family is exhausted.

That prerequisite is now a separate software-only transaction. Its v1
contract freezes one exact-name native C922 format inventory, zero capture
sessions or frames, no D405 lifecycle, and an evaluator-owned 640×480
fractional-rate rule with a maximum `0.05 fps` deviation from 30. The observer
will enumerate only; it cannot select, score, start a stream, or authorize a
new campaign. The standalone Swift observer and independent Python evaluator
were committed before the single observation. That observation exhausted its
one-attempt budget but crashed during JSON serialization on a non-primitive
Swift bridge value before writing raw inventory. A separately committed
fail-closed sealer recorded `prerequisite_abstention`, zero usable inventory,
and no candidate. No second v1 observation is permitted.

A separately versioned v2 prerequisite was frozen before implementation. Its
exact implementation was committed at `995e8bb` without device access. The
sole read-only observation then completed under exact head `79fdbe8`: the
native C922 surface contains 33 formats and 209 frame-rate ranges. The frozen
evaluator found 14 exact-640×480 candidates, admitted two within `0.05 fps` of
30, and selected subtype `420v` at `30.00003000003 fps` (deviation
`0.00003000003 fps`) by the preregistered tie-break. The observation budget is
exhausted at `1 / 1`; capture sessions, frames, D405 lifecycle operations,
robot motions, simulator replays, and provider calls remain zero.

This closes only the supported-format prerequisite. It does not prove callback
delivery, container timing, physical exposure continuity, cross-camera
synchronization, metric depth, simulator calibration, or task success. A
future callback-source measurement must be separately preregistered against
this exact candidate and cannot reuse the exhausted v1 source-localization
family.

That separately preregistered callback-delivery v1 observation is now terminal
degraded. One exact-implementation C922-only session produced `243` native
output callbacks and zero Apple drop callbacks, but every delivered sample was
`1920×1080 420v` rather than the applied `640×480 420v` candidate. Mean PTS
interval was `0.04200826446267907 s`; maximum was
`0.08303333341609687 s`, above the frozen `0.049999950000049996 s` gate.
The evaluator failed `exact_dimensions` and `bounded_pts_interval`. The result
isolates the next prerequisite to post-input-association AVFoundation format
configuration and post-configuration/start verification; v1 is exhausted and
cannot be retried. It does not reclassify D405/container, exposure,
cross-camera, simulator, or task evidence.

Callback-delivery v2 is also terminal degraded and exhausted. Its sole
post-input-association session preserved the frozen `640×480 420v` format and
`0.03333330000003333 s` frame duration through configuration commit, while the
session preset remained `AVCaptureSessionPresetHigh`. On `startRunning()`,
AVFoundation changed the active device format to `1920×1080 420v` with a
`0.0416666006945489 s` frame duration. The observer stopped fail closed after
one delivered sample. The evaluator failed `exact_format_after_start`,
`minimum_output_callbacks`, `exact_dimensions`, `strictly_increasing_pts`, and
`bounded_pts_interval`. This localizes the next prerequisite to a separately
preregistered post-commit format/preset binding mechanism before session
start; v2 cannot be retried. It remains source-callback evidence only.

Callback-delivery v3 resolved that start-time format override. Keeping the
associated device configuration lock through commit and initial start
preserved exact `640×480 420v` format and `0.03333330000003333 s` frame
duration at every lifecycle stage, and all `305` output samples retained the
same format with zero Apple drop callbacks. Mean PTS interval improved to
`0.034180811403769586 s`; median was about `0.033 s`. The frozen strict result
is nevertheless `callback_delivery_degraded`: the first of `304` intervals was
`0.0659999999916181 s`, above the `0.049999950000049996 s` maximum, while the
remaining `303 / 303` intervals stayed within the gate. V3 is exhausted and
cannot be retried. The format-negotiation prerequisite is closed; a separately
preregistered warm-up-bounded measurement window is now required before
source cadence can be verified.

Callback-delivery v4 now verifies that production-style pre-roll window. It
reused the exact reviewed v3 lock-through-start observer for one eleven-second
session and retained all `334` exact `640×480 420v` samples with zero Apple
drop callbacks. The frozen first source-PTS second remained visible as `27`
warm-up samples, including a `0.06700000003911555 s` startup gap. The scored
window contained `307` samples and `306` intervals across
`10.199999999953434 s`; its mean interval was
`0.033333333333181156 s` and maximum `0.03400000010151416 s`, below the
unchanged `0.049999950000049996 s` gate. The independent evaluator returned
`steady_callback_delivery_verified` with no failed gates. This closes the C922
source-format and steady-cadence prerequisite; it does not prove exposure
continuity, cross-camera synchronization, D405 reliability, or calibration.

The separately preregistered production lifecycle test is also complete and
must remain a terminal negative. The recorder now opens the D405 before the
C922 and finalizes the C922 before the D405, so the D405 lifecycle boundaries
sit outside the C922 container window. The sole ten-second stationary session
used one D405 session and one C922 session with zero retries, replacements,
robot motions, simulator replays, or provider calls. This C922 container had
`314` frames and zero inferred gaps. D405 completed with source progress
and `63` frames, but its container contained one `0.600 s` interval from PTS
`11.6` to `12.2`, equal to two inferred missing intervals. That gap
diagnostically brackets the reported common-window/C922-stop boundary; the
clocks are not exposure-synchronized. The frozen evaluator therefore returned
`reject_stationary_nested_dual_camera_lifecycle`. No threshold changed and no
retry is permitted.

The zero-session D405 format prerequisite is now terminal and supported. Its
sole exact-device inventory contained 12 native formats and 56 rate ranges.
The independent evaluator found two eligible exact 424×240 @ 5-fps candidates
and selected format 0/range 4, native subtype `2vuy`, under the frozen
0.01-fps/subtype/tie-break rule. Budget use was one inventory, zero capture
sessions, zero frames, and zero camera lifecycle operations, robot motions,
simulator replays, or provider calls. This is design input only; it does not
prove that a native two-input common session works.

That native common-session gate is now terminal degraded and exhausted. The
sole preregistered stationary metadata-only `AVCaptureSession` admitted both
exact devices and outputs. It delivered `338` C922 callbacks and `61` D405
callbacks with zero drops; after the visible one-second source-PTS warm-up,
the scored counts were `315` and `60`, maximum intervals were `0.034033 s`
and `0.200000 s`, and the common host window was `10.447306 s`. All callback,
cadence, and common-window gates passed. Both devices, however, reported reset
format indices after the session stopped, so the frozen evaluator returned
`common_session_callback_delivery_degraded` on exactly
`after_stop:c922_format_index` and `after_stop:d405_format_index`. No
threshold changed and no retry, container, robot motion, simulator replay, or
provider call occurred. A tracked guard now refuses before device delegation.
This proves bounded active-session callback health only; it is not a production
writer, exposure synchronization, motion reliability, metric depth,
calibration, simulator, or task result. Per the preregistered decision rule,
the next camera architecture is a separately preregistered isolated host.

Production recorder integration now treats that frozen result more narrowly
without changing it. The two failed post-stop indices are AVFoundation format
object-identity lookups: the raw after-stop states retained the exact dimensions,
subtypes, frame durations, device identities, and stream bindings, and no
captured callback or finalized writer depends on the lookup. The physical
Studio recorder at implementation `5515e5d` therefore uses one native common
session and gates admission on exact active-session identity, first-frame
delivery after the existing visible one-source-PTS-second warm-up, explicit
input/output binding, per-stream writer completion, zero Apple drops, and zero
writer backpressure. It retains separate source containers, callback/host
timestamp lineage, hashes, frame counts, and browser derivatives.

The first bounded stationary production-path capture opened no robot gateway
and made no robot command. It delivered `323` C922 plus `56` D405 callbacks
with zero Apple drops or writer backpressure and completed both native writers,
but exposed the D405's initial source-PTS `0` sentinel as a writer-timeline
defect. The committed repair retains that sentinel and all warm-up callbacks in
the ledger while excluding the first source-PTS second from both writers.

One post-repair stationary camera-only production recording now closes the
recorder verification step. The exact common session observed `377` C922 and
`67` D405 callbacks, excluded `22` and `7` warm-up callbacks, and finalized
`355 / 355` C922 plus `60 / 60` D405 source/browser frames. Both written
timelines were strictly increasing with zero inferred missing intervals, zero
large gaps, zero Apple drops, and zero writer backpressure. The D405 sentinel
remained visible in provenance but was not written; source durations were
`11.833333 s` and `12.000000 s`. An offline receipt projection was accepted by
the existing Studio catalog as two hash-verified feeds. No robot gateway,
motion, retry, metric depth, exposure synchronization, calibration, task
success, or physical authority was involved.

The evaluator-owned exact-mode C922 calibration implementation is consolidated
at `1eabc49`. Its already-consumed offline evaluation remains honestly
`calibration_dataset_not_ready`: zero declared or accepted frames, zero model
fits, and no calibration receipt. The nominal `20 mm` square and
`200 × 140 mm` grid values are not metric authority. Calibration cannot begin
until a human supplies a physically measured printed target, one observable
constant focus setting, and 18 distinct exact-mode views frozen into `12 / 3 /
3` fit/validation/held-out splits with the preregistered position, scale, tilt,
and orientation diversity.

The successor P8/P13 transaction is implemented at
`configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json` with
the readiness command `sim2claw metrology-transaction-preflight`. It is an
operational sequencing manifest only: no camera session, new frame, robot
motion, fit, evaluator admission, or physical authority has been used. Its
first live action is the readiness command itself; human-only work remains to
print/mount and physically measure the target, lock and record focus, hold the
board and camera stationary, capture the frozen views, survey A1/H1/A8, and
complete the two independent annotations.

The isolated-host inventory is now terminal and exhausted. The sole strict
metadata connection reached `silicon.local` on macOS `26.3.1` with no stderr
and no retry. It found zero C922 camera/USB matches and zero D405 camera/USB
matches, so the frozen evaluator returned
`isolated_overhead_host_requires_c922_attachment` on exactly the two target
C922 match-count gates. Budget use was one inventory and one connection, with
zero camera sessions, frames, remote files, robot motions, simulator replays,
or provider calls. A tracked guard refuses any second inventory before process
delegation. The proposed architecture remains to keep the D405 and robot path
on `kelly-claude` and move only the fixed overhead C922 USB attachment to
Silicon. Until that physical attachment occurs, no remote capture transport,
source delivery, cross-host clock, synchronization, calibration, simulator,
or task claim is available.

The independent metric-registration readiness gate is also terminal. It
verified the existing current-workcell C922 C2→C1 capture receipt, video, frame,
camera identity, resolution, orientation, and closed authority, then returned
`measurement_prerequisites_missing`. Available RGB pixels did not substitute
for a deterministic frame-extraction receipt, direct board measurement,
exact-mode intrinsics/distortion, eight independently annotated distributed
board points with held-out scoring, metric object keypoints, or camera
extrinsics. The result contains ten missing prerequisites, zero invalid source
inputs, and one of one offline evaluations used; camera sessions, new frames,
robot motions, simulator replays, provider calls, and training rows are zero.
A tracked guard closes v1. Geometry/scale remains `missing`; any acquisition
or fit requires a new preregistered transaction.

One of those ten missing inputs now has a separately verified successor
artifact. The C922 frame-lineage gate rederived video frame index `29` at PTS
`1.000000 s` through the tracked, hash-bound decoder wrapper. Its PNG bytes and
decoded RGB24 bytes both match `overhead_start.png` exactly. Budget use was one
probe, one derivation, and zero retries or hardware/simulator operations. This
receipt may remove the extraction-lineage item in a new metric-readiness
version; it does not rewrite the terminal v1 packet or change geometry/scale.

The v2 closure evaluator remains `0 / 6`: geometry/scale and
contact/compliance are missing; kinematics, action/timing, and actuator/load
path are partial; task/EE consequence is failed. It reports the exact remaining
measurements and does not convert partial progress into a percentage or a
simulator/task claim. The next scientific step requires a separately
preregistered physically isolated camera host, plus physical repair and strain
relief of the D405 path before any motion qualification. Only afterward add
metric registration, calibrated force/current/load
observability, device/actuator timing, reset/loaded trials, and strict held-out
physical consequence. Another simulator family, silent retry, or post-hoc
camera threshold change is not an acceptable substitute.
The owner now explicitly authorizes necessary physical tests and guarantees
the workcell is clear. Each physical packet remains execution-blocked until
its own preregistration, exact hardware/calibration, torque-off, start-envelope,
dual-camera, controlled-return, and evaluator gates pass. The authorization
does not reopen the rejected shoulder simulator candidate, training, promotion,
provider, paid-compute, or public-release authority. The frozen four-packet
HIL and eleven-file S2 evidence sets remain immutable.

The Replay-integrated Twin surface also passed a narrow rendering repair after
independent review found that two concurrent Three.js viewers could share one
canvas and emit WebGL program-location errors. Viewer creation and scene loads
are now single-flight/serialized at committed implementation `3195280b`; the
original missing → paired → paired sequence has zero WebGL errors in Chromium
and WebKit. This is product reliability evidence only and does not change any
fidelity-domain, simulator, task, or physical verdict.

## Completed four-hour HIL identifiability loop

From `2026-07-24T02:37:10-05:00` through at least
`2026-07-24T06:37:10-05:00`, record exactly four additional bounded unloaded
physical packets—gripper, shoulder lift, elbow flex, and wrist flex—then use
their content-addressed evidence to close only the simulator factors they
actually identify. The authoritative prompt is
[`docs/autonomous-workflow/goal-loop-four-hour-hil-identifiability.md`](docs/autonomous-workflow/goal-loop-four-hour-hil-identifiability.md).

The owner authorized the physical tests and guaranteed the chessboard workcell
will remain clear. Motion still requires the exact identified follower,
calibration, torque-off, dual-camera, action-envelope, telemetry, controlled
return, and evaluator gates. Each packet gets one attempt and no adaptive
retry. The arm is powered only during the short packets; the remaining loop is
offline evidence integration, action-identical simulator comparison, Studio
observability, and verification.

The strict task score remains `0/11`. These unloaded measurements cannot by
themselves prove pawn transport, physical transfer, training admission, or
simulator promotion. Frozen S2 evidence remains read-only.

All four one-attempt packets are now recorded and follower torque is off.
Gripper and shoulder lift passed the independent packet gates. Elbow completed
an `18.37°` span but is excluded from fitting because its sustained tracking
gap triggered the frozen stall warning. Wrist flex completed a `28.75°` span
and returned, but its D405 source did not finalize, so the packet is excluded
from admitted evidence. Neither rejected packet may be retried.

The sole simulator follow-up was frozen before execution in
`configs/evaluations/hil_shoulder_range_external_validation_v1.json`. It
compared the current declared shoulder range with the pre-existing hash-bound
follower endpoint range, mutated only shoulder lift, and consumed exactly two
action-identical simulator replays. Shoulder RMSE fell from `4.289°` to
`1.281°`, but elbow regressed by `0.511°`, beyond the frozen `0.25°` ceiling,
and strict task/EE consequence was unavailable. The evaluator rejected the
candidate; no simulator parameter, posterior, calibration, or task score
changed.

Two separately versioned offline audits now rederive all four traces. They
show that none passes the scale/offset, actuator-latency, dynamic-response,
backlash, or reset-drift identification gates. The requested/applied audit
also localizes the elbow sequence to gateway rate limiting at sample `59`,
peak raw current at `68`, velocity collapse under tracking error at `83`, and
stall warning at `99`. This is diagnostic chronology, not force or causal
load-path proof.

Replay and Twin fidelity publish the four verified packets, available camera
feeds, requested-versus-applied identity, observed/missing/failed gap domains,
and exact next prerequisites. The physical gateway now emits ordered
same-process host timestamps for future packets while explicitly leaving
actuator acknowledgement and synchronized device-clock fields unavailable.
Final state/log binding, exact-head proof tiers, one full suite, and the
minimum `06:37:10-05:00` exit remain. No push is authorized.

## Active Studio project mapping

Make the full sim-to-real system legible through one Studio evidence system
shared by researchers and bounded agents. The Project map must cover Capture,
Scene, Simulate, Replay, Evaluate, Diagnose, Improve, and Learn/transfer; bind
each stage to existing routes and agent-readable contracts; show proof class,
missing prerequisites, and authority; and fail closed when a receipt or
project binding is invalid.

Learning Factory remains contextual improvement/evaluation machinery rather
than a standalone primary destination. The agent participates in the governed
outer loop and never owns timestep control, evaluator scoring, admission,
promotion, training, or robot authority. No synthetic fidelity percentage or
missing physics replay may be introduced.

The implementation candidate is recorded in
[`docs/run-logs/2026-07-24-studio-project-map-agent-access.md`](docs/run-logs/2026-07-24-studio-project-map-agent-access.md).
The Replay surface now removes the retired pixel-filter “visual twin” and
admits only receipt-bound MuJoCo traces. Seven physical sources retain
byte-identical action-frozen simulator pairings; one additional physical source
has a separately labelled source-command diagnostic whose unit conversion and
model-bound clipping explicitly prevent an exact-action claim. Fourteen
physical sources remain simulator-unavailable. Invalid source, receipt,
response-trace, or state-trace hashes fail closed.

Studio exposes one Reality / Twin / Compare switch, one synchronized timeline,
and contextual Twin fidelity/evidence drawers. The source badge is
informational rather than a duplicate route. A loopback-only explicit command
may generate a diagnostic replay for an existing recording, but read-only
Studio exposes no write control and no generated replay can self-admit
mechanism, consequence, task, training, promotion, or physical authority.

The official SAIL observatory and publication package have been regenerated
from the committed compiler and remain physical-authority false. Exact-head
short tiers, one full repository suite, and independent review still own final
verification; no push is authorized by this checkpoint.

## Completed overnight dual-camera simulator calibration

For the three-hour window ending `2026-07-24T03:16:30-05:00`, convert the
new dual-camera, fresh-current empty-gripper recording into a deterministic
derived diagnostic and bind its exact command tensor to the current simulator.
The authoritative bounded prompt is
[`docs/autonomous-workflow/goal-loop-overnight-dual-camera-sim-calibration.md`](docs/autonomous-workflow/goal-loop-overnight-dual-camera-sim-calibration.md).

Terminal result: the raw recording remains immutable and unqualified, with six
reported excursions rather than the intended five. The one frozen,
action-identical two-replay comparison reduced aggregate body-joint RMSE from
`3.4281°` to `2.2801°` but regressed elbow RMSE by `0.8700°`, narrowly
regressed gripper RMSE, and had no strict task consequence. The independent
evaluator therefore rejected the global range candidate.

A subsequent zero-replay offline audit found that shoulder lift never moved
from its endpoint command (`0.0°` span) and elbow covered only `10.022°`, below
the frozen `15°` identifiability gate. Neither joint-specific range scale is
identified, so no shoulder-only correction is admitted. GPT-5.6's useful
timing/calibration-envelope advice is retained as critique only; an
inapplicable bootstrap claim and its pre-audit shoulder-only recommendation
were not adopted.

The receipt-verified Twin fidelity view now exposes the partial aggregate
reduction, joint regression, excitation gaps, procedure mismatch, and exact
next measurement fields. No unattended robot motion, task-score change,
training, simulator promotion, paid compute, push, or new retained-C2 family
occurred.

## Active current-workcell measurement and calibration

Collect the independently synchronized current-100 mm evidence required by the
closed actuator external-validation result, then use the fixed methodology to
fit and evaluate at most one action-frozen composite simulator candidate. The
authoritative prompt is
[`docs/autonomous-workflow/goal-loop-current-100mm-physical-measurement-calibration.md`](docs/autonomous-workflow/goal-loop-current-100mm-physical-measurement-calibration.md).

The owner has authorized bounded camera capture, robot episodes, and data
collection. The preregistered torque-off baseline is complete with 30/30
fresh-current samples and 239 diagnostic camera frames. After the owner
confirmed that the overhead view showed the intended task setup rather than an
uncleared workcell, the gateway completed one slow positioning move and one
camera-bound historical trace replay. The selected `b2 to c2` source ran in
reverse for all `566 / 566` requested rows. Only `394 / 566` commands were sent
within the 0.25-degree exactness tolerance and `175 / 566` samples were
gateway-clamped, so the result is unqualified physical command-replay
observation only. It is not exact-action, task-success, calibration, or
training evidence. Follower torque is confirmed off.

Work continues through the preregistered empty-gripper and synchronized
measurement gates. No action assistance, post-held-out family expansion, or
score change is allowed. The strict task score stays `0/11` because this run
did not have evaluator-owned metric task consequence and visibly showed no
obvious endpoint board-state change in sampled start/end frames.

The owner then requested the canonical forward `c2 to c1` replay with the
D405 wrist stream captured alongside the C922. Three action-unchanged physical
replays completed; the first two are excluded from dual-camera proof because
the D405 stream stopped after approximately five seconds. After a camera-only
USB/serial-load test, the final attempt used the D405's supported
424x240-at-5-fps mode and captured all 175 wrist frames through 34.8 seconds,
plus 1,049 overhead frames through 34.97 seconds. The final robot replay
completed 527/527 rows, delivered 501 within 0.25 degrees, safety-clamped 70,
and released torque.

The board endpoint remained visually unchanged. The wrist stream shows the
jaws centering on the pawn without transporting it. During the critical
approach/closure window, actual shoulder/elbow/wrist tracking lag reached
approximately 5-8 degrees even though requested-to-sent clamp error stayed at
or below 1.758 degrees. This is evidence for a combined approach-timing and
grasp-retention gap, not a completed task or an admitted simulator
recalibration. No force, grasp-load current, metric wrist depth, or
camera-to-gripper calibration was available to separate those mechanisms.
The baseline receipt digest is
`4dbb666ab68fa41688b3d346f54797d947fd0771af8f2ec20edc1ac379eb4021`;
the replay capture receipt SHA-256 is
`3fafb113a7b89e0b80640b9c7b4cc2016db16ecafcb9f46cba79a79a1330499f`;
the run log is
[`docs/run-logs/2026-07-23-current-100mm-bounded-physical-replay.md`](docs/run-logs/2026-07-23-current-100mm-bounded-physical-replay.md).

## Active actuator-response external validation

Evaluate, without refitting, whether the previously selected action-frozen
servo deadband/load-response candidate transfers from its 11-episode selection
session to the five independently recovered 72 mm historical acquisition
sessions. The authoritative prompt is
[`docs/autonomous-workflow/goal-loop-actuator-external-validation.md`](docs/autonomous-workflow/goal-loop-actuator-external-validation.md).

The cohort is frozen at five episodes and 2,186 rows. Baseline and candidate
actions must remain byte-identical, float64 `[N, 6]`, unclipped, unassisted, and
unresampled. The only family is the existing baseline versus the prior selected
candidate; the budget is exactly ten simulator replays, zero retries, and zero
provider calls.

The external evaluator alone owns the preregistered gates: at least 2% pooled
joint-RMS improvement, improvement on at least four of five episodes, a
positive 95% whole-session bootstrap lower bound, and pooled EE RMS
non-regression. These historical trace results cannot change the separately
owned 0/11 strict task score, refit or promote parameters, establish current
100 mm spatial/contact calibration, or open training, physical, gateway, or
motion authority.

Terminal result: the single authorized run used all `10 / 10` replays with
zero retries and zero provider calls. The selected candidate reduced pooled
joint RMS from 1.41098 to 1.36004 degrees (3.61%) and pooled EE RMS from 13.756
to 13.233 mm (3.80%), with improvement on four of five sessions. It failed the
frozen bootstrap-direction gate because the 95% joint-improvement interval was
`[-0.000649, 0.069475]`. The evaluator therefore returned
`external_trace_validation_reject_task_completion_unchanged`.

The independent strict task result remains 0/11. No candidate was promoted and
no current-workspace calibration changed. This family is closed; the next
scientific prerequisite is independently synchronized current-100 mm
angle/current/load/contact measurement, not another post-result simulator
parameter search.

## Active Silicon recovery and repository reconciliation

Recover the unfinished Sim2Claw work found on `silicon.local`, preserve it
losslessly, and integrate only the parts that remain compatible with current
proof, safety, and Studio contracts.

Baseline: clean centralized `main == origin/main` at
`3a0e45864419a393ef902d255a48518b5d728f3b`. The Silicon checkout was
`102` commits behind at `090549ae7824b244c81a1af7d5e0484e8a747f41` and
contained `20` modified tracked files plus `18` untracked source files.

Recovery contract:

- preserve the exact 38-file source snapshot on the quarantined
  `codex/silicon-recovery-20260723` branch;
- retain the 34 owner-directed attempt receipts and 128 physical replay
  receipts under ignored `runs/` with byte-identical directory manifests;
- label all recovered physical history as unqualified command-replay
  provenance: zero receipts verify task success;
- keep ordinary Studio startup free of physical demo authority; expose the
  recovered controller only through a separate explicit loopback-only opt-in;
- retain current receipt-owned media rotation, exact scene/trace revision
  binding, the 18/18/7/11 Replay comparison truth, and all frozen S2 evidence;
- do not run the gateway, robot, camera capture, simulator adapter, provider,
  training, promotion, or VideoSim paths during reconciliation.

Completed milestone: the exact source snapshot is quarantined, the compatible
subset is integrated, the physical controller is default-closed, publication
bindings are refreshed, and the full repository suite passes. Centralization
is limited to a normal push of the reviewed `main` chain plus the quarantined
recovery branch.

Data-completeness closeout: every Silicon dataset/run file already present was
byte-identical, all missing raw ACT, teleoperation, multicamera, transfer, and
orchestrator data was copied into the ignored canonical roots, and conflicting
or explicitly truncated generated outputs were preserved separately as
excluded provenance. No credential, environment, cache, build product,
synthetic test campaign, or stale Studio process registration was promoted as
project data.

Recalibration assessment: the five recovered 72 mm recordings now make the
frozen sim/real bridge joint-response-ready across 2,186 hash-verified rows.
Their 0.15–0.20 s lag and 2.830°–3.452° historical sim-replay body-joint RMSE
can support a future preregistered actuator-response cross-check. They do not
make the current 100 mm spatial comparison, policy training, closed-loop
comparison, contact/friction fit, or strict task score ready. No calibration
or task score changed in this transaction.

## Closed SAIL executed-benchmark and retained-C2 adapter transaction

Replace the remaining label-conditioned benchmark and synthetic-fixture
adapter limitations with two bounded executable evidence surfaces:

1. a versioned structural benchmark whose registered methods actually execute
   from frozen public inputs and are scored only by a separate sealed
   evaluator; and
2. exactly one non-fixture retained-C2 trusted adapter, or a sealed
   prerequisite abstention if its action-frozen raw inputs cannot be verified
   without widening authority.

Authoritative goal-loop prompt:
[`docs/autonomous-workflow/goal-loop-sail-executed-benchmark-c2-adapter.md`](docs/autonomous-workflow/goal-loop-sail-executed-benchmark-c2-adapter.md).

Baseline: clean `main == origin/main` at
`616f9896650870913915087095a9a9bae9aad9ed`. The closed D6 packet remains
read-only at `outputs/dev-loop/final/merge-readiness-packet.json`, file
SHA-256 `c7d66da11896c27b1fdb39ff2bbc39ddf3c456ae8cf919957cb7e9ca91deb775`,
packet digest
`f88070030f27c6b0f61b8ca37f10e9942d48ef2b5bf389236183632ea8c27b28`.
It proves the prior transaction only and cannot authorize this one.

Transaction milestone: **S2-04 — exact-head verification, independent review,
and scoped push**. S2-01 is complete as a separately reviewed synthetic
benchmark checkpoint. S2-02 was frozen and tested with zero real replays before
its preregistration commit. S2-03 used the single authorized intervention and
closed as a retained-simulator terminal negative.

Current milestone: **D6 — verification and closeout**. This marker remains
owned by the canonical autonomous-development control-plane candidate; the
closed D6 packet named above is immutable and S2 does not reopen it.

The benchmark acceptance target is trustworthy executed measurement, not a
required SAIL win. The C2 lane is limited to one preregistered intervention,
eighteen action-identical anchor replays, zero retries, and no post-result
family expansion. Provider calls, paid/Brev compute, training, simulator
promotion, physical capture, gateway access, robot motion, and transfer
authority remain closed.

Progress ledger:

- Transaction state: evaluator-executed benchmark v2 is materialized and
  reviewed; the one four-candidate non-fixture C2 intervention executed once
  and is frozen as an evaluator-rejected terminal negative.
- Completed: clean baseline and immutable D6 packet identity reconciled;
  benchmark-v1 label scoring and fixture-only adapter gap confirmed.
- Baseline evidence: `main == origin/main == 616f989` before S2; the D6 packet
  terminal authority is true with zero live leases and remains immutable.
- Benchmark methods / controls / failures: `64 / 4 / 0`; all 25 declared
  golden checks actually executed and passed.
- C2 interventions / anchor replays / retries / measurement trials: `1 / 1`,
  `4 / 18`, `0`, `0`; campaign events: `1`.
- Consequence: `evaluator_reject`; mechanism effects were diagnostic but strict
  task-plus-EE passes were `0 / 4`, admitted evaluator evidence was `0`, and
  factor updates were `0`.
- Posterior before / after: flexural contact `0.5 / 0.5`; actuator load path
  `0.5 / 0.5`; observed information gain `0.0` bits.
- Frozen evidence: live receipt SHA-256
  `ff79ea13db0eeb712bfe3b14ce38a1dbf7d57e9aa2743bcaab151777c7a0639d`,
  adapter receipt SHA-256
  `b2e93b24466d3e562ab59483da5f6bff132240e37119f9ff2646c8220c466958`,
  and campaign-state SHA-256
  `9d305db1e6bce6042536422c17e9ea70f1752255108cb23da77c5f302e120448`.
- Remaining: read-only receipt validation, exact-head focused/SAIL/full-suite
  verification, fresh independent review, scoped push, and remote equality.
- Blocker / next scientific prerequisite: independently calibrated,
  synchronized force/deformation/angle/current measurement acquisition. It is
  not authorized or started during S2 closeout.
- Next step: verify without executing another simulator replay, obtain fresh
  `PASS`, push the exact scoped commits, and verify local/remote equality.

## Closed autonomous development operations and advancement baseline

Harden the repository's autonomous-development loop into a deterministic,
resumable, receipt-gated, process-safe, and measurable control plane. Reconcile
authority surfaces, implement task/review/test/process receipts and exact test
reuse, prevent duplicate/orphaned work, produce merge-readiness packets, run a
seeded DevLoopBench, modularize the SAIL live operator, and add a trusted
deterministic adapter boundary.

Authoritative plan:
[`docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md`](docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md).

Active goal-loop prompt:
[`docs/autonomous-workflow/goal-loop-autonomous-dev-ops-advancement.md`](docs/autonomous-workflow/goal-loop-autonomous-dev-ops-advancement.md).

Closed milestone: **D6 — terminal at `616f989` through the generated
post-push packet named above**.
D1-D3 are independently accepted after two corrective review cycles and a
final `PASS`:
canonical current-state drift is unique and fail closed; role, receipt, merge,
and actual-child process lifecycles are bound; exact tests execute once and
reuse only the matching receipt; and DevLoopBench reports configured
control-label coverage with its limited proof class explicit. D4-D5 are also
independently accepted: the retained operator is modular with a versioned,
byte-identical non-receipt migration, and the registered development fixture
adapter derives and rereads its own result behind global abstention gates.

The reviewed continuation was fast-forwarded with owner authorization. Local
`main` and `origin/main` were equal at the D1-D3 checkpoint `6e6abd5`; D0-D6 execute on `main` with
scoped commit/push authority. Do not rewrite or fork that completed history,
open a provider or paid-compute lane, train, run a simulator campaign, capture
physical data, access a robot gateway, or command motion.
Only `docs/autonomous-workflow/project_state.json` owns live workflow state;
the orchestration ledger is rendered/history evidence and must fail validation
when stale.

Read-only physical readiness is negative: the expected SO-101 leader/follower
ports and calibrations are absent, the only `/dev/cu.usbmodem*` candidate is an
ignored billboard, no usable camera/USB device was enumerated, and no
synchronized jaw-force or rubber-deformation/profile sensor is present.
The D6 committed state was deliberately nonterminal (`active`, `FULL_VERIFY`,
`D6=in_progress`). Its generated `merge_ready` packet, verified against the
then-current project-state bytes, local and remote HEAD, and zero live process
leases, is the prior transaction's terminal operational authority. This new S2
transaction does not mutate or inherit that packet.

Physical capture and robot motion remain blocked by hardware/calibration
readiness; do not open the gateway or manufacture measurement evidence.

## Active SAIL decision/evidence control-plane integration and ablation

The user paused the open-ended B2 parameter-family search after it accumulated
completed causal diagnostics without an evaluator-owned anchor pass. The active
objective is now to make the existing SAIL residual, belief, acquisition,
posterior, influence, sparse loop-closure, invariance, and consequence surfaces
operate as one retained-project decision/evidence control plane, then ablate that plane
against the manual campaign sequence. A correct evidence-bound abstention is an
accepted terminal outcome.

Authoritative goal-loop prompt:
[`docs/autonomous-workflow/goal-loop-sail-live-operator-integration.md`](docs/autonomous-workflow/goal-loop-sail-live-operator-integration.md).

Historical continuation branch: `codex/sail-live-operator-integration`, now
fast-forwarded into `main` at `1ee6b7d`.

The interrupted predecessor task is
`019f87bd-5440-78b2-a74b-c447fe287cbe`. Read it for evidence and context, but
do not resume its instruction to continue parameter families until a win.

Closeout ledger (2026-07-22):

- Current state: independently rereviewed and merge-ready with no blocking
  correctness finding. The generic decision plane completed the retained C2
  path and terminally abstained for the missing identifying measurement.
- Completed: authority prompt and both named Codex tasks read; branch verified
  clean at pushed commit `c407f8e`; 32 complete manual families / 514 C2
  candidate replays / 0 anchor passes frozen as the ablation baseline.
- Evidence: receipt SHA-256 `80e427ec673043ca875b226a73a832c45b587baa6547d87f0e38fbb82b7807cd`;
  B2-02X remains a separate incomplete 17-of-18-artifact work-in-progress
  screen with no complete receipt.
- Interventions used / budget: `0 / 1` new SAIL-selected families and `0 / 18`
  new C2 anchor replays; `0 / 6` separately counted synthetic measurement
  trials.
- Hypotheses retained: `flexural_rubber_contact_v1` and
  `actuator_load_path_v1`, each at posterior probability 0.5 because no result
  was opened.
- Hypotheses rejected: none; observed information gain is unavailable, not
  imputed.
- Remaining: owner decision on PR/merge. A synthetic,
  packet-bound, zero-device-I/O result lane is implemented; any physical
  measurement campaign still requires separate capture and motion authority.
- Control boundary: generic caller-authored simulator-result admission is
  disabled. One registered generic development fixture adapter independently
  derives and rereads mutation, response, likelihood, factor, and consequence
  evidence; it contains no C2/task ID whitelist and grants no C2 campaign or
  promotion authority. Persistent budgets use one ignored canonical
  campaign/config-keyed state path independent of output; the exported receipt
  verifier rejects artifact, authority, stale-state, and adapter-identity drift.
- Blockers: synchronized jaw-force and rubber-deformation/profile evidence is
  unavailable. This is the accepted terminal measurement-acquisition outcome;
  it grants no capture or robot authority.
- Final review: fresh reviewer task `019f8caa-e7bd-7201-9231-d5a2d7f7d0f2`
  returned `merge-ready; no blocking correctness findings`; six targeted tests
  passed against pushed commit `1ee6b7d`.
- Next step: finish D6 verification and final review on `main`. Do not resume B2
  or open a new C2 family; retain the sealed acquisition packet. The only
  simulator executor is the development fixture adapter, which is not a C2
  adapter or campaign authorization. The locally recomputed synthetic
  measurement lane remains separately admissible.

## Paused B2 compliant-pad evaluator win loop

Continue past B1's rigid-contact terminal negative by testing a bounded,
physically motivated segmented rubber-cap model. Each pad segment has its own
normal slide travel, stiffness, damping, and explicit modeled mass. Recorded
actions, evaluator thresholds, trace guards, and the C2 release index remain
immutable; contact-triggered command holding is disabled.

Pause snapshot: **B2-02W complete; B2-02X paused incomplete after 17 of 18
friction-release anchor artifacts, before a complete screen receipt**. The
incomplete B2-02X outputs remain diagnostic work-in-progress and are not a
completed campaign or accepted result.

Active brief:
[`docs/briefs/035-compliant-pad-evaluator-win.md`](docs/briefs/035-compliant-pad-evaluator-win.md).

Goal-loop ledger:
[`docs/autonomous-workflow/goal-loop-compliant-pad-win.md`](docs/autonomous-workflow/goal-loop-compliant-pad-win.md).

Frozen contract:
[`configs/sail/grasp_retention_normal_compliance_v1.json`](configs/sail/grasp_retention_normal_compliance_v1.json).

## Completed B1 grasp-retention resolution loop

Continue from the project-wide terminal negative and resolve the specific C2
physical-retention versus simulated-drop gap. The retained physical video,
joint position, command, and current traces now constrain the candidate family:
the real gripper remains mechanically loaded about 3.33 degrees short of its
closed command, while the simulator closes through that loaded aperture and
loses bilateral contact.

Final milestone: **B1-06 complete — 98 action-frozen candidate replays produced
zero anchor passes; simulator promotion remains closed**.

Active brief:
[`docs/briefs/034-grasp-retention-physical-trace-resolution.md`](docs/briefs/034-grasp-retention-physical-trace-resolution.md).

Goal-loop ledger:
[`docs/autonomous-workflow/goal-loop-grasp-retention-resolution.md`](docs/autonomous-workflow/goal-loop-grasp-retention-resolution.md).

Closeout:
[`docs/research/2026-07-22-c2-grasp-retention-resolution.md`](docs/research/2026-07-22-c2-grasp-retention-resolution.md).

The source action array, evaluator thresholds, trace guards, and policy remain
immutable. The loop localized the fixed-pad placement bug, reproduced the
loaded mapped joint position to within 0.03 degrees, and delayed bilateral
contact loss from source frame 323 to 399 in the best retention frontier. No
candidate also preserved transport, slip, and release retention. The exact
remaining acquisition is direct jaw force plus rubber-cap profile/deformation
under load; no robot, training, simulator-promotion, or physical authority is
opened.

## Completed post-Phase-1 application loop

Apply the completed Phase 1 system to the full retained project evidence and
determine whether it can produce evaluator-owned simulator gains or resolve
reproducible inconsistencies. The immediate diagnosis anchor is the best
C2-to-C1 pawn transport replay, whose action-frozen simulated grasp loses the
pawn before intended release.

Historical milestone: **A1-06 complete — terminal negative for bounded contact-model
promotion, with contact localization and post-first-lift observability gains**.

Active brief:
[`docs/briefs/033-sail-project-application-and-grasp-retention.md`](docs/briefs/033-sail-project-application-and-grasp-retention.md).

Goal-loop ledger:
[`docs/autonomous-workflow/goal-loop-sail-project-application.md`](docs/autonomous-workflow/goal-loop-sail-project-application.md).

All eleven retained action episodes were opened by earlier campaigns. Three
declared sentinels may guide bounded acquisition; the other eight may be run
once only after a candidate family is frozen and remain retrospective
evaluation, not fresh hold-out evidence. Existing task thresholds and trace
guards are immutable. Training, physical calibration, simulator promotion,
and robot authority stay closed unless their separately owned gates pass.

## Completed Phase 1 authority

The active program authority is
[`docs/goals/SAIL_CLAWLOOP_GRAND_MASTER_PLAN.md`](docs/goals/SAIL_CLAWLOOP_GRAND_MASTER_PLAN.md).
Complete Phase 1 milestones P1-00 through P1-17 in dependency order. Only one
milestone may be `in_progress`; its acceptance criteria, tests, receipts, run
log, and reviewer verdict must be satisfied before the next milestone begins.

Phase 1 uses no new physical observations or robot trials. Retained physical
evidence is retrospective, new causal evidence is synthetic or prospective
simulator evidence, and all ACT/GR00T data generation or policy selection stays
closed unless an evaluator-owned TwinWorthiness certificate opens the declared
capability. Source actions remain byte-identical in the action-frozen lane.

Phase 1 remains complete. Phase 2 still awaits a related workcell and
separately granted capture/motion authority; the active application loop does
not substitute for those prerequisites.

Phase 1 freeze brief:
[`docs/briefs/032-sail-publication-freeze.md`](docs/briefs/032-sail-publication-freeze.md).

Live milestone status is maintained in the master plan's Section 12 ledger and
in `docs/autonomous-workflow/project_state.json`. The research documents named
by the plan are rationale, not competing execution plans.

## Preserved historical achieved evidence

The following closed loops and achieved slices retain their original evidence
and claim boundaries. They do not override the active SAIL/ClawLoop sequence.

## Closed continuation loop: grasp coordinate descent

Status: `TERMINAL NEGATIVE FOR ONE PROMOTED COMPOSITE; BOUNDED SENSITIVITY WIN`

Run a bounded, action-frozen, one-coordinate-at-a-time simulator campaign until
the unchanged evaluator verifies either at least 6/11 lift-and-transport
outcomes or one strict task success. Source action arrays, values, ordering,
dtype, and SHA-256 remain immutable. The accepted 1.21185-degree joint RMS and
11.3437 mm EE RMS may regress by at most 1%.

Adaptive coordinate selection uses only three declared sentinel episodes. The
remaining eight episodes are run once after the composite is frozen and must
contribute at least 4/8 lift-and-transport outcomes unless a strict success
already satisfies the alternative stop lane. Already-opened confirmation data
remain regression-only.

Dense opposing-jaw contact, contact span/normal opposition, retention time,
post-grasp slip, sustained lift, transport progress, release, and task gates
guide the search. Geometry, gripper response, contact, and object-dynamics
coordinates are simulator sensitivity probes. They do not identify physical
parameters or permit simulator, training, policy, or transfer promotion.

The 2026-07-21 frozen closeout preserves identical per-recording action hashes
and verifies one trace-safe practical advancement: changing only the simulator
step from the clean-v2 setting to 2.25 ms increases lifts from 2/11 to 4/11,
while joint RMS is 1.21378 degrees and EE RMS is 11.4168 mm, both inside the
predeclared 1% limits. The 10,000-replicate paired whole-episode bootstrap has
a 95% interval of 0.000--0.455 for the lift-rate delta, so this is not a
statistically significant claim.

A bounded base-height family reaches 4/11 lifts and 2/11
lift-and-transport outcomes, but violates both trace guardrails and is not
promoted. The union across five already-frozen posterior hypotheses covers
6/11 lifts and 5/11 lift-and-transport episodes; that is sensitivity coverage,
not the performance of any one simulator. No frozen candidate reaches 6/11
lift-and-transport or one strict success.

An explicitly non-promotable measured-joint-state upper-bound replay reduces
sentinel EE RMS to 0.535 mm and closed-window gripper RMS to 0.003 degrees yet
produces only 1/3 lifts and 0/3 transports. The retained evidence therefore
cannot identify a single remaining scene/contact correction: metric vertical
registration, per-episode pawn centers, pawn properties, and the rubber jaw-tip
collision profile remain confounded. The loop is closed without simulator or
training promotion; reopening requires at least one of those missing metric
measurements or new real replay anchors.

A bounded follow-on rubber-tip campaign localized retained-grasp drops and
tested continuous sleeves, raised bands, and material/contact variants. Sliding
friction 2.0 improved mean retained grasp by 6.7% and mean final target distance
by 22.0%, but left lift/transport counts unchanged and failed the full-set EE
RMS guard. V3 therefore remains the default; the rubber result is a partial
simulator sensitivity diagnostic, not a promoted parameter or physical
calibration.

## Closed continuation loop: significant fidelity advancement

Status: `RMS STOP CONDITION SATISFIED; COMPOSITE AND TRAINING PROMOTION CLOSED`

Continue from the retained-data publication baseline until deterministic,
evaluator-owned evidence verifies at least one of these action-frozen outcomes:

- at least 5% whole-episode grouped-CV improvement beyond 1.2956 degrees joint
  RMS, with EE RMS no worse than the 12.936 mm baseline; or
- target-piece consequence improves beyond 2/11 lifts and 0/11 strict
  successes to at least 6/11 lift-and-transport outcomes or one strict success.

The same contiguous float64 source action arrays, values, ordering, and SHA-256
must be preserved. Simulator timing, actuator response, and separately declared
contact geometry may change; IK, offsets applied to actions, clipping,
corrective suffixes, and assistance remain forbidden. Grouped training-episode
CV selects mechanisms. Already-opened confirmation data are regression-only and
cannot select or promote a candidate. A lower residual or simulated reward is
diagnostic until the frozen evaluator admits the full vector.

The 2026-07-21 continuation crossed the RMS lane with byte-identical actions.
Four-fold whole-episode validation reduced pooled body-joint RMS from
1.2955577 to 1.2118497 degrees (6.461%) and EE RMS from 12.9364 to 11.3437 mm
(12.312%). A deterministic 10,000-replicate paired episode bootstrap places
the joint-RMS relative-improvement 95% interval at 4.398--8.540%, with 100%
of replicates improving and 91.62% crossing the 5% materiality threshold.
This interval is conditional on 11 episodes from one retained acquisition
session; it is not independent-session or physical-population evidence.
The already-opened two-episode confirmation moves in the same direction but
remains regression-only. The selected elbow load-bias coefficient equals the
frozen grid's -1.5 lower boundary, so its magnitude is not identified and the
grid will not be expanded post hoc.

This is not a grasp advancement: contact remains 11/11, lift regresses from
2/11 to 1/11, destination-inside endings increase from 0/11 to 2/11, and strict
success remains 0/11. The loop stops because the explicitly disjunctive RMS
criterion passed, while simulator composite promotion and training admission
remain closed.

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
- A separate non-promoting physical-source GR00T N1.7 probe now has a complete
  5,000-step checkpoint over all 18 recovered recordings. On an in-sample,
  seeded 317-step open-loop diagnostic, checkpoint 5000 improves action MSE by
  44.86% and MAE by 27.15% over checkpoint 2000 across all nine receipt-label
  instruction groups. A controlled wrong-instruction rotation further raises
  checkpoint-5000 MSE by 17.57%; correct instructions have lower MSE on 16/18
  trajectories and all nine group aggregates. These are representation and
  language-conditioned imitation diagnostics only: the rows remain unadmitted,
  five E1-to-F1 rows are outside the product move set, eleven folder/receipt
  conflicts remain preserved, and there is no held-out, closed-loop, replay,
  or physical-policy verdict.
- A simulator-gap audit now holds every recorded or retained model-produced
  action array byte-identical across simulator variants. A geometry-only board
  fit lowers train event RMS from 17.414 to 12.954 mm and already-open
  confirmation RMS from 23.549 to 15.944 mm, but leaves command-to-encoder
  end-effector tracking unchanged and produces 0/12 contacts and 0/12 task
  successes on retained GR00T action replay. This is gap attribution, not a
  policy repair, policy promotion, or physical-transfer result.
- A tracked 5.56 MB Studio publication bundle exposes the seven strongest
  retained V3 grasp replays as phone-friendly Three.js traces in a clean clone.
  It preserves source action hashes, proof labels, evaluator consequences, and
  a shared scene revision; the ranking is visual simulator diagnosis only and
  contains zero strict task successes.

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
   The later owner-directed 5,000-step physical-source probe is recorded as an
   explicit non-promoting exception: its inputs remain unadmitted and its
   in-sample diagnostic does not satisfy this evaluator gate.

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
- PASS (OFFLINE SEAM ONLY): the existing timing/control stage can now consume
  a cohort of current-schema P4/P5-eligible recordings, reject holds and weak
  excitation, freeze whole-episode train/validation/held-out groups, select
  without held-out access, and prove every replay consumed the unchanged
  gateway-sent action tensor. No current physical cohort is eligible or fit.
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
- BLOCKED PRODUCT CHALLENGER: an exploratory B--G-shaped GR00T checkpoint now
  exists, but no admitted current-scope training dataset, frozen held-out
  comparison, closed-loop consequence result, or promoted B--G checkpoint
  exists. The exploratory checkpoint cannot populate the orchestrator skill
  registry or authorize physical motion.
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
