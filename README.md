# sim2claw

**Clean-room simulation-to-robot project.**

This is a fresh repository. It intentionally contains no copied simulator,
training, gateway, automation, configuration, receipt, dataset, checkpoint, or
runtime implementation from the earlier repository.

The previous repository is preserved intact at
[`jakekinchen/sim2claw-imported-archive`](https://github.com/jakekinchen/sim2claw-imported-archive).
Its documents were reinserted here as inert reference material under
[`docs/reference/imported/source-tree/`](./docs/reference/imported/source-tree/).
They inform future design, but they do not prove that anything exists or works
in this repository.

## Start here

1. [Current goal](./GOAL.md)
2. [Manual build plan](./docs/BUILD_PLAN.md)
3. [Documentation index](./docs/README.md)
4. [Imported-document boundary](./docs/reference/imported/SOURCE_BOUNDARY.md)
5. [Polycam chess-table scene](./docs/POLYCAM_CHESS_TABLE_SCENE.md)

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
```

The default portrait render contains the measured white table, a configurable
400 mm playing board with a wood frame, 32 independently simulated pieces, two
white articulated SO-101 arms, the fiducial sheet, left tripod, and simplified
window/sill/blinds background visible in the owner-provided photo. The table
dimensions come from the capture's high-confidence RoomPlan object. Board,
robot, prop, and camera placement remain clearly marked single-photo visual
estimates.

## Current truth

- Repository state: fresh runtime and first simulation scene implemented.
- Simulator: the photo-aligned chess workcell with two articulated SO-101 arms
  compiles, steps, and renders.
- Mac runtime: verified on Apple Silicon with Python 3.12 and MuJoCo 3.10.0.
- NVIDIA runtime: not implemented.
- Training and evaluation: not implemented.
- Gateway and robot integration: not implemented.
- Physical authority: closed.

The NVIDIA doctor contract exists and fails closed when Linux, `nvidia-smi`,
or explicit EGL selection is absent; no NVIDIA host has been verified here.
The scene does not yet contain a frozen manipulation task or evaluator.

Every later capability will continue to be implemented and verified manually
from this clean boundary. Historical claims remain historical until this
repository produces fresh code and fresh evidence of its own.
