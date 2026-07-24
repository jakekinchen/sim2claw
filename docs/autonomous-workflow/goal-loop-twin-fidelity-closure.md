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

## Progress Ledger

```text
Current state: 0/6 required domains are fully closed; trustworthy partial evidence exists.
Completed: Closure evaluator, container-timing instrumentation, Studio closure matrix, and six-packet multilevel HIL preregistration.
Evidence: Baseline 1859ee2; closure contract 4e387a7b; multilevel HIL contract 8dbe616e; HIL b364aae6; S2 11/11 unchanged, 1 event / 4 replays / 0 trials.
Remaining: Commit the preregistration, verify the live envelope, execute at most six one-attempt packets, then evaluate only admitted measurements.
Blockers: Device/actuator timing, calibrated force/current, metric registration, repeated excitation/reset trials, strict task/EE consequence.
Next step: Freeze the software/preregistration commit before any robot motion.
```
