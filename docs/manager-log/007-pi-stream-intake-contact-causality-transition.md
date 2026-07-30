# Manager transition 007 — Pi stream intake and contact causality

Date: `2026-07-30`

Campaign: `observable_registration_contact_causality_v1`

## Owner direction

Intake the retained Pi stream, include it in the greater analysis plan, and
determine whether it can help synchronize actions.

## Evidence reconciliation

The successful retained physical D1-to-D2 source has C922 and D405 RGB but no
Pi IMX708 recording. Pi video, relative PTS, capture receipts, execution
receipts, and host-timestamped joint samples exist for later guarded executions
and contact-free tri-camera runs. Those files are useful, but they cannot be
presented as a third view of the successful source or merged with its actions.

The Pi capture receipt exposes host process bounds and `rpicam-vid --save-pts`
relative timestamps. It explicitly does not establish camera exposure time or
cross-camera exposure synchronization. Existing host-start-plus-PTS placement
is therefore diagnostic only.

## Transition

OR21 is activated as a model-identical, byte-identical OR19 introspection. It
must reproduce OR19 before reporting internal orientation, support, contact,
wrench, relative-velocity, or slip traces.

OR22A is prospectively frozen as a fail-closed Pi/action association:

1. Hash-bind every same-run video, PTS sidecar, capture receipt, execution
   receipt, and joint-sample trace.
2. Freeze image-motion and joint-motion features, lag grid, thresholds, and
   splits before task consequence frames are opened.
3. Estimate only one constant offset per run from setup, precontact, or
   contact-free robot motion.
4. Validate on contact-free tri-camera runs and apply without refit to later
   guarded executions.
5. Publish interval-valued action associations with uncertainty, or emit
   `PI_ACTION_ASSOCIATION_INSUFFICIENT`.

OR22 then permits bounded retained RGB proxies. The successful source remains
C922/D405-primary. Pi can support only same-run robot geometry, motion timing,
and later-run negative context. OR23–OR25 form the subsequent discriminator,
independent-mechanism, and prospective exact-replay gates.

## Authority and proof limits

All camera, physical motion, serial, gateway, heldout, task-attempt, training,
paid-compute, simulator-promotion, and transfer authorities remain false. This
transition changes the analysis control plane only. It does not open hardware,
claim exact Pi exposure synchronization, restore wrist depth, approve a global
mapping, identify contact parameters, or establish task transfer.
