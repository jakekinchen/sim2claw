# Parking-Recovery Transfer Goal Loop

## Mission

Goal-loop through RP00--RP08 plus the owner-authorized RP04K REAL->SIM
hard-cutover in
`parking-recovery-transfer-successor-task-queue-20260729.md` until genuine
bidirectional task transfer is evidenced or a new receipt-backed terminal
safety/external boundary remains after all safe agent-controlled alternatives
in that queue are exhausted.

## Source of truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. The parking-recovery successor queue.
4. Immutable causal-closure queue and receipts.
5. Current campaign graphs and receipts.
6. This goal loop.
7. Advisory Fable output.

## Rules

- Exactly one queue card is active.
- RP00 is simulation-only and runs exactly once after its freeze commit.
- No physical authority is implied by an RP00 pass.
- Never weaken collision, contact, camera, gateway, exact-byte, evaluator,
  attempt, or cleanup gates.
- Never ask the owner to reposition the robot or pawns.
- Every task failure stays in its direction-specific denominator.
- Global mapping stays unapproved; only a preregistered task-bounded mapping
  may be admitted.
- Policy ranking stays insufficient unless at least four paired physical cases
  exist under a prospectively frozen pilot.
- Fable is advisory and cannot override repository evidence or safety.

## Progress ledger

- RP00: complete PASS at receipt SHA-256
  `e1bc7d8e1bbeeaa4b1e08f26d7e609e2714c33800d22899bd876f7298c75db7b`.
- RP01: complete PASS at receipt SHA-256
  `e9e99a4ad774a04e5dc031a9b6060df6e32f7ceceb6e56fa40cfba61f481fc1f`.
- Active card: RP04K frozen software-only REAL->SIM hybrid replay.
- Certified threshold: `93 deg`.
- Certified parking target: `91 deg`.
- REAL->SIM: `0/0`.
- SIM->REAL: `0/0`.
- Physical task attempts: `0/10`.
- Physical authority: false.

The follower elbow mechanical-resistance signature closes further hardware
task motion until human service. RP04K must not open a camera, gateway, serial
bus, torque, or robot action. It may run one prospectively frozen local
simulator replay over the existing camera-verified Phase-A source. Its
command+mode and observed-state+mode ledgers remain distinct from the strict
pure-action ledger.

Fable is reserved for a genuine blocker where the correct next trajectory is
unclear. Routine queue transitions and verification do not require Fable.

## Stop conditions

Success requires at least one REAL->SIM and one distinct SIM->REAL task
success. A terminal stop requires an immutable receipt demonstrating either
that RP00 has no viable margin target, RP02 cannot reach the certified target
safely, or RP03 has no safe family at the achieved lock.
