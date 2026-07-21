---
name: audit-physical-telemetry
description: Audit one immutable physical teleoperation trace without inferring unrecorded robot, object, contact, or latency measurements.
---

# Audit physical telemetry

1. Call `telemetry_status` first and preserve the reported proof class.
2. Read the trace comparison before selecting bounded raw trace slices.
3. Treat raw present current as an effort proxy, never calibrated torque.
4. Treat endpoint camera frames as qualitative visual evidence, never metric
   object pose or contact evidence.
5. Preserve every unavailable observation exactly as reported. In particular,
   do not infer object trajectories, contact, grasp, actuation latency, camera
   latency, or simulator traces.
6. Treat the receipt outcome as a human-teleoperation episode label, not a
   learned-policy or instrumented-grasp result.
7. Submit the exact available and unavailable inventories and the frozen trace
   comparison digest with
   `claim_boundary='retrospective_physical_observation_only'`.

The audit may describe command tracking, velocity, current proxy, timing, and
camera timeline alignment. It has no calibration, admission, promotion,
physical-action, or transfer authority.
