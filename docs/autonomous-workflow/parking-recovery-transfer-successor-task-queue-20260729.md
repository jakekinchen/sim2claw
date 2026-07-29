# Parking-Recovery Transfer Successor Queue

Status: `ACTIVE_RP02_EXECUTION_PACKET_FREEZE`

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
| RP02 | `IN_PROGRESS_PACKET_FREEZE` | Execute parking once under separately reopened physical authority. | Hash-pinned executor; fresh timestamped preflight; held-joint and camera/writer stops; exact C922+Pi enclosure; reviewed gateway only; target reached; hold gate passes; exact receipt; torque off and `60 s` read. No retry without new preregistration. | Final above `93 deg`, stall, camera/writer loss, held-joint drift, or cleanup failure safely stops; above `93 deg` is terminal. |
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

Finish and review the RP02 executor and packet. No owner authorization
document exists, so the executor must remain uncallable for physical motion.
No camera, gateway, serial, torque, motion, pawn contact, or task-attempt
authority is open.

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
