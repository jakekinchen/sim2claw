# Pawn Sim-to-Real Bridge at the 100 mm Workcell

Date: 2026-07-18 America/Chicago

## Scope correction

The current integrated simulator truth is commit `b3ac222` and workcell v3, not the
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
5. Air-tighten mechanism (`-0.10 rad` on the board, `-0.12 rad` after lift):
   exact replay completed, but final XY was `139.836 mm`, height error was
   `13.719 mm`, and upright cosine was `-0.135675`. The worst protected-pawn
   displacement remained below the gate at `3.165 mm`. Zero rows were admitted.
   Source receipt `85693c1645a7293d201c4b49e83453ea9deeae0524b492c1f3444ed62ccc0994`;
   verdict receipt `850b7760be1968d521b675519b9f5164e7ac21dfc2f69ce8808eec861716ef82`.
6. Lower collar target (`35 mm` instead of the original `41 mm` neck target):
   exact replay completed, but final XY was `50.085 mm`, height error was
   `13.719 mm`, and upright cosine was `-0.135675`. Zero rows were admitted.
   Source receipt `f89db83d166d8917f5d3134424c696a353293d734d7f62a057f4710869179292`;
   verdict receipt `3a6c334013b782293e0d4ee4ca843dc8d85fa83a0933040cc7b7b1526c3092dc`.
7. Original grasp redirected to the lower-residual `d6` destination: the
   generator aborted fail-closed during the post-release vertical extract when
   IK residual reached `12.399 mm`, above the unchanged `3 mm` bound. It has no
   completed receipt and contributes zero rows. The checked-in diagnostic
   remains the original `c8` to `c6` mechanism.

These are geometric-expert mechanism diagnostics, not learned-policy passes.

## Physical cohort and policy finding

The tracked five-episode physical ledger is intact at SHA-256
`22de7ec867448f8a3b524775bf586dc7fd013dc266d741e77b31a57d8bc87870`,
but it binds the 72 mm board pose. The five owner-local recording directories
were copied read-only from `jakekinchen@silicon` over Tailscale into the ignored
local recording root. Every ledger-bound receipt, sample stream, overhead
video, replay receipt, and replay state trace matches its frozen SHA-256.

The executable bridge now verifies `2,186` physical joint-response rows. Across
the cohort, best observed command-response lag is `0.15 s` for the two 20 Hz
episodes and `0.20 s` for the three 10 Hz episodes. These measurements authorize
joint-response comparison only; the pixels and square labels still describe
the historical 72 mm scene.

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

Current raw-verified receipt SHA-256:
`f35cf032d0ecbee482955b680531bdb1c413379b42d34496747a428f68f406e9`.
Joint-response calibration is ready. Readiness remains false for 100 mm spatial
comparison, pawn-policy training, and pawn-policy closed-loop comparison.

## Robot-anchored camera transfer

The hash-bound physical frame at `15.0 s` in recording
`20260718T225419Z-bdd95fdf` was registered to the historical 72 mm chessboard
using 64 reviewed grid intersections. A square-pixel pinhole fit produced a
`946.572 px` focal length, `28.455 degree` vertical field of view, and
`11.303 px` reprojection RMS. The resulting camera pose is stored relative to
the fixed left SO-101 mount, rather than moving the simulated robot to improve
the overlay.

That same robot-relative camera renders both the historical 72 mm scene and the
current 100 mm scene. The receipt mechanically verifies that the current board
is another `28 mm` robotward from the recorded scene. The old video remains
historical evidence; its current-scene image is only a transfer preview.

The independent robot-landmark check does not pass yet. The physical red wrist
ring centroid and the current simulator's `left_gripper` body-origin surrogate
differ by `179.015 px`, above the frozen `15 px` threshold. This localizes the
remaining calibration work to physical/simulator joint-zero and exact landmark
correspondence rather than hiding it in a board or robot translation. The
camera overlay is therefore visual-only and authorizes zero imitation rows.

Robot-anchored overlay receipt SHA-256:
`7aa5a052412c523b0df672db55691d4bb58c2afa821801e35ef0291af39c7f10`.

No held-out rows were opened, no physical authority was created, no GPU job was
started, and authenticated `brev ls --json` returned `{"workspaces": null}`.
