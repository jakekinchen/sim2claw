# Goal Loop — Isolated Overhead Host Inventory v1

## Mission

Determine, without opening either camera, whether `silicon.local` can own the
exact fixed C922 overhead camera as the physically separate host in a future
lifecycle-isolated dual-camera architecture. Keep the motion-coupled D405 and
robot path on `kelly-claude`.

## Ordered Source of Truth

1. The owner's evaluator-owned Twin-fidelity closure objective.
2. Exact clean baseline
   `40e59f000d0588fc36780694c57046d0d157f2e7`.
3. The sealed native common-session terminal-degraded receipt and guard.
4. Existing read-only Silicon provenance and the unverified
   `silicon_overhead_snapshot_v1` consumer contract.
5. `configs/evaluations/isolated_overhead_host_inventory_v1.json`.
6. Exact committed runner/evaluator identities.
7. `GOAL.md`, project state, orchestration ledger, and run logs.

## Intended Outcome

One content-addressed, zero-session remote inventory either verifies that the
exact C922 is present on `silicon.local` and the D405 is absent, identifies the
single physical C922-attachment prerequisite, or seals a precise access/tooling
abstention. It does not open a camera, prove a capture transport, align clocks,
or change any Twin-fidelity domain.

## Acceptance Criteria

1. Preserve all frozen S2, HIL, D405, C922, lifecycle, and common-session
   evidence byte-identically.
2. Commit this goal and contract before implementing the remote runner or
   making an SSH connection.
3. Freeze `kelly@silicon.local:22`, batch mode, strict known-host checking, a
   five-second connect timeout, and one connection attempt with no retry.
4. Allow only host, macOS, camera, and USB metadata from `/bin/hostname`,
   `/usr/bin/sw_vers`, and `/usr/sbin/system_profiler`. Do not read the remote
   repository, copy code, write a remote file, or invoke a shell pipeline.
5. Create no local or remote `AVCaptureSession`; capture zero frames and use
   zero camera lifecycle operations.
6. The independent evaluator owns host/platform checks and exact target
   matching for one C922 with USB vendor/product `1133:2140`. It separately
   requires zero D405 `32902:2907` matches for this overhead-host design.
7. Emit `isolated_overhead_host_ready` only if the remote metadata supports
   the declared architecture. If the C922 is absent, emit
   `isolated_overhead_host_requires_c922_attachment`; do not substitute another
   camera. If identity, authentication, tooling, schema, or accounting is
   unverifiable, emit `prerequisite_abstention`.
8. Add adversarial tests for host/user/port substitution, command injection,
   unexpected executable or data type, target/excluded-device mutation,
   session/frame/write accounting, malformed output, retry, and output-root
   replay.
9. Commit exact runner/evaluator/test bytes before the sole observation.
10. Seal raw/evaluation/receipt hashes and exact budgets. Do not proceed to
    capture until this result has independent read-only review.

## Evidence Standard

Report exact commits/trees; goal, contract, runner, evaluator, SSH executable,
raw, evaluation, and receipt hashes; resolved remote hostname and macOS
version; matched target/excluded device counts; return code; connection and
zero-session/frame/write accounting; tests; frozen-evidence proof; verdict; and
closed authority.

## Decision Status

### Confirmed

- The same-Mac nested FFmpeg and native common-session families are exhausted.
- The native common session delivered healthy active callbacks but failed its
  frozen post-stop identity gates.
- `silicon.local` is a separate previously audited Mac host reachable through
  SSH; the existing overhead snapshot contract is explicitly not live-verified.
- The fixed overhead C922 is the lower-risk camera to move between hosts. The
  D405 remains motion-coupled to the robot-side path.
- The sole strict inventory reached `silicon.local` on macOS `26.3.1` and
  found zero C922 camera/USB matches and zero D405 camera/USB matches.

### Assumptions

- No device-presence assumption remains. Silicon is reachable, but neither
  target nor excluded camera is attached.

### Recommended Default

- Do not retry this inventory. Physically attach the fixed overhead C922 to
  Silicon while leaving the D405 on `kelly-claude`, then preregister a new
  exact-device confirmation and capture-transport transaction.

### Open Questions

- When the physical C922 USB attachment can be moved to Silicon.
- Future source timestamp transport and cross-host clock-alignment behavior;
  neither is part of this inventory.

## Execution Rhythm

1. Commit preregistration.
2. Implement and adversarially test the strict runner/evaluator offline.
3. Commit exact bytes and obtain a pre-observation review.
4. Execute one zero-session remote inventory.
5. Evaluate once, seal, review, and choose capture implementation or physical
   attachment prerequisite.

## Progress Ledger

```text
Current state: Terminal attachment-required result; one inventory/connection budget exhausted with no retry.
Completed: Preregistration 76beee9; final reviewed implementation 7810c65; 1/1 zero-session inventory; tracked exhaustion control.
Evidence: Raw f3cf7ed8; evaluation fdcd1359; receipt file 109532c8 / digest 44ad7049; Silicon macOS 26.3.1; C922 0 camera/0 USB; D405 0 camera/0 USB.
Remaining: Physical C922 USB attachment to Silicon, then a new capture-transport transaction.
Blockers: The fixed overhead C922 is not attached to Silicon.
Next step: Do not retry. Await physical attachment while advancing independent offline Twin-fidelity prerequisites.
```
