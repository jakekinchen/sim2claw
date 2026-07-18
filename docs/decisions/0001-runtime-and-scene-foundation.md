# Decision 0001: Runtime and First Scene Foundation

Status: accepted for the first Mac simulation slice

Date: 2026-07-17 America/Chicago

## Decision

Use one Python 3.12 `uv` environment with exact direct pins and a checked-in
transitive lock. The first scene uses the canonical MuJoCo Python bindings and
repo-native procedural geometry plus the reviewed public SO-101 model from
MuJoCo Menagerie. Owner-provided Polycam and photo artifacts act as
visual/measurement references, never collision or promotion authority.

## Adopted dependencies

| Dependency | Pin/source | Reason | License/notes |
| --- | --- | --- | --- |
| CPython | 3.12.x | One portable interpreter supported on Apple Silicon and NVIDIA Linux | PSF; patch version selected by `uv.lock` |
| MuJoCo | 3.10.0 from official PyPI | Canonical physics, MJCF compiler, and in-process offscreen renderer | Apache-2.0 |
| NumPy | 2.5.1 from official PyPI | Deterministic homography solve, inverse projection, and alignment residuals | BSD-3-Clause |
| Pillow | 12.3.0 from official PyPI | Deterministic JPEG-to-PNG conversion because MuJoCo rejects the capture JPEG as a direct texture | MIT-CMU |
| hatchling | 1.27.0 build-system pin | Minimal standard wheel/editable build backend | MIT |
| uv | external bootstrap tool | Creates the locked runtime without a repo-copied environment | Not installed by this repo |
| Polycam capture `8873…7009` | Owner-provided share link plus exact artifact hashes | Measured table dimensions and optional visual alignment overlay | No reusable asset license observed; ignored local storage only |
| MuJoCo Menagerie SO-101 | `google-deepmind/mujoco_menagerie` commit `71f066ad0be9cd271f7ed58c030243ef157af9f4`, path `robotstudio_so101/` | Reviewed articulated geometry, joints, actuators, and collision meshes for the two photographed arms | Apache-2.0; exact upstream directory and license vendored |

MuJoCo's official Python model-editing API is used to attach two separately
loaded copies of the pinned SO-101 spec to photo-estimated table-edge frames.
The upstream files remain unchanged; white material overrides and joint poses
exist only in the assembled parent spec.

## Host support matrix

| Host | Runtime | Renderer | Current proof |
| --- | --- | --- | --- |
| Apple Silicon macOS | Python 3.12, MuJoCo 3.10.0 | Platform-default offscreen | Verified compile, step, render |
| NVIDIA Linux | Same lock | Must set `MUJOCO_GL=egl` and expose `nvidia-smi` | Preflight contract only; no host proof |

The doctor returns nonzero when any target-specific condition is absent. Mac
proof does not promote NVIDIA readiness.

## Consequences

- Direct dependencies and transitive versions are reviewable in
  `pyproject.toml` and `uv.lock`.
- Capture acquisition is reproducible while the share endpoint remains
  available, but redistribution remains closed.
- Board size and placement stay explicit estimates until a metric board
  measurement is supplied.
- Training, evaluator, gateway, and all physical paths remain closed.
- Robot mounts and joint poses are visual estimates, not calibration evidence.
