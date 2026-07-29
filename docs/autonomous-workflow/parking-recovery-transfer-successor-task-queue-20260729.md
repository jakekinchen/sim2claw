# Parking-Recovery Transfer Successor Queue

Status: `RP02A_FROZEN_PENDING_SCOPED_OWNER_AUTHORIZATION`

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
| RP02A | `FROZEN_PENDING_SCOPED_AUTHORIZATION` | Re-run parking once with the single prospectively declared clock-compatibility repair. | Preserve every RP02 target, geometry, collision, telemetry, camera, stall, hold, cleanup, and claim gate. Add one exact anchor row at elapsed zero and one `0.2 s` lead period before every changed destination; no destination bytes, target, limits, clipping, smoothing, or offsets change. | Any rate-limit/clamp/correction, target above `93 deg`, stall, camera/writer loss, held-joint drift, or cleanup failure safely stops. No reuse of the spent V1 authorization. |
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

Bind a new time-bounded owner authorization for the exact RP02A packet, then
execute it exactly once. The V1 authorization is spent and cannot be reused.
The only successor change is the prospectively frozen clock-compatible anchor
and target-transition timing; this is a localized gateway-contract repair, so
Fable is reserved rather than invoked.

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
