# Brief 084 — RP04N C922 Crown-Track Freeze

Decision: `CONTINUE`

Evidence anchor: `103`

## Active card

C2-RP04N from the realized-action calibration queue.

## Freeze slice

Before physical-frame annotations:

- bind the C922 source, sample file, RP04K receipt, RP04M registration, and
  current workcell;
- freeze sample indices
  `[255,263,271,280,288,296,304,313,321,329,337,346,354,362,370,379,387,395]`;
- extract the C922 frame nearest each bound sample's recorded overhead-video
  time, rotated exactly as RP04M;
- define pawn crown center as the only annotation landmark;
- randomize order independently for two annotation passes;
- retain visible/occluded/unusable labels;
- freeze disagreement, coverage, consecutive-invalid, D1-translation, and
  ordered-curve gates;
- prohibit simulator-track access until both annotation files are complete.

## Outcome slice

After both passes are immutable, compare their admitted mean crown centers
only with RP04K's observed-state-plus-observed-grasp-mode pre-release
simulator projection. No board-plane metric unprojection, timing fit, depth,
terminal D2 fit, RP04L input, or action claim is allowed.

Pass advances only:
`camera_projected_carry_prefix_real_to_sim: 1/1`.

Failure is terminal for RP04N. Neither outcome satisfies C6.
