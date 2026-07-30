# Observable Registration and Contact-Causality Successor Queue

Status: `ACTIVE_OR10_ZERO_NEW_DATA_C922_PIXEL_REFINEMENT_FROZEN`

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
| OR10 | `ACTIVE_PROTOCOL_BOUND_NO_OFFICIAL_RECEIPT` | Reconcile the prior homography-generated board lattice with actual retained C922 pixels and fit the richest identifiable zero-new-data board-plane camera challenger. | Bind two exact-mode fixed-mount fit cohorts; extract only a reviewed visible interior-board mask without simulator or task residuals; require at least `12` cross-cohort points, `≤0.75 px` agreement RMS, and `≤1.5 px` max; compare centered square-pixel zero-distortion, `k1`, and `k1+k2` families; radial complexity requires at least `5%` no-refit validation gain and no bound hit. The result remains an outcome-informed retrospective diagnostic with no exact-intrinsic, distortion, global-mapping, canonical-camera-replacement, hardware, replay, or transfer authority. | Contract and implementation are frozen for the official deterministic run. No camera was opened and no new physical data was collected. |

## Retained-data campaign closeout and acquisition continuation

The earlier retained-data fitting/replay cards are terminal. OR10 is a bounded
exception opened by the owner specifically to use already-retained image pixels
more faithfully; it does not reopen any sealed heldout or task outcome. The
campaign improved the validated
jaw-aperture projection but did not improve the exact-action task result:
aperture fit/validation RMS moved from `21.259→1.848 px` and
`24.045→3.828 px`, while the two exact-action simulator replays remain `0/2`
with zero selected-jaw contact. OR7A localizes the remaining error to a
`61.694 mm` fixed-jaw spatial gap at physical enclosure. OR7B proves that a
bounded shoulder-pan/shoulder-lift family is locally identifiable on fit poses,
but no admissible untouched validation cohort remains, so no spatial values
were fit and no successor replay was authorized.

The next admissible step is not another outcome-tuned replay. OR10 first
evaluates the actual retained board pixels under a proof-limited retrospective
protocol; after that, OR9 remains the prospective path for exact calibration
and spatial validation. OR9 freezes
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
Current state: ACTIVE_OR10_ZERO_NEW_DATA_C922_PIXEL_REFINEMENT_FROZEN
Active card: OR10
Completed: immutable predecessor C0-C9; OR0-OR9; OR7C/OR7D not run because their prerequisite failed; camera endpoint REAL-to-SIM 1/1
Evidence: OR10 binds two retained exact-mode C922 fixed-mount fit cohorts and a reviewed 14-intersection visible board mask; protocol tests pass before the official receipt
Remaining: run OR10 exactly once, close its diagnostic result, and publish its limitations
Physical boundary: follower elbow service, fresh current authority, torque-off identity/limits, and fresh CPU/fp64 route review; hardware authority false
Next step: build the deterministic OR10 receipt without opening hardware; then preserve OR9 as the exact-calibration/spatial-validation continuation
```
