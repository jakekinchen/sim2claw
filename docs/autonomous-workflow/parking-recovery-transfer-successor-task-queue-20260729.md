# Parking-Recovery Transfer Successor Queue

Status: `ACTIVE_RP00_STATIC_CERTIFICATE_FREEZE`

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
| RP00 | `IN_PROGRESS_FREEZE` | Prospectively freeze and run one route-level parking-target certificate across elbow locks `{97,95,93,91,90,88} deg`. | Existing CC03K family universe, compiler, collision/contact/camera/gateway gates, and false physical authority remain unchanged. At least one distinct family per direction passes at a maximum viable angle and again at a passing target at least `2 deg` lower. Code, contract, tests, and advisory predate the single run. | Zero passing angles, or no passing margin target, is a terminal simulation negative. Do not move hardware. |
| RP01 | `PENDING` | Freeze a high-clearance, contact-impossible elbow parking transaction to the RP00 target. | CPU preview clean; at most `5 deg` requested per step; read/verify each step; abort after two consecutive steps with less than `0.3 deg` progress; `10 s` hold drift below `0.5 deg`; torque-off cleanup; no task/pawn contact reachable. | Any unsafe preview or missing fresh anchor closes physical authority. |
| RP02 | `PENDING` | Execute parking once under separately reopened physical authority. | Cameras enclose; reviewed gateway only; target reached; hold gate passes; exact receipt; torque off. One retry may be separately admitted only for monotonic-but-short progress. | Stall above the RP00 maximum viable angle is a terminal external hardware boundary. |
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

Finish the RP00 implementation and contract, run focused tests and workflow
audit, commit and push the prospective freeze, then execute RP00 exactly once.
