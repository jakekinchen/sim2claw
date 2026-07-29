# Parking-Recovery Transfer Successor Queue

Status: `RP02D_HOLD_TIMING_PACKET_FROZEN`

Created: `2026-07-29`

Branch: `codex/bidirectional-transfer-goal-loop-20260728`

## Mission

Convert the new lock-angle hypothesis into the smallest honest route to
nonzero task transfer while preserving every collision, evidence, action,
camera, gateway, and attempt gate.

The prior causal-closure queue remains immutable authority for CC00--CC15 and
its terminal result at the exact `99.472527 deg` elbow lock. This successor
does not rewrite that result.

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
| RP02D | `FROZEN_PENDING_SCOPED_AUTHORIZATION` | Repeat the successful band-entry mechanism with only the first/recurring hold reset moved from `4.0 s` to `2.0 s`. | Preserve V3 requests, `[88,93] deg`, `15 s / 0.5 deg`, current/temperature, geometry, cameras, exact gateway, cleanup, and zero task authority. | Any failure stops safely. No second mechanism change or configuration write. |
| RP03 | `PENDING` | Freeze fresh task actions at the achieved lock. | Strict unchanged gates; fresh C922 scene admission; at least one distinct family per direction; exact bytes and evaluator freeze predate outcomes. | Zero eligible families ends the successor without a task attempt. |
| RP04 | `PENDING` | Complete a REAL->SIM task transfer. | Camera-owned physical success, then byte-identical CPU/fp64 replay success; first-divergence trace complete. | At most three task attempts; diagnose after two good-tracking failures. |
| RP05 | `PENDING` | Complete a distinct SIM->REAL task transfer. | Simulator success and robustness predate freeze; distinct family; camera-owned physical success with identical bytes. | At most three task attempts; failures stay in the denominator. |
| RP06 | `PENDING` | Approve a task-bounded mapping for the successful locked-elbow slice. | Scope and factors are preregistered; accepted wrist/pan/lift evidence plus successful first-divergence bounds support the exact task slice. | Never relabel as global mapping approval. |
| RP07 | `CONDITIONAL` | Pilot predictive policy ranking. | At least four paired physical cases remain within the ten-attempt ledger; controller set and ranking hypothesis freeze first. | Fewer than four pairs remains `INSUFFICIENT_PHYSICAL_SAMPLE`. |
| RP08 | `PENDING` | Package the result and return it to Fable for a defect check. | Exact ledgers, hashes, failures, mapping scope, policy limitations, Studio episodes, tests, cleanup, commit, and push agree. | Reopen the responsible card for a concrete in-scope defect. |

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

Commit and push RP02D, bind a fresh one-execution time-bounded authorization,
and execute once. A pass opens exact achieved-angle task freeze; it still
does not count as a task attempt or transfer.

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
