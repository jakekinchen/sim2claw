# SAIL Phase 2 Related-Workcell Operator Handoff

Phase 2 is ready to execute without redesign but is intentionally blocked. The
compiled packet classifies the unbound setup as `new_related_workcell`, reports
all 13 required identity fields missing, and opens neither capture nor motion.

## Frozen entry sequence

1. Obtain explicit owner authority for the requested operation.
2. Bind robot/servo identities, firmware, calibration, fingertip, board,
   transforms, cameras, table/fixture, and joint mapping.
3. Classify the setup as new-related unless every sameness condition is proved.
4. Freeze calibration, validation, held-out, and hardware-evaluation roles.
5. Run the reviewed gateway preflight torque-off.
6. Collect the 11-item static/read-only measurement package.
7. Score the three frozen Phase 1 predictions before changing the method.
8. Request separate motion authority, then run only the five empty and six
   interaction probes in the frozen packet.
9. Open held-out evidence once after the candidate family is frozen.

## Frozen predictions

- `P2-TIMING-RATE`: discriminate rate-dependent lag from load compliance with
  instrumented command-to-observation timing at multiple command rates.
- `P2-LOAD-PROXY`: test whether held-pose elbow signed error co-varies with a
  fresh synchronized current/load proxy after timestamp alignment.
- `P2-CONTACT-OBSERVABILITY`: obtain measured contact, retention, and slip;
  joint/EE residuals alone cannot establish interaction fidelity.

## Stop boundary

Missing authority, identity, gateway review, fresh timing/current, immutable
source/safety receipts, split integrity, camera-role separation, a matching
TwinWorthiness capability, or the original Phase 1 method/prediction freeze
causes a clean stop. The retired workcell is never overwritten or pooled. This
handoff is a protocol artifact, not evidence that a camera, bus, servo, or robot
is available.
