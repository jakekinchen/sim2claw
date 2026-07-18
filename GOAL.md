# Clean-Room Build Goal

Build sim2claw manually from the available design and research documents,
starting from a documentation-only repository and producing fresh,
repo-native implementation and evidence for every capability.

## Current achieved slice

- Python 3.12, MuJoCo 3.10.0, Pillow 12.3.0, and PyTorch 2.11.0 are directly
  pinned; `uv.lock` freezes the transitive environment.
- A fresh bootstrap and fail-closed Mac/NVIDIA doctor are implemented.
- Capture `8873B66C-774C-48B1-B51D-338645867009` is fetched with exact
  SHA-256 verification into ignored storage and converted by repo-native code.
- A new MuJoCo scene builds the measured table, a configurable chessboard, and
  32 dynamic pieces plus two articulated SO-101 arms; it compiles, steps, and
  renders on this Apple Silicon Mac.
- The scene is compositionally aligned to the owner-provided photo with the
  fiducial sheet, tripod, rear window/blinds, and portrait viewpoint. Estimated
  mounts and poses remain distinct from measured geometry.
- The scan can render as a non-colliding reference overlay. Physical authority
  remains closed.
- A frozen `chess_rook_lift_v1` task now separates eight training seeds from a
  zero-training-row held-out seed and binds a separately invoked CPU/fp32
  evaluator before policy selection.
- A fresh 957,350-parameter state-based ACT policy trained locally on MPS and
  passed one held-out simulation episode: 94.88 mm maximum rook lift, 94.01 mm
  final rise, 1,083 consecutive jaw-contact steps, and no assistance.

## Immediate mission

1. Expand evaluator-owned held-out pose coverage before making a robustness or
   promotion claim; the current pass is one fixed simulation task and seed.
2. Replace photo-estimated transforms with calibration evidence when owner
   measurements become available.
3. Add learning, gateway, and eventual hardware paths only as separately
   reviewed milestones.

## Non-goals at this boundary

- Do not copy source code, scripts, configurations, receipts, outputs,
  checkpoints, datasets, caches, or runtime environments from the archive.
- Do not treat imported documents as live authority or current proof.
- Do not claim Mac, NVIDIA, simulator, policy, gateway, camera, serial, or robot
  readiness before fresh repo-native verification exists.

## First milestone acceptance status

- PASS: a documented dependency lock and host support matrix exist.
- PASS: a new bootstrap creates the runtime from declared upstream sources.
- PASS: one new table-and-chess simulator workcell compiles and renders in
  process on a Mac.
- PASS: the same doctor contract has a fail-closed NVIDIA/EGL preflight.
- PASS: fresh tests and a run log are tracked; the ACT source implementation is
  recorded in commit `361e042`.
- PASS: no physical hardware path is opened.
- PASS: the first task, split, ACT recipe, and CPU/fp32 evaluator are frozen in
  repo-native code/configuration; one model-owned held-out episode passed.

The robot geometry/composition slice and one narrow ACT simulation task are
complete. This does not claim broad policy robustness, calibration, gateway,
sim-to-real transfer, or a physical workcell gate.
