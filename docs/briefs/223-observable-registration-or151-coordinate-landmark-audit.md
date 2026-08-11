# OR151 coordinate and landmark audit

The owner reopened a bounded simulator-only lane on 2026-08-11. OR151 tests one
pre-replay question: did OR34 copy a pawn position expressed in one world frame
into a scene with different board geometry, rather than transporting the
retained board-relative coordinate?

The audit binds immutable OR34, its full trace, the physical endpoint receipt,
OR19, and the exact OR18 scene. It compiles OR18 with the same canonical piece
reset and may call `mj_forward` only. It must compare board center, side, yaw,
D1 center, the copied world XY, the board-coordinate-transported XY, free-joint
translation, body position, and support plane. Nominal camera residuals are
reported only as non-calibrating diagnostics.

Pass requires zero dynamics steps, byte-identical bound sources, exact
body/free-joint landmark agreement, at least 10 mm legacy-copy error relative
to OR18 D1, and at most 5 mm retained within-square error after board-coordinate
transport. A pass authorizes only a separately frozen one-variable replay. It
does not change OR34 or establish physical world registration, camera
calibration, physics fidelity, task success, promotion, or transfer.
