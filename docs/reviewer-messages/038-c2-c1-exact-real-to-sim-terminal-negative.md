# Reviewer message 038 — C2→C1 exact REAL→SIM terminal negative

Decision: `REJECT_TRANSFER_AND_REQUIRE_HUMAN_SCENE_PLUS_ELBOW_INTERVENTION`

Evidence anchor: `100`

The physical executor consumed every counted action byte exactly, but it did
not pass terminal tracking and the separate setup-only reveal shows no upright
pawn on C1. The physical task is a failure.

The exact float64 physics leg also fails: there is no selected-pawn contact,
no lift, and the pawn ends one square from C1. The diagnostic reward has no
promotion authority, and pawn evaluator v3 does not own the prospective
float64/40 Hz execution contract. No evaluator-owned REAL→SIM success exists.
Phase 2 SIM→REAL remains forbidden.

No other current adjacent-square case is admissible without physical
intervention. The C pawn is toppled/displaced, while metric depth and a
metric image pose are unavailable, so its complete state cannot be matched
exactly in MuJoCo or restored safely by an unmeasured robot action. Treating
another pawn as the selected object would still begin from a scene mismatch.

The remaining demonstrated adjacent-square templates also enter the failed
elbow corridor: observed minima are `40.659341°` for B1→B2, `44.527473°` for
D1→D2, `47.604396°` for E2→E1, `43.648352°` for F1→F2, and `36.263736°` for
G2→G1. The one high-elbow C2→C1 source has now received its single exact
physical task attempt and failed.

Required human intervention, with robot power removed and the arm supported:

1. Restore the selected brown pawn upright at C2 and verify C1 empty, without
   moving the board or other pawns.
2. Inspect the follower elbow mechanism at servo ID 3 for horn/linkage slip,
   binding, cable load, and inadequate power under gravity; correct the
   physical cause until the configuration-free exact gateway can hold and
   track inward below `68.703297°` without a sustained error above `3°`.

Do not change servo IDs, EEPROM calibration, the board pose, camera mounts, or
prior receipts. After intervention, begin a new health/qualification campaign;
never rerun the existing D1 or C2 action bytes.

Accepted proof class:
`human_mechanical_and_scene_intervention_required_transfer_not_achieved`.
