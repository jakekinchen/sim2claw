# Goal Loop — D405 Capture Reliability

## Mission

Make future wrist-camera measurements fail promptly and explainably when the
D405 process remains alive but stops producing frames, then qualify the revised
capture path with a separately preregistered no-motion endurance campaign
before any new robot packet is considered.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity closure goal.
2. The clean exact checkout and live process/device state.
3. The sealed six-attempt multilevel HIL campaign and its two rejected D405
   reports.
4. `configs/evaluations/d405_capture_reliability_v1.json`.
5. The diagnostic-video recorder, HIL gateway, and existing evaluators.
6. `GOAL.md`, project state, the orchestration ledger, and run logs.

## Intended Outcome

The D405 recorder distinguishes a live process from a progressing source,
detects a bounded no-growth stall during capture, initiates controlled failure
while the gateway can still return safely, finalizes partial evidence without
silently admitting it, and records the exact shutdown path. A future
camera-only qualification packet can prove repeated acquisition health without
claiming metric depth, synchronized exposure time, robot behavior, or task
success.

## Acceptance Criteria

1. Preserve the sealed multilevel HIL campaign at six attempts, zero retries,
   four admitted packets, and two rejected packets. Preserve the historical HIL
   campaign and all eleven S2 files byte-identically.
2. Monitor D405 source-file progress independently of FFmpeg process liveness.
   After the frozen startup grace, no byte growth for the frozen timeout must
   raise a deterministic capture-stall error during the control loop.
3. Keep D405 RGB/display evidence separate from unavailable metric depth.
   File growth is a transport heartbeat, not a camera exposure timestamp,
   frame-drop proof, or common device clock.
4. Stop FFmpeg through the frozen bounded escalation: stdin `q`, process-group
   `SIGINT`, `terminate`, then `kill`. Report the first terminal stage and all
   attempted stages.
5. A detected source stall remains `failed` even if the partial Matroska file
   is readable after graceful interruption. It can never become admissible
   merely because FFprobe succeeds.
6. Missing files, non-growing files, early process exit, signal failure,
   unreadable output, and malformed timing evidence fail closed and have
   deterministic tests.
7. No robot motion, simulator replay, training, promotion, provider call,
   task-score change, or reinterpretation of the two rejected packets occurs
   in the software milestone.
8. Before future motion, run the separately frozen qualification campaign:
   six consecutive 40-second no-motion C922+D405 trials, no replacement trial,
   no source stall, valid container timing, at least 95% expected frame
   coverage per stream, and a content-addressed evaluator receipt.
9. Focused and proportional repository tests pass at a clean exact commit.

## Evidence Standard

Report the exact commit/tree, changed files, contract digest, unit/adversarial
test counts, preserved evidence hashes and budgets, recorder state fields,
shutdown-stage behavior, qualification result or abstention, and remaining
measurement blocker. Do not claim that a camera-only pass proves reliable
motion capture or metric depth.

## Decision Status

### Confirmed

- In two rejected packets FFmpeg stayed alive while D405 frames stopped at
  `13.6 s` and `22.8 s`.
- Both finalizers exhausted the existing timeout and returned `-9`; their
  FFmpeg logs were empty.
- The macOS host recorded a whole SuperSpeed USB-device removal in both failure
  windows, invalidated the D405 for every camera client, and re-enumerated it.
- One isolated and one simultaneous production-order stationary diagnostic
  each captured `200 / 200` D405 frames over `40.000 s` with no USB removal.
  This localizes the primary fault to motion-correlated cable, connector, or
  strain-relief behavior rather than encoder or dual-camera load, without
  identifying the defective physical segment.
- Four other packets completed 27–33 seconds of D405 capture and finalized in
  under 0.83 seconds.
- The exhausted six-attempt family cannot be retried.

### Assumptions

- File-byte growth is a useful transport heartbeat for the lossless FFV1
  Matroska source.
- `SIGINT` is the least destructive signal escalation after stdin `q` because
  it gives FFmpeg a chance to write the container trailer.

### Recommended Defaults

- D405 startup grace: `3.0 s`.
- D405 no-growth timeout: `3.0 s` (15 configured frame periods at 5 fps).
- Shutdown waits: `1.0 s` after stdin `q`, `3.0 s` after process-group
  `SIGINT`, `2.0 s` after `terminate`, and `2.0 s` after `kill`.

### Open Questions

- Which cable segment, connector, or mounting/strain-relief point causes the
  motion-correlated whole-device removal.
- Whether a separately repaired physical path remains reliable under bounded
  preregistered motion.
- Whether a different validated host or whole-device USB passthrough is needed
  after the physical path is repaired.
- Whether six no-motion trials qualify the current Mac path or produce a
  sealed acquisition abstention.
- Whether reliable D405 acquisition under robot motion ultimately requires a
  separate camera host.

## Execution Rhythm

1. Revalidate the sealed evidence and exact checkout.
2. Freeze one reliability rule before implementing it.
3. Add deterministic tests that reproduce alive-process/no-growth behavior.
4. Implement the smallest recorder change and verify fail-closed behavior.
5. Commit the software milestone before any live qualification.
6. Run only the frozen camera-only qualification or abstain.
7. Re-evaluate the Twin-fidelity prerequisite without changing past evidence.

## Progress Ledger

```text
Current state: Root cause is localized to motion-correlated whole-device USB removal; watchdog implementation and focused proof pass, stationary qualification remains pending.
Completed: Exact failure reports, macOS USB removal/re-enumeration timelines, direct SuperSpeed topology, isolated and simultaneous stationary diagnostics, source-progress watchdog, bounded signal escalation, fail-closed reports/tests, and a live class smoke.
Evidence: preregistration 0e4d578; contract e8232fd7; campaign 0e818d22; rejected reports 911d3363 and 10d28805; stationary diagnostics 200/200 twice; focused tests 29/29; live smoke 65 frames/13 seconds.
Remaining: Commit the software milestone, execute the frozen six-trial stationary qualification, then repair/restrain the physical cable path before any newly preregistered motion qualification.
Blockers: The defective physical cable/connector segment is not remotely serviceable or identified; reliable D405 acquisition under motion and metric depth remain unproven.
Next step: Freeze the recorder software commit, then run only the no-motion qualification campaign.
```
