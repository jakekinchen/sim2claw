# Goal Loop — Overnight Dual-Camera Simulator Calibration

## Mission

For the bounded three-hour window ending at
`2026-07-24T03:16:30-05:00`, turn the newly recorded dual-camera,
fresh-current empty-gripper observation into clean, content-addressed,
evaluator-owned diagnostic evidence; compare it with the current simulator
without changing action bytes; and implement only calibration or observability
changes that pass preregistered gates. A measured tie, loss, or missing-channel
abstention is an acceptable result. A task-score or physical-transfer claim is
not.

## Ordered Source of Truth

1. The owner's 2026-07-24 request and the live checkout/device state.
2. This goal and
   `configs/evaluations/current_100mm_measurement_acquisition_v1.json`.
3. The raw directory
   `datasets/manipulation_source_recordings/c2-to-c1__20260724T050132Z-02baf745/`,
   whose bytes and original receipt must not be rewritten or relabelled.
4. `docs/autonomous-workflow/goal-loop-current-100mm-physical-measurement-calibration.md`,
   the reviewed gateway, current simulator implementation, and independent
   evaluator contracts.
5. `GOAL.md`, `docs/autonomous-workflow/project_state.json`, generated
   receipts, and `.factory/orchestration-ledger.md`.
6. GPT-5.6 Pro advice, which is third-party technical critique only and has no
   execution, evaluation, promotion, or safety authority.

## Intended Outcome

Produce a derived measurement packet that verifies every source hash, maps
camera and telemetry timebases, segments the observed gripper excursions using
a frozen rule, quantifies per-cycle aperture/current/tracking/timing behavior,
and names missing force/depth/contact observables explicitly. Bind any
simulator comparison to the exact input tensor and simulator implementation.
Report the best evidence-supported simulator gap reduction, or abstain without
changing calibration if the data cannot identify a correction.

## Acceptance Criteria

1. The raw episode, its C922/D405 media, receipt, and frozen S2 evidence remain
   byte-identical.
2. Derived evidence is written separately, content-addressed, deterministic,
   and reproducible from public raw inputs.
3. The evaluator distinguishes the six observed excursions from the owner's
   intended five-cycle procedure; it does not silently discard, rename, or
   relabel a cycle.
4. Unknown force, metric depth, contact, deformation, and camera-to-gripper
   transforms remain unknown rather than zero.
5. Any simulator execution uses byte-identical float64 actions across
   variants, an exact implementation identity, a preregistered finite budget,
   and no IK, offset, clipping, resampling, suffix, or assistance.
6. Calibration fitting and evaluation are separated. No parameter is promoted
   from training error alone; strict consequence and held-out authority remain
   closed unless an independent evaluator-owned gate exists and passes.
7. The result reports per-joint and gripper timing/tracking/current metrics,
   camera coverage, simulator residuals, excluded observations, budget use,
   and proof class.
8. Focused tests and proportionate repository verification pass at the exact
   final code tree. Generated outputs remain ignored.
9. No unattended robot motion, physical task replay, training, policy
   promotion, paid compute, Brev resource, or push occurs in this transaction.
10. The three-hour window ends with committed scoped code/config/test/docs or
    a sealed blocker packet, a clean worktree, and an honest next prerequisite.

## Evidence Standard

Keep these proof classes separate:

- `physical_dual_camera_empty_gripper_observation_unqualified`
- `derived_empty_gripper_cycle_diagnostic`
- `action_frozen_simulator_joint_range_diagnostic`
- `offline_unloaded_joint_identifiability_diagnostic`

Completion evidence must include exact source and derived hashes, action
identity, simulator identity, segmentation rule, measured counts, test
commands/results, changed files, excluded or unavailable channels, authority
flags, and any remaining sim-to-real gap.

## Decision Status

### Confirmed

- The new recording contains 911 synchronized rows with fresh current, a
  1,625-frame C922 video, and a 270-frame/54.6-second D405 browser stream backed
  by a lossless source.
- Telemetry contains twelve alternating threshold crossings, forming six full
  excursions.
- The raw receipt says `full_episode / success / C2→C1`, so it is not already
  an admitted five-cycle calibration measurement.
- Contact force, metric D405 depth, deformation, and a camera-to-gripper
  transform are unavailable.
- The only authorized simulator family used two of two replays with identical
  action bytes. Endpoint-derived ranges reduced aggregate body-joint RMSE from
  `3.4281°` to `2.2801°`, but elbow RMSE regressed by `0.8700°`, gripper
  non-regression failed, and strict task consequence was unavailable. The
  evaluator rejected the candidate.
- The offline identifiability audit found `0.0°` shoulder-lift command span
  and only `10.022°` elbow span. Neither joint's range scale is identified
  from this episode, so the large shoulder-lift residual reduction cannot
  authorize a shoulder-only simulator change.
- GPT-5.6 reviewed the result inside the Robotics and Sims project. Its useful
  timing/calibration-envelope recommendations remain advisory. Its initial
  bootstrap-CI statement was inapplicable to this frozen evaluator, and its
  initial shoulder-only recommendation was superseded by the zero-span audit.

### Assumptions

- The owner intended five measurement cycles and an additional excursion may
  be setup/conditioning, but the evaluator must report rather than assume that
  interpretation.
- Existing data can identify actuator/gripper timing and current behavior more
  strongly than contact/friction or spatial task consequence.

### Recommended Defaults

- Preserve all six excursions and publish both all-cycle statistics and a
  clearly named five-intended-cycle sensitivity view only if the exclusion
  rule is frozen before inspecting comparative outcomes.
- Prefer a no-promotion diagnostic over fitting a confounded contact parameter.
- Use GPT-5.6 Pro for critique of the preregistration and failure modes, not for
  scoring local evidence.

### Terminal Finding

- This episode supports a repeatable, sample-quantized approximately
  `0.15 s` unloaded tracking lag on the sufficiently excited channels, but it
  does not measure command-application latency.
- The endpoint-range candidate is a rejected partial diagnostic gain, not a
  calibration improvement or task result.
- The next measurement packet must add independent capture/arrival,
  command-send/application, position-read, and current-read timestamps; reset
  and calibration-health receipts; and preregistered bidirectional
  shoulder-lift/elbow excitation before another range hypothesis.

## Execution Rhythm

1. Snapshot Git, source hashes, frozen evidence, simulator identity, and
   authority.
2. Ask GPT-5.6 Pro to critique the bounded plan using only a non-sensitive
   summary.
3. Implement the deterministic derived packet and adversarial tests.
4. Preregister the exact simulator comparison, budget, metrics, and stop
   conditions before execution.
5. Execute once only if the required public inputs and evaluator ownership are
   verified; otherwise seal an abstention.
6. Run focused verification, record receipts, update project state and ledger,
   commit scoped work, and stop at the deadline or terminal result.

## Progress Ledger

```text
Current state: Terminal diagnostic; partial aggregate reduction rejected; no simulator or task promotion.
Completed: Raw/data integrity, six-cycle evaluator, single two-replay action-identical comparison, offline joint identifiability audit, GPT-5.6 project critique, and receipt-verified Studio projection.
Evidence: implementations d0f053a/a509682/a5e58eb/b1cd6e5; action 4dcdabd0...; diagnostic c6791f94...; comparison evaluation 2bf577af...; identifiability report 22227ca7...; publication v2 b3435627....
Remaining: Exact-head verification and documentation closeout only.
Blockers: Contact force, metric depth/extrinsics/object pose, independent timing, reset/calibration-health, and strict task consequence remain unavailable.
Next step: Run focused/short/full proof tiers without simulator or physical replay, then close with no push.
```
