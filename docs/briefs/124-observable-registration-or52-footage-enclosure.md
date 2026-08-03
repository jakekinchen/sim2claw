# OR52 — Footage-only physical enclosure audit

Decision: `CONTINUE`

Evidence anchor: the owner has confirmed that no further hardware access is
available. The successful D1-to-D2 source still contains a hash-bound D405 RGB
stream and already accepted two-pass wrist landmarks.

## Required outcome

Reduce the existing, immutable wrist-footage annotations into an image-plane
enclosure and closed-command carry audit, then compare that physical proxy to
OR51's selected simulator trace. Use no new annotations, parameter fitting,
simulator replays, hardware, held-out evidence, or cross-episode evidence.

## Frozen gates

- Bind the successful episode, D405 RGB file, OR22 proxy rows, raw physical
  samples, and OR51 receipt by SHA-256.
- Use every row in the already frozen physical definite-carry interval for
  which both jaw tips and the pawn crown passed both annotation passes.
- Require at least eight co-accepted carry rows and a span of at least 80
  source samples.
- In each annotation pass, the crown projection onto the jaw axis must lie
  between the two accepted jaw tips for every co-accepted carry row.
- Derive the closed-command hold from the raw gripper command using only the
  frozen minimum target and tolerance. Require at least four co-accepted rows
  in that hold; report separation and normalized crown-coordinate dispersion
  without fitting a threshold.
- Preserve OR51's exact finding that only the moving jaw contacts the pawn and
  that bilateral named contact is absent.

## Claim boundary

This card may establish persistent image-plane enclosure and stable relative
carry evidence. It cannot prove metric aperture, depth, force, pressure,
bilateral physical contact, exact camera calibration, canonical collision
geometry, simulator promotion, task transfer, or physical authority.

## Terminal rule

If the frozen gates pass, publish the footage-derived constraint as the
strongest remaining physical contact-topology proxy and route future offline
work toward candidates that reproduce bilateral named contact and the physical
event sequence. If any gate fails, retain the prior OR22 insufficiency without
reannotation or threshold relaxation.
