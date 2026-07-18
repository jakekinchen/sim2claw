# Polycam Chess-Table Scene

## Source

- Owner-provided capture:
  `https://poly.cam/capture/8873B66C-774C-48B1-B51D-338645867009`
- Capture mode observed in the live viewer: Polycam space/LiDAR scene.
- Local source policy: exact artifacts are downloaded only into ignored
  `external/` storage. They are not redistributed because no reusable asset
  license was visible on the shared capture page.
- Source and generated-file identities are recorded in
  `configs/polycam/8873B66C-774C-48B1-B51D-338645867009.json` and verified by
  `sim2claw fetch-polycam`.
- Owner-provided correction photo: 2880 x 3840 JPEG, SHA-256
  `b673f959ddf608e1c64098e8c1194196741c5cbd938f2756c3bf2b20b1901889`.
  It is a visual composition reference and is not redistributed by the repo.

The live viewer exposed `raw.gltf`, `raw_geometry.bin`, one JPEG texture, and
`optimized_roomplan.json`. Repo-native code validates the exact SHA-256 values,
converts the bounded single-primitive glTF to OBJ, and converts the texture to
PNG for MuJoCo. No code, configuration, model, or artifact came from the inert
imported archive.

## Geometry contract

| Element | Value | Evidence class |
| --- | --- | --- |
| Table length | 1.3513037 m | RoomPlan, high confidence |
| Table width | 0.79171795 m | RoomPlan, high confidence |
| Table height | 0.7799972 m | RoomPlan, high confidence |
| Board side | 0.400 m | Visual estimate, configurable |
| Board with frame | 0.446 m | Derived from visual estimate |
| Square side | 0.050 m | Derived from estimated board |
| Pieces | 32 dynamic bodies | Fresh procedural simulation geometry |
| Robot arms | 2 articulated SO-101 models | Public upstream model; mounts and poses are photo estimates |

The RoomPlan table center and yaw are converted from Polycam y-up coordinates
to MuJoCo z-up coordinates. The board was aligned against the translucent scan
overlay and correction photo, but it remains an estimate because neither the
glTF nor RoomPlan marks the board as a metric semantic object.

## Photo-alignment contract

The correction photo is the visual truth surface for composition. The scene
therefore includes the two near-edge white arms, left arm reaching toward the
board, right arm folded upright, black pieces at the near side, fiducial sheet,
left tripod, rear window sill, horizontal blinds, and a front-left portrait
camera. These are explicit estimates from one view, not calibrated transforms.

Robot geometry is vendored from Google DeepMind's public MuJoCo Menagerie
`robotstudio_so101` directory at commit
`71f066ad0be9cd271f7ed58c030243ef157af9f4`. Its Apache-2.0 files are preserved
unchanged under `third_party/`; `sim2claw` attaches two copies and changes their
colors and poses in memory. See `third_party/mujoco_menagerie/robotstudio_so101/SOURCE.md`.

## Simulation behavior

- The scan mesh is visual-only: `contype=0`, `conaffinity=0`.
- The measured table, board collision slab, and all pieces are independent
  repo-native MuJoCo geometry.
- Both SO-101 arms retain six controlled joints and collision geometry; the
  assembled scene has 12 actuators.
- Every chess piece has a free joint and settles under gravity onto the board.
- The render command writes the generated MJCF, PNG, and JSON report under
  ignored `outputs/polycam_chess_table/`.
- The scene opens no camera, network, serial, servo, gateway, or robot path.

## Commands

```bash
./scripts/bootstrap_runtime.sh
uv run python -m unittest discover -s tests -v
uv run sim2claw fetch-polycam
uv run sim2claw render --output outputs/polycam_chess_table/photo-aligned.png
uv run sim2claw render --scan-overlay \
  --output outputs/polycam_chess_table/reference-overlay.png
```

## Proof interpretation

The current evidence proves a local Apple Silicon MuJoCo scene with two
articulated arms can compile, step, settle, and render, and that its composition
matches the major elements of the supplied photo. It does not prove calibrated
robot or camera transforms, exact chess layout, collision-free task motion,
task success, learned-policy readiness, NVIDIA rendering, sim-to-real
equivalence, or physical authority.
