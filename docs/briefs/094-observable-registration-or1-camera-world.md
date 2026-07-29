# Brief 094 — Observable registration OR1 camera/world model

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Establish the strongest gauge-fixed C922 camera/world model supported by the
OR0 corpus without fitting robot, jaw, contact, or task outcome parameters.
First decompose the accepted V04 projective camera to report focal, principal
point, skew, aspect, rotation, and center diagnostics. Then fit or rederive one
physical pinhole family from the frozen 9x9 board lattice with explicitly fixed
assumptions.

## Acceptance

- The board is the world gauge and its logical orientation is unchanged.
- The physical family fixes square pixels, principal point, and distortion
  policy before fitting; it may estimate only the board-supported focal and
  camera pose.
- The solver reports rank/conditioning, reprojection residuals, camera center,
  FOV, proper rotation, cheirality, and parameter plausibility.
- Existing V04 known-outcome validation is reported as reuse, not pristine
  heldout.
- The sealed D1-to-D2 task outcome, terminal pawn position, robot mapping, jaw
  offsets, and contact parameters are not fit inputs.
- If exact intrinsics remain unidentified, preserve that negative while
  emitting the strongest bounded projection model for OR2/OR3.
- Focused tests cover deterministic fit, hash drift, improper rotation,
  implausible projective decomposition, and proof ceilings.

## Stop

OR1 may accept a bounded camera/world projection or close exact calibration as
unidentifiable. It cannot approve robot/jaw/support mapping, contact physics,
task replay, hardware, or transfer.
