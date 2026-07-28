# Slice Brief 061 - C2→C1 terminal scene reveal

**Date:** 2026-07-27

**Status:** Terminal. V1/v2 were compile-rejected; v3 received its one
setup-only physical attempt and stopped safely.

## Objective

Reveal C2 and C1 after the immutable C2→C1 exact-v1 transaction stopped with
the arm occluding both task squares. This slice may adjudicate the prior pawn
outcome, but it cannot alter, retry, repair, or promote the prior task trace.

## V1 compile rejection

Start from the fresh configuration-free torque-off anchor
`[-11.868132, -67.692308, 101.142857, -17.714286, -100.879121, 2.494062]`.
The v1 straight interpolation to the row-0 high home anchor was rejected
before review, cameras, gateway open, torque, or motion because the CPU/fp64
preview crossed the frozen known-safe self-contact envelope. V1 remains
unchanged and is not executable.

## Frozen v2 route

V2 reuses the successful source recording's observed post-release withdrawal
geometry at rows 350, 375, 400, and 465. Two raw lift encoder readings were
`0.087912°` beyond the calibrated minimum; v2 explicitly commands the legal
`-106.637363°` limit at those waypoints rather than allowing runtime clipping.
The 801-row, 40 Hz, little-endian float64 route stays below `10°/s`.
The CPU/fp64 preview rejected this source-tail interpolation before review,
cameras, gateway open, torque, or motion because it introduced a
left-upper-arm/left-wrist model contact pair absent from the source-only
admission.

## Frozen v3 route

V3 uses the existing recovery mechanism from the in-range but model-contacting
source pose: move only elbow flex monotonically inward to the physically
reached `93.934066°` clearance value, then hold elbow exactly fixed while the
other five joints withdraw to the previously previewed and physically
executed stable high geometry. The 721-row route is setup/recovery-only.

## Gates

- CPU/fp64 preview must report no new robot self-contact and no external
  contact.
- C922, native D405 RGB, and Pi RGB start before motion and enclose the
  one-second terminal hold. D405 remains RGB-only; metric depth is false.
- Independent review binds the fresh anchor, exact route bytes, hardware and
  camera identities, no clipping/rate/offset/IK/repair semantics, and
  torque-off close.
- Stop on any tracking, stall, rate, clamp, bus retry, camera, identity, or
  contact issue.
- Execute at most once. No pawn, board, or table contact is authorized.

## Evidence boundary

Every byte is setup/observation-only and excluded from task and transfer
hashes. The immutable C2→C1 exact-v1 executor result remains terminal even if
this reveal shows a successful pawn consequence.

## V3 terminal result

The v3 action was independently hash-bound and executed once. It stopped after
401 of 721 motion rows because elbow flex settled at `97.010989°` against the
frozen `93.934066°` request while the other joints began the withdrawal. There
were no accepted clamps, rate limits, action repairs, or bus retries. All
camera lanes enclosed the action and the follower closed torque-off.

The final C922 frame exposed the task squares sufficiently to adjudicate the
immutable prior task: C1 was not occupied upright, while the selected C pawn
was displaced/toppled near its source cluster. The reveal therefore owns a
terminal negative camera consequence only; it does not promote its own
tracking or the prior task.
