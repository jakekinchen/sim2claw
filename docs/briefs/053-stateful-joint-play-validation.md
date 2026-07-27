# Brief 053: stateful joint-play validation

Status: candidate fit complete; new prospective route frozen but not executed
Branch: `codex/geometric-microtransfer-20260727`

## Mechanism result

The memoryless symmetric-deadband candidate failed its first round-trip
heldout because it improved joint RMS but worsened end-effector RMS. The next
model retains the original action bytes and passes them through a simulator-only
play operator: its internal target moves only when the requested target exits a
bounded, load-sign-conditioned interval.

Only four widths are fit:

- shoulder lift, shared in both directions: `2.125°`;
- elbow flex, against load: `0.125°`;
- elbow flex, with load: `2.125°`;
- wrist flex, shared in both directions: `1.000°`.

The three original one-way physical traces alone selected these values. Their
1,323 rows give `0.0745°` pooled joint RMS and `0.366 mm` end-effector RMS.
Against the previously selected memoryless deadband, the fit improves the
frozen robust objective by `96.9%`, joint RMS by `85.5%`, and end-effector RMS
by `85.1%`.

The already-open vertical round trip was not used for parameter selection. As
a family-support diagnostic, the selected play model improves its joint RMS
from `0.645°` to `0.303°` and its end-effector RMS from `4.123 mm` to
`2.767 mm`. This does not promote the parameters or replace a fresh heldout.

## New prospective route

The frozen route is a fixed-Z, negative-20-mm world-Y out-and-back. Its midpoint
IK residual is `0.061 mm`; pitch-joint excursions are `+3.976°` lift,
`-2.027°` elbow, and `+4.578°` wrist flex. It is directionally and
Jacobian-distinct from the vertical diagnostic while returning to the exact
starting action bytes.

Before any motion:

1. compile a fresh packet against the current torque-off pose and hardware
   identity;
2. require no new/worsened self-contact and no external contact over the full
   route;
3. verify packet, route, model, Pi contract, and play-fit content hashes;
4. independently review the packet;
5. require C922, D405, and Pi recorders live before torque-on.

During motion, any non-finite telemetry, altered action byte, clamp, rate limit,
stall, tracking-limit violation, assistance, or intervention aborts the first
unsafe sample and closes torque-off.

After motion, all three camera intervals must enclose the action and hold.
Parameter admission additionally requires the selected play model to improve
both joint and end-effector RMS over the selected memoryless baseline on this
new trace. Pawn contact remains forbidden regardless of this stage's outcome.

## Visual boundary

Pi tags 1 and 2 give a useful baseline-relative kinematic motion check, but the
frozen Pi camera candidate is offset by hundreds of pixels in absolute image
position for this mounting. Absolute overlay RMSE and photometric parity are
therefore invalid until a camera registration is frozen for this exact Pi
mount and orientation. C922 and D405 remain failure-localization streams even
when they do not see the link tags.
