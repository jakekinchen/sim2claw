# Causal-Closure Successor Task Queue

Status: `IN_PROGRESS_CC03K_DIRECTIONAL_DISPLACEMENT_STATIC_FREEZE`

Created: `2026-07-28`

Checkout: `/Users/kelly/Developer/sim2claw`

Branch: `codex/bidirectional-transfer-goal-loop-20260728`

## Mission

Use the accepted canonical task-plane registration and a defect-free,
current-anchor-seeded action set to close one complete causal task-transfer
chain for the smallest safely executable pawn consequence:

> exact action -> measured joint/link response -> contact onset -> planar
> object response -> task consequence -> one REAL->SIM success and one
> distinct SIM->REAL success.

The original straight sliding-push primitive remains the preferred claim, but
the elbow-locked workspace has a receipt-backed and independently reproduced
`<=32 mm` contact-height safety boundary. The active hard cutover is therefore
to a separately named **directional pawn displacement** primitive: selected
pawn displacement in a preregistered direction quadrant, with toppling/fall
quadrant secondary and exclusions stationary. This is not described as a
straight push or chess play.

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
- The authoritative V2 receipt SHA-256 is
  `c68599e9f18120f46bea955732ccc82c3582b9f18af280292f2aad73cfd47977`.
  Closeout decision
  `configs/decisions/canonical_seeded_action_static_v2_closeout.json`,
  SHA-256
  `ced92042e73ed53a5ccf27810ddce9d36f9a50f8f6a71110ca517bf116669929`,
  accepts static action freeze only and preserves false dynamic, mapping, and
  physical authority.
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
| CC01 | `DONE` | Implement `ObservableEpisode.v2-min` plus deterministic simulator and physical-source adapters without opening hardware. | Schema validates exact actions, monotonic timestamps, joint/link state, board-plane object SE(2)+covariance, contact/motion events, task outcome, and explicit missingness; synthetic fixtures prove serialization and first-divergence extraction. | Accepted closeout `fe586670e539d9047acac3f84167883f5fc50a6fac39c98cf0e2b47b16c52178`; no dynamic, mapping, or physical authority. |
| CC02 | `DONE` | Replay every v2-admitted current-anchor action in canonical CPU/fp64 MuJoCo and emit `ObservableEpisode.v2-min` traces. | Requested/applied action hashes remain exact; at least two distinct cases per direction report link, contact, object trajectory, exclusions, and outcome under direct-target and the frozen timing-stress plant; `2/2` per direction pass the unchanged task and robustness gates before case freeze. | Accepted closeout `2c7f8483663a619c25c6aece2c041a7327aa440b8d961857a101bbc0590a5ed5`; simulator-only, no mapping or transfer claim. |
| CC03 | `BLOCKED_SLIDING_PUSH_BOUNDARY_CONFIRMED` | Implement the minimum gauge-fixed `CalibrationGraph.v1` required to approve or reject the current physical/model mapping. | Shared variables cover fixed camera/board, robot-to-board rigid transform, physical-degree-to-MuJoCo sign/zero/scale, and declared jaw reference. Factors reuse accepted board/endpoint data, fixed-base evidence, one-joint sweeps, exact encoder holds, and an untouched composite held-out. Receipt reports factor residuals, Jacobian rank/spectrum, correlations, bounds, condition, and held-out result. | Wrist mapping passed only in a bounded elbow-locked scope. V4 plus Fable's independent pose sweep prove the unchanged sliding-push contact-height gate unreachable at the current anchor. No more sliding-push search. |
| CC03E | `DONE_MECHANICAL_RESISTANCE_SIGNATURE` | Sharpen the elbow diagnosis with a receipt-bound, no-contact telemetry probe and a matched wrist-flex control. | Preregistered range-safe elbow destinations and equal returns plus identical-magnitude wrist-flex control record requested/goal/sent/measured position, current/load, temperature, status, torque-enable readback, clocks, tracking/stall decisions, return residual, and torque-off cleanup at `>=5 Hz`. One torque disable/enable cycle precedes one repeated elbow probe; no configuration/gain write. | Accepted closeout `f9c5d8fa...`: symmetric partial elbow response with rising current/load, normal status/temperature, matched wrist tracking, no post-cycle recovery. Human repair boundary; no gain experiment. |
| CC03K | `IN_PROGRESS` | Prospectively freeze and statically screen the directional pawn-displacement primitive within the physically responsive envelope. | Static-only finite grid; selected pawn contacted collision-free at the modeled reachable head-height band; robot-board and exclusion margins, calibrated joint/gateway/slew margins, camera visibility, exact action identity, distinct direction families, and false physical authority all pass. At least one eligible family per direction is required. Primary displacement threshold and direction quadrant plus secondary topple/fall quadrant are frozen before dynamic outcomes. | If either direction has zero safe families, record a terminal workspace boundary. Do not weaken collision/contact/camera/gateway gates, relabel the result as sliding push, or continue outcome-informed family search. |
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
- CC01 is complete.
- CC03K is the only active card.
- The v1 seeded-action apparent pass is quarantined.
- The calibrated-range v2 static run passed `2/2` actions per direction with
  the exact hashes listed above.
- V2 receipt `c68599e9...` and closeout decision `ced92042...` are bound.
- `ObservableEpisode.v2-min` is accepted by closeout
  `fe586670e539d9047acac3f84167883f5fc50a6fac39c98cf0e2b47b16c52178`.
  Requested, mapped, sent, and applied rows are independently hash-bound;
  physical-source missingness and causal first-divergence extraction are
  tested.
- A focused test mistakenly executed the full V1 temporal implementation twice
  into temporary directories before a freeze commit. Closeout
  `1693f5c68af7298d27d6125340f48bd87b713f5fa3cd8639848b772eb5fc5f8d`
  quarantines both as non-admissible implementation validation; no temporary
  result or path is bound and no outcome informed a change.
- The outcome-identical V2 temporal successor is frozen at
  `ae31376f2707ed3c4e6372313dc21ad7734e51e0a19392967df3c444e27e2870`.
  Its four actions, two plant paths, five variants, gates, and causal channels
  are exactly inherited from V1.
- The official V2 temporal replay executed exactly once after its freeze. It
  rejected all four actions under the required two-plant/five-variant screen:
  REAL->SIM `0/2`, SIM->REAL `0/2`, and `0/40` passing outcomes. All `40/40`
  outcomes made selected contact, but `0/40` passed the no-lift gate; progress
  passed `23/40` and exclusion displacement passed `33/40`. The exact-action
  and trace checks pass on all eight case/plant paths. Receipt SHA-256:
  `727ecd642681a6cb4a85327ccd95e4637df60e3ebdf4e2acd49e26e8f2e526ff`.
  Closeout SHA-256:
  `98e3154e65a778c5f77e52cfc84b12e6886030a0bff7a4d66ac43fb8f184bfaf`.
- The result is preserved without action repair, gate weakening, mapping
  approval, or hardware authority. A bounded nominal-only contact-witness
  diagnostic is prospectively frozen at
  `fa1524a2e27c4666c2185303ecddaa1014876f70ac8560d13e4073ed00730482`.
  It replays the same four exact actions under the unchanged direct and ZOH
  paths only to localize modeled jaw/pawn contact height, normal, force, and
  timing before one mechanism is selected or rejected.
- The witness executed exactly once. Receipt SHA-256
  `89ecb1d20b2176fb0e890b1afda128c8f9eb577cc519277b171361626c4f5bc2`
  shows that all eight nominal case/plant rises follow jaw contact. Six of
  eight paths first contact above `50 mm` from the pawn root with strongly
  vertical contact normals; all first contacts are from enabled high-detail
  jaw collision meshes even though named collision primitives are also
  present. Closeout SHA-256
  `d32139d76575d727262bf2f0e100fb63ae7b7bf04db117820d6f2a6e69cad775`
  excludes the defective per-contact `support_contact_steps` count from use.
- One mechanism-only proxy collision challenger is frozen at
  `5bfefa645281fb9ea5fe99cbd93082d105c1972daeb7a5b9450ec7425432fdd6`.
  It disables only the three enabled left-jaw collision meshes and preserves
  named jaw collision primitives. Exact actions, plants, reset variants,
  gates, pawn/board geometry, mass, friction, damping, timing, and actuation
  remain unchanged. This is diagnostic, not calibrated physical geometry.
- The V1 challenger invocation failed closed at source-binding validation
  before output-directory creation, model loading, or any dynamic row. It
  inherited the obsolete base-V1 temporal implementation hash rather than
  applying the already declared current implementation binding. Closeout
  SHA-256
  `a6ec6ab6b5b434f083b6a13f180d25888a834d2c73828e3d63652fc2f00daa39`
  records zero outcomes and zero execution.
- V2 changes only compact-contract resolution for that binding and is frozen
  at `a911f2a3b1945176949eff6de775f8602b656d919f6273262faedc0fc82fa496`.
  The collision mechanism, exact actions, plants, variants, gates, and
  authority are unchanged from V1.
- V2 generated its episode and trace files but failed before its summary
  receipt because the compact JSON adapter omitted a pass-through serializer.
  Its `104` files / `125545280` bytes are uninspected and quarantined under
  aggregate SHA-256
  `8f9b470dea762611dbfb9537f6c20d1b3393a300e8238380f3a471845dc32412`.
  Closeout SHA-256
  `24e9eb55c93734e8bdde0c06b2fd2a11462e92236dc53be48c521b2aae89c5ef`
  grants no result authority.
- V3 adds only the missing JSON serialization pass-through and is frozen at
  `7edc2866728d6787548cb911c4d4c168973e7acf6e28800fdc19596e5cb03156`.
  No V2 outcome was parsed or used.
- V3 executed once and rejected the proxy-only collision mechanism:
  REAL->SIM `0/2`, SIM->REAL `0/2`, and no passing family. Progress passed
  `18/40`, no-lift `1/40`, and exclusion displacement `37/40`; all selected
  contact, excluded-contact, collision, camera, and exact-action checks
  otherwise preserve their stated gates. Receipt SHA-256
  `5f57802489563ec89ed6acdc57ae3f2d780e4c65629ea33f250060d005d6f9db`;
  closeout SHA-256
  `275cba65da93c343dd4a11287aac3b6db793f7d8f7e4b90098723b656deb6503`.
- The next one-mechanism successor is a static-only finite wrist-orientation
  and precontact-path grid frozen at
  `4912e8000648f088dd0677189f4a25715e750b59ddfecd7202e2f7b8ff2435cf`.
  It quarantines the four outcome-informed cases, enumerates `288` cells over
  the remaining `48` current-layout families, and gates first-contact height
  and vertical normal using kinematic `mj_forward` witnesses. Dynamic replay
  and physical authority remain false.
- V1 failed closed during module import before contract read, model loading,
  output creation, or static evaluation because the canonical square helper
  was referenced from the wrong module. Closeout SHA-256
  `2fe53c07c7d60aca6d343124809903f7a0af5bb0dbbd4ba928f22867628e4999`.
- V2 changes only that import source and is frozen at
  `e73b07b6a73eb60471949d18329e7ab2a4d5042c0e54d2c92f510e1f18021935`.
  Every grid, quarantine, gate, and authority field remains unchanged.
- V2 ran once and admitted only three distinct families (`2` REAL->SIM,
  `1` SIM->REAL), so dynamic replay remains closed. The three contacts are
  low and nearly planar (`13.592--13.940 mm`, `|n_z| 0.054--0.187`), while
  `225/288` cells failed IK. Receipt SHA-256
  `307b94fa25a84e725c567647367d6029c285ff496a995a0825476d4b7f5b4d39`;
  closeout SHA-256
  `9938421bedb9f06e8f514eb9c689a179870496c002983c61772614e440c5f45e`.
- V3 changes only precontact order—lift with live wrist, then rotate at
  clearance—and is frozen at
  `3519c6391ae5d14549a40fde10433eeb4e68435cf3f6ccd160475b17b344c019`.
- V3 ran once and left the exact V2 ceiling unchanged: three families,
  `2` REAL->SIM and `1` SIM->REAL. Receipt SHA-256
  `dc4d3e6010710597211337d226b219e671cd5325bde0586d943a237123ce0303`;
  closeout SHA-256
  `21d76b7c688103aeac481de98843eb3e24228b8f11367357f64b8e6c4e56b865`.
  Lift-before-rotation is therefore rejected as a sufficient mechanism.
- V4 changes only the precontact segment: descend at a geometry-derived
  `35 mm` rear standoff, then approach the unchanged contact point
  horizontally. Contract SHA-256
  `dc759ea2b13a9f29e82a86553b91cb4239f439876fc9f4926bc24c68bb236c64`.
  The family universe,
  quarantine, wrist/contact grid, jaw target, offset, stroke, clearance,
  gates, selection, dynamics, and physical authority remain unchanged.
- V4 ran once and passed the static gate with six eligible families and the
  selected `2` REAL->SIM / `2` SIM->REAL split. Receipt SHA-256
  `b9374eaa326af2bdb063eac577e76293c2a3e45f11001c1d135bdd7258a15e31`;
  closeout SHA-256
  `7b24317c4d11ad36506b89331da239669286a59414d4e5905b8af259512193c1`.
- The four exact V4 float64 action tensors are frozen for dynamic baseline
  plus diagnostic ZOH replay at contract SHA-256
  `ec29f12c57bdb2bcedc5fc4543ac593db1f1b12a846695e16071f69bb42495f6`.
  Requested bytes, row order, 40 Hz timing, five reset variants,
  ObservableEpisode.v2-min, first-divergence channels, and all gates remain
  unchanged.
- Dynamic V1 ran once and passed only `tan_pawn_f7__f7_f8`: REAL->SIM
  `0/2`, SIM->REAL `1/2`. All action, trace, timing, and rate-compatibility
  checks passed. The failures localize to neighboring-pawn displacement for
  two lateral cases and progress/no-lift boundaries for the remaining
  forward case. Receipt SHA-256
  `cbda502b2b07f75f87695c9e2a19635b01a7197e1cf90732d9c1bbb391c792e0`;
  closeout SHA-256
  `7491189fb996428c5bf6c0dcad6950a62c15205fcc9ad075fe624366a67d33e2`.
- The two V4 statically eligible families not opened dynamically are frozen
  for action materialization only at contract SHA-256
  `4d38d758fcf408fc1267c30acd599a554bd98d0a62ad67ed0a2140e2640ff6d1`.
  This is a two-case bounded completion, not renewed family enumeration.
- The completion ran once and reproduced both frozen hashes exactly without
  dynamics. Receipt SHA-256
  `7e8d927d932be0c11a67cf3147b214429e95458dac8dcbaa35b69e60f4c17cf3`.
- Reset temporal V2 is frozen at contract SHA-256
  `77ee0f180aaf656005edecfd2d3e08555080c14c03397e36059b53ce83fc54a3`.
  It replays all six exact actions and moves only nonselected pawns to
  deterministic offboard parking poses. The two unopened actions are
  validation cases. Selected pose, physics, both plant paths, five deltas,
  traces, gates, and false mapping/physical authority are unchanged.
- Reset temporal V2 ran once and passed `1` family per direction, below the
  required `2/2`. It eliminated excluded displacement but left only
  progress/no-lift boundaries; neither unopened validation family passed.
  Receipt SHA-256
  `e2986fac6f6e2e3d4ae0cb1191ae42d6b6955fab6cc46eaee2874b4a9c79c406`;
  closeout SHA-256
  `30633e88f8e0d43bba66f23377c4b0042a3d5cb15d784b7c377ee24c1929a206`.
- Four V4 cells that were already statically eligible at `10 mm` contact
  height are frozen for exact action materialization at contract SHA-256
  `3987ee1b898cb634b6f9688c2a35d057a0a07c936ab631b9d4deaa515067379a`.
  Their 14 mm predecessors remain immutable; no family search or dynamic
  outcome occurs in this step.
- The four low-contact actions reproduced their preregistered hashes exactly
  without dynamics. Completion receipt SHA-256
  `ee26fa9d39661f31063a1036cc9eb0edc935996e399cf46696b6b9f53ba02336`.
- Low-contact temporal V3 is frozen at contract SHA-256
  `fd00a7c4b16ed15d93dea4addf370be9374f4774073e58371c6345ce71ea69b4`.
  It assigns two cases per direction before dynamic opening and preserves the
  isolated reset, both plant paths, five deltas, physics, traces, and gates.
- Low-contact temporal V3 ran once and passed one family per direction, below
  the unchanged `2/2` gate. All identity, contact, exclusion, collision,
  camera, no-lift, and gateway checks passed. The only failures were progress
  at one lateral reset endpoint for `h7->h8` (`35.318514/35.824712 mm`) and
  `d7->e7` (`32.565617/34.508641 mm`) under direct/ZOH, respectively.
  Receipt SHA-256
  `9a907fd1764ade312173a20a200f63653d677bf4b9b1a1665cb9f7aa86a79634`;
  closeout SHA-256
  `ccedd64fc67bc88553be5a4944d314fde46c09b67243a30377448cf36c7362e2`.
- The next single mechanism is a bounded stroke-only static successor across
  all four low-contact families. Its sole stroke is `66 mm`: the unchanged
  `60 mm` stroke plus the full `6 mm` span of the already-frozen
  `+/-3 mm` reset uncertainty. No failed case receives a private adjustment.
  Contact height, wrist orientation, precontact path, jaw target, reset,
  physics, action rate, and every task/robustness gate remain unchanged.
- Stroke static V5 is frozen before execution at contract SHA-256
  `7df69f21911ef2631ef911fcbfe20c1fc7df6aeeac8473147e5706715d0c0b05`.
  It contains exactly one cell per complete V3 family, two per assigned
  direction, and no dynamic or physical authority.
- Stroke static V5 passed all four cells. Receipt SHA-256
  `f4b97af0f219b21cb7ee59bc39b123f85f6e3d66a943d6245ffe3cd9af9c2815`;
  closeout SHA-256
  `100bf81f5c77b1e1fdbb8a3b0d3c798e940a8f114ef912276cbaffb56ffc96c3`.
- Exact-action stroke temporal V4 is frozen before dynamic execution at
  contract SHA-256
  `7f385088702537cf0867dd4b83ea5a449a872cb3c095f53efd23b66c80239fa4`.
  It preserves the V3 direction split, isolated reset, two plant paths, five
  deltas, 40 Hz bytes, causal traces, and every acceptance gate.
- Stroke temporal V4 ran once: REAL->SIM passed `2/2`; SIM->REAL passed
  `1/2`. Three families pass both plants and all five resets. The only
  remaining failure is `d7->e7` progress at `lateral_plus_3mm`
  (`35.219246 mm` direct, `32.553492 mm` ZOH). Receipt SHA-256
  `0f4fb9e7eb50c1501e53b365795e11c1913310714878c9ef5663e00687985a8b`;
  closeout records stroke length as insufficient and freezes a uniform
  two-lane `-3/+3 mm` path-shape successor across all four families.
- Two-lane static V6 is frozen before execution at contract SHA-256
  `adb0908a23f4180a80a24dc49172d9a97f9ba13c1d847b4982816dcbf15286f7`.
  It contains the complete four-family set and applies the same two lanes,
  stroke, return, static gates, and false physical authority to every case.
- Two-lane V6 ran once and admitted `f7->e7` plus the missing `d7->e7`; the
  other two actions rejected only on the unchanged contact-normal gate.
  Receipt SHA-256
  `3e32303fa6ebb0f102a2562f76df43480c8880ab4400a7e80a3860c819a25940`;
  closeout SHA-256
  `97fbe64d7b4de126e3f29e2323cb613fea13ebd3dee2ae7d30f287f77dc4552c`.
- Static selector V1 is frozen at contract SHA-256
  `cdd2d7ced436b789d2c90fddece2d29d0c9725ec95a70e205b0227b063c53e8b`.
  It reads only the two static receipts and selects the eligible candidate
  with the lowest absolute vertical contact normal, tie-breaking canonical;
  dynamic outcomes are excluded.
- Static selector V1 passed `2/2` directions and chose three canonical
  single-lane actions plus the two-lane `d7->e7` action. Receipt SHA-256
  `18921a5d066c0e8e41f84850cc01a59bf44a6f3de64b62df8b9496d908ddeec9`;
  closeout SHA-256
  `0ca11fb87d1357034b82f37b7ab689ee1a259254c805e8e69c14a627c20cb661`.
- Selected temporal V5 is frozen before dynamic opening at contract SHA-256
  `a303b12eaf959186fc0b904023552ab8a4898ac691ec933d60b4cd00ae6b09a5`.
  Candidate fallback is forbidden after execution begins.
- Selected temporal V5 passed all four cases: REAL->SIM `2/2`,
  SIM->REAL `2/2`, both plants, all five reset variants, and every identity,
  task, and robustness gate. Receipt SHA-256
  `cf21bd8cc7b408d50ffcaae039fa993173514d49c4abf6f455bb7b484af0f36a`;
  closeout SHA-256
  `2c7f8483663a619c25c6aece2c041a7327aa440b8d961857a101bbc0590a5ed5`.
  This closes CC02 as simulator-only evidence.
- Minimum gauge-fixed CalibrationGraph.v1 is frozen before evaluation at
  contract SHA-256
  `f80e4e14539c43902b1c9d04257c937ca6c2a2cc41fe58892c5463034cbd358c`.
  Camera/board, robot/board, joint signs/zeros, and jaw reference are fixed;
  four joint scales are active; the untouched composite heldout is required.
- CalibrationGraph.v1 ran once. Its active Jacobian is full rank (`4/4`) and
  well-conditioned (`5.693663`), but mapping is rejected by elbow/wrist
  differential factors, the pose-K hold, and the missing untouched composite
  heldout. Receipt SHA-256
  `718cedd9ff0f8cb7389e92051fa288162527415f40d0b4c4f06186c80001908a`;
  closeout SHA-256
  `4bcefbd4595fbdf9698c6d48058ea726c62beffd28f26f2c89bf0158cb9241ea`.
- The symmetric two-sided no-contact composite tricam V1 route is frozen at
  SHA-256
  `0c9e41d71af945144e782778d5fa4f52f2096f6e2705598b7dad742d3a0069be`.
  Its packet compile failed closed before writing a packet because the staged
  path exceeded the frozen known-safe self-contact penetration envelope.
  Closeout SHA-256
  `ca9b3527361784649b72d011c17c545ebef59922d755bdfbeac96fcc9ddbddd9`;
  physical motion and task attempts remained zero.
- Composite tricam V2 is frozen at SHA-256
  `5cf70e332236729dbf5cd1562c8992947f59592e0590b33148654b24b47e69df`.
  It preserves all four active joints and the two-degree bound, uses the
  prospectively selected static-safe `(-,+,-,+)` one-sided excursion, returns
  exactly to the fresh torque-off start, and remains calibration-only. Its
  selected 961-row exact action SHA-256 is
  `25df23c1cc7a392e190b2eda42afcc23ea3b523e9ce760dfe607d3be3993502b`.
- Composite tricam V2 compiled from a fresh torque-off follower read with no
  modeled contacts and no action assistance. Packet SHA-256
  `d7f095627c4735ab4b6132aa6ff4666ca57372468837031a93ecc3fd887eb930`;
  plan SHA-256
  `1a8cabd2416c421061092506cf3595b02ba96573eec7a94747ce79cc4835930e`.
  Independent review admitted exactly one stage execution; review SHA-256
  `81b2524acd777e51497151ddbae09c81cdbe2b1a15c931572af45fdd99b590e1`.
  Compilation and review commanded no motion and opened no cameras.
- Composite tricam V2 executed exactly once. Execution receipt SHA-256
  `ef0d257151fd3f58f1c5e5659bb2d3ffdf5a339fe90352a499b070a061809b77`;
  all `961` motion and `80` hold samples completed, C922/D405/Pi enclosed the
  action, exact action identity held, the return residual stayed within the
  reviewed gate, and both the receipt and a fresh post-run preflight report
  follower torque off. This was calibration-only; task attempts remain zero.
- Composite heldout evaluator V1 is frozen after execution and before opening
  heldout frames at contract SHA-256
  `4c38902e8b8168fd1ef7d300a82951575db28801d748ae064ff6534dd744a59f`.
  It compares constant-offset-invariant Pi AprilTag motion for tags `1` and
  `2` against the frozen CAD projection along the exact measured trajectory.
  It may not fit parameters or automatically approve mapping.
- Composite heldout V1 rejected only the wrist-tag correlation factor. The
  upper-arm tag passed at `1.431815 px` RMSE and `0.980105` correlation; the
  wrist tag reported `5.196288 px` RMSE and `-0.525996` correlation. Receipt
  SHA-256
  `5b10d59d65248895943f0f4efbb88687de1bd25b8f889880ef8b48a6af81041a`;
  closeout SHA-256
  `8bb6f4c0295449c19e6423338c5e52bcde316d2ebb036052df6674d8170ba3f4`.
- The outcome-informed, diagnostic-only D405 relative-rotation check on that
  capture found `0.959153` observed/simulated rotation RMS ratio,
  `0.646797 deg` RMSE, `1.418678 deg` maximum error, and `0.796500`
  correlation. Together with the passing proximal tag and prior D405
  wrist-motion witness, this rejects a broad camera/base rewrite and points to
  Pi wrist-tag projection/mount confounding.
- A distinct elbow-only then wrist-only three-degree exact-return tricam route
  is prospectively frozen at SHA-256
  `370b3daba18a1022b4cc2911f15591c889fe3917a35e5b8ace92bfbc795c1380`.
  Both stages pass the exact static collision screen with action SHA-256 values
  `afda88ae...` and `d5d1aaff...`. The gauge-free D405 fixed-tag relative
  rotation evaluator implementation is frozen at SHA-256
  `a7628f277c502e6f8ed3113f953ef0b554778322ed1ee983705e4c08c00f85c6`.
- The downstream route compiled from the fresh torque-off anchor with plan
  SHA-256
  `fb17887d05ab8250e408f7bf89601f2379ba5ae9c09699c8ebfbebe5d794e695`
  and packet SHA-256
  `431a6d513bae769fcd21d6497e34023cf018c8d25b1d51384529fe94a43c590b`.
  Independent review admitted one execution per stage at review SHA-256
  `67c41e55b15571f22a9497a1e84dd6545d7f8ffc834b8d12fed3afeacd30d788`.
  Compilation and review used no physical motion.
- Downstream rotation stages 1 and 2 each executed exactly once as reviewed.
  Stage 1 receipt SHA-256 is
  `6613d126a4fc257a642a4dcc67b3f4398f97e96643b21212217e36f05b2c7843`;
  stage 2 receipt SHA-256 is
  `ccbf276b63505920dde91e03c206d0578ef42be8645b93ee9170a9faefd8135a`.
  Each completed all `641` action samples plus `80` hold samples with tricam
  enclosure, exact action identity, no task contact, and torque off. The
  active-joint return residuals were `0.087913 deg` for elbow flex and
  `1.406594 deg` for wrist flex.
- Exactly one stage-1 final-hold D405 frame was inspected between stages for
  operational safety only; no action-interval trajectory, metric, or outcome
  was opened. Stage-2 frames remain unopened. This provenance is explicit in
  the downstream heldout contract.
- The D405 action-interval rotation heldout is frozen before opening either
  action trajectory at contract SHA-256
  `e78908139ee586894ccfdcb5325c081251b23e795a34a8c7626d52e6409aaa8c`.
  Its evaluator implementation SHA-256 is
  `25ac3ad5bd95c35d5cc7946b5d25341a440b566f9ea6c732c443deefe5c59c43`.
  It may read only the bound captures, fit no parameter, and cannot
  automatically approve mapping.
- D405 rotation heldout V1 ran exactly once and rejected. Receipt SHA-256 is
  `0b1901baabf93a479d3b48faee1bc119f47b9627a71aedd00fd6f1adaacabc67`;
  closeout SHA-256 is
  `3391f6053f2910430dc4263817bb9645ea8207bad22dd214ad24059f916bbcab`.
  The elbow command produced only `0.087912 deg` measured excursion, so that
  stage lacked physical signal. The wrist moved `2.813187 deg`, but the
  frozen PnP rotation-magnitude correlation was `0.0`. Mapping remains
  unapproved.
- A post-result, outcome-informed localization found the raw wrist-stage tag
  corner displacement correlated `0.992415` with measured wrist excursion.
  This diagnostic cannot promote mapping, but it identifies the PnP-derived
  rotation channel—not raw D405 observability—as the wrist-stage defect.
- Corner-shape heldout V2 is prospectively defined by route SHA-256
  `80e2d59d56f91987741ceed3774711bd608a973f6f3e8cc88021de4f336d9aaa`
  and evaluator implementation SHA-256
  `fc9fd098525eae3c65de8a63d92a7602c5178a1e0a3ee793eea857226c1c9bf0`.
  It increases only the elbow excursion from three to five degrees, retains
  the wrist action at three degrees, replaces PnP rotation with normalized raw
  tag-corner trajectory shape, fits nothing, and requires no depth. Before
  either new capture exists, its provenance contract permits only one
  stage-1 final-hold frame for between-stage safety; both action trajectories
  remain unopened until the evaluator contract is frozen.
- Corner-shape V2 compiled from the fresh torque-off anchor with no modeled
  contact. Packet SHA-256 is
  `241eea8d705bf303d5f7c3d9c8e5c4e7b81def094108d221a584374b97c428e7`;
  plan SHA-256 is
  `0c2fad04474f95c9b1e882417bd451586432eb47c5eb1b7b69b417511b67a68b`.
  Stage action SHA-256 values are `c16b3e1e...` for elbow and `d4fd8f1a...`
  for wrist. Independent review admits exactly one execution per stage at
  review SHA-256
  `184052d965563e6d111dc33bb9ef3abb92188abdff98e94733db1c438b88bad9`.
- Corner-shape V2 stage 1 stopped safely at motion sample `233`. The commanded
  elbow reached `95.671703 deg`, but measured elbow remained within
  `[99.208791, 99.296703] deg`; the stall warning rejected the action, all
  cameras enclosed the stopped interval, and torque was released. Execution
  receipt SHA-256 is
  `8b72ae4c77d0a81fc2dc170ad3678831b79e4e739b3eb63694a27c6dccad8331`;
  closeout SHA-256 is
  `65f71a1bbf418e43632ebf834d2aaffab7e5f3b0dd6cdb45f8f3d4d0caacfbef`.
  Stage 2 under that packet is forbidden.
- The repeated two-, three-, and five-degree negative elbow nonresponse
  establishes an actuator-scope boundary for the current hardware state.
  Rather than ask for physical intervention or weaken safety, the task proof
  cuts over to elbow-locked action families. Elbow is a constant encoder
  anchor, not an approved actuated mapping factor.
- A single-stage wrist-only successor is frozen at route SHA-256
  `063342cfa052238950b7ad749095984e75652b44550ee12d535671103f36f03a`
  and evaluator SHA-256
  `e1abac05ab99bcddd3f3432d1f549f35fc7afd4be36e375040b2d02d4571ff26`.
  It retains the prior three-degree wrist action, uses raw tag-corner
  trajectory shape, fits nothing, opens no depth channel, and makes no elbow
  claim.
- Wrist-only V3 compiled from the fresh torque-off elbow-locked anchor with
  no new or worsened modeled contact. Packet SHA-256 is
  `819a2cbad0b611226213763d4640b87d8da83808a2a648a7b738323d7915201e`;
  plan SHA-256 is
  `2da67f0d028c503bf12172837305f8f8eb30a47a84de872ae5ee4d3624985201`;
  exact wrist action SHA-256 is `7cdb934e...`. Independent review admits one
  execution at review SHA-256
  `233fb3e7067384e1e321082e1b6edde6a1f19abb950a2dc5f096638817dc1dca`.
- Wrist-only V3 executed exactly once. All `641` action rows and `80` capture
  hold rows completed with exact action SHA-256 `7cdb934e...`; C922, D405,
  and Pi enclosed the interval; both native cameras reported zero drops and
  zero writer backpressure; final wrist residual was `1.054945 deg`; and
  torque closed false. Execution receipt SHA-256 is
  `53672fa50261887f352e2d9cc17d45ce770edbe4b4d4d70fa1eb635f3d54b507`.
  This was calibration-only motion and does not enter either transfer
  denominator.
- A static model audit rejected the proposed missing camera-mount inheritance
  defect. `left_camera_mount` is a child of `left_gripper`, which is a child
  of `left_wrist`; a synthetic `+3 deg` wrist-flex perturbation rotates
  `left_wrist`, `left_gripper`, and `left_camera_mount` by exactly `3 deg`
  while leaving `left_lower_arm` unchanged. The prior `1.318681 deg` value
  was trajectory RMS, not peak gain. Decision SHA-256 is
  `3e65536edb2a7e9950fdb3565c15905e63219bfdf6b6e0303660f6d8ba7e1b7c`;
  the model remains unchanged.
- The one-shot V3 held-out contract is frozen after execution and before any
  V3 frame is opened at SHA-256
  `862acd451e684c680b69467bb596d5dcfbf4ff28c686dada2de6b35dc62e0733`.
  It binds the packet, review, execution, candidate model, evaluator and
  dependency hashes; fits no parameter; requires no depth; and grants no
  automatic mapping or task authority.
- V3 executed once and rejected, but the result cannot be interpreted as a
  mapping negative. The inherited helper appended live MuJoCo `xmat` views
  without copying, collapsing every simulated trajectory sample to the final
  pose. The immutable receipt SHA-256 is
  `87850780c2a298016601d062d231238ed1df6158e97cadf2d8761cf34919c28f`;
  closeout SHA-256
  `59d34e6e29bd6047fbcb1939ec53d559b698bee9976ef14bf8f14590e0c1f628`
  preserves the reject while withholding a mapping verdict.
- Copy-safe V4 changes only matrix ownership during simulated trajectory
  accumulation. The implementation SHA-256 is
  `1ff1b08569560c455577541abf06d8422fda383718bc2de165af4089e88c07f1`;
  actions, alignment, observed corner extraction, normalization, gates,
  model, mapping, and authority are unchanged. A diagnostic-only contract
  over the now-open V3 capture is frozen at SHA-256
  `7b214e47d82e0d8630b31b4350184e979528d4f8f2a37832d8f370340b883baa`.
  It cannot approve mapping even if it passes; a fresh prospective capture is
  still required.
- The first V4 diagnostic invocation stopped before receipt creation or any
  metric result because the copy wrapper recursively resolved itself.
  Closeout SHA-256 is
  `90a91c8553c288c1e9c5ba6145c7019c93171774c36aaced0c30ae9da10833eb`.
  V5 changes only wrapper binding: it captures the original rotation callable
  before temporary patching. V5 implementation SHA-256 is
  `feedf3ede2c7aa723f209157254c4c904a81a778c0dae57d909e16a8ba52899b`;
  its new-output diagnostic contract SHA-256 is
  `dfc17f942c1e5c0432326bfdd9848f18c19f31d0330bbd21cb79f29eddba0c35`.
- The V5 copy-safe diagnostic passed every unchanged gate on the opened V3
  capture: normalized correlation `0.985783`, RMSE `0.062148`, maximum error
  `0.168894`, and simulated peak `2.813187 deg`. Receipt SHA-256 is
  `a7f1bfa773067b4185b266910de14126daf9db4631e79c23e6b8d96abf671d07`.
  It remains diagnostic-only and does not approve mapping.
- A fresh prospective wrist capture is compiled from torque-off anchor wrist
  `-16.395604 deg`. Route SHA-256 is `5e1ad4b6...`, packet SHA-256 is
  `68513862...`, plan SHA-256 is `1e880940...`, exact action SHA-256 is
  `6872ca20...`, and review SHA-256 is `dbbd9f88...`. Static preview adds no
  new or worsened contact and admits exactly one no-contact execution.
- Fresh wrist-only V4 executed exactly once. Execution receipt SHA-256 is
  `cb4820f697128a16a68b6c481a3919d56a0ad5e00e66d3c4fb35e3a9a7f615e6`;
  all `641` action rows and `80` hold rows completed, exact action SHA-256
  `6872ca20...` held, C922/D405/Pi enclosed the action, the two native cameras
  reported zero drops and zero writer backpressure, final wrist residual was
  `1.318681 deg`, and torque closed false. This was calibration-only and does
  not enter either transfer denominator.
- The fresh wrist heldout contract is frozen after that execution and before
  any V4 frame is opened at SHA-256
  `607a4b8c8a2eecc086bfa08b65e1d1c19012e1546aa0e4ecb2dca930ea8735e6`.
  It reuses the copy-safe V5 implementation and every unchanged V5 diagnostic
  gate, binds exact action `6872ca20...`, requires no depth, fits no parameter,
  and grants no automatic mapping, task, simulator, or transfer authority.
- The fresh prospective heldout passed every frozen gate at receipt SHA-256
  `16b7896c45904c7563d00f8b8386cddf3892de9deec70c77c0a2c9ff087294c6`:
  normalized correlation `0.985523`, RMSE `0.073090`, maximum error
  `0.144659`, `90` detected frames, measured wrist excursion `2.725275 deg`,
  and simulated excursion `2.725275 deg`. It fits no parameter and the receipt
  itself does not promote mapping.
- Closeout SHA-256
  `78c4f24d7722004e0808ed3f5cbfbc84b63b643ecdd8c6f00641c5759daac545`
  accepts the current wrist-flex channel only for a bounded elbow-locked task
  scope, alongside the prior passing shoulder-pan/lift and fixed
  registration/jaw factors. It rejects the original four task actions because
  their elbow spans are `109.881072--173.297076 deg`, while repeated physical
  probes established the elbow as a nonresponsive actuated channel. Global
  six-joint mapping, camera refit, the original task actions, evaluator V2,
  hardware, and transfer remain unapproved.
- A prospective elbow-locked static successor is frozen at SHA-256
  `52b836d4df577258ef3f9549e44c2135bf6202a37ac989439302423a7f1084fa`.
  It uses the fresh torque-off V4 anchor, retains the quarantined four cases
  and the same finite `48`-family/`288`-cell maximum grid, geometry, jaw,
  stroke, collision, camera, gateway, contact, and two-per-direction gates,
  reads no dynamic outcome, and changes only the IK active set so elbow flex
  must remain bitwise constant. Static simulation is its only execution
  authority.
- V1 stopped before model loading, grid enumeration, or output creation
  because its resolved V1 base retained a stale historical implementation
  binding instead of applying the already-frozen V4 binding. Runner closeout
  SHA-256 is
  `83e46134ea45b121fce5a86674fdd305d15ac8954ff3b712a28597525c20a144`.
  It contains no static result and cannot be interpreted as a family failure.
- Wiring-only V2 is frozen at SHA-256
  `8b1393209494b3b8f6a4630f5a1b7dd9e510178745e51a1e229f446b6b7858c6`.
  It changes only resolved-contract implementation binding; live seed, elbow
  lock, family universe, grid, gates, selection, model, outcome blindness, and
  authority are unchanged.
- V2 opened all `288` static cells and rejected all of them at the frozen IK
  residual gate before collision/contact evaluation; `0/48` families were
  eligible and no actions were selected. Receipt SHA-256 is
  `74ce790dfcbab663f10cdda10ff2af9270ded6352dd8b50c074c522342bf0479`.
  Implementation audit found that the wrapper applied the elbow lock and fresh
  anchor but omitted the intended V4 `35 mm` rear-standoff override, so the
  negative is valid only for the resolved original vertical-precontact path.
  Closeout SHA-256 is
  `5dd660cec8ec94c8170c96bed53f04e0bbaca78de9d4c000ff1840c1b15aa8de`.
- Static-only reachability localization found that the best original-path
  family still missed a stage by `28.305 mm`, while a `40 mm` target height
  admitted an effectively zero-residual position solution for `h1->g1`.
  Contact-height V3 is prospectively frozen at SHA-256
  `3d1e00daf8c673e8c509bc0e7dba146f4fc3b548ce2f9cea2ba80f6d53f2c404`.
  It explicitly materializes the intended `35 mm` rear-standoff path and
  replaces only the `10/14 mm` target heights with `36/40 mm`; the modeled
  first-contact witness must still stay at or below the unchanged `32 mm`
  gate. The `48` families, `288`-cell maximum, quarantine, stroke, jaw,
  collision, camera, gateway, contact-normal, direction, and authority gates
  remain unchanged.
- V3 also rejected all `288` cells at IK before collision/contact evaluation;
  receipt SHA-256 is
  `8a61f2501af576e22383d9419dfbad0bfcc872146292db100b92941e9f1e8a16`.
  Exact stage localization on `h1->g1` at the frozen `40 mm` target found
  low-precontact `1.406 mm`, contact `0.803 mm`, and pushed `0.212 mm`
  residuals, all below the `4 mm` gate, while high preclear and high retreat
  missed by `67.394 mm` and `40.153 mm`. Closeout SHA-256 is
  `03a73adefe514e4d1d68c37434f7b725a0859fc6bc69cfc274faa1716e4a39b7`.
- Path-shape-only V4 is frozen at SHA-256
  `3351b2c6b4967d05bfcc86e59c0439a42e653d98305bbe6a903db61b0f203f95`.
  It removes only the unreachable high-preclear and high-retreat stages and
  follows low precontact -> contact -> the unchanged `60 mm` pushed endpoint.
  It retains the fresh anchor, bitwise elbow lock, `36/40 mm` targets,
  `35 mm` backoff, `48` families, `288` cells, quarantine, jaw, collision,
  camera, gateway, first-contact-height, contact-normal, and two-per-direction
  gates. Static simulation is its only authority.
- V4 is the terminal static safety negative for the current nonresponsive
  elbow anchor. Receipt SHA-256
  `eceb14e34d32738151f06c0557c0a40f5bfdb71ac5d85774f44a61315a62b94e`
  records `279/288` IK rejects and `9/288` compiled cells across only two
  families. Every compiled cell introduces arm self-collision and contacts the
  pawn at `44.774--48.270 mm`, above the unchanged `32 mm` ceiling; one also
  fails contact normal. Eligible families remain `0/48`, directions `0/0`,
  dynamics false, and physical attempts `0/10`. Closeout SHA-256 is
  `0df993af40b6ea274878d874a315d46757f7a2e44a918730c948807f15395b33`.
- Safe in-scope elbow-locked alternatives are exhausted without weakening a
  gate: original path, binding-corrected finite grid, contact-height
  successor, and direct low path. CC03 cannot approve a task-scope mapping
  because no safe action exists at the physically nonresponsive elbow anchor.
  Further task progress requires a genuine hardware/external state change
  (responsive elbow repair, a different reachable actuator/tool, or an
  explicitly redesigned physically executable proof task).
- The existing Fable project thread completed a read-only adversarial review
  at commit `e4d4f3d`. Advisory summary SHA-256 is
  `96b5f641e624c70fac4d352819976d9fd8df3c138a0237f32491caa09cd50024`.
  Its independent pose sweep reproduced the locked-elbow sliding-push
  boundary, while identifying reachable `45--58 mm` pawn contact and a
  distinctly labeled directional-displacement/knockdown consequence as the
  only honest route to nonzero transfer before hardware repair.
- Fable's elbow diagnosis is adopted as a correction to the admission
  wording: the channel is nonresponsive for task admission but not proven
  mechanically dead. `CC03E` will bind full telemetry and a matched wrist
  control. RAM gain change remains deferred and unauthorized.
- More elbow-locked sliding-push successors, simulated-other-arm/tool routes,
  and new viewer/architecture work are receipt-backed rejects. `CC03K` is the
  prospectively frozen proof-task redesign; it cannot inherit a straight-push
  claim.
- `CC03E` V1 was prospectively frozen before physical execution at contract
  SHA-256
  `95666864bb00d8cb43308399eacf6c6bac377610d789b8f4b92e1640af5f317a`
  and executor SHA-256
  `7dd414f3793e4c40821adb45c89ad48721d827d5a420a3f85ae822eaac9a4db7`.
  A fresh torque-off preflight then found the elbow at `99.648352 deg` with a
  `102.109890 deg` calibrated maximum, making its `+3/+5 deg` targets
  inadmissible. V1 was not executed; closeout SHA-256 is
  `9bff36ce9a15922fc22b1ea6c8e788fc184d11a4c4b08bd2044604239092bc84`.
- `CC03E` V2 is frozen before motion at contract SHA-256
  `d221e9a925b5949ab7315485f8bd5e30c08f139aba00ac097d7976f8af8723b5`
  and executor SHA-256
  `f6f3e9466eeddb0beaf612a6ddfde8c6b46da38b3254eff30312a425f8af5998`.
  It records `-3/-5 deg` elbow destinations and their equal positive-direction
  returns, the full `+3/-3/+5/-5 deg` wrist-flex control, one torque off/on
  repeat, exact-target and calibrated-limit checks, native D405 enclosure,
  and six optional servo registers at `5 Hz`. It grants no pawn, task-attempt,
  gain-write, or configuration-write authority. `36` focused tests pass.
- V2 then stopped before output creation, camera open, gateway open, or motion
  because its executor expected a nested identity object instead of the
  reviewed preflight's top-level identity fields. Closeout SHA-256 is
  `ddb71eefe667525198cebf2eebe956636bb87ba9af23db32c296800a09bf371e`.
- `CC03E` V3 changes only that preflight parser, reusing the accepted parser
  from the live-anchored setup path. V3 is frozen before motion at contract
  SHA-256
  `31eb35429f37aaf82d0517d9be8e22b7bddb0afd061af2b5b528e037ec4067d9`
  and executor SHA-256
  `1e8e5fcb68b24a4d586f061d1941426aad65c3cbff6fd7d5508bb1c3674ab4f6`.
  All V2 probe geometry, telemetry, camera, stop, and authority fields remain
  unchanged. `36` focused tests pass.
- V3 opened the D405 and reviewed gateway, but the first planned row was
  already `0.5 deg` from the fresh anchor and arrived before a command clock
  interval existed. The gateway rejected it before sending any row. Receipt
  SHA-256 is
  `f2e778ed2d7c7fb4de9a648067ac29a68659c9c796c6923339bc413a32ef10d2`;
  closeout SHA-256 is
  `03b64d11f57038361127808ee387110a59ae50fcd9e2eef3ae937d50ac9c143a`.
  Camera enclosure completed, telemetry/sent rows are zero, and torque closed
  off.
- `CC03E` V4 changes only the trajectory prefix by adding one exact live-anchor
  row. V4 is frozen before execution at contract SHA-256
  `0bc1fdcd4fc6455b563e0174842e7ea9aa2b6ef37065b527d38e0a6490912976`
  and executor SHA-256
  `8201f67662e90221fa5c79552970f44c4cf215874f5754e59bb3deddd8c2c843`.
  Every V3 destination, timing, camera, telemetry, stop, and authority field
  remains unchanged.
- V4 completed all `217/217` exact rows, including the post-torque-cycle
  repeat, with D405 enclosure (`67` frames, zero large gaps) and torque-off
  cleanup. Receipt SHA-256 is
  `876cc47862b21f719646b7797b3e67c5dc8ec7e654735e984f4ee09265da666b`;
  closeout SHA-256 is
  `f9c5d8fac4c2b50eb46dcc0e566f076f216dd6925c121712b9f2675f3ea685a8`.
  The elbow achieved only `1.58--1.76 deg` of a five-degree probe in both
  directions while current/load rose as high as raw `24/196`; the matched
  wrist reached `4.84 deg`. Status stayed `0`, torque readback `1`,
  temperature `25--26 C`, and the torque cycle did not restore response. This
  is accepted as a mechanical-resistance signature. Gain writes remain
  unauthorized; elbow inspection/repair is a human boundary.
- `CC03K` V1 is prospectively frozen before model loading or enumeration at
  contract SHA-256
  `852dfc133f4c74e6ee25728610b4b77b73a76f63f237e7243ec6997fa430902b`.
  Its static-only grid covers the unchanged `48` nonquarantined families,
  three wrist rolls, and `45/50/55/60 mm` head-height targets (`576` maximum
  cells), with the elbow exact at `99.472527 deg`. It requires contact in the
  `35--65 mm` band, collision/board/exclusion, calibrated limit/rate, camera,
  and contact-normal gates, and selects one distinct family per direction.
  Future primary consequence is `>=20 mm` selected-pawn displacement inside a
  frozen `45 deg` direction quadrant with exclusions `<=2 mm`; topple/fall
  quadrant is secondary. Static and physical authority remain false beyond
  model loading/static enumeration, and this primitive cannot inherit a
  straight-push or chess-play claim.
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
- Strict causal episode contract, simulator adapter, physical-source adapter,
  serialization, immutability, and first-divergence tests.

Blockers:

- No approved physical/model mapping for straight sliding-push actions.
- Directional-displacement static feasibility is not yet frozen or tested.

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

- Freeze `CC03K` statically. Physical task authority remains false unless
  at least one safe family per direction survives and CC04 freezes the new
  evaluator/cases prospectively.
