# Sparse-pawn simulator correction

Date: 2026-07-18 America/Chicago

## Reported mismatch

The Studio's interactive simulator still displayed a full 32-piece chess setup
after the current task contract had moved to a two-sided sparse pawn layout.
The pawn silhouette also did not resemble the owner's physical wooden pawn.

## Root cause

Commit `8a34c9f` added the correct 16-pawn scene and explicitly routed new
teleoperation recording and physical-command replay through it. The Studio's
only interactive 3D episode, however, was an older scripted grasp artifact. Its
saved state trace explicitly referenced `/api/scene?layout=standard`, so the
browser correctly reconstructed the historical 32-piece scene. Separately, the
current-scene catalog card still contained the hard-coded subtitle `32 dynamic
pieces`. The UI therefore presented historical full-board evidence as though it
were the current workcell.

## Correction

- New scripted grasp probes explicitly build
  `sparse_two_sided_pawns` and write that layout into their state traces.
- Piece discovery supports brown/tan current-task pawns while remaining generic
  enough for older explicit standard-layout tasks.
- The regenerated trace contains only brown pawns at A2, B1, C2, D1, E2, F1,
  G2, H1 and tan pawns at A8, B7, C8, D7, E8, F7, G8, H7.
- The Studio current-scene card now declares `16 sparse pawns` and carries the
  current layout identifiers.
- Current inspection posters and the scripted probe were regenerated from the
  corrected scene.

## Pawn model

`IMG_5346.HEIC` was used as a silhouette reference only; it was not copied into
the repository and provided no trustworthy metric scale. The existing
board-relative pawn scale was retained. For the current sparse layout, the prior
two-disc, capsule, and sphere assembly was replaced with a lathed-style native
MuJoCo profile: stepped foot, rounded base, flared lower body, narrow waist,
collar, and spherical head. Brown and tan materials were adjusted toward the
walnut and light-wood appearance of the physical set. The explicit legacy
`standard` layout keeps its lightweight primitives so historical manifests stay
replayable and the legacy endpoint remains fast enough for compatibility tests.

## Proof

- The updated scene compiles and steps with exactly 16 pawn bodies.
- Each pawn uses 11 cylindrical profile rings, two ellipsoidal transitions, and
  one spherical head, with no capsule primitive.
- The regenerated scripted probe grasped `tan_pawn_c8`, lifted it 95.1 mm, held
  contact for 100 percent of the lift/hold window, and passed its existing
  scripted-probe gate.
- The new state trace has 304 MuJoCo states at 30 Hz and contains no legacy
  white/black piece bodies.
