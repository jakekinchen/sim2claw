# Pawn Sim-to-Real Bridge at the 100 mm Workcell

Date: 2026-07-18 America/Chicago

## Scope correction

The current simulator truth is commit `7acd8b4` and workcell v3, not the
superseded 72 mm pose:

- scene: `operator_updated_chess_workcell_v3`;
- workspace: `workspace_board_fiducial_robotward_100mm_20260718_v3`;
- board pose: `board_robotward_100mm_20260718_v3`;
- board center: `[0.04, -0.065] m` in the table frame;
- board and fiducial total robotward displacement: `0.100 m`.

The 72 mm pose remains resolvable only to replay already-frozen evidence. It is
not relabelled as current.

## Versioned source and evaluator boundary

New recordings and pawn evaluations now use:

- `chess_pick_place_source_episode_v2.json`, SHA-256
  `215cec284096aab58881a1151b828c6a883c324de8f5e904a74213a9df72ed4b`;
- `chess_pick_place_pawn_evaluator_v2.json`, SHA-256
  `fa086802099d4da26263d02b32d70868df67f9dd034d4aa0fdc2aa2fd33c5e60`.

The v1 source/evaluator contracts remain loadable and select the historical
72 mm board center explicitly. Adapters resolve an episode's source contract by
its recorded hash, so updating the current workcell does not rewrite old
evidence. Historical replay also omits the newer visual-only Antler mug body,
because even a fixed visual body changes MuJoCo's full integration-state vector.
The original 72 mm source episode replays successfully after the v3 update with
the same `111.887 mm` rise and `14.824 mm` final XY result; the new regression
receipt is
`61449e69b8d49c363924343df0ee7a2d58ed2b135c044bccc283048bce73861c`.

## 100 mm mechanism checks

The previously admitted 72 mm c8-to-c6 action mechanism was regenerated under
the exact v3 scene and independently replayed at float32, 20 Hz, ten physics
steps per action.

1. Original close target (`-0.10 rad`): exact replay and all safety, identity,
   lift, height, upright, speed, clearance, and release gates passed. The pawn
   slipped during transit and finished `54.455 mm` from c6, so strict success
   was false and zero rows were admitted. Source receipt
   `068db18664ed629734690bc4c012a2d25142e8a42f709df691296c1023ff8d18`;
   verdict receipt
   `c45a386f2fca1b6cfec186c7f0745e9da999d7340dd393fe370194d131b7cd28`.
2. Separately versioned deeper close (`-0.28 rad`): retained more transport but
   destabilized the pawn. Final XY was `33.615 mm`, height error `13.719 mm`,
   upright cosine `-0.135674`; zero rows admitted. Source receipt
   `b43df236742725e09815e7780ab7b6d6308bbef1b709143ac2c0c1534e30c7ab`;
   verdict receipt
   `57c5853f9e8c124e621737a106d833816eb71d4f4fd95a6dada9feb2e8aa4376`.
3. Moderate close (`-0.15 rad`): the generator aborted fail-closed during lower
   when the IK residual reached `5.093 mm`, above the frozen `3 mm` bound. It
   has no completed receipt and contributes zero rows.
4. Narrow bracket (`-0.12 rad`): the generator likewise aborted during lower at
   `3.272 mm` IK residual. It has no completed receipt and contributes zero
   rows. The checked-in source mechanism is restored to the complete, diagnostic
   `-0.10 rad` baseline; no close-value sweep is opened.

These are geometric-expert mechanism diagnostics, not learned-policy passes.

## Physical cohort and policy finding

The tracked five-episode physical ledger is intact at SHA-256
`22de7ec867448f8a3b524775bf586dc7fd013dc266d741e77b31a57d8bc87870`,
but it binds the 72 mm board pose. Its owner-local raw directories are absent
from both the canonical and source worktrees on this Mac. Therefore the new
bridge receipt reports zero verified raw rows and cannot yet derive per-joint
lag, error, rate-limit frequency, or velocity envelopes.

The physical actions are human teleoperation traces, not a learned policy. The
only newly preserved learned artifact is the historical GR00T N1.7
phase-progress checkpoint-1000, manifest
`d5b0f78b98e0b598e79da6a3ef9a95ade8a0f2331324b5ec18ff60c80d1bb8b6`.
It was 0/6 on old rook/king development and has zero pawn authority. It may be
used only as warm-start provenance or a declared negative baseline after a new
pawn dataset and loader proof exist.

## Executable bridge

`sim2claw sim-real-bridge` now verifies the 100 mm scene/config/source/evaluator
identities, the physical ledger, every expected raw payload hash when present,
and the historical checkpoint boundary. With raw rows it computes per-joint
tracking RMSE, maximum error, best command-response lag, rate-limit frequency,
and observed velocity envelopes. It deliberately refuses to transfer old board
pixels, piece/target labels, contact dynamics, task success, or imitation rows.

Current receipt SHA-256:
`c9eae6bf735118b801b423cb2faa446577e3557ae5ac8a7180d2752f7df37088`.
Current readiness is false for joint-response calibration, 100 mm spatial
comparison, pawn-policy training, and pawn-policy closed-loop comparison.

No held-out rows were opened, no physical authority was created, no GPU job was
started, and authenticated `brev ls --json` returned `{"workspaces": null}`.
