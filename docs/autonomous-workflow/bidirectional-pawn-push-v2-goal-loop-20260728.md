# Bidirectional Pawn-Push V2 Goal Loop

## Mission

Autonomously complete the smallest honest, camera-verifiable bidirectional
straight pawn-push proof by closing the causal chain from exact action through
joint/link response, contact, planar object response, and task consequence.
Stop only at a genuine receipt-backed safety or authority boundary after safe
in-scope alternatives are exhausted.

## Source of Truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. `docs/autonomous-workflow/causal-closure-successor-task-queue-20260728.md`.
4. The immutable predecessor queue
   `docs/autonomous-workflow/bidirectional-pawn-push-v2-task-queue-20260728.md`.
5. `docs/autonomous-workflow/bidirectional-pawn-push-v2-current-graph.json`.
6. Immutable camera, gateway, simulator, evaluator, action, and cleanup
   receipts.
7. `GOAL.md`, repository tests, and workflow protocols.
8. Advisory Fable output, which never overrides repository evidence.

The causal-closure successor queue is the sole active task list. The
predecessor v2 queue remains immutable authority for its terminal results.

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
- `ObservableEpisode.v2-min` preserves exact actions, timestamps, joint/link
  state, board-plane object state/covariance, contact/motion events, outcome,
  and explicit missingness.
- The four canonical seeded actions complete their frozen simulator
  consequence screen only after the v1 stock-range defect is closed and a
  calibrated-range v2 static receipt admits their exact hashes.
- The physical/model mapping receives a gauge-fixed, held-out-reviewed
  approval before any physical task packet.
- Evaluator ID/SHA, case list, mappings, scene, setup actions, task actions,
  stop rules, and camera thresholds are frozen before counted motion.
- Requested, mapped, and sent task bytes are identical; there is no clipping,
  retiming, offset, IK repair, assistance, correction, retry, or state forcing.
- C922 owns physical outcomes; CPU/fp64 MuJoCo owns simulator outcomes.
- At least one distinct complete success exists in each direction.
- Studio exposes synchronized spatial and temporal evidence, direction-specific
  numerators/denominators, failures, hashes, proof class, and limitations.
- After all implementation/evidence cards pass, the complete package receives
  an adversarial review in the existing project Fable thread. Every material
  recommendation is implemented or dispositioned with repository evidence,
  and the updated result returns to Fable for a final defect check.
- Tests, workflow audit, torque/process/camera/gateway cleanup, Brev cleanup,
  scoped push, graph update, and the CC13--CC15 Fable feedback loop complete.

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

- The predecessor V2 campaign is terminal without task or transfer authority.
- Canonical current-workcell cutover and task-plane registration pass.
- Legacy actions are rejected because their starts do not match the live
  anchor and the physical/model mapping is not approved.
- The v1 current-anchor-seeded apparent pass is quarantined because its live
  elbow seed is about 2.64 degrees outside the stock MuJoCo elbow limit.
- The calibrated-range v2 static rerun is frozen and passed at `fc23364`,
  re-admitting the same four exact actions `2/2` per direction with a minimum
  selected model-joint margin of `0.001829670515161086 rad`.
- Its authoritative receipt SHA-256 is
  `c68599e9f18120f46bea955732ccc82c3582b9f18af280292f2aad73cfd47977`;
  closeout decision SHA-256
  `ced92042e73ed53a5ccf27810ddce9d36f9a50f8f6a71110ca517bf116669929`
  preserves false dynamic, mapping, and physical authority.
- CC01 is complete. `ObservableEpisode.v2-min` closeout SHA-256
  `fe586670e539d9047acac3f84167883f5fc50a6fac39c98cf0e2b47b16c52178`
  accepts strict causal serialization and adapters without dynamic or
  physical authority.
- CC02 in the successor queue is the sole active card.
- Wrist depth is omitted and unnecessary for this campaign.
- One writer uses
  `codex/bidirectional-transfer-goal-loop-20260728`.

Recommended default:

- Replay only the calibrated-range v2-admitted exact actions through the
  accepted object/contact episode contract.
- Implement only the gauge-fixed calibration-graph factors required to
  approve or reject the current physical/model mapping.
- Fit only the simulation mechanism identified by first divergence, preserving
  exact actions and untouched held-outs.
- Complete bidirectional task evidence before the required bounded
  policy-screening pilot; do not delay transfer for new model training.

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

Owner physical authorization is time-bounded from `2026-07-28 22:38 CDT`
through `2026-07-29 05:38 CDT`. It allows reviewed, recorded, productive
physical actions after their queue gates pass; it does not waive any safety,
identity, preregistration, evidence, action-integrity, or cleanup gate.

## Progress Ledger

```text
Current state:
Active card: CC02 canonical CPU/fp64 direct-target plus 0.11 s ZOH replay.
Completed: CC00, CC00A, CC01.
Evidence: V2 static receipt c68599e9...; V2 closeout ced92042...; ObservableEpisode closeout fe586670....
REAL->SIM successes/attempts:
SIM->REAL successes/attempts:
Heldout open count:
Physical task attempts:
Physical/camera/torque state: closed/no motion; latest recorded torque state false.
Remaining: CC02 through CC15.
Blockers: dynamic consequence and physical/model mapping remain unapproved.
Next step: freeze and execute CC02 with one ObservableEpisode per exact action and plant path.
```

## Physical Authority Boundaries

Only the reviewed SO-101 gateway may command the robot. Cameras start before
motion and enclose each transaction. Stop immediately on torque uncertainty,
identity mismatch, missing C922 authority, unsafe geometry, unreviewed
contact, tracking/stall breach, changed bytes, or cleanup failure. Never
perform EEPROM, servo-ID, gain, torque-limit, unreviewed controller, training,
paid-compute, or unrelated work. No human repositioning is assumed.

## Stop Conditions

Stop successfully only after both directional transfer successes, the bounded
policy-screening result, the executable task-world bundle, the targeted
variation connection, the iterative Fable review has no material unresolved
in-scope proof defect, and the full closeout package exists. Stop
unsuccessfully only with a receipt-backed robot/camera safety or authority
boundary after safe autonomous alternatives in the queue are exhausted. A
counted stopped action stays in its denominator.
