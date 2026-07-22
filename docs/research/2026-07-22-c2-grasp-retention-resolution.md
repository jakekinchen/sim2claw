# C2 grasp-retention simulator-gap resolution

## Decision

The issue is diagnosed but no simulator candidate is promoted. Across eight
frozen campaigns, 98 C2 replays retained the exact source action SHA-256
`402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
Zero passed the combined loaded-aperture, lift-and-transport, slip, and
contact-through-release gate, so the three sentinels and all-eleven promotion
lanes correctly remained closed.

The exact unresolved mechanism is force-dependent deformation of the physical
rounded rubber caps and the resulting distributed contact patch versus jaw
force. The retained overhead video and cached 5 Hz current cannot identify that
mapping. A rigid box or capsule contact primitive is insufficient.

## What the loop discovered

- The accepted simulator's fixed rubber sleeve is displaced from the rigid
  fixed-jaw box that actually carries the C2 load. Aligning it delays bilateral
  contact loss from source frame 323 to 381, a 58-frame causal gain.
- The physical gripper stays mechanically loaded: normalized command/measurement
  medians are 1.07% and 4.39%. In mapped joint units the closed-window medians
  are -0.15401 and -0.09017 radians; the accepted simulator is about 3.12
  degrees too closed.
- Feetech documents 6.5 mA per current-feedback unit, a 7.8 kg-cm/A torque
  constant, and a 1:345 gear ratio. The retained median raw current of 7 maps
  to a 0.0348 N-m output-torque proxy, while the accepted MuJoCo force range is
  8.82 N-m. Constant low torque cannot close the jaw, confirming that closure
  and geared holding require a hysteretic actuator model.
- A contact-armed load-hold model matches the physical mapped aperture within
  0.03 degrees. A 6D version retains contact to frame 399, two frames before
  intended release, but changes the lift/transport consequence.
- A transport-preserving composite matches aperture within 0.04 degrees but
  loses contact at frame 328. Rounded rigid capsule pads also fail. Thus
  aperture fit, transport, and retention cannot be jointly reproduced without
  deformable pad evidence.

## Ruled out as standalone repairs

Higher scalar friction, actuator-zero shifts, finite global force, binary
contact force limiting, 3D/4D/6D contact dimensionality, softened rigid
contacts, thicker rigid sleeves, collision occlusion, and box-versus-capsule
pad shape all fail at least one frozen consequence gate.

## Required acquisition before reopening

Use an operator-owned, bounded calibration packet rather than a pawn task:

1. Three unloaded close/open cycles and three blocked closures at each of two
   known jaw gaps.
2. Jaw angle and motor current at 100 Hz or faster through close, contact,
   hold, and release.
3. Direct fingertip normal force versus commanded and measured angle.
4. Rubber-cap profile, thickness, durometer or compression curve, and loaded
   contact-patch dimensions.
5. A synchronized side view that resolves both fingertip contact heights and
   pawn pose.

This document grants no robot-motion authority. The experimental
`gripper_load_hold_enabled` path is disabled by default and remains
non-promoted.

## Evidence

- Closeout receipt: `outputs/sail/grasp-retention-closeout-v1/receipt.json`
- Receipt SHA-256:
  `479e87231df4579b817ac8bd2fd62363c2a15f974e3467802aa0809e35ec3d26`
- Receipt digest:
  `3887636e0a04b09289337e09a06c82867fcd6beb13b46b27fcfed8e6f73d2f14`
