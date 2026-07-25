# Goal Loop — Evaluator-Owned Twin Fidelity Closure

## Mission

Advance the current SO-101 pawn workcell toward a trustworthy digital twin by
closing six ordered fidelity domains with receipt-bound measurements and
independent evaluator gates. “Perfect” means every required domain passes its
frozen gate on the same workcell and action identity; it is never inferred from
appearance, lower RMS alone, or a synthetic percentage.

## Ordered Source of Truth

1. The owner's instruction to proceed until the twin is perfect.
2. The live checkout, hardware/process state, and exact generated evidence.
3. This goal, its versioned closure contract, and the current HIL publication.
4. Existing SAIL receipts, Twin fidelity projection, physical gateway, and
   camera recorders.
5. `GOAL.md`, `docs/autonomous-workflow/project_state.json`, and the
   orchestration ledger.
6. Earlier experiments and external advice, which may motivate a probe but
   cannot score, admit, or promote it.

## Intended Outcome

The project has one evaluator-owned closure matrix for geometry/scale,
kinematics, action/timing, contact/compliance, actuator/load path, and task/EE
consequence. Every row identifies its measurement, unit, source identity,
threshold, evaluator, result, and missing prerequisite. Studio exposes the
same read-only matrix used by agents. A project-level `perfect` verdict is
possible only when all six required rows pass with no unknown required field.

## Acceptance Criteria

1. Preserve the frozen S2 eleven-file hash set and `1 event / 4 replays /
   0 measurement trials`, plus the four-attempt HIL campaign, byte-identically.
2. Create a versioned closure contract with exactly six required domains,
   explicit denominators, frozen thresholds or explicit unavailable
   prerequisites, and no post-result weighting.
3. Add deterministic container-timing analysis for future C922 and D405
   recordings: monotonic PTS, interval distribution, repeated-PTS count,
   repeat-picture count, and inferred missing-frame intervals. Label these as
   container/encoder timing, not exposure time, device synchronization, or
   proven camera drops.
4. Invalid, missing, stale, or action-mismatched evidence fails closed. Unknown
   is distinct from failed and from observed zero.
5. Reuse existing verified HIL/SAIL loaders. The closure evaluator may project
   their admitted facts but may not rescore or mutate their scientific result.
6. Studio exposes closure counts and per-domain prerequisites inside Twin
   fidelity without a write control or invented weighted percentage.
7. The owner explicitly authorizes the physical tests needed for this closure
   goal and guarantees the workcell is clear. Every motion packet must still be
   separately preregistered, bounded, start-envelope checked, dual-camera
   covered, executed through the reviewed gateway, returned under torque, and
   independently evaluated before another packet. This authorization does not
   open training, provider, paid-compute, promotion, or public-release authority.
8. Focused and proportional repository verification pass at an exact clean
   commit, with generated outputs ignored and content-addressed.
9. Completion is either six of six evaluator gates passing or a sealed
   external measurement/authority blocker naming the remaining observables.

## Evidence Standard

Report the exact commit/tree, changed files, closure contract digest, per-domain
state, focused and repository test receipts, preserved S2/HIL hashes and
budgets, Studio observations, excluded evidence, authority, and blockers.
Infrastructure readiness, diagnostic simulator evidence, physical HIL
observation, and strict task consequence remain separate proof classes.

## Decision Status

### Confirmed

- Current strict task consequence is `0 / 11`.
- The owner authorizes necessary physical tests and guarantees no person or
  object will obstruct the workcell.
- The four HIL packets are frozen: two admitted and two rejected.
- The prior shoulder-range simulator candidate was rejected.
- Container PTS can improve recording diagnostics but cannot provide
  device-clock or actuator-application timing.

### Assumptions

- The highest-value safe first slice is measurement-readiness infrastructure,
  not another simulator search.
- Existing HIL and SAIL verifiers remain the owners of their receipts.

### Recommended Defaults

- Count passed required domains as `passed / 6`; do not convert the count into
  an overall percentage.
- Treat physical capture and bounded motion as owner-authorized but
  execution-blocked until a separate packet passes its preregistration and
  live safety gates.

### Open Questions

- Actuator acknowledgement/application time and device-synchronized clocks.
- Calibrated current-to-torque/force provenance.
- Metric board/object/camera registration and wrist extrinsics.
- Repeated multi-level, multi-speed, loaded and reset trials.
- Strict pawn and end-effector consequence on held-out physical episodes.

## Execution Rhythm

1. Revalidate checkout, receipts, hardware authority, and live Studio.
2. Choose the smallest missing observable that can be closed safely.
3. Freeze its contract and evaluator before acquiring or inspecting results.
4. Implement, test, and expose it through the existing read-only product path.
5. Recheck all frozen evidence and compare against the six closure gates.
6. Continue while a safe, useful step exists; otherwise seal the exact blocker.

## Bounded P8/P13 metrology transaction

The next geometry/scale attempt is controlled by the versioned manifest
[`configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json`](../../configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json).
It reuses the existing C922 and stationary workcell-registration commands and
evaluators; it does not add an evaluator hierarchy or promote any evidence.
The manifest freezes the shared exact C922 mode and observable constant focus,
the physically measured printed-grid and direct playing-side receipts, a
stationary fixed-board capture with no robot motion, the current workspace and
board pose identities, physical A1/H1/A8 survey metadata, two independent
eight-point annotations, and the existing `1.5 mm`, `1.5 mm`, and `2 px`
residual thresholds.

The readiness command is:

```text
sim2claw metrology-transaction-preflight --transaction configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json --output runs/current-100mm-p8-p13-metrology-v1/readiness.json
```

It is read-only with respect to devices and returns the exact remaining
physical inputs before any capture. The transaction remains blocked until the
owner supplies those inputs; a blocked readiness report is not calibration or
registration authority.

## Progress Ledger

```text
Current state: 0/6 required domains are fully closed; trustworthy partial evidence exists.
Completed: Closure evaluator, container-timing instrumentation, Studio closure matrix, preregistration commit 6bc8745, the exact six-attempt multilevel HIL campaign, and the non-hardware P8/P13 metrology transaction/readiness control layer.
Evidence: Closure v2 contract de72fce3; campaign 0e818d22; 6 attempts / 0 retries / 4 admitted / 2 rejected; closure report 8cad9232; HIL b364aae6 unchanged; S2 11/11 unchanged, 1 event / 4 replays / 0 trials.
Remaining: Geometry/scale and contact/compliance are missing; kinematics, action/timing, and actuator/load path are partial; strict task/EE consequence is failed. The new P8/P13 transaction is blocked before capture on its named physical inputs.
Blockers: Intermittent D405 completion under motion; device/actuator timing; calibrated force/current; measured printed-grid and board scale; exact-mode calibration frames; stationary A1/H1/A8 survey and annotations; loaded/reset trials; strict held-out physical task/EE consequence.
Next step: Run the transaction readiness command above. If it remains blocked as expected, perform only the listed human physical setup and then follow its existing P8/P13 command sequence. Do not retry the exhausted v1 readiness family, open robot motion, or start another simulator search.
```
