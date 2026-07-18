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
- Owner-provided overhead alignment photo: 2880 x 3840 JPEG, SHA-256
  `1201ca9ec105aabb8bb06d126ed582c1c1b30fb1f4f6c94de79f82d355d56ced`.
  Its table, board, clamp-contact, fiducial, and ledge landmarks are frozen in
  the capture config; the image itself remains outside Git.

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
| Board playing side | 0.3556 m | Photo registration plus aligned textured-mesh cross-check |
| Board with frame | 0.4064 m | Aligned scan visual fit range: 0.394–0.418 m |
| Square side | 0.04445 m | Derived from registered playing side |
| Board rear clearance | 0.0277 m | Overhead-photo planar registration |
| Clamp separation | 0.486 m | Overhead-photo planar registration |
| Sill bottom above table | 0.140 m | Photo estimate; not RoomPlan semantic geometry |
| Pieces | 32 dynamic bodies | Fresh procedural simulation geometry |
| Robot arms | 2 articulated SO-101 models | Public upstream model; mounts and poses are photo estimates |

The RoomPlan table center and yaw are converted from Polycam y-up coordinates
to MuJoCo z-up coordinates. The raw glTF is additionally transformed by the
inverse `optimized_roomplan.alignment_transform`; omitting this step displaced
the scan from the semantic table frame. The board remains an estimate because
neither the glTF nor RoomPlan marks it as a metric semantic object.

## Photo-alignment contract

The correction photo is the visual truth surface for composition. The scene
therefore includes the two near-edge white arms, left arm reaching toward the
board, right arm folded upright, black pieces at the near side, fiducial sheet,
left tripod, rear window sill, horizontal blinds, and a front-left portrait
camera. These are explicit estimates from one view, not calibrated transforms.

The overhead photo changes the table-edge layout from the first visual pass:
the reaching arm is mounted near the table center at `(-0.040, 0.365) m`, and
the right arm at `(-0.526, 0.365) m` in the scene's table frame. Their clamp
contacts reproduce the frozen photo landmarks within about 2 source pixels.
The fiducial center reproduces its photo landmark within about 7 source pixels.

The board was physically moved between evidence surfaces. Its Polycam-capture
center is estimated near `(-0.022, 0.182) m`, while the later overhead photo
places it at `(0.040, -0.165) m`: a 0.352 m center displacement. The simulator
uses the later photo's layout; the scan overlay draws both poses rather than
silently treating them as one observation.

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
uv run sim2claw compare-alignment --photo /path/to/overhead-Photo-1.jpg
```

The comparison command writes:

- `alignment/photo-layout-overlay.png` — measured table outline, corrected
  board and clamps, observed photo landmarks, dimensions, and ledge estimate;
- `alignment/polycam-scan-overlay.png` — properly transformed textured scan,
  its historical board pose, the later photo pose, and current clamp contacts;
- `alignment/alignment-report.json` — homography, residuals, distances,
  artifact hashes, and limitations.

## Proof interpretation

The scene/render evidence in this document proves a local Apple Silicon MuJoCo scene with two
articulated arms can compile, step, settle, and render, and that its composition
matches the major elements of the supplied photo. It does not prove calibrated
robot or camera transforms, exact chess layout, collision-free task motion,
learned-policy robustness, NVIDIA rendering, sim-to-real equivalence, or
physical authority. A later, separately frozen ACT task proves one narrow
simulation episode; see
[`run-logs/2026-07-17-act-chess-rook-lift.md`](./run-logs/2026-07-17-act-chess-rook-lift.md).
The current table-plane registration has a board-corner RMS of about 0.033 m;
that residual includes lens distortion, manual landmark uncertainty, and the
fact that the photo is not a calibrated camera. Exact 3D alignment still
requires a camera calibration and a direct measurement of the board and sill
profile.
