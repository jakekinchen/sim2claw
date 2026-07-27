# Phase A REAL → SIM — D1→D2

Date: 2026-07-27
Outcome: `phase_a_visual_artifact_passed_physics_ineligible_fail_closed`
Proof class: `physical_source_to_visual_kinematic_simulator_partial`

## Selected source

`datasets/manipulation_source_recordings/d1-to-d2__20260727T041737Z-89190e53`

The C922 source visibly shows an upright pawn on D1 at the start and upright on
D2 at the end. D405 corroborates the close gripper/board interaction but does
not establish metric object pose. This source was selected over B5→A5 for its
clearer visible outcome, shorter complete dual-camera trace, and matching
nominal simulator piece.

The source receipt still says B2→B1. That conflict is preserved in the
comparison receipt and Studio; no raw source field was changed.

## Reviewer-visible artifact

- Studio feed: `Phase A proof` in the existing Physical pawn episodes catalog.
- MP4: `phase_a_comparison.mp4`, 640×1080, 20 fps, 531 frames, 26.55 s.
- MP4 SHA-256:
  `fa265434d04ac25ed99264e866eb8b7563142d5580a135bcec78bfd4742c327d`
- Poster SHA-256:
  `ef5fd26cd3815227ebb5dc8cff4725f6724a702cad2eff5f0933623fdb1a7e3a`
- Kinematic trace SHA-256:
  `09a931d5a018497bc29c34ae6a842493e40bae8b461a8eb5b1cb25659bca0bb5`
- Receipt SHA-256:
  `224c6b16ec672543946b77fe91403fa2d9e6849bce371812c0a096aaf032f6df`

The three lanes are visibly distinct:

1. REAL SOURCE — original C922 footage.
2. VISUAL/KINEMATIC TWIN — MuJoCo/CAD driven directly by observed physical
   joints; no dynamics or contact claim. The pawn is hidden during the
   unmeasured carry rather than given an invented trajectory.
3. ACTION-FROZEN PHYSICS — not executed; the video displays the exact blockers.

## Binary evaluator receipt

Passed:

- raw metadata conflict preserved;
- physical visual outcome verified;
- kinematic artifact hash-bound;
- physics lane fail-closed;
- Phase A browser artifact complete.

Failed:

- exact action replay eligible;
- physics task success.

Action hashes:

- operator-requested float32 bytes:
  `5d58874c166d2df9b890177ab9f1ef0a6934e53d46242b2346bf3428e5904c79`
- gateway-sent float32 bytes:
  `3b034bd965d4bf1a71591cc77f033e97f1fe8eb30aa75cb314cc529b4e40e3ef`
- observed physical joints float64 bytes:
  `ec75ad25adf9957311e837744af7340e27b602cfec5a2985db7841b5c3558312`
- source timestamps float64 bytes:
  `68e87c15992123e4415b2a3ec6d1a8e68cffd1ca642ac35002ed255544829f48`
- simulator-applied action: `null`.

Exact physics replay is ineligible because:

- 0/531 rows are marked precompiled exact;
- 151/531 rows were gateway rate limited;
- 151/531 rows were safety clamped;
- 284/531 operator-requested rows differ from gateway-sent rows;
- no actuator application/ack timestamps were recorded;
- the receipt requires float32 replay rather than frozen float64;
- direct physical targets exceed current MuJoCo actuator controls, and clipping
  is forbidden;
- irregular host-call timing cannot be reproduced by the fixed simulation step
  without forbidden retiming.

The C922 container has no source frame for the last 15 source rows. The artifact
does not duplicate or repair those frames.

## Verification

- `uv run pytest -q tests/test_real_to_sim_transfer.py` — 2 passed.
- `uv run pytest -q tests/test_studio.py -k 'not versioned_studio_posters_match_current_scene_sources'`
  — 16 passed, 1 deselected, 2 subtests passed.
- The deselected poster-receipt test concerns a pre-existing stale
  `scene.py` hash in a versioned Studio asset and is unrelated to this slice.
- Python compile checks and `node --check` passed.
- In-app browser verification loaded the exact catalog episode, reported
  640×1080 / 26.55 s / ready state 4, played past 1.4 s, and displayed
  `REAL → SIM Partial` plus `Physics gate Blocked`.

No robot bus was opened, torque was not enabled, and no physical motion
occurred.

## Public application bundle

Publication completed on 2026-07-27:

- Release:
  `https://github.com/jakekinchen/sim2claw/releases/tag/phase-a-real-to-sim-d1-d2-20260727`
- Release target:
  `b66c951a7aa612062b0c9c437b7b84b436ed6a3b`
- Release state: public, non-draft, non-prerelease.
- Local ignored bundle:
  `artifacts/publication/phase-a-real-to-sim-d1-d2-20260727`
- Published asset count: exactly four.

The four assets are:

1. `phase_a_comparison.mp4` —
   `fa265434d04ac25ed99264e866eb8b7563142d5580a135bcec78bfd4742c327d`
2. `phase_a_comparison_poster.png` —
   `ef5fd26cd3815227ebb5dc8cff4725f6724a702cad2eff5f0933623fdb1a7e3a`
3. `CLAIMS_AND_METRICS.md` —
   `83d1a4dfa9eae429d7e18b0932c2fc24a96e9a6800ebe26b86ccaf62eb27b874`
4. `PUBLIC_RECEIPT.json` —
   `c6edd5fa6ea3612bdb3c4fef2d8f636492151e4b25e6ec884c0f3e072f494e67`

All four assets were downloaded again from the unauthenticated public release
URLs and matched the local bundle byte for byte. The release page returned
HTTP 200 without GitHub credentials.

Privacy review passed. The release omits the raw source recordings, complete
dataset, kinematic trace, credentials, absolute private paths, device and
network identifiers, and unrelated artifacts. Generated media remains outside
Git history; only the public claim/metrics and redacted receipt contracts are
tracked.
