# Physical Gateway Torque-Off Preflight

Date: 2026-07-18 America/Chicago

## Result

Both saved SO-101 buses opened, matched their calibration files, returned six
joint positions and raw available current values, reported follower torque off,
and disconnected with no remaining serial handle.

- gateway: `sim2claw.so101_physical_gateway.v1`
- leader: `/dev/cu.usbmodem5B3D0448141`
- follower: `/dev/cu.usbmodem5B3D0406411`
- physical motion during preflight: none
- follower torque enabled: false
- initial maximum body reading difference: 196.0 degrees
- physical motion during both inspections: none

The initial read showed the arms at different physical poses, so the Record
page correctly blocked Start. After the operator placed both arms in the same
physical pose, a second torque-off read reported:

- paired-pose registration ready: true
- maximum body calibration offset: 8.6 degrees
- gripper calibration offset: 0.0 calibrated points
- follower torque enabled: false

The matched physical pose does not yield identical numerical positions because
the two arms have distinct calibration frames. The gateway therefore captures
the paired readings as a local relative zero. It does not move the follower to
the leader's absolute calibration coordinates.
