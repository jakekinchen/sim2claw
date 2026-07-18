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
Historical material informs future design, but it does not prove that anything
exists or works in this repository.

## Start here

1. [Current goal](./GOAL.md)
2. [Manual build plan](./docs/BUILD_PLAN.md)
3. [Documentation index](./docs/README.md)
4. [Archive index](./docs/reference/ARCHIVE_INDEX.md)
5. [Prior-results summary](./docs/reference/PRIOR_RESULTS_SUMMARY.md)
6. [Polycam chess-table scene](./docs/POLYCAM_CHESS_TABLE_SCENE.md)

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

## Render the first scene

The base scene is self-contained after bootstrap. This command compiles,
settles, and renders the workcell without fetching the Polycam scan:

```bash
uv run sim2claw render \
  --output outputs/polycam_chess_table/photo-aligned.png
```

The command writes a PNG, generated MJCF, and machine-readable JSON report
under ignored `outputs/` storage. This is an in-process, offscreen simulator
workflow; the repository does not currently expose an interactive MuJoCo
viewer.

### Optional Polycam scan overlay

Fetch the exact owner-provided Polycam artifacts into ignored `external/`
storage, then render the scan as a non-colliding visual reference:

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

### Scripted grasp probe

The simulator also exposes a deterministic scripted grasp probe:

```bash
uv run sim2claw grasp-probe
```

It writes phase frames and a JSON receipt under ignored `outputs/` storage.
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
