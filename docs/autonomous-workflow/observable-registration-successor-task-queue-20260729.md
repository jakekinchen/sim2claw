# Observable Registration and Contact-Causality Successor Queue

Status: `ACTIVE_OR0_RETAINED_EVIDENCE_AUDIT`

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
| OR0 | `ACTIVE` | Freeze and inventory all admissible retained camera, pose, board, tag, 3DGS, action, and outcome evidence. | Deterministic rebuild; every source is hash-bound; fit/validation/sealed roles and unavailable channels are explicit; no hardware is opened. | Receipt, closeout, tests, source hashes, and an observability matrix. |
| OR1 | `PENDING` | Establish the best gauge-fixed C922 camera/world model supported by retained nonsealed evidence. | Intrinsic assumptions are explicit; board/static constraints fit on declared views; camera validation is untouched; robot/link residuals are reported separately. No global mapping approval from a single-plane homography. | Accepted camera model or a receipt-backed camera-identifiability boundary plus the strongest bounded projection model. |
| OR2 | `PENDING` | Reconcile robot base, articulated links, wrist, jaws, board, and support plane under the frozen camera model. | Fixed base, articulated links, jaws, board, and support each have separate fit and untouched gates. A global approval requires every mandatory channel to pass. | Versioned mapping candidate, residual report, rejection diagnoses, and approval boolean. |
| OR3 | `PENDING` | Compile an observable physical episode supplement for the sealed D1-to-D2 source. | C922 and wrist RGB timestamps are bound; jaw/pawn visibility, two-dimensional tracks, board-plane coordinates where valid, grasp/lift/release events, covariance or bounds, and missing depth/contact are explicit. Two-pass or independent validation is required for gating observations. | Deterministic visual-observation artifact compatible with `ObservableEpisode.v2-min`, plus tests and receipt. |
| OR4 | `PENDING` | Localize the earliest physical/simulator contact-and-object divergence under exact C6 actions. | Camera-projected simulator jaws/pawn and physical observations share a frozen time base; the evaluator distinguishes actuator, jaw projection, candidate contact, object motion, and outcome. Unknown physical metric depth remains unknown. | Ordered first-divergence receipt with exact sample/time bounds and causal-channel classification. |
| OR5 | `PENDING` | Prospectively declare one smallest simulator mechanism supported by OR4 and nonsealed evidence. | One mechanism family only; parameters and fit/validation/sealed splits freeze before evaluation; identifiability and regression gates are explicit. | Frozen contract or terminal `no_identifiable_mechanism` closeout. |
| OR6 | `PENDING` | Fit and validate the declared mechanism without touching C6 or held-out outcomes. | Fit improvement and untouched validation pass; camera, action bytes, actuator plant, and unrelated mechanisms remain unchanged. Reject non-identifiable or outcome-tuned candidates. | Versioned simulator candidate, parameter provenance, fit/validation residuals, and promotion decision. |
| OR7 | `PENDING` | Freeze and run one successor exact-action replay. | New experiment ID; exact C6 gateway-sent bytes and row order; frozen initialization and evaluator; no later observations; natural contact only. Report selected-jaw contact, first object motion, progress, final pose, collisions, and change versus immutable C6. | Immutable successor receipt. Material advancement requires a later first causal divergence, selected-jaw contact, or improved task gates; task success is claimed only if every frozen gate passes. |
| OR8 | `PENDING` | Publish and close the evidence chain. | Studio exposes physical/simulator camera alignment, tracks, missingness, residuals, first divergence, mechanism change, C6-versus-successor outcome, proof limits, and mobile/desktop acceptance. Focused and broad relevant tests pass; queue/graph/GOAL agree; `HEAD == origin/main`; worktree clean. | Closeout commits, screenshots or acceptance receipt, exact ledger, and next physical/service boundary if any. |

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
Current state: ACTIVE_OR0_RETAINED_EVIDENCE_AUDIT
Active card: OR0
Completed: immutable predecessor C0-C9; camera endpoint REAL-to-SIM 1/1
Evidence: C922 1029 frames; D405 RGB 171 frames; exact 531-row C6 action; accepted task plane; visual 3DGS registration
Remaining: OR0-OR8
Physical boundary: follower elbow service; hardware authority false
Next step: implement deterministic observability inventory and freeze fit/validation/sealed source roles
```
