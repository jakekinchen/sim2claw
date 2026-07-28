# Slice Brief 059 - Prospective exact D1→D2 REAL→SIM v4

**Date:** 2026-07-27

**Status:** Terminal negative after its one physical execution; no pawn
contact and no physics or SIM→REAL promotion.

## Objective

Execute one prospective D1→D2 pawn task physically, then replay the identical
counted canonical float64 task bytes in MuJoCo from the matched boundary state.

## Frozen boundaries

- Full torque-on transaction: 1,121 rows at 40 Hz, SHA-256
  `325b8a0c2cf709d399ba4ec51c1b95ddefec23b040c76b9cd3192949d9ce62a8`.
- Recovery/setup prefix: first 80 rows, excluded from transfer claims,
  SHA-256
  `998c5fd64272f608bbcdbca229cf4abc1250a8a1e09c793e7a56b8f28b712c0f`.
- Counted task suffix: 1,041 rows, unchanged from the pre-motion v3 candidate,
  SHA-256
  `360f22d790897dc4634ed28ddfea64c7d2b201c2a0094d83ff62d728fded9e69`.
- The v4 wrapper changes only the first excluded setup row to exactly match
  the fresh clipped command anchor.

## Admission gates

- Fresh C922 source-callback still must show the unchanged upright D1 pawn,
  empty D2, and full task corridor.
- Pi owns external robot context. Native D405 is action-enclosing supporting
  RGB only; `metric_depth:false`.
- CPU/fp64 preview must clear source-only robot self-contact before the counted
  boundary and report no external contact.
- The exact gateway may send the reviewed recovery command anchor before the
  frozen rows. That command and all setup bytes are excluded from the task
  hash.
- The counted suffix permits no clipping, rate limiting, offsets, IK, action
  repair, retiming, assistance, changed thresholds, or corrective suffix.
- Cameras start before setup motion, the physical task is attempted once, and
  every closeout guarantees follower torque off.

## Promotion rule

REAL is evaluated first from C922 board evidence. Only afterward may MuJoCo
consume the exact counted bytes. SIM→REAL remains forbidden unless the
independent evaluator promotes both the physical and physics D1→D2 outcomes.

## Terminal result

The one reviewed physical attempt completed the excluded 80-row setup prefix
and 609 counted task rows. It stopped safely before pawn contact when elbow
flex remained at `57.538462°` against the continuing inward request near
`54.197802°`. No clamp, rate limit, threshold change, action repair, or
corrective suffix was accepted. All camera processes closed and the follower
closed torque-off.

Because the physical task did not reach contact and did not succeed, the
counted action was not promoted as a REAL task result and SIM→REAL stayed
closed. The bytes are immutable and may not be rerun.

Accepted proof class:
`prospective_exact_task_terminal_tracking_failure_before_pawn_contact`.
