# Hardware Canary Protocol

This document freezes Phase 1's operator-facing boundary; it does not authorize
Phase 2.

Preflight order:

1. Require explicit owner setup/capture/motion authority for the requested
   operation.
2. Use only the reviewed physical gateway; begin torque-off.
3. Bind robot and servo identities, firmware, calibration, fingertip profile,
   board identity and dimensions, transforms, cameras, table/fixture geometry,
   and joint mapping.
4. Classify the setup `new_related_workcell` unless every sameness requirement
   is independently proven.
5. Freeze calibration, validation, and hardware-held-out trial IDs before
   motion; reject any overlap with training.
6. Keep wrist, side, and depth cameras evaluator-only unless a separate policy
   ablation is frozen.
7. Require a valid `TW-PHYSICAL-CANARY` certificate and separately verify
   gateway/owner authority.

If any step fails, camera capture and motion remain disabled. The retired
workcell is never overwritten or pooled automatically, and Phase 2 results do
not reopen the method.
