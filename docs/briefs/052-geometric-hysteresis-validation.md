# Brief 052: geometric hysteresis validation

Status: active
Branch: `codex/geometric-microtransfer-20260727`
Proof target: one prospective, no-contact, simulator-derived Cartesian
out-and-back whose exact float64 actions are replayed on the follower while
C922, D405, Pi IMX708, encoders, and current telemetry remain live.

## Why an out-and-back

The first prospective vertical move completed all 441 exact rows under the
three-camera gate. Its final lift, elbow, and wrist-flex residuals were
`-2.314°`, `+2.352°`, and `-1.065°`. The first 0.5-degree tracking divergence
appeared at `0.75 s` on elbow, `1.125 s` on wrist flex, and `1.625 s` on lift.
There was no rate limit, clamp, stall, assistance, intervention, or pawn
contact.

After torque-off the arm relaxes to the shoulder-lift lower limit. A one-way
descent from that pose cannot safely excite negative lift motion. The next
stage therefore performs a 15 mm vertical rise and returns to the exact
starting Cartesian pose before torque is disabled. Both directions occur in
one camera and gateway transaction.

## Bounded fit to falsify

The three executed geometric stages contain 1,323 exact rows. A bounded
lift/elbow/wrist deadband fit selected:

- shoulder lift: `1.5°`;
- elbow flex: `2.0°`;
- wrist flex: `1.0°`.

Against the rigid actuator it reduced pooled joint RMS from `0.976°` to
`0.513°` and end-effector RMS from `4.516 mm` to `2.459 mm`. Against the prior
lift/elbow-only deadband it improved joint RMS by `24.5%` and end-effector RMS
by `14.6%`. The parameters are fit evidence only and are not promoted.

The old additive elbow load-bias variant remains rejected. The current three
stages do not span enough load magnitude to identify a continuous load
coefficient.

## Frozen route

The midpoint is a candidate-model `+15 mm Z` pinch-point offset with
`0.639 mm` IK residual. The command deltas from the fresh anchor are:

`[-0.020°, +2.858°, -6.444°, +4.125°, -0.088°, 0]`.

The second segment reverses those exact deltas and ends at the start. Each
segment receives 180 fixed 40 Hz intervals, producing one 361-row action and
an 80-row final hold. Simulation must consume the same action bytes as the
physical gateway.

## Gates

Before motion:

1. the fresh torque-off pose and hardware identity must match the packet;
2. the whole piecewise action must be contact-clean in the current candidate
   scene;
3. C922, D405, and Pi must all report live recording.

After motion:

1. all 441 rows must be exact and unassisted;
2. all three camera streams must enclose the action and hold;
3. follower torque must be off;
4. the selected deadband candidate must improve both joint and end-effector
   RMS over the prior deadband on this held-out trace;
5. final return error must be at most `1.0°` on lift, elbow, and wrist flex.

Failure rejects the tied symmetric-deadband assumption. It does not authorize
post-hoc action correction. Pawn contact remains forbidden until a new
held-out geometric route passes.
