# Brief 062 — canonical task-plane registration

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Freeze and run one motion-free evaluator that recomputes the already sealed V4
camera/robot/board registration through `sim2claw.current_workcell`.

## Acceptance

- Standard playing-corner order is exactly `a8, h8, h1, a1`.
- The canonical outer corners agree with the compiled board within `1e-9 m`.
- All 16 reset pawns agree with canonical square centers within `1e-9 m`.
- All 64 canonical square centers are unique.
- Four sealed heldout observations are recomputed without reopening images.
- Task-plane RMS and maximum are each strictly below `25 mm`.
- Reprojection RMS and maximum are at most `8 px`.
- The prior frozen result is reproduced to `1e-9` without refit.
- Camera, gateway, serial, recapture, motion, and task authority remain false.

## Stop

Pass closes the post-cutover registration gate only. Reject closes as a
terminal canonical-registration negative. Neither result authorizes a
physical task packet or transfer claim.
