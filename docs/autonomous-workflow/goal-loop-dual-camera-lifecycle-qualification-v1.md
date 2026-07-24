# Goal Loop — Dual-Camera Lifecycle Qualification v1

## Mission

Remove the known C922 container-timeline gaps caused by opening and closing the
D405 inside the C922 capture window. Change only the production camera
lifecycle order, then evaluate one short stationary dual-camera session without
robot motion or any simulator, task, synchronization, or metric-depth claim.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity closure goal.
2. Exact clean `main@e62e337ca13f6d0d2d80e62d031af35137f4f7a2`.
3. The independently reviewed C922 callback-delivery v4 result.
4. The sealed D405 reliability campaign and its terminal dual-camera negative.
5. `configs/evaluations/dual_camera_lifecycle_qualification_v1.json`.
6. The production `OverheadVideoRecorder`, `WristVideoRecorder`, teleoperation,
   and HIL capture surfaces.
7. The separately committed runner/evaluator and raw one-session evidence.

## Intended Outcome

Production dual-camera capture starts the D405 first and waits for its recorder
startup before opening the C922. It stops and finalizes the C922 before stopping
the D405. One independent evaluator re-probes the resulting raw containers and
returns either a bounded stationary lifecycle-health pass, a reject, or a
prerequisite abstention. The result remains camera transport/container evidence
only.

## Acceptance Criteria

1. Preserve all eleven S2 artifacts, both HIL campaign states, the sealed D405
   campaign, and C922 callback v1-v4 evidence byte-identically.
2. Commit this prompt and its contract before implementation or camera use.
3. For physical dual-camera recording, start order is exactly D405 then C922.
4. Stop order is exactly C922 then D405, including error cleanup.
5. Both camera processes remain live throughout the common measurement window.
6. Deterministic tests prove the nested lifecycle order in teleoperation and
   HIL paths and prove cleanup when the second camera fails to start.
7. Freeze exactly one ten-second stationary common-window session, no
   replacement and no retry.
8. The runner records monotonic lifecycle anchors, recorder reports, exact raw
   artifact hashes, device discovery, and closed authority. It does not score
   itself.
9. The evaluator separately re-probes both raw containers and requires:
   completed recorders; D405 progressing with no detected source stall; exact
   nested lifecycle order; at least 95 percent of the frozen common-window
   frame budget on each stream; numeric monotonic container PTS; and zero
   inferred missing intervals on each stream.
10. Missing devices, changed runtime identity, malformed events, extra trials,
    replayed/duplicated events, changed hashes, lifecycle inversion, source
    stall, unreadable media, insufficient coverage, or PTS gaps fail closed.
11. The evaluator reports container PTS only. It cannot claim camera exposure
    timestamps, cross-camera synchronization, metric depth, motion reliability,
    robot behavior, simulator calibration, or task success.
12. No robot gateway, robot motion, simulator replay, provider, paid compute,
    training, promotion, task-score change, or physical-task authority.
13. Focused/static tests and a fresh independent read-only review are required;
    no broad repository suite is required for this bounded camera change.

## Evidence Standard

Report the exact commits and trees, contract/source/evaluator/runtime identities,
device names, lifecycle anchors and order, frame counts, PTS spans and interval
statistics, source-progress state, verdict, failures, operation budget, raw
artifact hashes, receipt digest, preserved evidence, and authority limits.
A pass establishes one stationary lifecycle-safe container capture only.

## Decision Status

### Confirmed

- The D405 completed all six sealed stationary transport trials with no source
  stall or inferred missing interval.
- The sealed dual-camera campaign failed because the C922 contained gaps at the
  D405 open and close/finalization boundaries.
- Production teleoperation and HIL currently open C922 before D405.
- Production teleoperation and HIL already finalize C922 before D405.
- C922 callback v4 independently verified exact 640x480 `420v` steady delivery
  after a fixed one-source-PTS-second warm-up.

### Assumptions

- Keeping D405 lifecycle transitions outside the C922 container window removes
  the previously observed boundary coupling without hiding source timing.
- One stationary pass is sufficient to validate lifecycle ordering but not
  motion-correlated D405 cable reliability.

### Recommended Defaults

- D405: 424x240, 5 fps, `uyvy422`, FFV1 Matroska source.
- C922: 640x480, 30 fps, `nv12`, H.264 MP4.
- Common measurement window: ten seconds.
- One attempt, zero replacements, zero retries.
- Minimum common-window frame coverage: 95 percent per stream.
- Zero inferred missing container intervals.

### Open Questions

- Whether the D405 cable/connector remains attached under bounded arm motion.
- Whether metric-depth capture is available through a validated host path.
- Whether an independent timing source can establish exposure synchronization.

## Execution Rhythm

1. Freeze prompt and contract.
2. Implement and test nested production lifecycle order.
3. Commit exact runner/evaluator bytes before camera use.
4. Recheck devices, frozen evidence, process ownership, and unused output root.
5. Execute exactly one stationary session.
6. Independently evaluate and seal the raw evidence.
7. Update the Twin-fidelity state and obtain fresh read-only review.

## Progress Ledger

```text
Current state: Preregistered before implementation or camera use.
Completed: C922 v4 independent PASS; D405 6/6 stationary transport result and lifecycle-boundary C922 gaps reconciled.
Evidence: C922 v4 receipt 7354ce1d / digest 0933f548; D405 campaign 57d4983c / evaluation 80ed9ac3 / receipt cfc11ff3.
Remaining: Commit lifecycle implementation and evaluator, run one stationary session, seal and review.
Blockers: Motion-correlated D405 cable reliability remains outside this stationary transaction.
Next step: Implement D405-first/C922-second start and reverse stop ordering with deterministic tests.
```
