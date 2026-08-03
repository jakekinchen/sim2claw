# OR54 — Second successful same-rig footage replication

Decision: `CONTINUE`

Evidence anchor: OR52 extracts persistent image-plane enclosure from the
successful D1-to-D2 D405 RGB episode. A separate successful source recording
from the same native dual-camera rig contains `632` action samples, `196` D405
RGB frames, and `1181` C922 frames, but has not been admitted to the observable
registration campaign.

## Required outcome

Determine whether the exact two-pass Lucas-Kanade method used by the primary
episode can recover both jaw tips and the pawn crown during the second
episode's raw-action-derived closed-gripper hold. This is a replication
diagnostic, not held-out validation: the success label and footage were already
known before the card was frozen.

## Frozen scope

- Bind the recording receipt, raw samples, D405 browser RGB video and metadata,
  plus OR52 and OR53 closeouts by SHA-256.
- Treat receipt semantics (`brown_pawn_b2`, `b2` to `b1`) as authoritative.
  The directory label `b5-to-a5` is filename context only and must be reported
  as a metadata conflict.
- Derive the longest exact closed-command hold from raw actions, then inspect
  only D405 frames `100–125`, whose nearest source samples must all fall inside
  that hold.
- Use the same bidirectional optical-flow parameters and `8 px` disagreement
  gates as the primary episode. Permit only the six frozen endpoint anchors;
  no per-frame manual correction or interpolation.
- Require at least `20/26` two-pass-accepted rows for each jaw tip and the pawn
  crown before calling the enclosure signature replicated. Otherwise abstain
  per point class and preserve any narrower accepted result.

## Claim boundary

The recording is non-metric, not exposure-synchronized, not held out, and
already labeled successful. OR54 cannot establish metric aperture, depth,
force, bilateral physical contact, calibrated geometry, simulator promotion,
or task transfer. It runs no simulator and changes no parameters.
