# B-G pawn source-fit and contact-sensitivity run

Date: 2026-07-19 America/Chicago

Outcome: **terminal negative; no source-fit adapter accepted**

This run implements the proposed gripper-close proxy, compares the resulting
simulated pinch point with the labeled source/destination square centers, and
scores the same permitted physical teleoperation source commands with the
already frozen B-G simulation reward. It also records the evaluator score for
every simulator configuration run.

It is not an ACT policy evaluation. No compatible B-G pawn ACT checkpoint
exists locally. The commands are human-owned ACT-source demonstrations, not
policy weights or learned policy actions. No training, hardware, robot, camera,
serial bus, gateway, network research, physical held-out data, Brev, paid
compute, or physical motion was used.

## Frozen specification and identities

- source-fit contract:
  `configs/optimization/pawn_bg_source_fit_v1.json`
- source-fit contract SHA-256:
  `9144e42316dc007f8fcd381c6b7c054cbfe12e8c7b639d2a06f1f91070172910`
- B-G reward contract SHA-256:
  `e702ad7fa3a366bc24c552c4cd0e5df66842d5fe7f6ef824266b8cfb2ee8d0c7`
- physical product catalog SHA-256:
  `7eb770b5be222ef970b97e1c1128f604121d324bb573672b9f8ef9b40a36a15e`
- pre-existing physical system-identification split SHA-256:
  `1aa839a31b896a26a000ed27ff649232427e3406403c66d7fe79c60b0a0acb08`
- provisional baseline adapter config SHA-256:
  `ebbcbee27555a767f40f347a36d1c54cb6faba2e1e843c197968f41dd1d9227d`
- owner visual manifest SHA-256:
  `3fab56dbf83e1a152f44f0daf88c0d43c44bfbc0ce3c23c0c2e0aa603797101e`
- rubber-tip contact-prior contract SHA-256:
  `e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499`
- bounded least-squares seed: `190719`
- discrete joint-sign hypotheses: `32`
- full nominal physics shortlist: `3`

The optimizer could change only five body-joint signs and five zero offsets in
a separate diagnostic adapter. Radians-per-degree scale and the gripper
mapping remained fixed. Offset bounds were the exact intersection that keeps
every permitted training command and measured joint row inside the unchanged
MuJoCo actuator limits. Simulator geometry, joint limits, actuators, mass,
inertia, reward, evaluator, initial conditions, and task mappings were not
optimized.

The admission rule was frozen before the run: a candidate must have no
clipping and strictly beat the provisional baseline on task consequence
success, selected-piece contact, diagnostic reward, final target distance, and
then pinch-point RMS in that lexicographic order. Otherwise no adapter is
accepted.

## Data used

The quantitative source-fit cohort is the intersection of the 13
owner-reviewed B-G product episodes with the already existing `train`
partition:

- 11 physical teleoperation episodes;
- 10 distinct directed B-G rank-1/rank-2 moves;
- 22 extracted events: one source near-close and one destination reopen per
  episode;
- six-joint follower actual/command rows sampled at 20 Hz;
- task-labeled source and destination square centers from the frozen 100 mm
  simulator registration.

The two product episodes assigned to `held_out` (`d1-to-d2` and
`g1-to-g2-redo`) were listed by metadata only. Their samples, receipts, and
videos were not opened. The receipt records `held_out_episode_assets_read=false`
and `held_out_validation_performed=false`.

The 11 hash-bound C922 overhead videos and 22 owner-reviewed initial/final
markers were used only for qualitative phase and episode review; their
quantitative endpoint weight was zero. The separate, explicitly non-held-out
D405 wrist release was also hash-bound and reviewed. It primarily shows the
gripper and ceiling rather than the board, so it was used only to corroborate
open/close phase and had zero object/endpoint metric weight:

- wrist video SHA-256:
  `19f2d6f853d8145ba1b6239b41cf31182778bc69e5bd4518069694af48780c2b`
- wrist release manifest SHA-256:
  `50bd9205a45d852cb9edb4ba143d899660adbc41ad16dc0f3d4be14750360fdf`
- wrist source receipt SHA-256:
  `1ea97cd3ebb53694802b8b7f120625419c10e778ea133f85cb1f7da7c5fe1221`

These data contain no measured Cartesian end-effector trajectory, pawn pose
trajectory, calibrated camera pose, force, or contact labels.

## Gripper-close proxy

For each permitted episode, the frozen extractor finds the first source-open
peak in the first 55% of the actual gripper signal, the valley before the final
reopen, and the first descent crossing within 15% of that valley. Five body
joint samples centered on that crossing are averaged. Destination reopen is
the maximum actual gripper value in the final 45%. Forward kinematics then
compares the simulated jaw pinch point with the corresponding labeled square
center at an explicitly estimated pawn-neck height of `0.038 m`.

This is the user's proposed proxy made deterministic. It does not prove the
physical gripper was centered when it closed, and the task label is not a
measured object or hand trajectory.

## Results

The provisional adapter clipped at least one command and placed measured rows
outside limits in all 11 episodes. Its 22-event pinch-point RMS was
`0.30955046011340426 m`.

The best bounded candidate had adapter SHA-256
`9edd37f81fce7aa0d6d19a6dcf162a3c944d0f5437e5778164b8fe8cdc68b868`,
body-joint signs `[-1, 1, 1, 1, -1]`, and zero offsets:

`[-0.18590713072668855, 1.986768170091566, -2.255409959876831,
0.1573889255319273, -2.157249866581557] rad`.

It eliminated clipping for all permitted rows and reduced overall event RMS to
`0.11842208424410972 m`, a `61.74385132532977%` reduction. Exact residuals:

| Event proxy | Count | Mean distance | RMS distance | Maximum distance |
|---|---:|---:|---:|---:|
| source near-close | 11 | 0.1075865114217004 m | 0.11035592241845217 m | 0.14751809497471222 m |
| destination reopen | 11 | 0.12214386426954432 m | 0.12597281635579400 m | 0.17070057209485426 m |
| combined | 22 | 0.11486518784562237 m | 0.11842208424410972 m | 0.17070057209485426 m |

Despite the kinematic fit, the frozen consequence score worsened. No selected
pawn was contacted or lifted, and no episode succeeded:

| Configuration/run sequence | Mean reward | Clipped episodes | Selected-pawn contact | Lifts | Successes |
|---|---:|---:|---:|---:|---:|
| provisional baseline / nominal | 0.1000001624739021 | 11/11 | 0/11 | 0/11 | 0/11 |
| best candidate / nominal | -0.5818180192583345 | 0/11 | 0/11 | 0/11 | 0/11 |
| best candidate / rubber low prior | -0.5818180192583345 | 0/11 | 0/11 | 0/11 | 0/11 |
| best candidate / rubber midpoint prior | -0.5818180192583345 | 0/11 | 0/11 | 0/11 | 0/11 |
| best candidate / rubber high prior | -0.5818180192583345 | 0/11 | 0/11 | 0/11 | 0/11 |

All 55 candidate/variant episode replays remained finite. Maximum selected-pawn
rise was only `0.00000009077044993421879 m`; mean final target distance was
`0.04445000091877156 m`. Rubber-tip settings were outcome-insensitive because
the selected pawn was never contacted. This does not establish that the real
rubber bands are irrelevant.

The candidate was therefore rejected by the frozen admission rule. The
accepted adapter is `null`, promotion is forbidden, and the result is
`terminal_negative_no_source_fit_adapter_accepted`.

For the displayed B1-to-B2 episode, reward was `-0.8999996038285638`, selected
pawn contact/lift/success were all false, and wrong-piece contact plus
`0.029546378868293584 m` collateral displacement caused additional gate
failures.

## Score sequence and visual evidence

The ignored machine-readable score sequence records all five comparable
configurations in frozen order. The plot uses the same 11 training-side source
episodes, reward, and evaluator for every row. It is source-fit/sensitivity
history, not physical calibration history or held-out validation.

- source-fit receipt:
  `outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/receipt.json`
- receipt SHA-256:
  `b834f84fbfa8073ac671d1149749059e62aa292f7ad1acee98d5a4f9d94d6121`
- deterministic receipt core SHA-256:
  `dbc66475bbc9a336604e976de89190c49c613a6957baf6236aae7e6707924b30`
- score-sequence JSON SHA-256:
  `e4f752ef9626ba71bcb2e26f35cd84390977b288e68500cab52fdc691ac97e7a`
- score plot SHA-256:
  `11dc9bd3d62b3a9c88e81801d330dfaf17d16ebe1dd673aa780295c8c9a0d911`
- synchronized B1 physical-overhead/simulator video SHA-256:
  `5177563212c31527fc2f8fb208bff4456f7ae2cdb1410e32e7a919261c8781b2`
- comparison poster SHA-256:
  `b0143cfa8a723ea4b04518ab039fc09de3114b6afb6f2e46eeb5383f3b0260f6`
- visual receipt SHA-256:
  `5bd3f2cf31457c71befb582f5e9ff24d282c9c395afea90c3072ea49bd6c79cb`

The simulator panel deliberately uses the best **rejected** adapter and labels
every frame `NOT CALIBRATED`; it is shown to diagnose the remaining spatial
gap, not to present accepted replay equivalence.

The first comparison used the scene's top-down camera. It was superseded at the
owner's request by a C922-angle render frozen in
`configs/experiments/pawn_bg_c922_angle_transfer_v1.json`, SHA-256
`4179694f20bc1e5aa6270bb20f0b2a616d99845d15cdb00773bac9f1aec24f71`.
The visual transfer uses the proposal-only current B1 board homography
`3252c0a3aa8b57d643880ed17ff589db56670be3522cd2f92d288ce9b6c442e1`,
a `635.3212940802823 px` square-pixel focal approximation, and a
`41.38928095678845 degree` vertical field of view. Simulated board corners
reproduce the raw C922 perspective with `1.9442390799611005 px` RMS and
`3.003278728572313 px` maximum residual; both panels then receive the source
receipt's 180-degree orientation correction. A separate 180-degree
physical-board-axis-to-simulator mapping resolves the checkerboard-symmetric
corner ambiguity and places the simulated camera over the same board corner.

This aligns the board perspective without moving the simulated robot. The
corrected render shows the arm entering from the same right/bottom side as the
physical panel. The angle transfer is visual-only, not an accepted camera
calibration or evaluator input.

## Owner-corrected B-G appearance and joint-state replay

A later owner review corrected four display facts for the comparison surface:

- the beige and brown board-square colors are exchanged;
- the rendered pawn colors are exchanged between the two sides;
- the robot-side sparse row contains exactly `B1, C2, D1, E2, F1, G2`;
- robot-side A/H pawn bodies are absent from this review scene.

These corrections are isolated in the B-G review renderer as visual layout
`two_sided_sparse_pawns_bg_rows_1_2_7_8_visual_v1`. Semantic piece IDs are not
renamed, and the shared scene source was restored byte-for-byte to SHA-256
`5247d7ef694ef56721124d7e8a1fbb832e29789bcc1842cdfd1340ee980293ee`.
That preserved the frozen evaluator, Studio source receipts, and historical
replay-limit audit. The display layout does not change or rescore the frozen
source-fit benchmark.

The B1 comparison now has two explicitly separate trajectory modes:

1. `measured_actual_state`: each simulator joint is placed at the hash-bound
   follower encoder state after applying the best rejected adapter, then
   `mj_forward` is called. This is kinematic display only. It does not step a
   commanded arm trajectory and has no reward, contact, or dynamics authority.
2. `command_driven_physics`: the original source command is applied to the
   unchanged MuJoCo actuators and physics is stepped. This remains the relevant
   motion-model diagnostic, but the adapter is still rejected and its displayed
   score is the already frozen command-replay score.

The measured-state replay has zero simulator-minus-mapped-encoder error by
construction. The command-driven comparison against the same 368 B1 samples
reported:

| Joint | Physical command-actual RMS | Sim-mapped-actual RMS | Maximum absolute error |
|---|---:|---:|---:|
| shoulder pan | 1.704921 deg | 1.827787 deg | 6.482854 deg |
| shoulder lift | 3.169448 deg | 3.237364 deg | 7.797788 deg |
| elbow flex | 3.293654 deg | 3.330314 deg | 5.927254 deg |
| wrist flex | 2.398791 deg | 2.510251 deg | 5.877803 deg |
| wrist roll | 2.236267 deg | 2.369269 deg | 9.359462 deg |
| gripper | n/a | 0.038224 actuator RMS | 0.173901 actuator |

For the shoulder lift, 49/368 rows met the fixed descriptive heuristic:
measured change below 0.5 degree per sample while absolute command-minus-actual
error exceeded 2 degrees. The same heuristic also fires on other joints
(including 101 elbow rows), so it is evidence of stalls/holds under tracking
error, not proof that a visible plastic part is a mechanical stop. No joint
limit, gain, damping, action semantics, or evaluator threshold was fitted.
The existing sysid contract correctly forbids promotion while the joint frame
adapter is rejected and no permitted physical held-out validation is available.

Final ignored artifacts:

- measured-state video SHA-256:
  `500c4ef5543f60f5350e16eaf0ba02485c572ef845ba0c89fee8ad3f84feed47`
- measured-state poster SHA-256:
  `d94f0cf86b8ca40c9b1e2e282da35e7e19e01f77c7575c2afa36c83042219fb9`
- measured-state tracking JSON/chart SHA-256:
  `41525c88c5d2ba08ecaff92975bf5a364ffd148266405cf724e5cd13f568d14f` /
  `e19d236810f3c6e73ce8349a630ecc40c616fd680c667c83a85e07784e4376cf`
- measured-state comparison receipt SHA-256:
  `c07d54a748eadf39c5879e92ff1df88e5d1ab9b6c98e9f38e87d81bb6ee88d0b`
- command-driven video SHA-256:
  `78f40b3a96facdd7ac0b28267724f6a67bf4a67e4472110a216dc1f9dbb91ad0`
- command-driven poster SHA-256:
  `14aeaeeaebb8a7f93a80e5762500551430b6b9ae6c7645de620419ff6d41cf9b`
- command-driven tracking JSON/chart SHA-256:
  `62b0c21dfc4f7d248bfd25154fc22aa2c11587213b90d828f1f80ed7aed0cc0b` /
  `695cce471518c6c9c695a4802aa95554257a8b60f8c9727527bf9b5e8bace9c8`
- command-driven comparison receipt SHA-256:
  `919a0b942ee48afbc58e382dc5b3f06a10757789b33e1024a29e2fbe6c301e9f`

Post-repair verification passed: 44 focused tests and 2 subtests, then 404
full-suite tests and 306 subtests in 21.78 seconds; `uv lock --check`, source
distribution and wheel build, and `git diff --check` also passed.

## Commands

```bash
uv run sim2claw pawn-bg-source-fit \
  --source-repository-root /Users/kelly/Developer/sim2claw \
  --output outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/receipt.json

uv run sim2claw pawn-bg-source-fit-visuals \
  --source-repository-root /Users/kelly/Developer/sim2claw \
  --receipt outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/receipt.json \
  --folder-label b1-to-b2 \
  --simulation-camera c922-angle-transfer \
  --trajectory-mode measured-actual-state \
  --output-directory outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/visuals

uv run sim2claw pawn-bg-source-fit-visuals \
  --source-repository-root /Users/kelly/Developer/sim2claw \
  --receipt outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/receipt.json \
  --folder-label b1-to-b2 \
  --simulation-camera c922-angle-transfer \
  --trajectory-mode command-driven-physics \
  --output-directory outputs/pawn_bg_act_v1/pawn_bg_source_fit_v1/visuals
```

SciPy `1.18.0` is now an explicit project dependency because the bounded,
deterministic least-squares solver is directly imported by this evaluator.
MuJoCo remains the forward-kinematics and simulation runtime. OpenCV/ffmpeg and
Pillow create review-only videos, posters, and plots. Generated outputs remain
ignored.

## Verification

- focused camera/source-fit regression set: `21 passed` in `0.40 s`
- full suite: `402 passed, 306 subtests passed` in `21.27 s`
- `uv lock --check`: passed (`94` packages resolved)
- source distribution and wheel: built successfully
- `git diff --check`: passed
- historical joint-limit audit reproduction: exact prior runner-output SHA-256
  `40dc058e817cdc652297b32d92c37dd7abd63edd74851204f5ebaadb8426cb49`
- canonical checkout status: inspected read-only; unrelated concurrent changes
  were present and this lane did not edit them
- core contract/optimizer commit:
  `6245c9c4e61a9a79ac54293625b9a257b6a928e4`
- comparison/history tooling commit:
  `849499e414d0348ca52e40896063880a3deb6009`
- C922-angle comparison commit:
  `86bcb7236cafd545554248d4fff0f2e1d1f28563`
- corrected C922 corner-mapping commit:
  `a5dff97b3ef11e1415e3bac3b9974e488dccf9ff`

## Independent proof-wording audit

Accepted wording is limited to the 11-episode training-side source-fit cohort,
the deterministic gripper-event proxy, exact simulator residuals and task
scores, the rejected adapter, contact-prior non-sensitivity before selected
pawn contact, and the lack of a compatible B-G ACT checkpoint.

Rejected wording includes physical calibration, sealed or measured sim-to-real
gap, physical endpoint error, camera calibration, rubber-property validation,
ACT policy success, learned B-G skill, training admission, physical replay
equivalence, held-out performance, language generalization, composability,
transfer, or physical authority. Closing the next gap requires measured
base/mount and joint registration plus synchronized, metric Cartesian gripper
and pawn/contact trajectories. A compatible B-G policy would then need its own
frozen training split and separately owned held-out evaluator.
