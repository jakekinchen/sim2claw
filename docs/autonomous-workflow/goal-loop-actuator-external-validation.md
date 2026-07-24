# Goal loop: actuator-response external validation

## Mission

Determine whether the already-selected action-frozen actuator response model
generalizes beyond its retained 100 mm selection session by evaluating it once
against the five recovered 72 mm recordings. Keep selection, external
validation, and strict task consequence evidence separate, and report a pass
or terminal negative without changing policy actions, simulator parameters,
thresholds, or task authority.

## Source of Truth

Use these sources in descending authority order:

1. The owner's direct instruction to proceed with the recommended
   preregistered actuator-response cross-validation.
2. This goal-loop prompt and clean
   `main@78122d33e932f641312a9f370cfcdf704fcc96cd`.
3. The committed external-validation contract, exact source receipts, raw
   recordings, and evaluator artifacts.
4. The frozen servo load-bias and fidelity-advancement receipts that selected
   the candidate and independently scored its current-session consequences.
5. The Silicon completeness log, frozen physical intake ledger, sim/real
   bridge, `GOAL.md`, project state, and orchestration ledger.

Repository bytes and content-addressed receipts outrank summaries. Generated
outputs are evidence, not authority. Archive material may not be copied.

## Intended Outcome

The repository has a deterministic evaluator-owned external-validation path
that:

- replays the existing baseline and already-selected actuator response model
  against all five recovered recordings with byte-identical source actions;
- reports paired joint/EE trace metrics, uncertainty, budgets, and an honest
  external-generalization verdict;
- separately verifies the existing strict consequence receipt and preserves
  its task score;
- promotes no parameter and grants no training, physical, task, gateway, or
  motion authority.

## Acceptance Criteria

1. Freeze the two variants, five episode identities, thresholds, 10-replay
   budget, bootstrap, proof classes, and stop rules before real evaluation.
2. Use the 11-episode 100 mm campaign only as prior selection evidence. The
   five 72 mm episodes are external evaluation only and cannot change the
   candidate, thresholds, or model family.
3. Verify every external recording, sample payload, historical replay receipt,
   and state trace against the frozen intake ledger before replay.
4. Preserve each mapped `float64 Nx6` action array byte-for-byte across both
   variants. No IK, clipping, offset, resampling, suffix, assistance, or action
   reorder is allowed.
5. Execute exactly two variants over five episodes once: 10 replays, zero
   retries, zero provider calls, and no post-result family expansion.
6. Candidate execution emits raw metrics and identities only. A separate
   evaluator function owns aggregation, thresholds, bootstrap, and verdict.
   Candidate-authored scores or promotion claims are rejected.
7. The preregistered external trace gate requires all of:
   at least 2% pooled body-joint RMS improvement, at least four of five
   episode-level improvements, a positive 95% paired whole-episode bootstrap
   lower bound, pooled EE RMS no worse than baseline, and action invariance.
8. Verify the existing independent strict consequence receipt separately.
   External joint/EE evidence may not create object, contact, task, physical,
   policy, or transfer evidence.
9. A pass establishes only cross-session simulator trace-model robustness. A
   failure is a valid terminal negative. Neither outcome changes the strict
   task score or promotes the candidate.
10. Repeated materialization from the same inputs is byte-identical. The
    isolation guarantee is trusted-code interface and identity separation, not
    hostile-code or cryptographic sandboxing.
11. Add adversarial tests for source drift, duplicate episodes, malformed raw
    results, action substitution, budget expansion, evaluator/config drift,
    threshold mutation, candidate self-scoring, and task-receipt mutation.
12. Preserve all frozen S2 hashes and the 1-event/4-replay/0-trial campaign
    state. Run focused tests, SAIL short tiers, and one full repository suite
    at the final exact commit before scoped push.

## Evidence Standard

Completion requires:

- preregistration and implementation commit preceding real execution;
- exact contract, implementation, source receipt, ledger, action, raw result,
  evaluator result, and final receipt hashes;
- episode/sample/replay/retry/provider counts;
- per-episode and pooled joint/EE metrics with bootstrap interval;
- external trace verdict and strict task score before/after;
- explicit proof classes, excluded failed traces, and unchanged authority;
- focused, SAIL, and full-suite results;
- clean worktree and local/remote equality.

Test counts prove implementation integrity, not physical or task success.

## Decision Status

Confirmed:

- The existing global gain/damping/force fit improved held-out joint RMS by
  only `0.0088°`; it is not reopened.
- The selected response model uses `110 ms` delay, `1.5°` shoulder-lift
  deadband, `2.0°` elbow deadband, and `-1.5` bounded elbow load-response
  coefficient.
- The coefficient is a simulator model-class value at a frozen search
  boundary, not a measured physical torque or firmware parameter.
- The five recovered recordings predate the current 100 mm registration and
  contain no evaluator-qualified task outcomes.
- Provider, paid compute, training, promotion, physical capture, gateway,
  motion, and transfer authority remain closed.

Recommended defaults now frozen:

- Treat all five recovered recordings as one external evaluation cohort.
- Use 10,000 deterministic whole-episode bootstrap replicates.
- Accept trustworthy measurement rather than requiring a win.

Open questions resolved only by execution:

- Whether the selected response model improves the independent 72 mm cohort.
- Whether any trace robustness changes the strict task score (it may not do so
  without independent task consequence evidence).

## Execution Rhythm

1. Reconcile current state and frozen source identities.
2. Implement and test the fail-closed path without opening real results.
3. Commit the preregistration and implementation.
4. Execute the 10-replay external evaluation once.
5. Materialize evaluator-owned artifacts and record exact evidence.
6. Run final verification and compare every acceptance criterion.
7. Commit and push only after all integrity gates pass.

## Progress Ledger

Maintain `actuator_external_validation` in project state and mirror it in
`GOAL.md` and `.factory/orchestration-ledger.md`:

```text
Current state:
Completed:
Evidence:
Episodes / samples / replays / retries:
External trace verdict:
Strict task score before / after:
Remaining:
Blockers:
Next step:
```
