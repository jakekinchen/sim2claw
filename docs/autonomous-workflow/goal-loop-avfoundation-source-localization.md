# Goal Loop — AVFoundation Source Localization

## Mission

Determine whether the repeatable C922 container-timeline gaps at D405
stream-open and stream-close boundaries already exist in AVFoundation source
delivery or arise later in the FFmpeg/encode/mux path. Build source-level
observability first, then run at most the separately frozen no-motion campaign.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity closure objective.
2. The clean exact checkout and live Mac camera/device state.
3. The sealed D405 reliability campaign, evaluation, and receipt.
4. `configs/evaluations/avfoundation_source_localization_v1.json`.
5. Apple AVFoundation/CoreMedia APIs and the exact local Swift/FFmpeg
   implementations.
6. `GOAL.md`, project state, the orchestration ledger, and run logs.
7. The GPT-5.6 Pro review as advisory design input only.

## Intended Outcome

The repository has a native, versioned, read-only AVFoundation source probe
that records sample callback cadence, source PTS, Apple drop reasons, session
events, device connect/disconnect events, and exact runtime/source identity.
An independent evaluator compares the six fixed control trials with the six
fixed D405-lifecycle trials and returns one bounded source-layer verdict
without reclassifying the earlier C922 container rejection.

## Acceptance Criteria

1. Preserve all eleven frozen S2 artifacts, both HIL campaign states, and the
   sealed D405 campaign/evaluation/receipt byte-identically.
2. Commit the source-localization contract before implementing or executing a
   live campaign. The fixed order has six control and six treatment trials,
   zero replacements, zero robot motions, and zero provider calls.
3. Build the source probe from manually authored repository code and the
   system Apple frameworks. Bind the exact Swift source, compiled executable,
   Python runner, compiler, FFmpeg, and FFprobe identities.
4. Select the C922 by exact device name. Fail closed on missing/duplicate
   devices, unavailable formats, permission failure, session failure,
   malformed events, early exit, incomplete output, or identity drift.
5. Record source callbacks with local sequence, `CMSampleBuffer` PTS/duration,
   `mach_continuous_time`, format identity, and Apple dropped-frame reason
   attachments. Record session interruption/runtime-error and device
   connection notifications.
6. State the timing guarantee exactly: source PTS and host time are not a
   shared cross-camera exposure clock. A missing container interval is not
   automatically a missing physical exposure.
7. The evaluator alone owns interval, boundary-window, replication, and
   aggregation logic. The probe emits observations and never scores or
   promotes them.
8. Add adversarial tests for schema drift, source/runner/binary substitution,
   missing or duplicate trial IDs, order mutation, replayed events, malformed
   PTS, action/authority mutation, USB removal, early probe exit, and post-hoc
   threshold change.
9. Repeated evaluation materialization is byte-identical. Generated camera
   outputs remain ignored; only versioned code/config/tests and durable
   digests are committed.
10. If Swift/AVFoundation cannot expose the required source callbacks without
    widening camera or system authority, implement and test the interface and
    emit a sealed prerequisite abstention. Do not invent source evidence.
11. Focused tests, proportional SAIL tiers, and one exact-head full repository
    suite pass before centralization.

## Evidence Standard

Report exact commits and trees, source/runtime hashes, trial IDs and counts,
per-cell callback/drop/gap measurements, boundary alignment, USB events,
verdict, receipt digests, test counts, frozen-evidence hashes, and closed
authority. Keep infrastructure proof, camera-source evidence, container
evidence, motion reliability, metric depth, simulator fidelity, and task
success as separate proof classes.

## Decision Status

### Confirmed

- The sealed D405 stationary campaign is `0/6` because each C922 MP4 contains
  lifecycle-boundary container PTS gaps.
- D405 source transport itself passed all six stationary trials with no
  inferred gaps, source stall, or USB removal.
- Frame-level C922 gaps align with D405 open and close/finalization in every
  sealed trial.
- Container PTS does not identify whether the gap originated in the camera,
  AVFoundation, FFmpeg, the encoder, or the muxer.
- The Mac has Swift 6.3 and the AVFoundation SDK.

### Assumptions

- A native `AVCaptureVideoDataOutputSampleBufferDelegate` can expose source
  callbacks and Apple drop-reason attachments without robot or metric-depth
  authority.
- Equivalent control/treatment source-probe trials can localize a replicated
  source-layer discontinuity but cannot, by themselves, prove physical
  exposure loss.

### Recommended Defaults

- C922 source probe: `640 × 480`, `30 fps`, preferred bi-planar 4:2:0 format.
- Fixed 30-second source window.
- D405 treatment lifecycle: open at `5 s`, stop at `25 s`.
- Boundary window: `±1.5 s`.
- Large source interval: greater than `1.5 × 1/30 s`.
- Six fixed trials per cell and zero replacements.

### Open Questions

- Whether C922 `didDrop` reports discontinuity, late frame, or buffer
  exhaustion at D405 lifecycle boundaries.
- Whether source callbacks remain continuous while only the sealed FFmpeg
  container path gaps.
- Whether a long-lived dual-camera supervisor or Linux second host is required
  after source localization.
- Whether the current D405 cable path can be physically repaired and
  motion-qualified in a later transaction.

## Execution Rhythm

1. Freeze the contract and evidence baseline.
2. Implement source-probe schemas, parser, verifier, and adversarial tests.
3. Compile and test without opening cameras.
4. Commit the exact implementation and bind its hashes.
5. Execute only the frozen no-motion campaign or abstain.
6. Evaluate from raw source events in a separate step.
7. Update Twin fidelity prerequisites without changing prior evidence.

## Progress Ledger

```text
Current state: Source-localization contract drafted from clean main after the sealed D405 terminal negative.
Completed: Exact source-vs-container hypotheses, fixed control/treatment order, measurements, evaluator verdict vocabulary, budgets, and closed authority.
Evidence: baseline 87534c5; sealed campaign 57d4983c; evaluation 80ed9ac3; receipt cfc11ff3; GPT-5.6 Pro advisory review retained without proof authority.
Remaining: Freeze the preregistration commit, implement and test the native source probe, then decide whether the frozen no-motion campaign is executable.
Blockers: None at preregistration; camera permission and AVFoundation event support remain live preflight gates.
Next step: Rebind project authority and commit the preregistration before source-probe implementation.
```
