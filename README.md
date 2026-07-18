# sim2claw

**Clean-room simulation-to-robot project.**

This is a fresh repository. It intentionally contains no copied simulator,
training, gateway, automation, configuration, receipt, dataset, checkpoint, or
runtime implementation from the earlier repository.

The previous repository is preserved intact at
[`jakekinchen/sim2claw-imported-archive`](https://github.com/jakekinchen/sim2claw-imported-archive)
at commit `798491e`. It is consulted read-only; no prior-project file is copied
into this repository. Freshly authored maps of the relevant history live in
[`ARCHIVE_INDEX.md`](./docs/reference/ARCHIVE_INDEX.md) and
[`PRIOR_RESULTS_SUMMARY.md`](./docs/reference/PRIOR_RESULTS_SUMMARY.md).
The archive and local read-only `sim-link` checkout inform future design, but
they grant no authority or proof that anything exists or works here.

## Start here

1. [Current goal](./GOAL.md)
2. [Manual build plan](./docs/BUILD_PLAN.md)
3. [Documentation index](./docs/README.md)
4. [Archive index](./docs/reference/ARCHIVE_INDEX.md)
5. [Prior-results summary](./docs/reference/PRIOR_RESULTS_SUMMARY.md)
6. [Polycam chess-table scene](./docs/POLYCAM_CHESS_TABLE_SCENE.md)
7. [First ACT chess-rook run](./docs/run-logs/2026-07-17-act-chess-rook-lift.md)
8. [GR00T N1.7 overnight campaign](./docs/run-logs/2026-07-18-groot-n17-chess-overnight.md)
9. [NVIDIA machine 2 recovery goal](./docs/goals/NVIDIA_MACHINE_2_GR00T_ROBUSTNESS_OVERNIGHT.md)
10. [Goal-conditioned ACT pick-and-place program](./docs/goals/GOAL_CONDITIONED_ACT_PICK_PLACE.md)
11. [Goal-conditioned ACT architecture decision](./docs/decisions/0004-goal-conditioned-act-pick-place.md)

## Install and verify

An Apple Silicon Mac is the currently verified host. Install
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) and ensure the
host has network access for the first dependency sync. The bootstrap selects
Python 3.12, creates `.venv/` from the checked-in [`uv.lock`](./uv.lock), and
runs a compile/step/render doctor:

```bash
./scripts/bootstrap_runtime.sh
uv run python -m unittest discover -s tests -v
```

[`requirements.txt`](./requirements.txt) is the runtime-only, pip-compatible
export of the same lock. It omits the development group and the local project
package; the `uv` bootstrap above remains the verified setup path.

MP4 export from `act-eval` additionally uses the system
[`ffmpeg`](https://ffmpeg.org/) CLI with H.264/libx264 support when it is
available. On macOS it can be installed with `brew install ffmpeg`. It is not a
Python package and does not belong in the generated `requirements.txt`; no
single FFmpeg version is part of the frozen Python runtime. If the CLI is
absent, evaluation still writes its action trace, rendered PNG frames, and
receipt, while the receipt records that no MP4 was created. When it is present,
the receipt records the exact executable version used.

## Choose and run a simulation environment

Scene reconstruction is not required to install this repository or run
simulation training. The intended selection rule is simple: use an existing
compatible simulation environment when one is supplied; otherwise use the
bundled programmatic MuJoCo workcell as the default. The current CLI provides
the bundled workcell but does not yet auto-discover arbitrary simulator asset
formats.

This command compiles, settles, and renders the bundled default without
fetching any Polycam data:

```bash
uv run sim2claw render \
  --output outputs/polycam_chess_table/photo-aligned.png
```

The command writes a PNG, generated MJCF, and machine-readable JSON report
under ignored `outputs/` storage. This is an in-process, offscreen simulator
workflow. Generated episodes can be inspected in the Studio's interactive 3D
view; the browser mirrors recorded MuJoCo poses and does not become a second
physics engine.

## Open the browser visualization studio

Replay the repo's generated episodes as synchronized interactive 3D state
traces, video, or phase frames; orbit and inspect the workcell; browse
task-grouped evidence; watch active training/evaluation
processes, and collect labeled ACT source demonstrations from the SO-101 leader
to the MuJoCo follower:

```bash
uv run sim2claw studio
```

Open `Record`, choose one of the eight brown pawn source squares and an
unoccupied destination in rows 1–4, then Start/Stop and label the observed
outcome. The board preview and current task simulator show the mirrored tan
pawns at A8, B7, C8, D7, E8, F7, G8, and H7 as static far-side pieces. Start
defaults to B1→B2 at 30 Hz, persists the operator's metadata choices, and
automatically performs the bounded follower Sync, torque-off verification, and
paired-pose check;
`uv run sim2claw teleop-preflight` remains available as a separate diagnostic.
Saved episodes go to ignored
`datasets/act_source_recordings/` storage and are not training data until replay
and evaluator admission.

The current owner-local physical cohort is indexed by the tracked
[`physical_teleop_episode_intake_20260718.json`](./configs/data/physical_teleop_episode_intake_20260718.json)
ledger and reviewed in
[`2026-07-18-physical-episode-intake.md`](./docs/run-logs/2026-07-18-physical-episode-intake.md).
It records five saved physical sources and zero admitted training rows; the raw
samples and C922 videos remain ignored and local.

Replay and process views remain read-only. Recorder controls are loopback-only.
Physical Start requires a cleared-workcell acknowledgement, a bounded Sync of
an already-nearby follower, a countdown, and relative-zero registration through
the reviewed gateway. Sync refuses a body mismatch above 20 degrees, ramps
instead of jumping, and finishes torque-off. Recording then permits up to
90 degrees of relative body travel (180 degrees for wrist roll), clamps every
target to the follower calibration, and uses 4-degree command steps. A
time-based stall guard releases torque only after five seconds without
measurable progress. Failed attempts are retained under ignored diagnostic
storage while the recorder returns to ready automatically. Saved physical
traces can be replayed in MuJoCo for joint-space error,
but the Studio cannot promote a checkpoint or turn that comparison into a task
success claim. See
[`VISUALIZATION_STUDIO.md`](./docs/VISUALIZATION_STUDIO.md) for its artifact
adapters and live heartbeat contract.

Creating a different environment is an optional, project-specific build step.
An agent may combine reviewed CAD or mesh assets, textures, measurements,
images, video, and optionally a Polycam capture to author it. That process is
non-deterministic and is not a prerequisite or a claimed one-command script.

### Optional Polycam reference workflow

Polycam was one input to the initial bundled scene, not a recurring setup or
training step. Only fetch these owner-provided artifacts when inspecting or
rebuilding its non-colliding scan reference overlay:

```bash
uv run sim2claw fetch-polycam
uv run sim2claw render --scan-overlay \
  --output outputs/polycam_chess_table/reference-overlay.png
```

### Optional owner-photo alignment

The photo comparison is not reproducible from the repository alone. It
requires the owner-provided 2880 x 3840 overhead JPEG with SHA-256
`1201ca9ec105aabb8bb06d126ed582c1c1b30fb1f4f6c94de79f82d355d56ced`.
The command rejects any other file:

```bash
uv run sim2claw compare-alignment \
  --photo /path/to/exact/overhead-Photo-1.jpg
```

## Run the ACT chess-rook episode

The first narrow learned-policy task is frozen in
[`configs/tasks/chess_rook_lift_v1.json`](./configs/tasks/chess_rook_lift_v1.json).
It trains a fresh state-based conditional-VAE Action Chunking Transformer from
eight synthetic simulation demonstrations, then invokes a separate CPU/fp32
evaluator on seed `9101`:

```bash
uv run sim2claw act-train
uv run sim2claw act-eval \
  --checkpoint outputs/polycam_chess_table/act/chess_rook_lift_v1/checkpoint.pt
```

The evaluator writes an ignored checkpoint-linked receipt, complete action
trace, rendered frames, and MP4 under
`outputs/polycam_chess_table/act/chess_rook_lift_v1/eval/`. The accepted local
run lifted `black_rook_a8` by 94.88 mm and held it through the final window.
This is one bounded learned-policy simulation episode, not a robustness,
calibration, gateway, sim-to-real, or physical-robot result.

## Export the dynamic GR00T chess dataset

The next lane is frozen in
[`configs/tasks/chess_pick_place_groot_v1.json`](./configs/tasks/chess_pick_place_groot_v1.json).
It is genuinely language and RGB conditioned: commands name a black rook or
king and a destination square, while the dataset records the workcell camera,
six SO-101 joint positions, and six absolute joint targets.

```bash
uv run sim2claw groot-expert-eval --split held_out --episode-index 0
uv run sim2claw groot-expert-eval --split held_out --episode-index 2
uv run sim2claw groot-export \
  --output datasets/chess_pick_place_groot_v1
```

The export is GR00T LeRobot v2.1 with `meta/modality.json`, typed parquet,
20 FPS RGB MP4, normalization statistics, natural-language task rows, and a
hash receipt. Generated data remains ignored. The first curriculum is
explicitly sparse: the rook and king remain visible while other pieces are
parked at reset. This is not full-board capability. A full-board expert was
rejected after it moved the target but swept a queen off the board.

The local exporter and scripted evaluator do not prove that GR00T loads,
trains, serves, or succeeds. Those are separate NVIDIA/Brev gates in
[`09-autonomous-milestones.md`](./docs/autonomous-workflow/09-autonomous-milestones.md).

### NVIDIA research assignments

- **Machine 1 — nominal baseline:** owns the frozen v1 sparse-board dataset,
  5,000-step checkpoint sweep, and nominal held-out consequence evaluation.
- **Machine 2 — recovery and robustness challenger:** owns a new versioned
  curriculum for pose error, nearby distractors, and grasp recovery. Its full
  unattended overnight command is
  [`NVIDIA_MACHINE_2_GR00T_ROBUSTNESS_OVERNIGHT.md`](./docs/goals/NVIDIA_MACHINE_2_GR00T_ROBUSTNESS_OVERNIGHT.md).

The two machines must use separate checkouts and branches. They compare only
through frozen evaluator receipts; neither training process may promote itself.

The default portrait render contains the measured white table, a configurable
355.6 mm playing board with a 406.4 mm outer frame, 32 independently simulated
pieces, two white articulated SO-101 arms, the fiducial sheet, left tripod, and
simplified window/sill/blinds background visible in the owner-provided photo.
The table dimensions come from the capture's high-confidence RoomPlan object.
Board, robot, prop, and camera placement remain clearly marked single-photo
visual estimates.

`compare-alignment` verifies the overhead photo's exact SHA-256, registers its
table plane to the RoomPlan dimensions, and writes a photo overlay, an aligned
Polycam textured-mesh overlay, and a machine-readable residual report under
`outputs/polycam_chess_table/alignment/`.

### Scripted grasp probe

The simulator also exposes a deterministic scripted grasp probe:

```bash
uv run sim2claw grasp-probe
```

It writes phase frames, a 30 Hz MuJoCo body-state trace, and a JSON receipt
under ignored `outputs/` storage. The Studio opens the state trace in 3D by
default while retaining the five recorded phase frames as a source-evidence
toggle.
This is simulation-only scripted-grasp evidence. It is not a frozen task
evaluator, learned policy result, training-readiness result, or physical
capability.

## Current truth

- Repository state: fresh runtime and first simulation scene implemented.
- Simulator: the photo-aligned chess workcell with two articulated SO-101 arms
  compiles, steps, and renders.
- Alignment: the Polycam scan overlay is reproducible from the pinned capture
  endpoints. The photo comparison additionally requires the exact
  owner-provided overhead JPEG; the scan-to-RoomPlan transform is applied
  before comparison.
- Scripted grasp probe: implemented as simulation evidence, separate from task
  or evaluator proof.
- Mac runtime: verified on Apple Silicon with Python 3.12 and MuJoCo 3.10.0.
- NVIDIA runtime: pinned Brev setup/preflight scripts are implemented; live
  N1.7 execution remains a separate evidence gate.
- Training and evaluation: implemented for one frozen state-based ACT
  chess-rook lift task. A separate dynamic GR00T dataset/evaluator contract is
  implemented locally, but no learned GR00T result is claimed yet.
- Gateway and robot integration: not implemented.
- Physical authority: closed.

The NVIDIA doctor contract exists and fails closed when Linux, `nvidia-smi`,
or explicit EGL selection is absent; no NVIDIA host has been verified here.
The frozen ACT evaluator is simulation-only and never opens camera, network,
serial, gateway, or physical-robot paths.

Every later capability will continue to be implemented and verified manually
from this clean boundary. Historical claims remain historical until this
repository produces fresh code and fresh evidence of its own.
