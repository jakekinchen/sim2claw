# Observable Registration and Contact-Causality Successor Queue

Status: `IN_PROGRESS_OR32_SAMPLE232_BASE_YAW_PATH_GEOMETRY`

Created: `2026-07-29`

## Mission

Turn the retained physical D1-to-D2 episode and existing calibration campaigns
into a held-out-validated camera/world/robot/object registration, observable
physical pawn-and-jaw trajectory, and causal contact comparison. Use that
comparison to declare at most one evidence-supported simulator correction at a
time and evaluate a newly frozen replay without changing the immutable C6
negative.

The long-horizon target is a replay whose initial physical and simulated scene
state is explicitly bounded in every observable channel, whose camera
projections pass untouched validation, whose first physical/simulator contact
divergence is measured rather than inferred from final outcome, and whose
natural-contact result materially improves on C6. Global mapping approval and
task success are accepted only if their frozen evaluator gates pass.

## Source of truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. Immutable predecessor receipts and closeouts, especially C2, RP04N, C3A,
   C4, C5, C6, and the IMG_5349 registration.
4. This queue.
5. `configs/sail/observable_registration_current_graph_v1.json`.
6. `docs/autonomous-workflow/observable-registration-successor-goal-loop-20260729.md`.
7. Advisory model or research output, which remains non-authoritative.

## Current evidence boundary

- The C6 exact gateway-sent replay is an immutable `0/1`; it first disturbs the
  pawn at sample `386`, launches it at `388`, and forms zero selected-jaw
  contact samples.
- Robot joint response first crosses its retained threshold at sample `33`.
  The provisional end-effector comparison crosses at sample `37`, but global
  mapping is unapproved.
- The initial physical pawn XY is accepted at `3.101 mm` from D1 center. Pawn Z
  and upright orientation came from the simulator/support assumptions.
- Board/task-plane registration is accepted at `4.742 mm` RMS, but exact C922
  intrinsics/distortion and global robot/jaw/support mapping are not approved.
- RP04N proves only that the selected pawn crown is occluded for most of the
  carry. It does not establish that the C922 and wrist RGB streams lack usable
  jaw, silhouette, base, contact-event, or board evidence.
- The retained source contains `1029` C922 frames at 30 fps and `171` D405 RGB
  frames at 5 fps across the full 531-row action.
- The original successful D1-to-D2 source has no Pi IMX708 stream. Pi recordings
  exist only for later guarded executions and contact-free tri-camera runs, so
  they are independent auxiliary evidence and cannot be relabeled as a third
  view of the successful source.
- IMG_5349 supplies a board-conditioned relative-scale 3DGS registration with
  `3.759 px` held-out board-corner RMS. It is visual geometry, not metric or
  collision authority.
- Physical motion remains closed at the follower-elbow service boundary.

## Operating rules

- Exactly one card is active at a time.
- Preserve C6, RP04N, their inputs, outputs, actions, thresholds, and receipts.
- Freeze contracts, splits, annotations, evaluator behavior, and mechanism
  choice before opening the corresponding outcome.
- Fit only on declared fit observations. Do not use task outcome, sealed C6
  terminal position, or held-out observations to select parameters.
- Keep camera intrinsics, camera extrinsics, robot mapping, jaw geometry,
  contact/object dynamics, and actuator response as separately reported
  channels. A pass in one cannot silently repair another.
- Use the accepted board/task plane as the gauge. Do not let camera parameters
  absorb link/joint error or let joint offsets absorb lens distortion.
- RGB-only wrist evidence is admissible. Missing depth must remain explicit.
- Automatic tracking must emit confidence, visibility, and missingness.
  Ambiguous or occluded rows abstain; they are never interpolated into metric
  evidence without an explicit bounded model.
- No endpoint injection, object latch, observed-mode forcing, action repair,
  clipping, smoothing, retiming, IK, or terminal-state fit is allowed in an
  action-to-outcome replay.
- No camera, gateway, serial bus, torque, robot motion, physical task attempt,
  paid compute, or training is authorized by this queue.
- Commit and push scoped transitions. Preserve unrelated work and keep one
  writer.

## Critical-path queue

| Card | State | Required outcome | Acceptance gate | Evidence / stop boundary |
|---|---|---|---|---|
| OR0 | `PASS` | Freeze and inventory all admissible retained camera, pose, board, tag, 3DGS, action, and outcome evidence. | Deterministic rebuild; every source is hash-bound; fit/validation/sealed roles and unavailable channels are explicit; no hardware is opened. | Artifact `92402191296f3edcb518434a71ec35f7ea1969bccff091e94433a13790d68397`; 20 sources; 531 exact rows; 1029 C922 and 171 wrist RGB frames. |
| OR1 | `PARTIAL_ACCEPTED` | Establish the best gauge-fixed C922 camera/world model supported by retained nonsealed evidence. | Intrinsic assumptions are explicit; board/static constraints fit on declared views; camera validation is untouched; robot/link residuals are reported separately. No global mapping approval from a single-plane homography. | Artifact `f6add6ce80386e9795d2f51e65d42dfad042ebf095b3a1b325aa253c2d4baeb4`; bounded board model `2.270 px` RMS; exact intrinsics remain unidentified; prior projective camera rejected as nonphysical. |
| OR2 | `TERMINAL_NEGATIVE` | Reconcile robot base, articulated links, wrist, jaws, board, and support plane under the frozen camera model. | Fixed base, articulated links, jaws, board, and support each have separate fit and untouched gates. A global approval requires every mandatory channel to pass. | Artifact `3151318a6c58ad0d56b8b01376b29e964c1da2df0972e4c5b397ca2fcc9b4292`; rigid fit/validation `16.324 / 16.302 px` tip RMS; modeled jaw separation underpredicts observed by about `21.2 px`; global mapping remains false. |
| OR3 | `PASS` | Compile an observable physical episode supplement for the sealed D1-to-D2 source. | C922 and wrist RGB timestamps are bound; jaw/pawn visibility, two-dimensional tracks, board-plane coordinates where valid, grasp/lift/release events, covariance or bounds, and missing depth/contact are explicit. Two-pass or independent validation is required for gating observations. | Artifact `0913aee74cfc08a491a6e17184fb9ecfbf7265208dcb354801ed8010d7c059b2`; physical contact bounded to samples `228–232`, carried motion `260–390`, release `400–407`; endpoint upright at D2. |
| OR4 | `PASS` | Localize the earliest physical/simulator contact-and-object divergence under exact C6 actions. | Camera-projected simulator jaws/pawn and physical observations share a frozen time base; the evaluator distinguishes actuator, jaw projection, candidate contact, object motion, and outcome. Unknown physical metric depth remains unknown. | Artifact `e6a44d7c1791fcae8a5403b10ed6d580874bafc91d6cb4bb3d10e1f4564f1745`; physical enclosure by sample `232`, simulator selected-jaw contact absent, and first simulated pawn motion at `386`: `154` samples / `7.697 s` later. |
| OR5 | `PASS` | Prospectively declare one smallest simulator mechanism supported by OR4 and nonsealed evidence. | One mechanism family only; parameters and fit/validation/sealed splits freeze before evaluation; identifiability and regression gates are explicit. | V1 artifact `d3f784d9ee6865b5ec831ea0f4049112a1fbd5d570a31105b1d9c8ebeababd15` remains negative. V2 artifact `74845f8e2553a1a9dfd8c6ae9bf82399111d7caf865feea68d7e408936b7a902` accepts the unchanged single zero-offset family with aggregate singular value `204.972 px/rad`, rank `1`, condition `1.0`; visual validation remained unopened. |
| OR6 | `PASS` | Fit and validate the declared mechanism without touching C6 or held-out outcomes. | Fit improvement and untouched validation pass; camera, action bytes, actuator plant, and unrelated mechanisms remain unchanged. Reject non-identifiable or outcome-tuned candidates. | Artifact `a9347475ae827fc650430ce8c728a59ab16bd3bd4acc5e53b5284b7ed33c8565`; offset `0.049482 rad`; aperture RMS `21.259→1.848 px` fit and `24.045→3.828 px` no-refit validation; all gates pass; global mapping false. |
| OR7 | `TERMINAL_NEGATIVE` | Freeze and run one successor exact-action replay. | New experiment ID; exact C6 gateway-sent bytes and row order; frozen initialization and evaluator; no later observations; natural contact only. Report selected-jaw contact, first object motion, progress, final pose, collisions, and change versus immutable C6. | Artifact `600dd7973b32dd92cc4612762f44f80843572ea51457beb4a92380e554c4baeb`; exact pawn trace remains C6: zero jaw contact, motion `386`, launch `388`, final D2 error `69.148 mm`. Aperture alone is rejected as the sufficient task mechanism. |
| OR7A | `PASS` | Localize the signed jaw-to-pawn geometric gap over physical enclosure samples `228–260`. | Kinematic forward evaluation only; exact applied states and initial pawn; named collision geoms; C6 and OR6 mappings compared without fit or dynamics. | Artifact `f9d384dbde3e6a4df2c58304a7b75e2d9c4a6a77df1a2b06f8060563ca70a4c6`; minimum fixed-jaw gap `57.204 mm`; at physical enclosure sample `232`, gap `61.694 mm` and candidate midpoint-to-pawn vector `[+72.970,-24.138,-93.272] mm`; aperture mapping changes fixed-jaw gap by `0 mm`. |
| OR7B | `TERMINAL_NEGATIVE` | Declare one task-bounded jaw-center/global wrist spatial mechanism, if OR7A and nonsealed static evidence identify it. | One mechanism; fit data and a fresh retained validation image cohort freeze before annotation/open; contact/task outcome excluded. | Artifact `dcb88a286a2a8709fa829903df6167950f785869805fd438470fc3dabcf1586d`; pan/lift zero-offset family is fit-identifiable at rank `2`, condition `1.428`, singular values `[842.700,589.932] px/rad`, but admissible untouched validation is `0/4`; no parameters fit and no images opened. |
| OR7C | `NOT_RUN_PREREQUISITE_FAILED` | Fit and no-refit validate the spatial mechanism. | Static fit and newly opened validation pass; aperture remains fixed; camera, action, plant, contact, and object remain unchanged. | OR7B has no admissible untouched validation cohort; fitting is prohibited. |
| OR7D | `NOT_RUN_PREREQUISITE_FAILED` | Run another exact-action replay only if OR7C passes prospectively frozen static gates. | New write-once experiment; exact C6 identity; one declared spatial change on top of OR6; natural contact only. | OR7C did not run; no spatial candidate or replay authority exists. |
| OR8 | `PASS` | Publish and close the evidence chain. | Studio exposes physical/simulator camera alignment, tracks, missingness, residuals, first divergence, mechanism change, C6-versus-successor outcome, proof limits, and mobile/desktop acceptance. Focused and broad relevant tests pass; queue/graph/GOAL agree; `HEAD == origin/main`; worktree clean. | Closeout SHA `815384a834061bc9ee2387537a6e72c5e1a573f48a50f4ce95b6931b8527fff5`; publication receipt artifact `22e1b8102bf3f629a2a6c0b1b030910493fe34604d521ea4e64121506e858657`; supplement artifact `59215118ae4c6c2829d852c6e26db4099e8aaa9ef7f56befaec559e2c4d602ce`; desktop and `390×844` mobile acceptance pass; `51` broad tests pass. |
| OR9 | `PASS_DESIGN_READY_BLOCKED_EXTERNAL_INPUTS` | Freeze the exact post-service four-pose validation acquisition seam without opening hardware. | Four fresh validation-only joint targets are prospectively fixed inside the modeled visibility envelope; pan span is at least `10°`, lift span at least `3°`; both distal jaw endpoints and board lattice are required; D405 depth is optional; prior images, annotations, outcomes, and action arrays are excluded. The readiness evaluator must pass design gates and fail closed before route/action compilation on service, authority, fresh torque-off limits, and a fresh CPU/fp64 route review. | Closeout SHA `dd1757e9a93ff69c15ed05ae64657230cfa7ed1fe183ce44e0f75a217c011987`; artifact `da04d93eda4313d8be121e0299b1e887b13cd27f10e76f6c58efbf60f73003b1`; `16/16` design gates pass; four targets span `20°` pan and `3°` lift; actions/images/motion/attempts remain zero; `54` broad tests pass. |
| OR10 | `PASS_BOARD_PLANE_DIAGNOSTIC_EXACT_INTRINSICS_UNIDENTIFIED` | Reconcile the prior homography-generated board lattice with actual retained C922 pixels and fit the richest identifiable zero-new-data board-plane camera challenger. | Bind two exact-mode fixed-mount fit cohorts; extract only a reviewed visible interior-board mask without simulator or task residuals; require at least `12` cross-cohort points, `≤0.75 px` agreement RMS, and `≤1.5 px` max; compare centered square-pixel zero-distortion, `k1`, and `k1+k2` families; radial complexity requires at least `5%` no-refit validation gain and no bound hit. The result remains an outcome-informed retrospective diagnostic with no exact-intrinsic, distortion, global-mapping, canonical-camera-replacement, hardware, replay, or transfer authority. | Artifact `520998b716b2d5f42123f21502c37b145ba398f1f3238aa524da5dd9ef0eda13`; `14` points agree across cohorts at `0.366 px` RMS / `1.145 px` max; prior model scores `4.214 px` RMS on those pixels versus `0.973 px` cross-cohort for the selected zero-distortion challenger, a `76.905%` reduction. Pooled focal is `736.802 px` / vertical FOV `36.084°`. `k1` has no gain; `k1+k2` gains only `0.279%` and hits the `k2` bound. Exact intrinsics, distortion, global mapping, and canonical replacement remain false. |
| OR10B | `TERMINAL_DISAGREEMENT_ZERO_DATA_LANE_CLOSED` | Run the final zero-new-data camera successor: a focal/lens-family corroboration against retained hackathon-era C922 videos from a different workspace, mount, and camera angle. | Use only the 14 frozen historical train videos not opened for this advisory, preserve all three historical held-outs, apply the frozen OR10 saddle protocol without mask iteration, require at least `12` intersections, `≤0.75 px` cross-episode dispersion, at least `2×` OR10 radial-span coverage, and focal agreement within `3%`. One run closes the zero-new-data camera lane. | Artifact `5cf7db1d5d7633ceec66885ecaa94f5e92db754cb77785c53c4c5a00f28df145`; `30` intersections pass at `0.632 px` mean / `0.741 px` max cross-episode dispersion and `2.376×` OR10 radial span. Historical focal is `623.252 px` at `0.432 px` RMS with all 14 episode fits spanning `620.128–625.962 px`; OR10 is `736.802 px`, a `15.411%` disagreement that fails the frozen `3%` gate. Historical camera-unit identity and focus/FOV state are unresolved; no exact intrinsic, distortion, current-extrinsic, mapping, camera-replacement, replay, or transfer claim is promoted. |
| OR11 | `TERMINAL_NEGATIVE_BLOCKED_EXTERNAL_METRIC_ANCHOR` | Build the proof-safe named-geometry contact-phase successor and the independent metric board-to-base acquisition seam. | Preserve the exact C6 action/timestamp/initialization identities. Task samples `224` and `228–232` are evaluation-only and cannot enter a fit loss. Resolve exact jaw-pad and pawn geoms; reproduce the exact internal applied-state schedule; use `mj_forward`/`mj_geomDistance` without integration for the phase gate; require no precontact through `224` and phase-correct named-pad contact during `228–232` before any new dynamics. Fit at most one independently declared mechanism on non-contact static evidence with rank, conditioning, bound-margin, no-refit validation, and leave-one-pose-out gates. If current retained evidence is insufficient, emit a deterministic external-input receipt for `robot_base_to_board_metric_anchor_v1`; do not fabricate a correction or open hardware. | Factor isolation artifact `c186e444a9444e6371d600274e87bc765efaa30d82bdb7e5a384b2169764d391` is `CONFOUNDED_NO_PROMOTION`. Exact 5 ms kinematic evaluation emits 5,294 applied-state rows and zero integration steps; at physical enclosure sample `232`, named fixed/moving jaw gaps are `61.693 / 97.374 mm`, the pawn is not bracketed, and no named contact exists. Contact-phase artifact `b1c3b834c0acbbf581001849d311bf9eca4853b1dd306bf83b39be6f3d52a1be`; dynamic replays `0`. Metric-anchor readiness artifact `a7f0986d75da40a0400f727615589cd33ae1a8683af4079574d66311f12b34a3`; measurement rows `0`, candidate transforms `0`, task attempts `0`. |
| OR12 | `PASS_TRANSLATION_CANDIDATE_MATERIAL_GAP_REDUCTION_NO_CONTACT` | Bind the owner's post-hackathon home-workspace board and follower-base measurements, verify the SO-101 base STL identity, fit one translation-only board-to-left-base candidate with explicit uncertainty, and evaluate it under the exact OR11 named-geometry contact-phase schedule. | Preserve the baseline scene, camera, yaw, joint mapping, actions, timestamps, row order, contact/object parameters, and every predecessor receipt. Treat `15.5 in` as the primary outside board side, preserve the existing measured playing surface, derive frame width, and bind the approximate `38.75 cm` orthogonal side as a consistency diagnostic. Use the owner-reported `16.6 cm` front clearance and `12.25 / 15.5–15.6 cm` side gaps only through named STL outline extrema with declared uncertainty. Base dimension measurements validate STL identity and cannot rescale it. Fit only planar translation; yaw remains frozen and unapproved. Samples `224` and `228–232` remain evaluation-only and cannot update the candidate. | Artifact `c4fee2fa113aaecce400b596ae37f0bcb334823307e2a5f27a63f712cc7be685`. The four owner base dimensions match the exact 4,577-vertex STL within `1.001 mm`, so scale remains unchanged. The candidate moves the base `+50.370 / -2.922 mm` in table XY with `2.695 mm` maximum standard uncertainty. At sample `232`, fixed-jaw gap falls `61.693→26.580 mm`; minimum phase gap is `19.665 mm`; midpoint-to-pawn planar error falls `76.858→27.049 mm`. Vertical residual remains `-85.272 mm`; no named contact exists and dynamic replays remain `0`. Yaw, base height, global mapping, canonical replacement, and transfer remain unapproved. |
| OR13 | `PASS_STATIC_GEOMETRY_AND_CAMERA_CENTER_CANDIDATE_NO_CONTACT` | Bind the owner's measured `34 mm` pawn, `40–41 mm` squares, approximate `30 mm` board border, and post-hackathon Logitech camera height/ranges as a staged static successor. Reconcile board/object geometry before fitting any camera orientation, then compile one explicit derived simulator candidate. | Preserve OR12 base translation, board center/yaw, pawn horizontal profile, exact actions, contact/object dynamics, and all predecessor receipts. Use `40.5 mm` as the bounded square midpoint, preserve the exact `393.7 mm` outside board, and derive the frame. Scale detailed pawns vertically only. Triangulate camera center from `305 mm` desk height and `430/565 mm` front-corner rays; use the independent `320 mm` planar offset only as a consistency check. Only after those values freeze, fit focal plus orientation to OR10's already-reviewed nonheldout intersections with the center fixed. No dynamics, camera open, heldout, or promotion. | Artifact `91a7c68e743d13532ecb7a796b53970f3b877efc917ce15b86db8b9db15e2474`. Candidate geometry is `40.5 mm` squares, `324 mm` playing side, `34.85 mm` frame, and compiled `34 mm` pawn. Camera rays imply `324.422 mm` planar distance, `4.422 mm` from the separate `320 mm` estimate, with center `[−170.593,+324.422] mm` about the outside-board center and `305 mm` above the desk. The compiled camera position is exact; retrospective orientation validation is `6.857 px` RMS with focal `363.333 px`, but exact intrinsics and heldout approval remain false. The shorter measured pawn increases sample-232 fixed-jaw gap `26.580→45.473 mm`; this is an honest geometric correction, not a contact optimization. Named contact and dynamics remain zero; base height/global mapping remain unapproved. |
| OR14 | `TERMINAL_NEGATIVE_CAMERA_COHORT_MISMATCH_LOCALIZED` | Recalculate the geometry-dependent belief graph under OR13 and rank one bounded robot-side static mechanism from retained non-contact jaw-endpoint observations. | Preregister base-height residual, shoulder pan/lift offsets, wrist flex/roll offsets, and local tool-height families before evaluating them. Freeze the OR13 camera and geometry; fit only six static poses; score four known-outcome validation poses without refit; require full-rank conditioning, bound margin, orthogonal jaw-separation protection, and leave-one-fit-pose-out stability. The clamp/support stack bounds base height to `±4 mm`. No task row, contact timing, or outcome may enter fitting. | Artifact `27a31536e0535c9e82ada67bee2af3397f9490e7cc7de8fd0af9c8a92f8340cf`; OR13-camera jaw midpoint baseline is `103.116 / 99.904 px` fit/validation and every family hits a bound or misses improvement gates. Base mesh is `2.400 mm` below the modeled clamp top, rejecting a large base-height shift. OR13 lacks camera-mount binding to retained pixels, so this localizes a cross-session camera mismatch rather than proving a robot error. |
| OR15 | `TERMINAL_NEGATIVE_NO_PHASE_CORRECT_NAMED_CONTACT` | Quarantine the current OR13 camera from retained replay calibration, compose OR13 board/pawn/base geometry with the same-session OR10 camera and the already-frozen OR11 shoulder candidate, then run one exact kinematic contact-phase gate. | Camera and joint values are frozen before the task window opens; no refit, task row, outcome, dynamics, integration, or action change. Report no-refit static pixel metrics and require no precontact through `224` plus named jaw/pawn contact during `228–232` before any dynamics. | Artifact `d4ffb2c9e8cdf8042935f2a7c405b97b696baac5d34dcdd132b07f11e7b41db8`; same-camera midpoint improves `19.45% / 23.67%`, planar task-phase error falls `27.049→12.439 mm`, but vertical residual worsens `−85.272→−101.401 mm`; no named contact and no dynamics. |
| OR16 | `TERMINAL_NEGATIVE_NO_PHASE_CORRECT_NAMED_CONTACT` | Re-evaluate the already-existing clean-room historical body-joint mapping candidate under OR13 static geometry as a quarantined outcome-informed diagnostic. | Freeze the exact five historical offsets, including `+18.701°` shoulder lift, before opening the task phase. No new fit, action change, integration, dynamics, promotion, or transfer claim. Require no precontact through `224` and named contact during `228–232`. | Artifact `66dbfedec16a8e614ef994751e5f813fe7bc1002d71dddd87b815c54b25f4d80`; sample-232 fixed-jaw gap falls `61.838→3.194 mm` and vertical body-origin residual falls `−101.401→−20.243 mm`, but the pawn is not bracketed and no named contact occurs. |
| OR17 | `TERMINAL_NEGATIVE_GAUGE_NO_EFFECT` | Apply the historical board-yaw candidate through the canonical-rank hardcutover migration without refitting it. | Subtract the frozen `180°` rank-frame change exactly; preserve task initialization, joint mapping, actions, and all static geometry; no dynamics or promotion. | Artifact `a2ba9d44c9bfcda2a22c2b29ea0af123262d4ed054fd494ec68eb0eea362ef6d`; changing nominal board yaw has byte-identical contact metrics because the retained pawn is initialized directly in world XY. This is an informative gauge negative. |
| OR18 | `PASS_QUARANTINED_UNILATERAL_NAMED_CONTACT_NO_DYNAMICS` | Correct the task mismatch between a push and the inherited bilateral-grasp evaluator, then test one explicitly outcome-informed robot-yaw candidate with the historical body mapping and canonical gripper baseline. | Require no intended jaw contact through sample `224` and a named unilateral jaw contact during `228–232`. Board support is reported but is not misclassified as jaw contact. No action change, integration, dynamics, global mapping, or transfer claim. | Artifact `36057bb69f0da745418c4d61b44d6ff76480539aa806fe36de779d715bf9f37e`; precontact minimum clearance `6.475 mm`; first exact moving-jaw/pawn contact at sample `231`; actions unchanged; zero integration steps. Candidate selection used task rows and is permanently quarantined. |
| OR19 | `PASS_QUARANTINED_EXACT_ACTION_CONTACT_AND_PROGRESS` | Run one exact-action dynamic diagnostic after repairing the canonical rank-1-near reset-layout composition. | Use the exact 531-row C6 requested/sent/timestamp/applied tensors, the OR18 scene, frozen historical mapping/ranges, canonical gripper baseline, natural contact only, and the C6 task gates. The selected pawn must have no initial non-board overlap. Report contact, motion, progress, outcome, and collateral displacement. | Artifact `f33198841ce3e70a11dfc7f2e617174248e436bd18474b3bb626700b6674e184`; canonical reset has zero initial non-board contacts; named jaw contact begins at `231`; pawn motion begins at `248`; signed D2 progress is `47.513 mm`, passing the `36.025 mm` gate; final D2 error is `9.945 mm`. Full task fails because tilt is `102.106°`, height error `14.539 mm`, and collateral displacement `11.451 mm`. Exact actions and order are unchanged. |
| OR20 | `PASS_LOCALIZED_OBJECT_CONSEQUENCE_BLOCKED_IDENTIFIABILITY` | Localize the first residual after phase-correct contact without another parameter search. | Bind OR19 trace, retained physical event windows, the existing contact-identifiability negative, and the mechanism registry. Report first simulator planar/vertical consequence and physical lift/carry timing. No parameter fit or simulator mutation. | Artifact `4374827196aae08617b9899387cbdd31e5bfcd625e773efadbf95229ac908668`; simulator planar and vertical motion both cross `1 mm` at sample `248`, one sample after the physical candidate-lift window starts and 12 samples before definite physical carry. The remaining channel is object orientation/contact consequence, but retained evidence lacks metric orientation trajectory and known contact force required to identify contact height, mass/COM, friction, or compliance. |
| OR21 | `PASS_EXACT_REPRODUCTION_CONTACT_TRACE` | Reproduce OR19 with model-identical, byte-identical actions while emitting internal contact-causality traces. | Freeze the exact OR19 model/config/action/timestamp/initialization identities. At the 5 ms internal step, emit pawn orientation/angular velocity/support state, named unilateral and bilateral contacts, contact position/normal/wrench where available, jaw/pawn relative velocity, and slip. The OR19 selected-contact, motion, progress, exclusion, collision, and outcome fields must reproduce exactly within frozen deterministic tolerances. No parameter selection, camera fit, or simulator mutation. | Artifact `18d9ba676efa53d3c845972bcd8dd4e26aecf9fe06e6ab80f9e5167f272a09fc`; OR19 reproduces exactly. Unilateral contact and slip begin at sample `231`, tilt exceeds `5°` at `248`, bilateral contact begins at `255`, and sustained support loss begins at `260`. The residual is localized to unilateral contact/slip before bilateral enclosure; no physical force or parameter is identified. |
| OR22A | `PASS_METHOD_VALIDATION_TARGET_APPLICATIONS_FAIL_CLOSED` | Intake the later Pi IMX708 streams and associate frames with action intervals using only robot-motion timing cues. | Hash-bind each Pi browser video, raw timing sidecar, capture receipt, execution receipt, and joint-sample trace. Estimate one run-specific constant offset only; never infer exposure synchronization from host capture bounds. Freeze motion features, lag grid, acceptance thresholds, and validation splits before task consequence frames are opened. Fit on contact-free or setup/precontact motion only; require at least three independent motion/hold transitions, a unique peak with at least `20%` margin, leave-one-transition-out lag span no more than two Pi frames, and accepted association intervals no wider than `100 ms`. Otherwise return `PI_ACTION_ASSOCIATION_INSUFFICIENT`. | Artifact `befe9ba7e81da015403726486428216707e458c853129f3f0c8cc4c993329310`; method gate passes on `3/4` contact-free runs with `33.318–43.319 ms` association widths. D1 exact-v4 has sharp Pi/C922 visual lag `0.965 s`, `r=0.887833`, but fails the frozen joint corroboration gate at `120 ms`; C2 exact-v1 has only one outcome-excluded setup transition. Both guarded-run associations fail closed. |
| OR22 | `PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT` | Extract retained RGB proxies for the object-orientation/contact-consequence residual without manufacturing metric depth. | Use C922 and D405 RGB from the successful source as the primary episode. Use accepted Pi associations only for same-run precontact robot geometry, motion timing, and later-run failure context. Every track carries source episode, interval uncertainty, confidence, visibility, and abstention. No cross-episode frame merge, metric depth restoration, contact-force inference, or task-result use in alignment. | Artifact `22ac866bd98258801c3965c4f6b1d37251ab60ff08dc8c63a7e60dbd314210c7`; 23 jaw proxies and 10 crown proxies. Sim contact `231` lies inside physical `228–232`, sim tilt `248` lies inside physical lift `247–260`, and sim support loss `260` equals physical carry start `260`. Pawn-axis orientation abstains because accepted pawn-base rows are `0`. |
| OR23 | `MECHANISM_NOT_IDENTIFIABLE` | Freeze one mechanism discriminator from OR21 simulator traces and OR22 retained visual proxies. | Evaluate only samples `210–300`; exclude terminal task outcome from selection. The discriminator must distinguish one predeclared channel such as off-center contact moment, jaw/pawn slip, support transition, or downstream collision. Select exactly one branch or return `MECHANISM_NOT_IDENTIFIABLE`. | Artifact `0e8dbd6dffa341a7f6cd26745c8a2ed93835a31bca654166dded4ec0cd1c38f0`. Contact, lift, and carry-start timing correspond, but none of the four branches has its required physical discriminator. No branch, fit, correction, or replay is admitted. |
| OR24 | `NOT_RUN_PREREQUISITE_FAILED` | Admit at most one independently constrained mechanism correction. | The chosen family must have an independent retained measurement or public component property, explicit uncertainty, bound margin, and an untouched no-refit check. Contact height, mass/COM, friction, and compliance remain prohibited when the required independent witness is absent. | OR23 selected no branch. The retained episode lacks a metric contact point, physical pawn-orientation path, resolved slip, support-contact state, and named pre-divergence collision witness; fitting is prohibited. |
| OR25 | `NOT_RUN_PREREQUISITE_FAILED` | Run one prospective exact-action replay only if OR24 passes. | Freeze a new experiment ID before execution; preserve the exact OR19 action tensor, row order, timing, scene initialization, and all unrelated mechanisms. Require natural named contact, progress at least `36.025 mm`, no exclusion/collision regression, and improved upright/height/collateral consequence on the untouched evaluator. | OR24 did not run, so no prospective correction or replay authority exists. Prior replay receipts remain immutable. |
| OR26 | `PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO` | Render the retained physical C922 episode and the exact OR21 physics trace on one synchronized 20 Hz timeline, then localize the first visible divergence by channel. | Bind the original 531-row timestamps, C922 action-start offset, OR21 internal trace, OR13 scene, and OR10 retained-pixel camera. Rescale the OR10 board-frame pose to the measured 324 mm playing surface, apply one frozen board-plane display homography, and render trace playback without rerunning or changing physics. Report frame-0 board geometry, robot motion-energy, pawn motion/orientation, missing source frames, and first thresholded divergence independently. Produce a browser-playable side-by-side MP4 and machine-readable curves. | Artifact `47e7822a48731364aaf2e1cd8b0c697e20b55064db731587e51f7f63c83afe36`; registered initial and terminal pawn endpoint errors are `10.774 px` and `12.584 px`. The material split is bounded to samples `248–260` (`12.402–13.002 s`): the simulator pawn tips and loses support while the physical source carries it upright. |
| OR27 | `PASS_HASH_VERIFIED_RESPONSIVE_STUDIO_PUBLICATION` | Publish OR26 as a read-only synchronized Studio surface for desktop and mobile inspection. | Serve only the hash-verified OR26 receipt, physical lane, simulator lane, poster, and comparison video. Provide one shared playhead, play/pause, stepping, speed, causal-event markers, and an explicit jump to the `248–260` divergence interval. Preserve independent source labels and make unavailable or hash-mismatched evidence fail closed. | `/visible-divergence.html` passed desktop and `390×844` browser inspection. The separately rendered lanes share playback, scrub, step, speed, and divergence-jump controls; all source media is hash-verified before publication. |
| OR28 | `UPRIGHT_CONSEQUENCE_PASS_PROGRESS_GATE_FAILED` | Test the smallest prior-evidence composition that could close the `232` physical enclosure versus `255` simulated bilateral-contact gap. | Keep the OR18 `6°` spatial/yaw candidate and exact OR19 action/model/timing/reset. Replace only OR19's canonical gripper baseline with the independently fit OR6 aperture offset `0.04948239306868429 rad`. Run exactly once with no contact/object parameter change. Require natural contact, preserve the `36.025 mm` progress gate, and report first bilateral contact, tilt/support consequence, height, collateral, and endpoint outcome. | Artifact `61f600b79fbf36413a124d9b2df73073c2bd493f8320f5a1b6e372ae772e2bad`. Tilt improves from `102.106°` to `0.000696°` and collateral becomes negligible, but first contact moves to `244` and D2 progress falls to `2.660 mm`; the progress gate fails. |
| OR29 | `NO_STATIC_BILATERAL_CANDIDATE` | Derive at most one aperture successor from the retained physical definite-enclosure event without reading another dynamic outcome. | Evaluate a frozen 17-value grid bounded by the OR19 baseline and OR6 independently fit offset. At exact applied states `220–245`, use forward kinematics and separate fixed/moving-jaw signed gaps to the selected pawn. Require no precontact penetration above `1 mm` and both jaw gaps within `±1 mm` at physical enclosure sample `232`; select by minimum maximum absolute jaw gap. No physics integration. | Artifact `52772ef1d4548be0a057ecdffdacd625e0d542286bcb5a8f5807279117485f65`; no eligible row. At the closest candidate the moving jaw gap is `-0.021 mm` while the fixed jaw remains `13.995 mm` away, ruling out aperture-only correction. |
| OR30 | `NO_STATIC_BASE_XY_APERTURE_CANDIDATE` | Test whether a bounded whole-base XY correction plus aperture can reproduce the retained sample-232 enclosure geometry. | Evaluate the exact OR29 aperture grid crossed with a frozen `[-20,+20] mm` world-XY base grid at `5 mm` spacing. Require no precontact penetration above `1 mm` and both jaw gaps within `±1 mm` at sample `232`. Select without dynamics by gap score, translation norm, then absolute aperture offset. | Artifact `887dc1e98816d6fdc1fba57595f4fe32c695bf0c95e590331545dd21f38045e1`; no row passes. The local basin is a `[-10,-10] mm` base shift: fixed gap `2.663 mm`, moving gap `0.645 mm` at an intermediate aperture, and precontact penetration `0.810 mm`. |
| OR31 | `NO_STATIC_REFINED_ENCLOSURE_CANDIDATE` | Refine the single OR30 local basin once before deciding whether a dynamic successor exists. | Freeze world-X and world-Y deltas from `-15` to `-5 mm` at `1 mm` spacing and aperture offsets from `-0.160529` to `-0.132529 rad` at `0.002 rad` spacing. Preserve the OR30 sample-232 bilateral and precontact gates and outcome-blind selection order. | The closest snapshot passes bilateral gaps (`0.861/0.967 mm`) but penetrates `3.091 mm` before contact; no candidate is admitted. XY/aperture alone cannot match both approach and enclosure. |
| OR32 | `ACTIVE_PROSPECTIVELY_FROZEN_PENDING_STATIC_RUN` | Test the remaining path-shape mechanism: bounded base yaw around the OR31 local basin. | Cross a `5×5` local XY grid, seven yaw deltas from `-6°` to `+6°`, and seven local aperture offsets. Preserve the same sample-232 bilateral and samples-220–227 precontact gates. Select without dynamics. | This is outcome-informed, quarantined, and cannot promote mapping. A dynamic replay is allowed only if both static gates pass prospectively. |

## Pi IMX708 auxiliary evidence and timing contract

The Pi evidence is divided by execution lineage. It must never be merged across
episodes merely because the robot followed related actions.

- The original successful physical D1-to-D2 source
  `datasets/manipulation_source_recordings/d1-to-d2__20260727T041737Z-89190e53`
  has C922 and D405 RGB only. Its `531` rows run at nominal `20 Hz`.
- The later D1-to-D2 exact-v4 guarded execution has a `1536×864`, nominal
  `30 fps`, `1040`-frame Pi browser video at
  `runs/prospective-real-to-sim/20260727-d1-d2-exact-v4/stage-1/final_hold_camera/pi_motion/pi_imx708.browser.mp4`,
  SHA-256 `ca1505972f2b2830ca16c02e163604fb48d85abb32906560ef3f4e6db6482d0b`.
  Its PTS sidecar SHA-256 is
  `c1614af7e99c557c50ef32dc1caa97ebc0d70dfcb9e6bfb0ab2644b2226e1d71`;
  execution receipt SHA-256 is
  `5f840da4d097a9f3fe7777140261955d513121945e6599a397142f88e50da21f`;
  joint samples SHA-256 is
  `2d09b20421ced3bcb4fb0ccce00f3eda3c24a5fd49452c498178a6cda8bd8ace`.
  That attempt stopped before pawn contact after `80` excluded setup rows and
  `609` counted task rows because of elbow tracking. Its resampled `40 Hz`
  actions are not byte-identical to the original `531`-row source.
- The later C2-to-C1 exact-v1 guarded execution has a `1536×864`, nominal
  `30 fps`, `1040`-frame Pi browser video with SHA-256
  `e40a7d78b7f7ca1fa9f5713e64bff78fb1f2144c0903aa467ea8b5459c1c80b0`.
  Its PTS sidecar SHA-256 is
  `c12a9b69595ece50dbe11b842ff199bceb256ba3966f15df32b61296ab11dd37`;
  execution receipt SHA-256 is
  `48a5642c131a3958f371dd3c6d81526b90f435b0d13d7283e196720d0f4cf14b`;
  joint samples SHA-256 is
  `9c8b9c146c67c2cc339506690a28df0e7fb63f5ffa81f4372fd58411182bfa97`.
  Its pawn displacement/topple is retained only as a negative consequence
  witness.
- Contact-free tri-camera runs under `runs/geometric-microtransfer/` are the
  development and no-refit validation source for the timing-association method.
  Task contact and task outcome are excluded from offset fitting.

`rpicam-vid --save-pts` supplies Pi-relative PTS. Existing capture receipts
provide host monotonic process bounds only and explicitly do not prove camera
exposure or cross-camera synchronization. Therefore
`host_monotonic_start + pi_pts` is not an exposure timestamp. OR22A will
normalize Pi PTS, compare predeclared robot/link image-motion energy against
host-timestamped joint-velocity energy and same-run C922 whole-arm motion, fit
one constant lag per run, and publish an interval-valued frame/action
association with uncertainty. Drift, scale, task-contact, and outcome fitting
are excluded in v1.

## Retained-data campaign closeout and causal continuation

The earlier retained-data fitting/replay cards through OR20 are immutable.
OR21 opens a model-identical introspection lane, and OR22A opens a separately
lineaged Pi timing lane. Neither reopens parameter fitting or promotion.
OR10 and OR10B are
bounded exceptions opened by the owner specifically to use already-retained
image pixels more faithfully; they do not reopen any sealed heldout or task
outcome. The
campaign improved the validated
jaw-aperture projection but did not improve the exact-action task result:
aperture fit/validation RMS moved from `21.259→1.848 px` and
`24.045→3.828 px`, while the two exact-action simulator replays remain `0/2`
with zero selected-jaw contact. OR7A localizes the remaining error to a
`61.694 mm` fixed-jaw spatial gap at physical enclosure. OR7B proves that a
bounded shoulder-pan/shoulder-lift family is locally identifiable on fit poses,
but no admissible untouched validation cohort remains, so no spatial values
were fit and no successor replay was authorized.

The next admissible step is not another outcome-tuned replay. OR10 has
evaluated the actual retained board pixels under a proof-limited retrospective
protocol and publishes the resulting inspection camera in Studio. OR10B is the
single final retained-data focal-family corroboration: it uses a different
hackathon-era workspace, mount, and camera angle, so it cannot validate current
extrinsics or camera center. OR10B exhausted that lane with a well-supported
negative: historical pixels were plentiful and repeatable, but their focal
estimate disagreed with OR10 by `15.411%`. The result cannot identify whether
the cause is camera-unit identity, autofocus or digital FOV state, workspace
mount state, seed bias, principal point, or lens-model error. OR9 remains
the prospective path for exact calibration and spatial validation. OR9 freezes
the four new no-contact C922 static targets and the fail-closed requirements
that must precede route compilation. It does not reuse prior action arrays or
grant authority. Until post-service inputs exist and a versioned successor
passes a fresh route review, global mapping, metric wrist depth, matching
action-to-task transfer, and physical transfer remain unapproved.

## Milestone invariants

### M1 — Retained evidence is queryable

Every source needed to reproduce the visual and causal comparison is immutable,
hash-bound, role-labeled, and locally available. This is invariant because no
later calibration or replay claim is auditable without it.

### M2 — Camera and geometry errors are separated

Camera/world projection error, robot articulation error, jaw geometry error,
support-plane error, and object observation error each have their own residual
and held-out gate. This is invariant because a joint optimizer can otherwise
hide the actual sim-to-real gap.

### M3 — Physical contact consequence is observable

The retained physical episode exposes a time-bounded jaw/pawn/contact-event
trace with visible uncertainty and abstention. This is invariant because final
endpoint agreement cannot identify the mechanism that produced it.

### M4 — One causal mechanism is tested prospectively

The selected simulator change is justified by earlier residuals and validated
away from the sealed outcome. This is invariant because repeated C6 tuning
would be outcome fitting.

### M5 — The successor result is immutable and legible

The new replay either advances a frozen metric or establishes a more precise
remaining boundary. Studio and repository receipts show exactly what changed
and what did not.

## Completion condition

The preferred successful stop is:

- a held-out-valid camera/world model;
- globally approved task-bounded physical/model mapping;
- a validated observable physical pawn/jaw/contact-event episode;
- a measured first contact/object divergence;
- one evidence-supported simulator correction;
- and a newly frozen exact-action replay with natural selected-pawn jaw contact
  and a materially improved task consequence.

If the retained evidence cannot support a mandatory component, exhaust safe
alternatives that do not reuse sealed outcomes. A blocked stop is allowed only
after the same genuine external/safety boundary persists for three goal turns
and no remaining safe card can advance any accepted metric. A narrower camera
model, visible-contact timeline, or later first-divergence bound is progress
and must be completed before invoking that boundary.

## Progress ledger

```text
Current state: IN_PROGRESS_OR32_SAMPLE232_BASE_YAW_PATH_GEOMETRY
Active card: OR32; static yaw/path-shape grid frozen
Completed: immutable predecessor C0-C9; OR0-OR23 and OR26-OR31; OR7C/OR7D and OR24/OR25 not run because their prerequisites failed; camera endpoint REAL-to-SIM 1/1
Evidence: OR31 can match the enclosure snapshot but only with 3.091 mm precontact penetration. XY translation plus aperture cannot match the physical approach and enclosure simultaneously.
Pi intake: the original successful source has no Pi view. OR22A validates the motion-curve method on 3/4 contact-free runs, but both guarded-run target applications fail their frozen gates and remain unsynchronized context only.
Aligned and mapped: exact OR19 action/model reproduction and the contact/lift/carry-start event timeline are accepted; each candidate consequence mechanism and its missing physical discriminator is explicit in OR23.
Remaining: full matching task outcome, exact intrinsics, pristine heldout extrinsics, globally approved mapping, and physical pawn/contact mechanics remain unapproved. No retained-data correction can be identified without outcome tuning.
External boundary: hardware authority remains false; the retained four-pose validation is outcome-known and cannot promote a global mapping
Next step: evaluate the frozen base-yaw path-shape grid; dynamically replay only if both precontact separation and bilateral enclosure pass
```
