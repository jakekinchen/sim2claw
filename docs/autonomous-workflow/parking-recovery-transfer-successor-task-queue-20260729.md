# Parking-Recovery Transfer Successor Queue

Status: `RP04D_REACHABLE_LOCK_STATIC_SCREEN_FROZEN_PENDING_ONE_RUN`

Created: `2026-07-29`

Branch: `main`

## Mission

Reach nonzero bidirectional task transfer through the smallest evidence-backed
route while preserving every collision, evidence, action, camera, gateway, and
attempt gate.

The prior causal-closure queue remains immutable authority for CC00--CC15 and
its terminal result at the exact `99.472527 deg` elbow lock. This successor
does not rewrite that result. RP00--RP03D also preserve the achieved-lock
parking result and the subsequent static passes and dynamic negatives. Those
negatives close the locked-elbow task route; they do not erase the separately
frozen natural-anchor canonical wrist-path V5 simulator pass.

## Starting ledger

- REAL->SIM successes/attempts: `0/0`.
- SIM->REAL successes/attempts: `0/0`.
- Physical pawn-task attempts: `0/10`.
- Global physical/model mapping: not approved.
- Policy-ranking evidence: `INSUFFICIENT_PHYSICAL_SAMPLE`.
- Physical authority: false.

## Queue

| ID | Status | Required outcome | Acceptance gate | Stop / redirect |
|---|---|---|---|---|
| RP00 | `DONE_PASS` | Prospectively freeze and run one route-level parking-target certificate across elbow locks `{97,95,93,91,90,88} deg`. | Existing CC03K family universe, compiler, collision/contact/camera/gateway gates, and false physical authority remain unchanged. At least one distinct family per direction passes at a maximum viable angle and again at a passing target at least `2 deg` lower. Code, contract, tests, and advisory predate the single run. | Receipt `e1bc7d8e...` passes: `97/95 deg` reject, `93/91/90/88 deg` pass with `1` family per direction. Threshold `93 deg`; target `91 deg`. No motion or task attempt. |
| RP01 | `DONE_PASS` | Freeze a high-clearance, contact-impossible elbow parking transaction to the RP00 target. | Fresh torque-off anchor bound; no-op setup; full `[88, 99.6] deg` corridor previewed every `0.1 deg`; moving chain stays at least `120 mm` from table, board, and pawns; all robot contacts remain absent; at most `5 deg` requested per step; read/verify each step; abort after two consecutive steps with less than `0.3 deg` progress; `15 s` hold drift below `0.5 deg`; torque-off cleanup; no task/pawn contact reachable. | Receipt `e9e99a4a...` passes; Fable independently returns `CONTINUE_RP02_FREEZE`. No motion or task attempt. |
| RP02 | `DONE_FAIL_CLOSED_BEFORE_MOTION` | Execute parking once under separately reopened physical authority. | Packet SHA `79382c1a...`; hash-pinned executor; fresh timestamped preflight; held-joint and camera/writer stops; exact C922+Pi enclosure; reviewed gateway only; target reached; hold gate passes; exact receipt; torque off and `60 s` read. No retry without new preregistration. | V1 stopped before motion because its first changed target arrived at zero command time. Cameras completed, torque is off, pawn/task ledgers remain unchanged. |
| RP02A | `DONE_SAFE_STALL_ABOVE_CERTIFICATE` | Re-run parking once with the single prospectively declared clock-compatibility repair. | Preserve every RP02 target, geometry, collision, telemetry, camera, stall, hold, cleanup, and claim gate. Add one exact anchor row at elapsed zero and one `0.2 s` lead period before every changed destination; no destination bytes, target, limits, clipping, smoothing, or offsets change. | Exact rows executed, but the elbow stalled at `94.901099 deg`; gateway released torque and postflight passed. No pawn contact or task attempt. |
| RP02B | `V1_RANGE_REJECT_V2_FROZEN_PENDING_ONE_RUN` | Test a bounded no-write deep-request corridor after the measured proportional-torque stall. | V1 honestly rejected because the torque-off observation exceeded the calibrated command maximum. V2 sweeps only `[80.0,102.1] deg` at `0.1 deg`; strict contact-free through `99.6 deg`; above it allow only live-anchor modeled pairs with at most `0.5 mm` additional penetration; preserve `120 mm` moving-chain/environment clearance and false physical authority. | Any new/worsened contact, range, clearance, or inventory defect rejects without motion. A pass opens one prospectively frozen command transaction, not hardware authority. |
| RP02C | `FROZEN_PENDING_SCOPED_AUTHORIZATION` | Execute one no-write read-conditioned deep-request parking transaction. | Start floor `86 deg`; one prospective deepen to `82 deg`; changed requests remain at most `5 deg`; success only in `[88,93] deg` plus `15 s / 0.5 deg` hold; elbow current `>150` raw for `1 s` or temperature `>45 C` stops; exact cameras/gateway/cleanup/one-execution latch. | Any out-of-band, current, temperature, drift, camera, exact-action, or cleanup defect stops safely. Still zero task attempts. |
| RP02D | `DONE_PASS` | Repeat the successful band-entry mechanism with only the first/recurring hold reset moved from `4.0 s` to `2.0 s`. | Preserve V3 requests, `[88,93] deg`, `15 s / 0.5 deg`, current/temperature, geometry, cameras, exact gateway, cleanup, and zero task authority. | Passed at `92.439560 deg`; `15.017 s` hold, `0.175824 deg` drift, both cameras complete, torque off. |
| RP03 | `DONE_PASS` | Freeze fresh task actions at the achieved lock. | Exact RP02D torque-on pose, unchanged bounded family universe and static gates; at least one distinct family per direction; exact bytes predate outcomes. | Passed with exactly one eligible family per direction; no dynamic or physical execution. |
| RP03A | `DONE_IMMUTABLE_NEGATIVE` | Replay both exact achieved-lock actions under baseline and timing stress. | Preserve exact action bytes, 40 Hz row order, five reset deltas, `36.025 mm` progress, contact/exclusion/no-lift/collision/camera gates, direct target plus diagnostic `0.11 s` ZOH, and ObservableEpisode.v2-min first-divergence traces. Both cases must pass both paths. | Both directions rejected: contact occurred but progress and no-lift failed. Identity, camera, collision, and exclusions passed. |
| RP03B | `DONE_TERMINAL_STATIC_NEGATIVE` | Compile one bounded longer-stroke successor at the exact achieved lock. | Change only stroke from `40 mm` to the previously preregistered `66 mm`; preserve the 48-family universe, 576-cell bound, ranking, wrist/contact grid, IK, collision, contact, camera, calibrated-range, gateway-rate, one-family-per-direction, and false physical authority. | `0/576` cells were eligible; the uniform longer-stroke mechanism is closed without dynamics or hardware. |
| RP03C | `DONE_TERMINAL_DYNAMIC_NEGATIVE` | Replace only sparse joint interpolation between the existing 35 mm precontact, contact, and 40 mm pushed Cartesian endpoints with a deterministic chord-error-constrained corridor. | Static receipt `5a9230fa...` passed all 576 cells with one selected family per direction. Dynamic receipt `8b7a889d...` then ran all `20` frozen episodes. | `0/20` passed; every episode still failed progress and no-lift. Cartesian interpolation bow alone is closed. |
| RP03D | `DONE_TERMINAL_DYNAMIC_NEGATIVE` | Add one small tangent-seat waypoint after contact without changing the original push endpoint. | Static receipt `488bf150...` passed all 576 cells with one selected family per direction. Dynamic receipt `8bb253ef...` ran the exact 20 frozen episodes. | `0/20` passed. The tangent-seat and locked-elbow task route are closed without hardware. |
| RP04 | `DONE_EXISTING_SIMULATOR_PASS_RECONCILED` | Select the strongest already frozen natural-anchor simulator route without using later outcomes to alter its actions. | Canonical wrist-path V5 predates this successor and has exactly two families per direction across direct/ZOH and five resets, with exact actions and ObservableEpisode traces. | Receipt `cf21bd8c...` passes `40/40`; its four action tensors are immutable transfer candidates. This does not approve mapping or hardware. |
| RP04A | `DONE_TERMINAL_V5_TRACKING_NEGATIVE` | Approve or reject the coordinated-unloading hypothesis before any task packet. | The elbow-only fit passed its untouched tail, then the exact 20-episode challenger preserved all V5 requested bytes and the canonical evaluator. | `0/20` task episodes passed. All four V5 actions are closed for hardware; no retry, task-conditioned refit, action repair, or gate relaxation. |
| RP04C | `V2_ONE_PHYSICAL_EXECUTION_AUTHORIZED` | Extend execution evidence toward the smallest V5 contact-angle corridor without pawn or board contact. | V2 static receipt `accd098e...` passes: `1105` rows, reachable `-60 deg` pan, `-10.409 deg` elbow, `75.874 mm` worst-case clearance, both scenes contact-free, and all route gates. Packet commit `6ca36ab` passed four focused tests; one packet-hash-bound authorization is active until `12:29:14 CDT`. | No V1 retry. Any live start, camera, gateway, tracking, boundary, or cleanup defect stops safely; still zero task attempts. |
| RP04D | `REACHABLE_LOCK_STATIC_SCREEN_FROZEN_PENDING_ONE_RUN` | Compile task geometry around the physically observed elbow floor instead of ideal V5 angles. | Screen exactly `{85, 80, 77.5} deg` with the unchanged directional-displacement static family universe. `80 deg` is prospectively preferred as a `2.59 deg` margin above the observed `77.4066 deg` floor. Require at least one family per direction; no dynamic or physical task outcome enters selection. | If preferred `80 deg` fails, do not cherry-pick after outcomes. A pass may freeze only a dynamic simulator screen, not hardware. |
| RP04B | `PENDING` | Complete one REAL->SIM pawn-task transfer. | Camera-owned physical source success with exact evaluator outcome, then byte-identical CPU/fp64 replay of its action and initial state; complete object/contact/outcome and first-divergence traces. | At most three task attempts; diagnose after two good-tracking failures. Failures remain in the denominator. |
| RP05 | `PENDING` | Complete one distinct SIM->REAL pawn-task transfer. | V5 simulator success and robustness predate the exact-action freeze; use a distinct family; camera-owned physical success with identical requested bytes and declared physical timing. | At most three task attempts; failures remain in the denominator. |
| RP06 | `PENDING` | Pilot predictive policy ranking with three prospectively declared deterministic controllers. | Freeze controllers, ID/OOD distribution, rank hypothesis, and six-case physical sampling before outcomes; report exact denominators, Wilson intervals, and failure map. | Small evidence stays a pilot; do not claim general predictive authority. |
| RP07 | `PENDING` | Package evidence in Studio and the TaskWorldBundle. | Exact ledgers, hashes, source footage, simulator twins, residual timelines, mapping scope, policy uncertainty, failures, tests, cleanup, commit, and push agree. | Missing physics or physical evidence remains visibly missing. |
| RP08 | `CONDITIONAL_BLOCKER_ONLY` | Return the result to Fable only for an unresolved material trajectory blocker or final defect check. | Include the bounded question and exact repository evidence; independently reconcile recommendations. | Do not consume Fable for routine milestone updates. |

## RP00 freeze

- Lock grid: exactly `[97, 95, 93, 91, 90, 88] deg`.
- One run after the implementation, contract, test, and this queue are
  committed and pushed.
- The highest passing lock is the feasibility threshold.
- The recommended parking target must itself pass and be at least `2 deg`
  lower than that threshold.
- No grid expansion, task outcome, physical outcome, dynamic replay, mapping
  promotion, camera, gateway, serial, or physical motion is authorized.

## Current next step

Run the already frozen three-lock RP04D static task screen exactly once. If the
predeclared `80 deg` lock yields at least one family per direction, freeze its
exact action tensors for direct/ZOH dynamic replay before considering any
physical task packet. If it fails, preserve the bounded negative.

## RP00 immutable result

- Freeze commit: `9ebd45a`.
- Contract SHA-256:
  `fb0c8ab52d6b557c143af3a655f886e529c798c941abe954f33eab8851cb3617`.
- Receipt SHA-256:
  `e1bc7d8e1bbeeaa4b1e08f26d7e609e2714c33800d22899bd876f7298c75db7b`.
- `97 deg`: reject, `0` eligible families.
- `95 deg`: reject, `0` eligible families.
- `93 deg`: pass, `1` family per direction.
- `91 deg`: pass, `1` family per direction.
- `90 deg`: pass, `1` family per direction.
- `88 deg`: pass, `1` family per direction.
- Maximum viable lock: `93 deg`.
- Recommended parking target: `91 deg`, a passing `2 deg` margin.
- Physical task ledgers remain REAL->SIM `0/0`, SIM->REAL `0/0`, task
  attempts `0/10`.
- Physical authority remains false.

## RP01 immutable result

- Freeze commit: `dee24a0`.
- Contract SHA-256:
  `ec878defa98e1c46ac6e3184c6fda1553d4bb0a7ae60dc2fc1cfd327fad9d5e4`.
- Receipt SHA-256:
  `e9e99a4ad774a04e5dc031a9b6060df6e32f7ceceb6e56fa40cfba61f481fc1f`.
- `117 / 117` full-interval poses remained in calibrated range.
- Robot contact pairs: `0`.
- Minimum moving-chain clearance: pawns `150.831 mm`, board `202.394 mm`,
  table `218.394 mm`.
- Fable independently returned `CONTINUE_RP02_FREEZE`.
- Physical motion and task-attempt ledgers remain unchanged.

## RP02 reviewed packet

- Repair commit: `7a33fcb`.
- Packet SHA-256:
  `79382c1aa0a9ec6d292300bb34dcf1c910fafb6a64f57bfa8e549c87c79abfe6`.
- Executor SHA-256:
  `f01c89816d72ad4212b2a26323895755300795dd296942434d9f0788592728fa`.
- Focused tests: `20 passed`.
- Fable verdict: `READY_FOR_TIME_BOUNDED_OWNER_AUTHORIZATION`.
- Fable is now reserved for genuine trajectory blockers, not routine
  milestone review.
- Physical authority remains false until a separate authorization document
  validates.

## RP02 immutable V1 execution result

- Authorization commit: `e98d53d`.
- Packet SHA-256:
  `79382c1aa0a9ec6d292300bb34dcf1c910fafb6a64f57bfa8e549c87c79abfe6`.
- Receipt SHA-256:
  `64b1d498536a68dfd20c421251ae8d7884075a86006979f8b216893cfa17acd3`.
- The gateway established the torque-on anchor, but rejected the first
  `5 deg` destination before sending it because it was presented at
  effectively zero elapsed command time.
- Sent motion rows: `0`; telemetry rows: `0`; pawn contacts: `0`; task
  attempts: `0`.
- Both camera receipts completed and the configuration-free postflight
  confirmed follower torque off.
- This is a packet/compiler timing defect, not an elbow-mechanism result.

## RP02A prospective one-change repair

- Packet:
  `configs/hardware/parking_transaction_execution_v2.json`.
- Predecessor closeout:
  `configs/decisions/parking_transaction_execution_v1_closeout.json`.
- Row zero is the exact live torque-on anchor.
- Every changed destination receives one `0.2 s` lead period. With the
  unchanged maximum destination delta of `5 deg`, this is below the reviewed
  gateway allowance of `60 deg/s * 0.1 s = 6 deg`.
- Focused executor and gateway suite: `42 passed`.
- Physical authority remains false until a new packet-hash-bound,
  time-bounded authorization validates.

## RP02A immutable V2 execution result

- Packet SHA-256:
  `af3149ccceaf7d49b0f1765c11afbc66c7782a0d7968a9815042e90337e58a6d`.
- Receipt SHA-256:
  `fa328c856f41ecc703d3c21d76fae043355007355b9574c1da196d73e7a4f8de`.
- Exact rows executed with no rate limiting or safety clamping.
- The elbow progressed `99.472527 -> 94.901099 deg`, then the gateway stopped
  after `5 s` without measurable progress under a `91 deg` request.
- Plateau current was approximately `16--23` raw, load `192`, temperature
  `29 C`; torque-off postflight passed at `103.428571 deg`.
- Both cameras completed; pawn contacts and task attempts remain zero.
- This is the genuine trajectory blocker that triggered one targeted Fable
  consult under the reserved-use policy.

## RP02B prospective deep-request preview

- No servo configuration write is permitted.
- Requested floors will be considered only after a motion-free corridor
  preview passes.
- The strict contact-free segment is `[80.0,99.6] deg`.
- The live anchor segment ends at `103.5 deg` and may contain only the three
  model contact pairs already present at the exact torque-off anchor, with at
  most `0.5 mm` worsening.
- Fable suggested an upper bound of `104.5 deg`; independent reconciliation
  rejected it because modeled penetration worsened beyond the bound.
- Physical authority remains false.

## RP02B immutable V1 range rejection

- Receipt SHA-256:
  `0e409fab5447cc7c767b2f158dea9bea51ad1d8a1a1dc322688e3b6220a5d340`.
- Contact violations: `0`.
- Minimum pawn/board/table clearances:
  `140.575 / 186.980 / 202.980 mm`.
- The only failed gate was `joint_ranges_ok`: `103.428571 deg` is a
  torque-off observation above the calibrated command maximum
  `102.109890 deg`.
- V2 changes only the upper command-preview bound to `102.1 deg`. The
  reviewed live-anchor gateway's separately bounded `3 deg` torque-on anchor
  snap remains responsible for moving from the observation into the valid
  command range.

## RP02B immutable V2 pass

- Receipt SHA-256:
  `ef4a2b45a4355390205b3cd68a4e1058c82f70f0a294a228c9c658db8da3fb63`.
- `222 / 222` poses over `[80.0,102.1] deg` remained in calibrated range.
- Contact violations: `0`.
- Minimum pawn/board/table clearances:
  `145.387 / 192.554 / 208.554 mm`.
- No hardware, camera, serial, torque, pawn contact, or task attempt occurred.

## RP02C prospective transaction

- Packet:
  `configs/hardware/parking_transaction_execution_v3.json`.
- No gain, EEPROM, current-limit, torque-limit, or other configuration write.
- Read-conditioned requests descend at most `5 deg` per changed row toward
  `86 deg`, with one bounded `82 deg` fallback only after two no-progress
  intervals.
- A result counts only inside `[88,93] deg` after a `15 s`, `0.5 deg` hold.
- Current, temperature, held-joint, camera, gateway, and torque-off cleanup
  remain fail-closed.
- Physical authority remains false pending a separate exact packet-hash-bound
  authorization.

## RP02C immutable band-entry / hold-timing result

- Receipt SHA-256:
  `99619e6f77f8fdc9a812e11f475d21305f85163930fbcf5a4375977a0543ad01`.
- Observed elbow entered the certified band at `92.087912 deg` under the exact
  `88.406593 deg` deep request.
- The first `16` hold rows had `0.0 deg` observed drift, current at most `20`
  raw, and temperature `29 C`.
- The gateway stopped before the first planned `4 s` reset because its
  `5 s` stall clock carried approximately `2 s` from the final descent
  interval. Torque-off and both cameras completed.
- RP02D changes only the reset cadence to `2 s`; task attempts remain `0/10`.

## RP02D immutable achieved-lock result

- Receipt SHA-256:
  `1b3c792007b02f5e7118a6a3ddb73a4b97520a3ba1a3df89984214cb7e281578`.
- The robot reached `92.439560 deg` using the exact no-write deep request and
  held for `15.017248 s` with maximum drift `0.175824 deg`.
- Maximum observed elbow current remained low; temperature stayed
  approximately `29--30 C`.
- C922 and Pi camera receipts completed and cleanup confirmed torque off.
- This is a camera-backed mechanism success, not a pawn task attempt or
  transfer.

## RP03 immutable exact-lock static result

- Freeze commit: `c1a2f84`.
- Receipt SHA-256:
  `3a935d15860b732975d2839a4aba7fcda2239ff32e658b2df5fe5dc5ea45204b`.
- `brown_pawn_g2__g2_f2` is the frozen REAL->SIM family at action SHA-256
  `a19730f789fae4f813e31497925082e722767649afa08f208dbd49ba0179e042`.
- `brown_pawn_f1__f1_f2` is the frozen SIM->REAL family at action SHA-256
  `2a1a7ff9ff271c93c05afff0f9723ff0fa87862f8a1099eae8763b6b1a416cb4`.
- Both actions start at the exact RP02D achieved pose and keep the elbow
  model coordinate exactly constant at `92.439560 deg`.
- All selected static collision, contact, calibrated-range, gateway-rate, and
  camera gates passed. Mapping remains
  `provisional_range_audit_blocked`; physical authority remains false.

## RP03A immutable exact-lock dynamic negative

- Receipt SHA-256:
  `1588fd2bd559d5de7bd000e607f75b56c1c48e6b6624b04e2844c161cc3591bf`.
- Direction counts are REAL->SIM `0`, SIM->REAL `0`.
- All requested/mapped/sent identity, 40 Hz, camera, collision, exclusion,
  selected-contact, and gateway-rate checks passed.
- The 40-mm actions undertraveled: nominal direct progress was
  `16.217812 mm` for `g2->f2` and `5.290861 mm` for `f1->f2`, below the
  unchanged `36.025 mm` gate. Pawn vertical rise also exceeded `2 mm`.
- This is the first causal result at the achieved lock: RP03B changes stroke
  only to the already-preregistered `66 mm` bound. No physical attempt
  occurred.

## RP03B immutable 66-mm static negative

- Freeze commit: `42adc1e`.
- Receipt SHA-256:
  `a0b9615aeb1dfe519e1f6c4d3e04a8d754b013e215811ff451127e6d0fd14102`.
- All `576` cells were evaluated exactly once: `486` compile rejects and
  `90` static rejects, with `0` eligible families.
- The longer low path caused collision/contact-normal defects and widespread
  locked-IK infeasibility. It therefore cannot be sent to dynamics or
  hardware.
- The result rules out uniform stroke extension; it does not weaken the
  successful RP02D hold or RP03 exact-lock static family evidence.

## RP03C immutable Cartesian-corridor static pass

- Freeze commit: `dbe490c`.
- Receipt SHA-256:
  `5a9230faf9bb8ebdb8a7ef887f08fc4c72b6dc9684552e52903e3a08ad734d05`.
- All `576` frozen cells were evaluated: `483` compile rejects, `89` static
  rejects, and `4` eligible cells spanning exactly one selected family per
  direction.
- REAL->SIM action `cb819555...` has `515` rows; its maximum emitted-row
  Cartesian chord error is `0.404183 mm`.
- SIM->REAL action `94842077...` has `676` rows; its maximum emitted-row
  Cartesian chord error is `0.493325 mm`.
- Both actions preserve the exact `40 mm` endpoint, `35 mm` precontact,
  `40 Hz` timing, `92.439560 deg` elbow lock, contact grid, and all static
  safety/visibility/gateway gates. Post-contact task-axis backtracking is
  zero.
- This proves a statically admissible planar corridor, not task consequence.
  Physical attempts and transfer ledgers remain unchanged.

## RP03C immutable Cartesian-corridor dynamic negative

- Freeze commit: `0cf6956`.
- Receipt SHA-256:
  `8b7a889d231877d4163ff453327d74887b7870ea3f96fb68be6ed150962a60a5`.
- All `20` episodes ran: two directions, two plant paths, and five reset
  variants. Passing episodes: `0`.
- Every episode preserved identity, selected contact, exclusions, collision,
  camera, and gateway compatibility, but failed both progress and no-lift.
- Nominal direct REAL->SIM progress/rise was
  `12.363033 / 13.881540 mm`; SIM->REAL was
  `5.624995 / 4.877620 mm`.
- The interpolation-bow hypothesis is rejected without spending a physical
  attempt. RP03D changes only one prospectively frozen `1.5 mm`
  task-horizontal tangent-seat waypoint.

## RP03D immutable tangent-seat static pass

- Freeze commit: `dfd849a`.
- Receipt SHA-256:
  `488bf150d6706435a5a22be60797ece17b75730ab64c6feeba3c3f631a2f555c`.
- All `576` cells ran: `483` compile rejects, `89` static rejects, and `4`
  eligible cells spanning exactly one selected family per direction.
- REAL->SIM action SHA `993c3e92...` has `514` rows; SIM->REAL action SHA
  `7fb77329...` has `676` rows.
- Both preserve the original `40 mm` endpoint and contain the exact frozen
  `1.5 mm` tangent-seat waypoint. Chord error remains below `0.5 mm`,
  task-axis backtracking is zero, and all static gates pass.
- This opens exactly one 20-episode dynamic run, not hardware.

## RP03D immutable tangent-seat dynamic negative

- Freeze commit: `2c13895`.
- Receipt SHA-256:
  `8bb253ef0c9b3e6e9c960e90e68524f36f5418b74d985906aa077c1e4df5ff28`.
- All `20` episodes ran across two directions, two plant paths, and five reset
  variants; passing episodes: `0`.
- Identity, selected contact, exclusions, collision, camera, and gateway-rate
  gates passed, but the task progress and no-lift gates did not.
- One reset produced large progress by tipping/launching the pawn and still
  failed the no-lift gate. It is not a task success.
- This closes further local edits around the locked-elbow action family and
  spends no physical task attempt.

## RP04 reconciled natural-anchor V5 simulator pass

- Temporal closeout:
  `configs/decisions/canonical_wrist_path_selected_temporal_v5_closeout.json`.
- Temporal receipt SHA-256:
  `cf21bd8cc7b408d50ffcaae039fa993173514d49c4abf6f455bb7b484af0f36a`.
- The frozen screen contains `40` passing ObservableEpisodes: four cases,
  direct target plus diagnostic `0.11 s` ZOH, and five reset variants.
- Direction counts are exactly REAL->SIM `2` and SIM->REAL `2`.
- The three single-lane candidates are `tan_pawn_h7__h7_h8`,
  `tan_pawn_d7__d7_c7`, and `tan_pawn_f7__f7_e7`. Their action tensors start
  at the natural torque-off anchor and remain byte-frozen.
- The two-lane `tan_pawn_d7__d7_e7` remains an untouched reserve because it
  approaches a shoulder-lift limit more closely.
- V5 is simulator evidence only. Its mapping label remains
  `provisional_range_audit_blocked`, and physical authority remains false
  until RP04A passes.

## RP04A coordinated-unloading blocker decision

- The targeted Fable consult selected one no-contact coordinated V5 prefix
  instead of a fourth locked-elbow task mechanism.
- Independent reconciliation rejected a one-shot row-736 probe because the
  zero-rigid-transform stress scene contacts a different pawn at row `531`.
- The frozen row-490 prefix remains at least `40` source rows (`1.0 s`) before
  contact under both scene hypotheses and reaches elbow `39.718344 deg` from
  the `99.472527 deg` source anchor.
- Frozen source action: `tan_pawn_f7__f7_e7`, SHA-256 `e9f128e0...`.
- Frozen gateway segment boundaries: `[0, 433, 490]`; maximum permitted
  per-origin excursion: `80 deg`.
- This is a coordinated-unloading diagnostic only. It cannot move hardware,
  approve mapping, count a task attempt, or support transfer until the static
  compiler passes and a separate packet is frozen.

## RP04A immutable static pass

- Freeze commit: `b5becce`.
- Receipt SHA-256:
  `bfe84b39a01f1e8527da7ab59a1f2339f1a8831a9ef2408d38683330ee909800`.
- Physical-prefix SHA-256:
  `d0990da76953d742aa4a3688cd32feba3266f8a32206fdd2a1880e0ba8167021`.
- All `491` rows are inside calibrated limits and gateway rates.
- Registered and uncorrected stress scenes have no new robot contact and no
  selected-pawn contact through row `490`.
- Segment maximum body excursions are `73.999345 deg` and `11.385180 deg`,
  both below the frozen `80 deg` limit.
- Physical motion, task attempts, mapping approval, and transfer remain false.

## RP04A immutable physical result

- Execution receipt SHA-256:
  `1999c73276264269b14dd6319fffdccebdb143d890e19c0c3216b5d51cee771f`.
- All `434` forward source rows were requested unchanged and sent within
  `0.25 deg`; safety clamps: `0`.
- Observed elbow moved `100.087912 -> 50.593407 deg`, a new
  `49.494505 deg` coordinated-motion result.
- Maximum elbow requested/observed error was `4.840108 deg`, but error remained
  above `3 deg` for `10.325 s`; terminal elbow residual was `3.654885 deg`.
- The frozen `2 deg` boundary gate failed, so mapping remains unapproved and
  the second source segment did not run.
- Pi camera review shows no pawn or board contact. Controlled return completed
  within `1.670330 deg`; fresh postflight verified torque off.
- This is a meaningful physical mechanism advance and an exact mapping
  negative, not a pawn-task attempt or transfer.

## RP04A immutable tracking-fit result

- Fit-freeze commit: `cdc58c0`.
- Fit receipt SHA-256:
  `d51d316a18e42e30e9bb6db17a8e41a6ecc79fee914753ab0b81b7073360454e`.
- The first `304` no-contact forward rows fit only the elbow sample-domain
  response; the final `130` rows remained untouched chronological validation.
- Frozen parameters: `alpha = 0.040771249854421744`;
  bias `= 0.05965835013118282 deg/sample`.
- Heldout RMS error: `0.386783 deg`; maximum error: `0.910418 deg`.
- Relative improvement over requested-as-observed: `90.740966%`.
- No task outcomes, other joints, causal latency labels, physical motion,
  task attempts, or mapping approval entered this result.

## RP04A immutable tracking-temporal result

- Freeze commit: `91d2dd3`.
- Receipt SHA-256:
  `da3badac7a0e4af54bbdfd53f4f95af19da36e988d973ec78836ddca47ac6ad5`.
- The prior canonical direct/ZOH screen remains `40/40`.
- The elbow tracking challenger passed `0/20`; passing case counts are
  REAL->SIM `0` and SIM->REAL `0`.
- `h7 -> h8` lost selected contact entirely. The other three cases produced
  noncanonical collision and lift consequences.
- Every case extrapolated materially beyond the single no-contact physical
  support, from `592` to `2262` applied rows.
- This closes V5 for hardware without spending a physical pawn-task attempt.

## RP04C V1 immutable physical result

- Packet freeze commit: `ad761c1`; authorization commit: `229b7c7`.
- Receipt SHA-256:
  `88639f500df4e6c286bcc1a8480deaf366c0e0b5090d1634dab394dc67c9787b`.
- The first `123` route rows executed, rotating shoulder pan from the returned
  anchor to an observed minimum of about `-64 deg`.
- The requested `-115 deg` boundary remained `51 deg` away and the gateway
  reported shoulder-pan stall/safety clamp, so the elbow sweep never opened.
- Both cameras completed; visual review found no pawn or board contact.
- Controlled return completed within `1.495 deg`; postflight torque is off.
- No physical pawn-task attempt or mapping approval occurred.

## RP04C V2 immutable physical result

- Packet freeze commit: `6ca36ab`; authorization commit: `23fc410`.
- Receipt SHA-256:
  `5b8ecb4376533b1df21c369ddf7f2cfff5aa2b8c875a88363ca1525fceca27eb`.
- The reachable `-60 deg` pan boundary passed and `501` forward route rows
  executed before the gateway's five-second elbow no-progress stop.
- Minimum observed elbow: `77.406593 deg`, a new physical range result.
- Both cameras completed; visual review found no pawn or board contact.
- Controlled return completed within `1.495 deg`; postflight torque is off.
- This is a physical configuration-space advancement, not a task attempt,
  mapping approval, or transfer.

## RP01 freeze

- Fable independently returned `CONTINUE_RP01_FREEZE` after auditing RP00.
- Fresh configuration-free follower read passed with torque off, no device
  rewrite, follower
  `/dev/cu.usbmodem5B3D0406411`, and calibration SHA-256
  `192404b6d3c1337495d69649969459aa9d3f66816cd916c67da2588815e93ec4`.
- Fresh elbow anchor: `99.47252747252747 deg`.
- Target: `91 deg`; primary success at or below `92 deg`; marginal success at
  or below `93 deg`; above `93 deg` terminal.
- Frozen control law:
  `request_i = max(91 deg, read_(i-1) - 5 deg)`, then wait `2 s` and reread.
- Abort after two consecutive iterations below `0.3 deg` progress; maximum
  twelve requests.
- Setup is a no-op at the current anchor. The complete `[88, 99.6] deg`
  corridor, sampled every `0.1 deg`, must prove at least `120 mm` moving-chain
  clearance to table, board, and pawns plus zero robot contact.
- Telemetry is `5 Hz` on all six servos; hold is `15 s` with at most
  `0.5 deg` elbow drift.
- C922 and Pi cameras enclose any later execution; D405 remains optional.
- Cleanup disables torque and takes a configuration-free read after `60 s`;
  there is no return route.
- RP01 is setup/recovery evidence, not task evidence, and cannot change the
  `0/10` task-attempt ledger.
- Contract:
  `configs/hardware/parking_transaction_recovery_v1.json`.
- Physical authority remains false.
