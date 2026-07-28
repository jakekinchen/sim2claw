# Brief 050: geometric micro-lattice transfer

Status: terminal negative; mechanism isolated
Branch: `codex/geometric-microtransfer-20260727`
Proof target: one prospective, no-contact, simulator-derived Cartesian loop
whose exact joint commands are replayed on the follower and scored with
external Pi link fiducials.

## Live starting evidence

- Fresh torque-off gateway preflight passed at
  `[-8.351648351648352, -106.46153846153847, 98.41758241758242,
  -100.17582417582418, -126.37362637362638, 1.66270783847981]`
  degrees/percent.
- Fresh C922 frame
  `runs/geometric-microtransfer/20260727-current-layout-v1/c922/frames/frame-050.png`,
  SHA-256
  `dc9791f51bb384842731d52e9e3c788d8c4b80f87ea4cb771bd196ee7cbbf4ac`,
  shows the board, pawn layout, follower, and scene tags.
- Fresh Pi IMX708 frame
  `runs/geometric-microtransfer/20260727-current-layout-pi-v1/pi-imx708.jpg`,
  SHA-256
  `f87e58e201f24aa07d0ecf08c5a3e720a5cc2d5f5b177c7a338383c0c17b2b5a`,
  shows the follower and four link/base tags.
- The D405 was not enumerated by `rs-enumerate-devices`. The attempted static
  tricam capture stopped before robot motion and shut down its C922 owner.
  This campaign therefore uses C922 plus Pi and makes no metric-depth claim.

## Frozen simulator action

Use the current candidate model and provisional physical mapping only as a
diagnostic consumer. From the fresh physical anchor, solve three absolute
pinch-point targets with the existing damped least-squares reach solver:

1. table-frame `y - 7.5 mm`;
2. `y - 7.5 mm, z + 7.5 mm`;
3. `z + 7.5 mm`;
4. exact return to the original anchor.

The loop is a 7.5 mm rectangle. The three solved residuals are respectively
`1.332202 mm`, `1.298967 mm`, and `1.009257 mm`. Freeze each physical joint
target in `configs/hardware/geometric_micro_lattice_7p5mm_v1.json`, then let
the existing staged gateway create only direct, 40 Hz, at-most-10-degrees/s
interpolations. No IK, clipping, offset, or corrective action may occur after
the route is frozen.

## Prospective evaluator

Before motion, bind
`configs/evaluations/geometric_micro_lattice_transfer_v1.json`. Score:

- exact action and target identity;
- commanded/observed joint tracking at every hold;
- FK pinch-point displacement from the observed hold joints;
- unique Pi detections for tags 0, 1, and 2;
- absolute and anchor-relative tag-corner reprojection against the frozen
  three-link camera/tag candidate;
- return-to-anchor residual;
- absence of new MuJoCo contact, gateway clamps, rate limiting, and stalls.

The relative tag-corner score is the primary new signal because it tests link
motion while cancelling much of the fixed camera and tag-mount bias.

## Execution ladder

1. Compile the exact four-stage packet from a fresh torque-off read.
2. Seal a separate review receipt.
3. Execute one stage at a time through the reviewed follower-only gateway.
4. Record C922 source-callback frames during motion and one Pi still during
   each torque-on hold.
5. Close the gateway torque-off after every stage and evaluate the completed
   prefix before admitting the next stage.
6. Stop after the closed loop. Do not touch a pawn in this campaign.

## Stop conditions and claims

Stop before or during motion on hardware identity drift, an anchor mismatch,
missing camera ownership, new model contact, changed action bytes, a gateway
clamp/rate/stall condition, or a failed stage return gate. A completed loop is
only `physical_no_contact_geometric_transfer_diagnostic`; it cannot promote
the workcell registration, provisional joint transform, simulator parameter,
policy, pawn task, or physical task capability.

If it passes, the next campaign may compile one low-risk, currently occupied
checkerboard pawn move. If it fails, fit only the mechanism identified by the
frozen residual decomposition, then repeat this same loop as held-out
validation before any contact action.

## Closeout

Stages 1 and 2 executed all 882 exact motion/hold rows without clipping, rate
limiting, assistance, or a gateway stall. The physical follower stayed
torque-off after each close. Stage 3 correctly stopped before gateway open
because torque-off relaxation moved the elbow outside the frozen anchor gate.

The camera-only Pi refresh fit tags 1 and 2 to `3.058 px` combined corner RMS
on stage 1, but stage 2 did not uniquely decode tag 2. The view-dependent tag
gate therefore rejected the refresh; it was not promoted.

The action-frozen actuator check rejected the previously selected elbow
load-bias term. Against a rigid actuator model it improved pooled joint RMS by
`20.464%` and end-effector RMS by `6.353%`, confirming that actuator play is a
real gap. Against the simpler two-degree lift/elbow deadband, however, it
improved joint RMS by `8.605%` while worsening end-effector RMS by `32.985%`.
The load-bias term is not retained. The next admitted mechanism is
direction/load-conditioned joint play including wrist flex, with no pawn
contact until a separately frozen geometric probe validates it.
