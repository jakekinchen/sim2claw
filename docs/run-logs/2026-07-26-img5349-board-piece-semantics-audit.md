# IMG_5349 board and piece semantics audit

Date: 2026-07-26
Checkout: `/Users/kelly/Developer/sim2claw`
Starting revision: `47ab12520edd11dc4607f9a8a4425ff49a77c444`
Proof class: read-only historical-and-current-physical-to-simulator visual diagnostic
Physical authority: false

## Question

After the accepted visual-registration D4 correspondence
`source[0..3] -> [h8, h1, a1, a8]`, do IMG_5349 and the current MuJoCo
scene agree on board-square appearance, robot-side rank, near-side color, and
the sparse pawn layout?

No hardware was opened or moved. No prior-project/archive material was read.
The audit used the clean-room scene source, the private owner-provided
IMG_5349 frames and COLMAP cameras, three already-completed current C922
captures with follower torque off, and the visual-registration values already
under review in this checkout.

## Reproducible image measurement

Twenty frames from the accepted COLMAP component were used:
`1-8, 10, 12-15, 17-18, 20-22, 24-25`. Each source playing-surface corner was
projected through its recovered COLMAP camera, then the board was rectified to
an `800 x 800` image with:

| Source corner | Rectified target |
| --- | --- |
| `source[0]` | `h8` |
| `source[1]` | `h1` |
| `source[2]` | `a1` |
| `source[3]` | `a8` |

The median rectified image was sampled only on empty ranks 3-6. For each
square, a 10-pixel boundary was excluded and a 20-pixel-radius center disk was
excluded. The remaining BGR median was converted to 8-bit gray with
`0.114 B + 0.587 G + 0.299 R`.

The ordered manifest of the 20 source frame names and SHA-256 values hashes to
`465f8b223cf51ab07f4977acbb311505fd8681dae47396d0f0563607357fe351`.
Representative frame 22 hashes to
`f9024526bae02c0b4e240940d99e10e0e35f690f0b80f523c9d6486ebb79498b`.

| D4-labeled parity | Squares | Mean gray | Median gray | Range |
| --- | ---: | ---: | ---: | ---: |
| even (`a1`, `h8` class) | 16 | 139.634 | 141.267 | 116.330-164.133 |
| odd (`b1`, `a2` class) | 16 | 226.597 | 226.821 | 221.344-230.901 |

The two observed classes have a 57.211-gray-level empty margin. IMG_5349
therefore has dark even-parity squares and light odd-parity squares. The
shared scene does the exact opposite: `scene.py::_board_body` renders even
parity as `(0.83, 0.63, 0.36)` and odd parity as
`(0.27, 0.105, 0.025)`. This is a proven **64/64 square palette inversion**,
not a fit-quality interpretation.

## Orientation and semantic result

The source edge `source[0]-source[3]` is the arm/robot edge in the registered
frames. The D4 fit maps that edge to `h8-a8`, so the current shared scene calls
the robotward edge rank 8. The current MuJoCo base-to-playing-edge distances
confirm the same geometry:

| Base | Rank-8 edge | Rank-1 edge |
| --- | ---: | ---: |
| left | 0.2542 m | 0.6098 m |
| right | 0.4617 m | 0.7278 m |

That geometric naming disagrees by 180 degrees with the frozen task-label
evidence already documented in `pawn_bg_workcell_fit.py`: the owner-reviewed
robot-side sparse row is `B1/C2/D1/E2/F1/G2`, while the shared scene puts
ranks 7/8 on the robot side. IMG_5349 contains no printed file/rank labels, so
its checker pattern cannot independently adjudicate that semantic convention;
the pattern is invariant under a 180-degree rotation.

The configured `near_side_color: black` agrees with IMG_5349: dark pieces are
on the arm/robot edge. It does not agree with the current sparse render,
which places tan pawn bodies on ranks 7/8, the robotward edge under the D4
mapping.

## Current sparse-scene measurement

The already-completed H/I/D calibration captures provide a current,
motion-free test of the side-color hypothesis:

| Pose | C922 frame SHA-256 |
| --- | --- |
| H | `5101bb896d580fd8a292ba659d2141a06b65ad46634e58732d74c7ab22d2e07b` |
| I | `8a83135d7da877252913180c5fa49390abdf681da860341076658dd56888845d` |
| D | `e846c270faf76322f0de9a0ef65cbbd8eb7eebc6ad36008d6ddbba24bac522f1` |

Each frame is
`runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-<h|i|d>-v1/stage-1/c922_1920x1080_torque_off.png`.

Pose I exposes all eight light pawns on the window/far two rows and seven of
the eight dark pawns on the robotward two rows. Pose D exposes the eighth dark
pawn that the arm occludes in I. Nine-by-nine-pixel head-center patches were
sampled with the same 8-bit gray equation used above. The eight light samples
came from I; the dark samples use seven from I and the complementary eighth
from D.

| Current physical side | Pawns | Mean gray | Median gray | Range |
| --- | ---: | ---: | ---: | ---: |
| window/far, light | 8 | 131.163 | 132.231 | 102.686-157.868 |
| robotward, dark | 8 | 41.822 | 32.634 | 22.745-83.460 |

The means differ by 89.341 gray levels and the sample ranges have a
19.226-level empty margin. The current sparse physical scene therefore
preserves the same side-color orientation as IMG_5349: dark robotward, light
windowward.

Under the D4 mapping, the shared scene renders eight tan/light bodies on the
robotward ranks 7/8 and eight brown/dark bodies on the far ranks 1/2. The
current C922 captures prove that **16/16 sparse pawn render colors are on the
wrong side in the shared scene**. This upgrades side color from a
non-transferable historical inference to current physical read-only evidence.

## Piece-layout result and remaining boundary

IMG_5349 shows a full standard 32-piece arrangement: light pieces occupy all
of ranks 1/2 and dark pieces occupy all of ranks 7/8 after the D4 mapping.
The current task scene contains 16 pawns on alternating squares:

- brown: `a2,b1,c2,d1,e2,f1,g2,h1`
- tan: `a8,b7,c8,d7,e8,f7,g8,h7`

Relative to this historical capture, current-simulator occupancy covers
`16/32` source-occupied squares; all 16 simulator squares are source-occupied.
Only `8/16` simulator piece families agree because the four rank-2 and four
rank-7 bodies coincide with source pawns, while the eight rank-1/rank-8 pawn
bodies replace source back-rank pieces. The side colors are opposite on all
`16/16` current bodies.

The historical piece counts and piece-family comparison remain
**non-transferable**: IMG_5349 predates the sparse task layout and cannot prove
whether replacing standard back-rank pieces with pawns was intentional. The
new H/I/D captures do, however, independently prove the current eight-dark
robotward/eight-light-far appearance and remove that uncertainty for side
color.

## Decision

Do not mutate the shared/frozen scene from this audit.

The exact checker correction and the now-current-frame-confirmed piece-palette
correction already exist in the visual-only
`pawn_bg_source_fit_visuals._apply_bg_visual_layout` lane. It deliberately
keeps semantic piece IDs and the frozen evaluator scene unchanged. Promoting
that appearance into the shared scene would change rendered observations and
invalidate frozen-evaluator continuity. The H/I/D evidence proves the visual
mismatch, but it does not by itself authorize invalidating frozen evaluator
artifacts or relabeling semantic piece identities.

The requested current-frame side-color measurement is now complete. The next
unresolved falsifiable measurement is semantic orientation: a single known
board-corner tag transform or one registered, externally labeled pawn centroid
is required to decide file/rank names without assuming chess convention.
