# sim2claw

**Clean-room simulation-to-robot project.**

This is a fresh repository. It intentionally contains no copied simulator,
training, gateway, automation, configuration, receipt, dataset, checkpoint, or
runtime implementation from the earlier repository.

The previous repository is preserved intact at
[`jakekinchen/sim2claw-imported-archive`](https://github.com/jakekinchen/sim2claw-imported-archive).
Freshly authored maps under [`docs/reference/`](./docs/reference/) summarize
what may be consulted there. The archive and local `sim-link` checkout are
read-only guidance surfaces: they grant no authority or proof here.

## Start here

1. [Current goal](./GOAL.md)
2. [Manual build plan](./docs/BUILD_PLAN.md)
3. [Documentation index](./docs/README.md)
4. [Archive boundary and index](./docs/reference/ARCHIVE_INDEX.md)
5. [Polycam chess-table scene](./docs/POLYCAM_CHESS_TABLE_SCENE.md)
6. [First ACT chess-rook run](./docs/run-logs/2026-07-17-act-chess-rook-lift.md)

## Run the first scene

Python 3.12 and `uv` are required. The bootstrap uses the checked-in lock and
runs a compile/step/render doctor:

```bash
./scripts/bootstrap_runtime.sh
```

Fetch the exact owner-provided Polycam artifacts into ignored `external/`
storage, then render the photo-aligned workcell or its non-colliding scan
reference overlay:

```bash
uv run sim2claw fetch-polycam
uv run sim2claw render \
  --output outputs/polycam_chess_table/photo-aligned.png
uv run sim2claw render --scan-overlay \
  --output outputs/polycam_chess_table/reference-overlay.png
uv run sim2claw compare-alignment --photo /path/to/Photo-1.jpg
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

The default portrait render contains the measured white table, a configurable
355.6 mm playing board with a 406.4 mm outer frame, 32 independently simulated pieces, two
white articulated SO-101 arms, the fiducial sheet, left tripod, and simplified
window/sill/blinds background visible in the owner-provided photo. The table
dimensions come from the capture's high-confidence RoomPlan object. Board,
robot, prop, and camera placement remain clearly marked single-photo visual
estimates.

`compare-alignment` verifies the overhead photo's exact SHA-256, registers its
table plane to the RoomPlan dimensions, and writes a photo overlay, an aligned
Polycam textured-mesh overlay, and a machine-readable residual report under
`outputs/polycam_chess_table/alignment/`.

## Current truth

- Repository state: fresh runtime and first simulation scene implemented.
- Simulator: the photo-aligned chess workcell with two articulated SO-101 arms
  compiles, steps, and renders.
- Alignment: deterministic photo and Polycam comparison overlays are available;
  the scan-to-RoomPlan transform is now applied before comparison.
- Mac runtime: verified on Apple Silicon with Python 3.12 and MuJoCo 3.10.0.
- NVIDIA runtime: not implemented.
- Training and evaluation: implemented for one frozen state-based ACT
  chess-rook lift task; broader policy evaluation is not implemented.
- Gateway and robot integration: not implemented.
- Physical authority: closed.

The NVIDIA doctor contract exists and fails closed when Linux, `nvidia-smi`,
or explicit EGL selection is absent; no NVIDIA host has been verified here.
The frozen ACT evaluator is simulation-only and never opens camera, network,
serial, gateway, or physical-robot paths.

Every later capability will continue to be implemented and verified manually
from this clean boundary. Historical claims remain historical until this
repository produces fresh code and fresh evidence of its own.
