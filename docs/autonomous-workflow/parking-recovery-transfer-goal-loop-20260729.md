# Parking-Recovery Transfer Goal Loop

## Mission

Goal-loop through RP00--RP08 in
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
- Active card: RP01 parking-transaction freeze.
- Certified threshold: `93 deg`.
- Certified parking target: `91 deg`.
- REAL->SIM: `0/0`.
- SIM->REAL: `0/0`.
- Physical task attempts: `0/10`.
- Physical authority: false.

## Stop conditions

Success requires at least one REAL->SIM and one distinct SIM->REAL task
success. A terminal stop requires an immutable receipt demonstrating either
that RP00 has no viable margin target, RP02 cannot reach the certified target
safely, or RP03 has no safe family at the achieved lock.
