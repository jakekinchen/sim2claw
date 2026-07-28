# Slice Brief 060 - Prospective exact C2→C1 REAL→SIM v1

**Date:** 2026-07-27

**Status:** Terminal negative; the one physical attempt and exact physics leg
are complete. SIM→REAL is closed.

## Objective

Attempt benchmark case 2 using the current canonical C2 pawn and empty C1
square with geometry that stays entirely outside the immutable D1→D2 v4 elbow
stall corridor.

## Mechanism selection

D1→D2 v4 stopped after 609 counted rows when elbow flex remained at
`57.538462°` for one second against a `54.197802°` command. No pawn was moved.
The successful C2→C1 provenance recording's observed path stays between
`66.417582°` and `99.120879°` elbow flex. Its post-release segment ends at
source row 350 before the irrelevant return-to-home tail.

## Frozen boundaries

- Full transaction: 1,061 rows at 40 Hz, SHA-256
  `ecf950ea9252c3e6c1b7e4b5df333dfcb75eb2b5bff43ee5d4d1a7b6154828ed`.
- Setup prefix: 360 rows from the fresh torque-off anchor to the demonstrated
  high home anchor, excluded from transfer claims, SHA-256
  `510b096dc5eac17e0435ba281fa023b6d0b7884fb6816d115cb3ca344563c22e`.
- Counted C2→C1 task: 701 rows, SHA-256
  `0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da`.

## Gates

- C922 must admit a pawn at C2, C1 empty, and an unobstructed task corridor.
- CPU/fp64 preview must report no robot self-contact or external contact.
- C922, native D405 RGB, and Pi RGB start before setup motion; D405 depth is
  unavailable and unnecessary.
- No clipping, rate limiting, offsets, IK, retiming, assistance, repair,
  threshold changes, or corrective suffix is accepted.
- The physical action gets one attempt. REAL outcome is scored before the
  identical counted bytes can be applied in MuJoCo.
- SIM→REAL is forbidden unless both physical and physics C2→C1 task outcomes
  are independently promoted.

The first compiled packet was preserved as a pre-review software rejection:
its setup-prefix preview was valid but omitted from the serialized boundary.
Packet `packet.v2.json` includes that contact-free prefix preview and is bound
by independent decision `20260727-c2-c1-exact-v1-reviewed-v2`. No physical
motion occurred under the rejected packet.

## Terminal result

The independently reviewed v2 packet received one physical attempt. The
gateway issued all 1,061 frozen rows, including all 701 counted task rows,
without a clamp, rate-limited row, bus retry, action repair, offset, IK
correction, or suffix. It then stopped before the terminal hold because lift
and wrist-flex residuals exceeded the reviewed three-degree target tolerance.
The follower closed torque-off.

A separately reviewed setup-only reveal showed that C1 was not occupied by an
upright pawn and the selected pawn was displaced/toppled near C2. This is a
physical task failure. The reveal does not alter or retry the task.

The identical canonical task bytes were then mapped once with separately
hash-bound transform
`72812016bfa9dba2ba97fe448724394ad290a2b22458177bcbdec95aae0689e6`
and applied in MuJoCo at the frozen 40 Hz float64 contract. No control value
was out of range. The simulator never established jaw contact, recorded zero
piece rise, and ended one square from C1, so physics task success also failed.
The frozen pawn evaluator v3 cannot promote this replay because it owns a
different float32/20 Hz execution contract; its consequence thresholds fail
lift and final-square gates in any event.

Accepted proof class:
`exact_action_real_and_physics_terminal_negative_no_transfer_authority`.
