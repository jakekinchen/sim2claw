# Fable RP02 Pre-Motion Review

Status: `REPAIR_RP02`

Date: `2026-07-29`

Reviewer: Claude Fable 5, effort `High`, existing project thread

Reviewed branch and commit:
`codex/bidirectional-transfer-goal-loop-20260728` at `ed52ca3`

Review mode: read-only. No camera, gateway, serial, robot, or paid compute was
opened.

Fable verified the packet and executor hashes, fail-closed structure, rebase
gates, camera-before-gateway ordering, telemetry completeness, drift/camera
stops, cleanup attempts, and receipt paths. It found three material defects:

1. a stall inside the certificate-passing `(92, 93] deg` band skipped the hold
   and was mislabeled failure;
2. the `120 s` Pi bound left inadequate worst-case margin for gateway setup,
   twelve ladder intervals, hold, torque-off, `60 s` persistence, and
   postflight; and
3. `maximum_executions: 1` was not enforced because the CLI accepted any
   output directory.

Required repairs:

- a stall at or below `93 deg` must run the hold; a passing hold becomes
  `marginal_success_after_stall`;
- use a separately frozen Pi enclosure of at least `180 s`, with a
  proportionate minimum-frame gate; and
- require the output root to equal the packet-frozen path, making existence
  of that path the one-execution latch.

Fable also requested adverse-branch tests for marginal stall, held-joint
drift, camera failure, hold drift, and output-path reuse. If gateway torque
shutdown itself reports an error, the eventual owner authorization must tell
the present operator to power down at the supply.

This review authorizes repair and re-review only. Physical authority remains
false.
