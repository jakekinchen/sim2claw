# Goal Loop — AVFoundation Format Inventory

## Mission

Replace the sealed C922 `requested_format_unavailable` prerequisite with a
versioned, native, read-only inventory of the device's actual AVFoundation
format and frame-rate surface. Evaluate the inventory under a rule frozen
before observation; do not reopen the exhausted source-localization campaign.

## Ordered Source of Truth

1. The owner-authorized evaluator-owned Twin fidelity closure objective.
2. Clean centralized `main` at
   `2e8b33da36a73a002d248c353eeb7095bbb9fd7f`.
3. The sealed AVFoundation source-localization campaign, evaluation, and
   receipt.
4. `configs/evaluations/avfoundation_format_inventory_v1.json`.
5. Apple AVFoundation/CoreMedia APIs and exact committed Swift/Python code.
6. `GOAL.md`, project state, the orchestration ledger, and run logs.

## Intended Outcome

The repository can enumerate the exact-name C922's native AVFoundation formats
without creating an `AVCaptureSession` or receiving frames. A separate
evaluator validates the observation, publishes all available dimensions,
subtypes, and rate ranges, and determines whether the original 640×480 target
has a candidate within the frozen fractional-rate tolerance. The output may
inform a new future campaign contract but grants no stream execution.

## Acceptance Criteria

1. Preserve the eleven S2 files, both HIL states, sealed D405 evidence, and
   exhausted AVFoundation source-localization evidence byte-identically.
2. Commit this prompt and the inventory contract before implementing or
   executing the native inventory.
3. Select the device by exact localized name and require exactly one match.
4. Record the declared format fields for every `AVCaptureDevice.Format` and
   every supported frame-rate range; the observer never scores or selects.
5. Do not instantiate or start `AVCaptureSession`, create a device input or
   output, receive a sample buffer, or touch the D405.
6. The evaluator alone applies exact dimensions, `0.05 fps` maximum
   fractional deviation, media-subtype preference, deterministic tie-breaks,
   aggregation, and verdict.
7. Fail closed on authorization failure, missing/duplicate device, malformed
   or duplicate formats/ranges, non-finite values, source/evaluator/binary
   identity drift, replayed output, mutation, or operation-budget drift.
8. Bind the committed source, evaluator, compiler, compiled binary, raw
   inventory, evaluation, and receipt by SHA-256.
9. Repeated evaluation materialization is byte-identical. Generated inventory
   outputs remain ignored.
10. Execute at most one inventory observation. If it cannot be verified, emit
    a prerequisite abstention; do not substitute FFmpeg formats or fabricate a
    candidate.
11. Focused tests and proportional exact-head repository gates pass before
    centralization.

## Evidence Standard

Report exact commits/trees, contract/source/evaluator/compiler/binary hashes,
device match count, format and range counts, all eligible candidates, selected
candidate or abstention, budgets, receipt digests, frozen-evidence hashes,
test counts, and closed authority. Keep device enumeration, source delivery,
container timing, physical exposure, metric depth, simulator fidelity, and
task evidence as separate proof classes.

## Decision Status

### Confirmed

- All 12 prior attempts failed before session startup with
  `requested_format_unavailable`.
- No prior source samples or D405 lifecycle treatments were executed.
- The original runner required a 640×480 range containing exactly 30 fps.
- AVFoundation device-format enumeration does not require a running capture
  session.

### Assumptions

- The device remains available under the same exact localized name.
- A common NTSC-derived rate such as 29.97 may explain the strict 30 fps
  rejection, but that is not treated as fact before inventory.

### Recommended Defaults

- One observation, zero stream sessions, zero frames, and zero D405 opens.
- Preserve exact 640×480 dimensions for this decision.
- Admit only a nearest supported rate within `0.05 fps` of 30.

### Open Questions

- Whether 640×480 exists in the C922's native format list.
- Whether its nearest rate is 29.97, below the tolerance, or absent.
- Which media subtype/range a future source-probe contract should freeze.

## Execution Rhythm

1. Freeze prompt and contract.
2. Implement/test observer and independent evaluator without enumeration.
3. Commit exact source/evaluator identities.
4. Execute one bounded inventory observation.
5. Evaluate once, freeze evidence, and update authority/state.
6. Verify exact head and centralize only after PASS.

## Progress Ledger

```text
Current state: Preregistration is committed; observer/evaluator implementation passes static and focused gates without device enumeration.
Completed: Prior 12-attempt prerequisite abstention is frozen and centralized; target/rate tolerance/ranking/budgets/authority are specified; standalone Swift enumerator, independent evaluator, and adversarial tests are implemented.
Evidence: baseline 2e8b33d; preregistration 8a29d3f; prior campaign 7c8b6ad3; Swift source 289c3fc2; evaluator 3ec4e50a; 15 direct and 96 combined focused tests pass.
Remaining: Commit implementation, execute exactly one inventory observation, evaluate, freeze evidence, verify, and centralize.
Blockers: Actual native C922 format/rate surface is not yet observed.
Next step: Commit exact implementation identities before any device enumeration.
```
