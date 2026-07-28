# Bidirectional Pawn-Push V2 Goal Loop

## Mission

Autonomously complete the smallest honest, camera-verifiable bidirectional
straight closed-jaw pawn-push proof, or stop only at a genuine receipt-backed
safety or authority boundary after safe in-scope alternatives are exhausted.

## Source of Truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. `docs/autonomous-workflow/bidirectional-pawn-push-v2-task-queue-20260728.md`.
4. `docs/autonomous-workflow/bidirectional-pawn-push-v2-current-graph.json`.
5. Immutable camera, gateway, simulator, evaluator, action, and cleanup
   receipts.
6. `GOAL.md`, repository tests, and workflow protocols.
7. Advisory Fable output, which never overrides repository evidence.

The existing v2 queue is the only task-list source of truth. Do not create a
competing backlog.

## Intended Outcome

- At least one admitted REAL->SIM case: camera-owned physical consequence
  first, then byte-identical canonical little-endian float64/40 Hz replay in
  CPU/fp64 MuJoCo, with both outcomes passing the frozen evaluator.
- At least one distinct admitted SIM->REAL case: simulator consequence and
  robustness evidence first, then one safety-reviewed physical execution of
  the frozen identical bytes with C922-owned success.
- Every failure remains in its direction-specific denominator and the total
  physical budget does not exceed ten cases.

## Acceptance Criteria

- One preregistration commit predates every counted task action.
- Registration fit and sealed-heldout gates pass exactly as frozen in the
  queue.
- Sim-only push feasibility passes before evaluator freeze.
- Evaluator ID/SHA, case list, mappings, scene, setup actions, task actions,
  stop rules, and camera thresholds are frozen before counted motion.
- Requested, mapped, and sent task bytes are identical; there is no clipping,
  retiming, offset, IK repair, assistance, correction, retry, or state forcing.
- C922 owns physical outcomes; CPU/fp64 MuJoCo owns simulator outcomes.
- At least one distinct complete success exists in each direction.
- Studio exposes synchronized spatial and temporal evidence, direction-specific
  numerators/denominators, failures, hashes, proof class, and limitations.
- Tests, workflow audit, torque/process/camera/gateway cleanup, Brev cleanup,
  scoped push, graph update, and final read-only Fable defect review complete.

The only final capability claim is the narrow preregistered bidirectional
straight pawn-push claim recorded in the queue.

## Evidence Standard

Before closing any card, record changed paths, commands, tests, immutable
receipts and hashes, reviewer decision, physical/camera/torque state, attempt
ledger, limitations, and next gate in the v2 queue and graph. Simulation,
registration, physical observation, task outcome, and transfer remain
separate proof classes.

## Decision Status

Confirmed:

- The owner resumed V04 and authorized agent-led physical testing only after
  all prospective safety/evidence gates pass.
- V04 is the sole active card; the prior row-zero stop is immutable.
- Wrist depth is omitted and unnecessary for this campaign.
- One writer uses
  `codex/bidirectional-transfer-goal-loop-20260728`.

Recommended default:

- Preserve the frozen acquisition-v2 arrays and repair the start with a
  versioned, hash-bound time-only setup bridge.
- Prefer rank-3-ward pushes when the frozen feasibility audit supports their
  larger lattice clearance.

Open decisions are resolved only through the queue's recorded gates and
fallbacks. Do not activate deferred methods without their specified trigger.

## Execution Rhythm

Repeat:

1. inspect live repo, hardware, camera, process, torque, queue, and graph state;
2. choose the smallest action that moves the active acceptance gate;
3. update the queue and graph prospectively;
4. independently review and require `CONTINUE`;
5. execute once through the reviewed path;
6. verify receipts, hashes, tests, cameras, torque, attempts, and cleanup;
7. update the ledger immediately and commit scoped paths;
8. continue until both directional successes exist or a receipt-backed
   terminal boundary is reached.

Do not stop for planning, weak tooling friction, a recoverable camera defect,
or a preventable evaluator/registration defect.

## Progress Ledger

```text
Current state:
Active card:
Completed:
Evidence:
REAL->SIM successes/attempts:
SIM->REAL successes/attempts:
Heldout open count:
Physical task attempts:
Physical/camera/torque state:
Remaining:
Blockers:
Next step:
```

## Physical Authority Boundaries

Only the reviewed SO-101 gateway may command the robot. Cameras start before
motion and enclose each transaction. Stop immediately on torque uncertainty,
identity mismatch, missing C922 authority, unsafe geometry, unreviewed
contact, tracking/stall breach, changed bytes, or cleanup failure. Never
perform EEPROM, servo-ID, gain, torque-limit, unreviewed controller, training,
paid-compute, or unrelated work. No human repositioning is assumed.

## Stop Conditions

Stop successfully only after both directional transfer successes and the full
closeout package exist. Stop unsuccessfully only with a receipt-backed
robot/camera safety or authority boundary after safe autonomous alternatives
in the queue are exhausted. A counted stopped action stays in its denominator.
