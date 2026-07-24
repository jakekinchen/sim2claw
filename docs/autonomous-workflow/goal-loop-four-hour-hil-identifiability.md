# Goal Loop — Four-Hour HIL Identifiability and Sim-to-Real Closure

## Mission

Run a minimum four-hour, safety-gated hardware-in-the-loop transaction that
records four additional current-workcell calibration episodes, turns them into
content-addressed evaluator evidence, and closes only simulator factors that
the measurements actually identify. The physical arm is powered only for four
short preregistered packets. The remainder of the window is offline
integration, evaluation, Studio observability, and verification.

The owner directly authorized physical testing and guaranteed that no person
or object will enter the chessboard workcell. That opens the workspace-clear
gate. It does not waive exact device/calibration identity, torque-off
preflight, camera coverage, start envelope, current freshness, controlled
return, evaluator independence, or proof-class boundaries.

## Ordered Source of Truth

1. The owner's 2026-07-24 authorization and the live follower, camera,
   calibration, torque, repository, and process state.
2. This goal and
   `configs/evaluations/current_100mm_hil_identifiability_v1.json`.
3. The reviewed `sim2claw.so101_physical_gateway.v2`, diagnostic camera
   recorders, and physical replay validators.
4. Immutable raw action, command, joint, current, overhead, and wrist artifacts
   produced by this transaction.
5. The independent derived evaluator, current simulator implementation,
   `GOAL.md`, `docs/autonomous-workflow/project_state.json`, and the
   orchestration ledger.
6. Earlier recordings, simulator diagnostics, and external advice, which may
   motivate hypotheses but cannot score or promote this evidence.

## Intended Outcome

Produce four distinct unloaded HIL episodes—gripper, shoulder lift, elbow
flex, and wrist flex—whose commanded action tensors are frozen before torque
is enabled, whose overhead and wrist streams cover the motion, whose position
and current telemetry are timestamped, and whose final hold returns the
follower to its recorded start pose before torque is released.

Use the admitted measurements to estimate only identifiable timing,
range/scale, deadband, hysteresis, and unloaded load-response factors. Compare
the current simulator against the same action bytes and freeze any candidate
before independent consequence evaluation. Honest ties, losses, rejected
candidates, or explicit missing-observable abstentions are terminal results.

## Acceptance Criteria

1. The active loop begins at `2026-07-24T02:37:10-05:00` and does not claim
   terminal completion before `2026-07-24T06:37:10-05:00`. Torque-on time is
   limited to the four short packets; no idle powered hold is used to satisfy
   the wall-clock requirement.
2. The frozen S2 benchmark/C2 eleven-file hash set remains byte-identical and
   its campaign remains `1 event / 4 replays / 0 measurement trials`.
3. Exactly four new physical attempts are allowed, one per preregistered
   packet. Safety-aborted or camera-incomplete attempts consume their packet
   and are not silently retried, relabelled, or replaced.
4. Before each attempt, the identified follower and calibration hashes match,
   torque is off, Studio is idle, both cameras are discoverable, the
   start-bound action tensor passes calibrated limit and gateway envelope
   checks, and the owner's workcell-clear assertion is recorded.
5. All motion uses the reviewed gateway. No IK, task offset, clipping,
   resampling, post-result suffix, adaptive amplitude, leader-arm dependence,
   or action assistance is introduced.
6. Every action packet starts with a two-second hold, uses smooth bounded
   motion, ends with a two-second start-pose hold, and requires a controlled
   return on a non-bus failure. Torque may be released immediately only when
   the bus cannot safely command or verify a hold.
7. Every attempt writes raw requested, sent, actual, velocity, current,
   current-sample time, bus retry, clamp, stall, and return-state rows plus
   finalized C922 and D405 media reports and hashes.
8. An evaluator admits a packet only when its action identity, device and
   calibration identity, telemetry, camera coverage, completed return, final
   pose residual, and budget all pass. Unknown force, deformation, metric
   depth, contact, and camera-to-gripper extrinsics remain unknown.
9. Simulator variants receive byte-identical float64 actions. Fitting and
   scoring remain separate; lower joint RMS alone is diagnostic. No simulator
   parameter, task score, training row, policy, or physical capability is
   promoted without its separately owned consequence gate.
10. Studio exposes the new evidence through existing read-only project and
    Twin fidelity surfaces without inventing a completeness percentage or
    adding write authority.
11. Focused, short-tier, and one exact-head full-suite verification pass after
    the patch is frozen. Generated observations stay ignored; scoped
    contracts, code, tests, state, logs, and content digests may be committed.
12. No provider-backed evaluator or experiment, paid/Brev compute, new
    retained-C2 family, unbounded task replay, training, promotion, public
    push, VideoSim work, or physical claim expansion occurs. The owner's
    earlier request for one GPT-5.6 browser review is accounted separately as
    non-evidentiary method advice; it cannot score, admit, or promote a result.

## Evidence Standard

Keep these proof classes separate:

- `physical_hil_unloaded_joint_observation`
- `derived_hil_joint_identifiability_evaluation`
- `action_frozen_hil_simulator_comparison`
- `independent_cpu_fp32_hil_consequence_evaluation`

Completion evidence must report all four attempt outcomes, exact action and
artifact hashes, device/calibration identities, camera duration/frame
coverage, telemetry freshness, requested/sent/actual residuals, clamp/stall
and bus-retry counts, return-to-start result, simulator replay budget,
candidate decision, excluded evidence, unchanged S2 hashes/state, test
receipts, authority, and remaining observables.

## Decision Status

### Confirmed

- The identified leader and follower buses and both calibration files are
  present; LeRobot is `0.6.0`.
- A torque-off live preflight at the transaction start reported the follower
  at approximately `[-4.31, -106.02, 100.09, -10.51, -95.43, 1.66]` and
  follower torque disabled.
- The C922 and D405 are both discoverable by stable device name.
- The previous empty-gripper episode did not identify shoulder-lift range
  (`0.0°` span) and under-excited elbow (`10.022°` span).
- The owner guarantees the chessboard workcell will remain clear during the
  authorized tests.

### Assumptions

- Unloaded single-joint excitation is safer and more discriminating than
  another pawn task replay for the currently missing actuator factors.
- The follower's current start pose remains inside the calibrated envelope
  long enough to bind each packet immediately before execution.

### Recommended Defaults

- Use five smooth gripper excursions, one shoulder-lift away/return excursion,
  one elbow-flex away/return excursion, and one symmetric wrist-flex
  excursion.
- Keep every non-target joint at its captured start value.
- Prefer a sealed diagnostic or abstention over fitting contact/friction from
  unloaded measurements.

### Open Questions

- Whether raw motor current has sufficient signal for load-response
  identification.
- Whether the current simulator's servo model can improve all held-out joint
  consequences without a per-joint regression.
- Force, deformation, metric depth, contact state, and wrist extrinsics remain
  unavailable unless separately measured; this loop does not fabricate them.

## Execution Rhythm

1. Snapshot Git, processes, devices, calibration, cameras, torque, and frozen
   S2 evidence.
2. Freeze and commit this goal, the four packet definitions, budgets,
   evaluator gates, and safe-return policy before motion.
3. Implement and unit-test the reusable recorder/evaluator path with fake
   devices and cameras.
4. For each packet: recheck torque-off and cameras, bind the live start,
   freeze the action hash, record once, return/hold, release torque, hash, and
   evaluate before moving to the next packet.
5. Normalize and compare the four packets offline; run only the
   preregistered action-identical simulator comparison justified by admitted
   evidence.
6. Update Studio, state, ledger, and run log; run focused and short gates.
7. Continue safe offline analysis and verification until the earliest exit,
   then run one exact-head full suite and report the terminal evidence.

## Progress Ledger

```text
Current state: Four one-attempt packets, one two-replay simulator comparison, two offline audits, and the Studio publication are frozen; exact-head closeout remains active until at least 06:37:10-05:00.
Completed: 4/4 physical attempts; 2 admitted and 2 rejected; torque off; 2/2 action-identical simulator replays; evaluator reject; v1/v2 deterministic trace diagnostics; future host-timestamp observability; desktop/mobile Studio inspection.
Evidence: campaign b364aae6; physical summary 886ca149; simulator evaluation bfd126fd; v1 report a62481c1; v2 report e4fbc956; physical task score 0/11; S2 11/11 unchanged with 1 event / 4 replays / 0 trials.
Remaining: Final authority/state/log freeze, receipt-bound SAIL observatory regeneration, focused/short tiers, one exact-head full suite, final evidence recheck, and minimum-window exit.
Blockers: Actuator/device timing, calibrated current/force, camera PTS/drop counters, repeatable multi-level/multi-speed excitation, repeated reset trials, and strict task/EE consequence remain unavailable. They block calibration and promotion, not closeout.
Next step: Freeze the terminal authority record, restore exact-source Studio/SAIL receipts, and run the no-motion proof tiers.
```
