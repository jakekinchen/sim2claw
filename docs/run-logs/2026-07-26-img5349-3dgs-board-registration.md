# IMG_5349 3DGS board/CAD registration

Date: 2026-07-26
Proof class: `board_conditioned_monocular_3dgs_to_sim_visual_registration`

## Outcome

The complete private IMG_5349 Gaussian splat now opens in Studio in the same
frame as the complete reviewed MuJoCo scene. The baseline registration is
automatic and hash-gated; the seven UI sliders are residual inspection
adjustments on top of that baseline, not a substitute for it.

The fit used the playing-board plane and lattice from the coherent early
COLMAP camera component. All eight square-board symmetries were considered.
The selected mapping was:

- `source[0] -> h8`
- `source[1] -> h1`
- `source[2] -> a1`
- `source[3] -> a8`

The final transform is:

```text
x_mujoco = 0.11870953974973307 * R * x_sfm + t

R = [[ 0.12518189077632438,  0.37175025365593917, -0.9198539248861252 ],
     [ 0.9093013231236073,   0.3278788193328457,   0.2562549191694785 ],
     [ 0.3968634500521828,  -0.8685028662817663,  -0.2969885069712877 ]]
t = [-0.1344718910727699, 1.1549008194205992, 1.1281755440773265] m
```

The otherwise ambiguous board symmetry was selected by comparing both static
SO-101 base clouds against the exact left and right simulation CAD. The
selected orientation had approximate white-splat-to-CAD median distances of
`22.7 mm` on the left base and `39.0 mm` on the right base. Those distances
select an orientation; they are not admitted robot-pose measurements.

The source MOV reports creation at `2026-07-19T00:39:10Z`
(`2026-07-18T19:39:10-05:00`). That is 46 minutes after the tracked 100 mm
board/workcell registration commit at `2026-07-18T18:53:12-05:00`, so the
source chronology is consistent with the current board pose rather than the
older 72 mm pose. Timestamp/order evidence still does not replace a measured
workcell survey.

## Held-out validation and rejected cameras

Frames `1`, `6`, `20`, and `22` were excluded from the orthomosaic/grid fit.
Together they provide `166` accepted board corners at `3.758551 px` weighted
RMS, with a worst per-frame maximum of `6.6812 px`.

The initial attempt to validate one transform over all registered images was
invalid. COLMAP registered locally consistent but globally incompatible camera
segments. Frames `40-49` have gross board projection inconsistency; the later
`59-77` segment is mixed, with board parity/overlap collapsing especially in
`73-77`. Those segments are quarantined. The earlier all-segment Sim(3) and
its `3.21 px` claim are retracted rather than averaged into this result.

## Studio verification

The read-only Studio at a separate loopback port loaded:

- `334,537` verified splats;
- the automatic board/CAD registration;
- `45` reviewed MuJoCo bodies, including both full SO-101 visual trees and
  bases;
- the geometry overlay enabled by default;
- the `3.76 px` held-out RMS in the viewer status and proof notice.

Toggling reviewed geometry off/on showed the original splat and the simulation
layer independently. The board alignment is visibly coherent. Source/current
arm-pose mismatch, pawn appearance differences, and reconstruction
ghosting/noise remain visible and are therefore measurable follow-up gaps
rather than being masked by a manual recentering.

A subsequent current-frame audit bound the already captured H/I/D C922 images
and proved eight dark pawns robotward plus eight light pawns far-side. The
registered calibration overlay therefore swaps only the display colors of all
64 checker squares and all 16 logical pawn bodies to the current physical
palette. It does not rename a body, move geometry, alter physics, or change the
shared/frozen evaluator scene.

Validation commands:

```bash
uv run python tools/validate_img5349_registration.py
uv run pytest -q tests/test_img5349_registration.py tests/test_studio.py \
  -k 'not versioned_studio_posters_match_current_scene_sources'
node --check src/sim2claw/studio_web/studio3dgs.js
```

The focused result was `18 passed, 1 deselected, 2 subtests passed`. The one
deselected broad Studio test is independently blocked by a pre-existing stale
`scene.py` hash in the checked-in poster receipt; this slice did not regenerate
or reclassify that simulation artwork.

## Authority boundary

The tracked contract binds the source video, PLY, producer manifest, and the
three COLMAP model files by SHA-256. It recomputes the board-corner and
held-out summaries and fails closed if the source binding, proper rotation, or
negative authority flags drift.

Nominal board size conditions the displayed scale. This result does not
establish measured metric geometry, collision surfaces, contact/compliance,
actuator/load behavior, task consequence, learned-policy transfer, or
physical-control authority. Twin fidelity remains `0 / 6`.
