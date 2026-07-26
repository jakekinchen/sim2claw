# Slice Brief 042 — Pi Link-Tag Calibration

## Required outcome

Use the fixed Raspberry Pi IMX708 view and tag36h11 IDs `0`, `1`, and `2` to
make the follower pitch chain externally observable before fitting any joint,
camera, or simulator parameter.

## Current slice

Run one exact, CPU-previewed, follower-only shoulder-pan identity probe through
the reviewed gateway. Compare settled tag corners before and after the motion
to classify which visible tags are rigidly attached to the follower rather
than the nearby leader.

## Verification gate

- Fresh follower-only torque-off preflight passes.
- The exact command path is previewed with no new or worsened MuJoCo contact.
- The gateway reports no clamp, rate limit, stall, or tracking failure.
- Shutdown leaves follower torque off.
- IMX708 captures before and after the route retain full corners for every
  classified tag.
- A tag is not assigned to a follower link from appearance alone.

## Evidence boundary

This slice may establish tag-to-arm membership. It cannot establish camera
intrinsics, tag-to-link transforms, joint-zero offsets, physical transfer,
policy success, or task success.

## Next slice

After follower tags are known, acquire small independent shoulder-lift,
elbow-flex, and wrist-flex pose blocks. Fit IMX708 intrinsics from the known
20 mm tag squares, then run a separately held-out link-pose and pitch-zero fit.
