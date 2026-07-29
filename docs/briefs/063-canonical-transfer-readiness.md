# Brief 063 — canonical transfer readiness

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Freeze and run one read-only audit that compares the two strongest historical
directional candidates with the fresh physical torque-off anchor after the
canonical hard cutover and task-plane registration pass.

## Acceptance

- The canonical registration prerequisite remains accepted.
- Follower torque is false and both RGB cameras are available.
- Frozen action bytes decode as little-endian float64 at 40 Hz.
- The SIM_TO_REAL action stays inside calibrated bounds and gateway rates.
- The physical-to-model transform is explicitly calibration-approved.
- Each candidate's exact task start is within 10 degrees on every arm joint
  and within 5 percent on the gripper of the live anchor.
- Every check passes before any physical packet can be frozen.

## Stop

A reject authorizes only a fresh current-anchor-seeded action compiler in the
canonical runtime. It does not authorize a setup route, camera ownership,
gateway/serial access, torque, contact, or task motion.
