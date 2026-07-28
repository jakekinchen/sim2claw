# Reviewer decision 040: Q01 registration split freeze

Date: 2026-07-27

Decision: `CONTINUE`

Evidence anchor: `100`

## Independent audit

The reviewer loaded only the new manifest structure and recomputed SHA-256
for every declared path. The held-out files were treated as opaque byte
streams; no JSON field, image, video frame, or episode result was opened or
interpreted.

Acceptance results:

- Versioned split manifest exists and parses: pass.
- Seven fit inputs and four held-out inputs have explicit membership: pass.
- All eleven inputs exist and match their frozen SHA-256: pass.
- The held-out set is one independent completed B7 high-hover episode: pass.
- Held-out semantic inspection during Q01: none.
- Q02 family is bounded before fit: pass.
- Fit and held-out limits are both frozen at `25 mm`: pass.
- Action mutation is forbidden: pass.
- No robot motion, camera access, or paid compute: pass.

Manifest SHA-256:
`da203fae0e84ceb722631676858762e1ee3d5962be95c4555afb44f97bf51fdf`.

Q02 may fit only the frozen family. The B7 held-out content remains sealed
until the Q02 candidate is selected, serialized, and hash-bound.
