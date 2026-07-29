# Brief 093 — Observable registration OR0 corpus audit

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Implement one deterministic, hash-bound observability inventory for the new
successor campaign. It must bind the retained D1-to-D2 C922 and D405 RGB
streams, action/sample data, board/task-plane evidence, 3DGS registration,
existing static-geometry and first-divergence receipts, and immutable C6
outcome. It must assign fit, validation, sealed, diagnostic, or unavailable
roles without promoting any proof class.

## Acceptance

- The inventory validates file hashes, video dimensions/frame counts, action
  row count, camera timing metadata, and predecessor artifact identities.
- An observability matrix reports camera intrinsics, extrinsics, board,
  support, robot links, jaws, pawn path, contact, depth, actions, and outcome as
  available, bounded, diagnostic, or unavailable.
- The source-role split is fixed before OR1.
- Rebuilding produces the same canonical artifact digest.
- Focused tests cover drift, missing input, role leakage, and deterministic
  rebuild.
- No camera, serial, gateway, hardware, simulator outcome, or paid compute is
  opened.

## Stop

OR0 closes only the corpus boundary. It authorizes OR1 camera/world modeling,
not mapping approval, contact fitting, simulator correction, physical motion,
or transfer.
