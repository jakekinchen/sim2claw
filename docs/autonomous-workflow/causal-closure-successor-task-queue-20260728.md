# Causal-Closure Successor Task Queue

Status: `ACTIVE_CC01_OBSERVABLE_EPISODE_MINIMUM`

Created: `2026-07-28`

Checkout: `/Users/kelly/Developer/sim2claw`

Branch: `codex/bidirectional-transfer-goal-loop-20260728`

## Mission

Use the accepted canonical task-plane registration and a defect-free,
current-anchor-seeded action set to close one complete causal task-transfer
chain:

> exact action -> measured joint/link response -> contact onset -> planar
> object response -> task consequence -> one REAL->SIM success and one
> distinct SIM->REAL success.

After that narrow bidirectional proof exists, extend the same evidence into
contact system identification and a bounded policy-screening result. Do not
interrupt the immediate transfer path to build a broad scene editor, general
world model, or large training system.

## Source-of-truth order

1. Latest owner instruction selecting this combined causal-closure path.
2. `AGENTS.md`.
3. This successor queue and its live ledger.
4. The immutable predecessor queue
   `docs/autonomous-workflow/bidirectional-pawn-push-v2-task-queue-20260728.md`.
5. The current campaign graph and canonical receipts.
6. `docs/autonomous-workflow/bidirectional-pawn-push-v2-goal-loop-20260728.md`.
7. Advisory Fable/ChatGPT/World Labs comparisons.

The predecessor queue remains the authority for everything it attempted and
rejected. This queue is the sole active task list for successor work. No
predecessor receipt, denominator, action hash, held-out decision, or terminal
verdict may be rewritten.

## Starting evidence

Confirmed:

- The predecessor V2 campaign is
  `COMPLETE_TERMINAL_STATIC_NEGATIVE_NO_TRANSFER_AUTHORITY`.
- REAL->SIM and SIM->REAL remain `0/0`; physical task attempts remain `0/10`.
- Canonical current-workcell hard cutover is complete.
- Canonical task-plane registration passes:
  `4.741723 mm` held-out RMS and `7.104333 mm` held-out maximum.
- The canonical transfer-readiness audit rejected both legacy actions:
  their starts do not match the live anchor, and the physical/model mapping is
  still `provisional_range_audit_blocked`.
- The first current-anchor-seeded static compiler reported:
  `52` families, `208` cells, `44` eligible cells, and four frozen actions
  selected `2/2` per direction.
- That v1 result is quarantined as an apparent pass: its post-run diagnostics
  found that the live elbow seed is about `2.64 deg` outside the stock MuJoCo
  elbow limit even though it is inside the reviewed calibrated hardware
  range. It therefore cannot authorize dynamics, cases, or hardware.
- The versioned v2 static contract and implementation were frozen and pushed
  at commit `fc23364`, then executed once.
- V2 passed with `52` families, `208` cells, `44` eligible cells, and the same
  four exact actions selected `2/2` per direction. It applied the reviewed
  calibrated ranges and achieved a minimum selected model-joint margin of
  `0.001829670515161086 rad`.
- Dynamic consequence, mapping approval, physical execution, object
  trajectory agreement, task success, and transfer remain unproven.

Bound canonical evidence:

- Registration receipt:
  `runs/bidirectional-pawn-push-v2/20260728-canonical-task-plane-registration-v1/receipt.json`
- Readiness receipt:
  `runs/bidirectional-pawn-push-v2/20260728-canonical-transfer-readiness-v1/receipt.json`
- Quarantined seeded-static v1 receipt:
  `runs/bidirectional-pawn-push-v2/20260728-canonical-seeded-action-static-v1/receipt.json`
- Authoritative calibrated-range v2 receipt:
  `runs/bidirectional-pawn-push-v2/20260728-canonical-seeded-action-static-v2/receipt.json`
- V1 hashes independently re-admitted by v2:
  - REAL->SIM `tan_pawn_h7__h7_h6`:
    `73b681e2581ea1477f4deec90d1f48d78e8cce2b7c42923dd5c5b612415dbf42`
  - SIM->REAL `tan_pawn_h7__h7_g7`:
    `8526b423206ea88fe8d6edd5fb0ab5cf0d0a0333c68aa0489cd28430bebadfaf`
  - REAL->SIM `tan_pawn_f7__f7_f6`:
    `52c89c2f51e190ae0cd94512405e98b20fd6e630e139144503a0a68a3c3ddd87`
  - SIM->REAL `tan_pawn_f7__f7_g7`:
    `57e9192b8ec0a13331b1bfc6bf911c528f5dbe7df89055c89baa02465edab296`

## Combined architectural decision

### Adopt now

1. Close the seeded-static calibrated-range defect and admit a versioned
   current-anchor action set.
2. A minimum `ObservableEpisode.v2` contract that measures planar object
   response and contact/task events alongside exact action and joint/link
   state.
3. Dynamic replay of only the v2-admitted canonical seeded actions.
4. A thin, gauge-fixed `CalibrationGraph.v1` slice whose sole promotion
   question is whether the current physical-degree-to-MuJoCo mapping is
   approved for these cases.
5. One separately preregistered REAL->SIM case and one distinct SIM->REAL
   case.
6. A Studio first-divergence view covering links, contact, pawn response, and
   outcome.

### Adopt after object-response data exists

1. `ContactSysID.v1` with bounded contact/object parameters and derivative-free
   or hybrid search.
2. A `PolicyScreeningPredictive` certificate for several declared
   controllers/checkpoints.
3. `TaskWorldBundle.v1` as an executable bundle compiled to replay, Studio,
   system identification, and policy screening.
4. Failure-directed variations sampled from measured uncertainty and observed
   success/failure boundaries.

### Defer

- A broad/general calibration-graph rewrite beyond the variables and factors
  needed to approve this mapping.
- Markerless six-DoF pawn tracking when board-plane SE(2) is sufficient.
- Multi-camera exposure synchronization beyond the cameras actually used for
  the declared outcome; record clock availability instead.
- Full ClawStudio editor/product work before the causal slice is executable.
- RoboPose training, 4D Gaussian splatting, neural residual dynamics, broad
  domain randomization, large ACT/VLA training, deformable tasks, additional
  simulator backends, and paid compute.

## Required minimum data contract

`ObservableEpisode.v2-min` must represent, per available sample:

```text
host_monotonic_time
device_timestamp_by_camera
clock_mapping_status
command_requested
command_mapped
command_sent
command_applied_time_or_missing
measured_joint_state
estimated_link_poses
object_state_board_se2
object_state_covariance
object_observation_available
contact_state_or_probability
first_object_motion_event
task_outcome
```

Requirements:

- C922 owns physical board-plane object state and task outcome.
- CPU/fp64 MuJoCo owns simulator object state and contact witnesses.
- Missing timestamps, contact evidence, or object observations remain explicit;
  they are never interpolated into authority.
- Board-plane SE(2) is the initial object state. Height/lift remains a separate
  optional channel.
- Every physical frame and action sample binds its source timestamp and
  provenance.
- The exact task-action bytes remain immutable within a directional case.

## Queue

| ID | Status | Required outcome | Acceptance gate | Stop / redirect |
|---|---|---|---|---|
| CC00 | `DONE` | Preserve the terminal predecessor campaign and bind the canonical hard cutover, accepted registration, and rejected legacy readiness audit. | All cited receipts resolve; old denominators remain `0/0`, task attempts `0/10`; no legacy action is promoted. | Any hash/provenance mismatch reopens CC00 before successor execution. |
| CC00A | `DONE` | Reconcile the concurrent seeded-static v1 defect and finish the calibrated-range v2 rerun before using any action hash downstream. | V1 is explicitly closed as non-authoritative; v2 contract/code hashes predate its one run; calibrated model and gateway ranges are both named; every selected row has nonnegative model-limit and gateway margin; focused tests, workflow audit, receipt, reviewer decision, graph, queue, commit, and push agree. | A v2 reject remains a static negative and routes to one evidence-backed compiler/model correction. It never silently restores v1 or opens dynamics/hardware. |
| CC01 | `IN_PROGRESS` | Implement `ObservableEpisode.v2-min` plus deterministic simulator and physical-source adapters without opening hardware. | Schema validates exact actions, monotonic timestamps, joint/link state, board-plane object SE(2)+covariance, contact/motion events, task outcome, and explicit missingness; synthetic fixtures prove serialization and first-divergence extraction. | Do not add a learned residual, generic data lake, or broad editor. Missing physical timing is represented, not guessed. |
| CC02 | `PENDING` | Replay every v2-admitted current-anchor action in canonical CPU/fp64 MuJoCo and emit `ObservableEpisode.v2-min` traces. | Requested/applied action hashes remain exact; at least two distinct cases per direction report link, contact, object trajectory, exclusions, and outcome under direct-target and the frozen timing-stress plant; `2/2` per direction pass the unchanged task and robustness gates before case freeze. | If fewer than `2/2` pass in either direction, freeze first-divergence receipts. Change one prospectively declared simulation mechanism at a time, rerun untouched validation/held-out cases, and retain the old result. Do not resume unbounded action-family enumeration. |
| CC03 | `PENDING` | Implement the minimum gauge-fixed `CalibrationGraph.v1` required to approve or reject the current physical/model mapping. | Shared variables cover fixed camera/board, robot-to-board rigid transform, physical-degree-to-MuJoCo sign/zero/scale, and declared jaw reference. Factors reuse accepted board/endpoint data, fixed-base evidence, one-joint sweeps, exact encoder holds, and an untouched composite held-out. Receipt reports factor residuals, Jacobian rank/spectrum, correlations, bounds, condition, and held-out result. | Keep the accepted camera/board solution fixed unless a factor falsifies it. Add z-buffered body masks only if observability requires them. No broad graph rewrite. |
| CC04 | `PENDING` | Approve the mapping and freeze evaluator v2 plus at least two feasible distinct cases per direction. | `physical_model_mapping_approved:true`; canonical registration remains admitted; dynamic CC02 cases pass; evaluator, object tracker, camera thresholds, clocks/missingness, exclusions, mapping, scene, setup, task hashes, one-attempt rule, and maximum-ten ledger freeze prospectively. | Mapping reject routes back to one discriminating calibration factor/probe. Dynamic reject routes to one mechanism-specific simulator intervention. No physical packet. |
| CC05 | `PENDING` | Execute one admitted REAL->SIM case: physical task and object consequence first, then byte-identical replay in simulation. | C922-enclosed physical success; requested=mapped=sent identity; torque-off cleanup; exact simulator replay with no clipping/retiming/repair/state forcing; simulator outcome passes; full first-divergence trace includes links, contact, pawn state, and outcome. | A failure stays in the REAL->SIM denominator. If links agree but pawn response diverges, activate CC07; otherwise diagnose the earliest upstream channel before another case. |
| CC06 | `PENDING` | Execute one distinct admitted SIM->REAL case: simulator success and robustness first, then the frozen identical action once physically. | Sim outcome and robustness predate action freeze; distinct pawn/file; reviewed physical packet; C922-owned physical success; exact bytes; exclusions pass; torque-off cleanup. | A failure stays in the SIM->REAL denominator. Physical outcome never tunes the frozen case. |
| CC07 | `CONDITIONAL` | Fit `ContactSysID.v1` or another single mechanism-specific simulator correction only when the first-divergence evidence identifies it. | Bounded family covers only evidence-implicated variables such as effective pusher geometry/gap, pawn-board friction, contact softness/damping, object mass/CoM prior, command-to-contact latency, timing/actuator response, or an identified geometric variable; measured observables drive fit; fit/validation/untouched-heldout split and posterior ensemble freeze; exact policy actions remain unchanged. | Do not activate without measured divergence. Do not add neural residual dynamics. Reject non-identifiable, self-compensating, outcome-tuned, or heldout-selected parameter families. |
| CC08 | `PENDING` | Complete the bidirectional attempt ledger within ten physical cases. | At least one complete success in each direction; every failure disclosed; stop new physical cases immediately after both directions succeed. | A genuine terminal boundary requires receipt-backed safety/authority evidence after all safe frozen cases are exhausted. |
| CC09 | `PENDING` | Package the causal proof in Studio and the belief graph. | Synchronized spatial and temporal views show exact actions, joint/link residual, contact onset, pawn SE(2), first motion, final consequence, per-direction denominators, hashes, missingness, and claim boundary on desktop/mobile. | No substitute visual reconstruction for missing physics or object state. |
| CC10 | `REQUIRED_AFTER_TRANSFER` | Pilot `PolicyScreeningPredictive` with at least three declared controller/checkpoint variants, using deliberately differentiated scripted policies if trained checkpoints are not already admissible. | Frozen ID/OOD case distribution; rank correlation, outcome agreement, spatial failure overlap, boundary agreement, uncertainty intervals, and worst misranking; paired physical evidence is sufficient for the exact declared slice, or the result is explicitly `INSUFFICIENT_PHYSICAL_SAMPLE` rather than predictive. | This certificate grants decision utility only, never general twin fidelity or physical-transfer authority. Do not delay the first bidirectional proof for training. |
| CC11 | `REQUIRED_AFTER_SCREENING` | Implement `TaskWorldBundle.v1` from the successful slice. | One bundle binds workcell/transform graph, clocks, sensors, appearance/physics assets, observed channels, parameter posterior, source interactions, splits, evaluator, variations, policy-screening result, and certificates; compiles deterministically to MuJoCo, Studio, replay, sysid, and evaluation. | Do not build a broad editor or marketplace first. |
| CC12 | `REQUIRED_AFTER_SCREENING` | Connect measured posterior and policy failure map to targeted variation generation. | Variations sample only measured calibration/contact uncertainty, observed reset variation, and near-boundary/disagreement states; new checkpoints are screened against the frozen certificate. | No broad uniform randomization or held-out search. |
| CC13 | `PENDING` | Present the completed CC01--CC12 evidence package to the existing project Fable thread for an adversarial review. | Fable receives exact claims/limitations, directional numerators and denominators, action/evaluator/config hashes, object/contact/first-divergence traces, simulator changes plus untouched-heldout results, policy-ranking metrics/uncertainty, Studio/TaskWorldBundle evidence, failures, and remaining gaps. The prompt explicitly asks whether the project credibly demonstrates bridging the sim-to-real gap through coding agents, software engineering, and multiple composable mechanisms. | Fable is advisory and cannot override repository evidence, safety, heldouts, or proof classes. Do not accept vague requests for more architecture; require a concrete proof defect or implementation opportunity. |
| CC14 | `PENDING` | Triage and implement Fable's material in-scope recommendations. | Every recommendation is classified as: a new queue card with acceptance/evidence; a receipt-backed reject/defer decision; or already satisfied with exact evidence. All accepted recommendations are implemented, tested, evaluated on affected untouched heldouts, committed, pushed, and reflected in the graph and application package. | Reject recommendations that require overclaiming, evidence leakage, unsafe action, unbounded redesign, unavailable external authority, or work unrelated to the declared sim-to-real claim. A rejection records the evidence and rationale. |
| CC15 | `PENDING` | Return the updated result to Fable for a final defect check, then perform full closeout. | Fable reports no material unresolved in-scope proof defect, or every remaining issue is bound to a genuine external/safety/authority limitation. Focused/full tests, workflow audit, torque/process/camera/gateway cleanup, `brev ls` cleanup, scoped pushed commits, exact claim text, final graph, and application package all pass. | Any new concrete in-scope defect reopens CC14. Continue CC14<->CC15 until the review is clean or a genuine documented boundary remains. |

## Promotion and claim boundaries

Before CC05 and CC06 pass:

> The canonical workcell has accepted local registration and four
> calibrated-range, statically eligible current-anchor actions. Dynamic object
> response and transfer remain unproven.

After one complete success in each direction:

> Under a preregistered evaluator, at least one straight pawn-push case
> transferred REAL->SIM and one distinct case transferred SIM->REAL, with
> byte-identical task actions, camera-owned physical object outcomes,
> simulator contact/object traces, and every failed attempt disclosed.

Only CC10 may support a narrower policy-screening claim. Nothing in this queue
alone proves general world-model quality, full Twin fidelity, general
manipulation, learned-policy transfer, or broad policy ranking.

CC13--CC15 are a mandatory feedback loop, not a ceremonial review. The
successful closeout must show how the accepted Fable findings improved the
system or why each finding was already satisfied or rejected. The product
story must demonstrate that coding agents, evidence-oriented software
engineering, exact experimental controls, geometric calibration, causal
observability, mechanism-specific simulator correction, physical transfer,
and policy screening work together as one credible sim-to-real bridge.

## Live ledger

Current state:

- CC00 is complete.
- CC00A is complete.
- CC01 is the only active card.
- The v1 seeded-action apparent pass is quarantined.
- The calibrated-range v2 static run passed `2/2` actions per direction with
  the exact hashes listed above.
- Dynamic simulation has not executed for the v2-admitted action set.
- Physical/model mapping remains unapproved.
- REAL->SIM `0/0`; SIM->REAL `0/0`; physical attempts `0/10`.
- Cameras, gateway, serial, torque, paid compute, training, and physical task
  authority are closed.

Completed:

- Canonical workcell cutover.
- Accepted canonical task-plane registration.
- Legacy-action readiness rejection.
- Fresh current-anchor v1 static compilation, followed by a fail-closed
  calibrated-range defect finding.
- Calibrated-range v2 static freeze and pass at `fc23364`.

Blockers:

- No approved physical/model mapping.
- No time-indexed object/contact episode contract.
- No dynamic consequence pass for a v2-admitted action set.

## Time-bounded physical authorization

The owner authorized productive physical actions from `2026-07-28 22:38 CDT`
through `2026-07-29 05:38 CDT`, provided the actions are recorded and produce
useful evidence or learning.

This authorization:

- permits camera setup, reviewed gateway use, setup/return motions, transfer
  attempts, and bounded diagnostic probes when their queue gate is satisfied;
- does not promote the quarantined v1 actions or waive CC00A--CC04;
- does not waive robot identity, torque state, collision, exclusion, tracking,
  stall, action-byte, camera-enclosure, one-attempt, or cleanup gates;
- does not authorize EEPROM, servo-ID, gain, torque-limit, unsafe/unreviewed
  controller, destructive, or paid-compute changes;
- expires at the stated time. A packet not admitted before expiry returns to
  closed physical authority.

Next step:

- Implement `ObservableEpisode.v2-min`, then replay only the v2-admitted
  actions in simulation.
