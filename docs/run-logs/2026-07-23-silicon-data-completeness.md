# Silicon data completeness audit

Date: 2026-07-23

## Scope

This read-only source audit covered the live checkout at
`/Users/jakekinchen/Developer/sim2claw` on `silicon.local`, its Git
branches/worktrees/stash state, relevant Desktop/Documents/Downloads/Shared
locations, and mounted-volume inventory. The local destination was clean
`main@fe95ca0042813e482dbfa3f85f39350791b0784c`.

No simulator, trusted adapter, provider, training, capture, gateway, robot
motion, or physical task evaluation ran.

## Retrieved canonical data

Transfers used rsync with `--ignore-existing`; no local file was overwritten.
Every admitted remote source file is now present byte-identically.

| Root | Source files | Source bytes | SHA-256 manifest |
| --- | ---: | ---: | --- |
| `datasets/act_source_recordings` | 48 | 122,808,335 | `f86cacc92e5d29020e4b7436f50b9f72629509fee0f62bb43d57a22e3a1c646b` |
| `runs/teleop_recordings` | 138 | 289,174,566 | `79b009e833a7b1e0e07210df6c03cfbe1b82a5be66f9189a11fbd424b9d1191b` |
| `runs/multicamera_physical_replays` | 4 | 85,088,256 | `d8e8d317030819b3965f9e81a7b93257ca5d6e40b8b804f9a67463ec52257120` |
| `runs/transfers` | 12 | 814,530,761 | `32a9605442dadfac4b9aca383b6d21ab27265057a018db4091b5d65d1534f4a2` |
| remote `runs/task_orchestrator` source | 214 | 3,686,980 | `865bcd5fa5ed2cfdd96f68d345c8d5b6a9ffe37df4bd93c0cdb04d040c59afb1` |
| `outputs/roboscanner` | 4 | 9,617,063 | `605295bc04e2575f51f8503a7677cb486c0a4d0dd795f728ed74088f0797176d` |
| remote `outputs/task_orchestrator` source | 7 | 606,861 | `dc513dbb9e71ff225ba85d9df5010f49ed86008ea814cc18c2281d5a09c26b0a` |

The transfer added 359 canonical files totaling 1,324,118,935 bytes. Local
task-orchestrator roots contain a few newer local files as well; a checksum
dry-run from Silicon to local reported zero residual source files.

Three already-retrieved roots also match Silicon exactly:

- 144 manipulation-source files:
  `bad2e1891890e0fa7266f3951d8476a82848dc84faf35cf0ba9f1effa0a584db`;
- 239 physical-replay files:
  `9ffcdd8f2de92306ddf580029ce0c164cc85acf8763f116f5c45486c502c6992`;
- 71 owner-directed-loop files:
  `dc951952c4a211f3bc84db3100f504d084b783ada177375defbf13091c81bb7e`.

## Validation

- All six transfer archives match their sidecar SHA-256 files and are readable.
- All six ACT recordings match their receipt-owned sample hashes.
- All three multicamera videos match the capture receipt.
- 201 JSON files and 58 JSONL files parse.
- 34 videos are probeable with FFprobe.
- Six ACT recordings, 38 failed teleoperation attempts, one multicamera
  session, and six transfer archives are preserved.

These are historical source and diagnostic records. Labels in filenames or
operator notes do not prove task success, policy success, or transfer.

## Conflicts and exclusions

Ten older Polycam outputs differed from current local derivatives. The complete
13-file Silicon Polycam output set was preserved under
`runs/silicon-data-recovery-20260723/conflicts/` with manifest
`fa7794b7762ef713ad29f8e007fcb4dcdecf023453bbac9da4ee5055e29a0da2`;
the current canonical outputs were not overwritten.

One file was explicitly named
`IMG_5349-primary-real-splat.ply.truncated-20260719`. It was preserved only as
excluded provenance with SHA-256
`dbef38d4c098037857694b6bcb31aeb097dceac7ea40683b5564fe3cce1cb3ef`.
The complete 75 MB splat was already local.

The combined 14-file excluded-provenance root has manifest
`5f7ec006d03795401cb1478f7dc17119fd88e6868f6f32be902702f010770182`.

Not copied or admitted:

- `.env` or credentials;
- `.venv`, Swift builds, Python caches, and application caches;
- one synthetic Learning Factory component-test campaign;
- stale Studio process-registration files.

The three additional Silicon branch tips are ancestors of both current main
and the exact recovery branch. There is no stash, second Sim2Claw repository,
matching file elsewhere in the source account's normal data locations, or
mounted external data volume.

## Claim boundary

The audit establishes byte-preserved data provenance for the inspected
Silicon checkout and named host locations. It is not a whole-machine backup and
does not upgrade synthetic, simulation, replay, operator-reported, or physical
records into accepted task evidence. Physical and training authority remain
closed.

## Recalibration utility assessment

The recovered five task recordings now pass the repository's existing
fail-closed `pawn_sim_real_bridge_v1` inspection. All `2,186` joint
command/actual rows and their five historical joint-response simulation
replays match the frozen intake ledger. The bridge therefore reports
`joint_response_calibration_ready: true`, while retaining
`100mm_spatial_comparison_ready: false`,
`pawn_policy_training_ready: false`, and
`pawn_policy_closed_loop_comparison_ready: false`.

The recovered 72 mm cohort has aggregate per-joint command-to-actual RMSE of
`[1.106, 2.334, 2.506, 1.857, 1.437, 1.662]` in the recorded native units,
with a per-episode best-lag range of `0.15–0.20 s` and a rate-limited fraction
of `0.2310`. The current 18-recording 100 mm cohort has `7,741` rows,
aggregate RMSE `[1.406, 2.968, 2.948, 2.194, 2.019, 2.662]`, median best lag
`0.15 s`, and rate-limited fraction `0.3436`. The recovered commands extend
the current cohort's lower envelope only slightly for wrist flex
(`0.70°`), wrist roll (`8.26°`), and gripper (`0.12` native units); the
current cohort otherwise spans the larger command range.

The five already-existing historical simulation replays report aggregate body
joint RMSE from `2.830°` to `3.452°`, with the largest recurring residuals
around shoulder lift and elbow flex. This supports a future preregistered,
held-out actuator timing/rate-limit/load-path cross-check. It does not identify
contact, friction, board registration, piece pose, or task consequence.

Eight failed-attempt traces contain another `10,731` rows, but they terminate
in bus, stall, or shutdown faults and lack receipt-owned outcome/admission
records. They remain fault-diagnostic evidence only and were not included in
the bridge or calibration-ready count. The single three-camera replay is
timestamp-bound with approximately one-second alignment uncertainty and lacks
the depth/intrinsic/hand-eye calibration needed for metric object trajectories.

No simulator parameter, candidate family, threshold, policy, posterior, task
score, or proof class was changed. A higher task-completion score remains an
unmeasured possibility, not a result: the next defensible use is a separately
frozen actuator-model cross-validation transaction, followed by the existing
independent strict task/EE evaluator.
