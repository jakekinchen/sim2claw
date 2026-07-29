# Fable RP02 Repair Verification

Status: `READY_FOR_TIME_BOUNDED_OWNER_AUTHORIZATION`

Date: `2026-07-29`

Reviewer: Claude Fable 5, effort `High`, existing project thread

Reviewed branch and commit:
`codex/bidirectional-transfer-goal-loop-20260728` at `7a33fcb`

Review mode: read-only. No camera, gateway, serial, robot, or paid compute was
opened.

Fable verified in code:

- a stall at or below `93 deg` enters
  `marginal_success_after_stall` only after the same `15 s` / `0.5 deg` hold
  passes;
- the packet binds the `180 s` / `4500`-minimum-frame Pi enclosure, leaving
  about `55--60 s` over its worst-case runtime estimate;
- the output path is frozen before authorization is read, so directory
  existence is a one-execution latch;
- authorization must bind the exact packet SHA-256, name the present operator,
  and acknowledge supply power-down on a torque-cleanup alarm; and
- adverse tests cover the output latch, marginal stall, held-joint drift,
  camera loss, and hold drift.

Verified packet SHA-256:
`79382c1aa0a9ec6d292300bb34dcf1c910fafb6a64f57bfa8e549c87c79abfe6`.

Verified executor SHA-256:
`f01c89816d72ad4212b2a26323895755300795dd296942434d9f0788592728fa`.

## Narrow authorization boundary

Exactly one execution of `rp02-elbow-parking-20260729-v1`, bound to the packet
hash above, with:

- `physical_parking_transaction: true`;
- `physical_task_attempt: false`;
- `maximum_executions: 1`;
- a timezone-aware window no longer than `60 minutes`;
- a named operator present throughout; and
- acknowledgement to power down at the supply if torque cleanup alarms.

No authorization document currently exists. This review is not physical
authorization.

## Fable usage policy

Per the owner, Fable is reserved after this point for a genuine blocker where
the next trajectory is unclear. Routine queue transitions, implementation,
tests, receipts, and known-gate execution proceed locally without repeated
Fable consultation.
