# Pi base assembly audit

Date: 2026-07-26  
Proof class: `hardware_free_model_assembly_diagnostic_only`

## Outcome

The repository's authored SO-101 base and first moving-body visual assembly is
reproduced by the compiled MuJoCo model without a deterministic transform,
scale, axis, or parenting error. No model correction is justified.

For all seven group-2 visual meshes directly owned by `left_base` and
`left_shoulder`, the raw upstream STL vertices transformed by the authored XML
geom pose agree with the compiled mesh vertices transformed by the compiled
geom pose to:

- worst symmetric point-cloud RMSE: `1.10e-9 m`;
- worst point error: `2.54e-9 m`; and
- compiled mesh scale: exactly `[1, 1, 1]`.

This also verifies that the existing CAD projection tools are correct to use
`model.mesh_vert` with `data.geom_xmat` and `data.geom_xpos`. MuJoCo centers
and aligns raw asset vertices during compilation, records that operation in
`mesh_pos` and `mesh_quat`, and folds the inverse operation into the compiled
geom pose. Applying `mesh_pos` and `mesh_quat` a second time in the projection
tools would be an error.

The rejected two-center diagnostic therefore remains evidence of an
unresolved CAD-to-physical feature correspondence, physical hardware revision,
or upstream mount/calibration inconsistency. It is not evidence of a
repository assembly bug.

## Source and provenance

The reviewed source remains the unchanged public MuJoCo Menagerie SO-101 model:

- upstream repository:
  `https://github.com/google-deepmind/mujoco_menagerie.git`;
- upstream commit:
  `71f066ad0be9cd271f7ed58c030243ef157af9f4`;
- vendored source:
  `third_party/mujoco_menagerie/robotstudio_so101/so101.xml`;
- source XML SHA-256:
  `5ad49f2b45c083baac9ffe5d4d3213a5da7eac8039095bb2df177a697aae8308`;
- `base_so101_v2.stl` SHA-256:
  `bb12b7026575e1f70ccc7240051f9d943553bf34e5128537de6cd86fae33924d`;
- `sts3215_03a_v1.stl` SHA-256:
  `a37c871fb502483ab96c256baf457d36f2e97afc9205313d9c5ab275ef941cd0`.

The asset declarations have no scale override. The scene attaches a fresh
model copy to `left_robot_mount`; it changes visual materials and one
collision-only shoulder box, but it does not alter these visual meshes.

## Body and mount chain

The configured left mount is
`[-0.04, 0.365, 0.799] m` in the table frame with `-88 deg` yaw relative to
the table. The table yaw is `-20.388574 deg`. The resulting compiled base
transform is:

| Body | Parent | Compiled local position m | Compiled local quaternion wxyz |
|---|---|---|---|
| `left_base` | `world` | `[-0.0104775945, 0.921993745, 0.799]` | `[0.5850385438, 0, 0, -0.8110054884]` |
| `left_shoulder` | `left_base` | `[0.0388353, 0, 0.0624]` | `[0, 0, -1, 0]` |

The base quaternion is exactly the combined `-108.388574 deg` world yaw. The
shoulder body pose and parent are byte-for-value equivalent to the authored
XML after numeric parsing.

## Visual geom trace

Authored quaternions below are normalized. Compiled poses differ because
MuJoCo has folded its per-asset centering/alignment transform into each geom.
The final column compares complete transformed raw and compiled vertex clouds
in their common owning-body frame.

| Body / mesh | Authored pos m / quat wxyz | Compiled pos m / quat wxyz | Scale | RMSE / max m |
|---|---|---|---:|---:|
| base / `base_motor_holder_so101_v1` | `[-0.006365,-0.000099,-0.0024]` / `[0.5,0.5,0.5,0.5]` | `[0.0061593623,-0.0000092879,0.0488308662]` / `[-0.0029835228,0.7404456605,0.0027081502,0.6721041499]` | 1 | `8.20e-10 / 2.13e-9` |
| base / `base_so101_v2` | `[-0.006365,0,-0.0024]` / `[0.5,0.5,0.5,0.5]` | `[0.0128156774,-0.0000035971,0.0166977675]` / `[-0.6394743739,0.6399597240,0.3010847472,0.3014499159]` | 1 | `1.10e-9 / 2.54e-9` |
| base / `sts3215_03a_v1` | `[0.0263353,0,0.0437]` / `[1,0,0,0]` | `[0.0274071612,-0.0000000032,0.0438176432]` / `[0.5063098304,0.4936095173,0.4936095173,0.5063098304]` | 1 | `7.04e-10 / 1.38e-9` |
| base / `waveshare_mounting_plate_so101_v2` | `[-0.0309827,-0.000199,0.0474]` / `[0.5,0.5,0.5,0.5]` | `[-0.0285876549,-0.000199,0.0474203057]` / `[-0.7071067812,0.7071067812,0,0]` | 1 | `5.20e-10 / 8.74e-10` |
| shoulder / `sts3215_03a_v1` | `[-0.030399,0.000422,-0.0417]` / `[0.5,0.5,0.5,-0.5]` | `[-0.0303990032,0.0003043568,-0.0427718612]` / `[0.0127003131,0.9999193478,0,0]` | 1 | `7.04e-10 / 1.38e-9` |
| shoulder / `motor_holder_so101_base_v1` | `[-0.067599,-0.0001778,0.01585]` / `[0.5,0.5,-0.5,0.5]` | `[-0.0328736979,-0.0003015369,-0.0239117366]` / `[0.5011009506,0.5015249366,-0.5026409619,0.4946944903]` | 1 | `6.89e-10 / 1.34e-9` |
| shoulder / `rotation_pitch_so101_v1` | `[0.012201,0.000022,0.0464]` / `[0.7071067812,-0.7071067812,0,0]` | `[-0.0268940290,-0.0000206371,0.0066907593]` / `[0.6966044617,0.1236182429,0.1283141538,0.6949793032]` | 1 | `9.97e-10 / 2.15e-9` |

## Discrete hypothesis checks

Only the named, concrete assembly and correspondence hypotheses were tested.
No geometry or image-space transform was free-fit.

1. **Wrong compiled mesh-local frame — rejected.** All seven final vertex
   clouds agree at nanometer numerical precision.
2. **Wrong scale — rejected.** Every compiled mesh scale is one. Reinterpreting
   the raw STL coordinates at `0.001x` or `1000x` produces per-mesh cloud RMSE
   between `19.5 mm` and `54.5 m`; unit scale produces at most `1.10 nm` RMSE.
3. **Accidental asset-axis flip — rejected.** Reflecting one raw asset axis
   before the authored geom transform produces nonzero RMSE from `0.035 mm` to
   `93.4 mm`, versus at most `1.10 nm` for the authored orientation.
4. **Whole-base axis reversal — rejected.** Under the frozen tag-validated
   camera, the two-center image RMSE is `80.87 px` for the authored transform.
   The three proper 180-degree base rotations produce `124.92–182.38 px`.
   Single-axis reflections produce `78.23–154.58 px`; the marginal
   `reflect_y` result still leaves `78.23 px` and is neither a proper rotation
   nor a source-backed assembly.
5. **Wrong parent for the servo center — rejected.** The observed second center
   remains within 1 px horizontally over H, I, F, and fresh N. The base-owned
   servo center is fixed at `[724.68,371.94] px`; the same topology transformed
   through the moving shoulder servo projects at `x=741.25–763.18 px`,
   `y=257.96–258.78 px`. It is both much farther away and moves with shoulder
   state.
6. **The two physical labels are swapped — rejected.** With H labels
   `[577.5,492.5]` and `[700.5,425.5]`, the authored CAD ordering gives
   `80.87 px` RMSE. Swapping the two CAD centers gives `140.48 px`.

The two topology centers do trace cleanly back through the compiled geoms:

| Feature | Compiled mesh center m | Raw asset center m | Base-body center m |
|---|---|---|---|
| base side fastener aperture | `[0.00729504,-0.03671297,0.01482388]` | `[0.01484988,0.04809998,-0.00446362]` | `[-0.01082862,0.01484988,0.04569998]` |
| base-servo output cylinder | `[0.00000002,0.01882735,0.01190472]` | `[0.01249456,0.00000001,0.01924129]` | `[0.03882986,0.00000001,0.06294129]` |

Their authored three-dimensional center distance is `54.6237 mm`. Under the
frozen shared camera they project to `[643.57,419.95]` and
`[724.68,371.94] px`, compared with physical H detections
`[577.5,492.5]` and `[700.5,425.5] px`.

## Terminal status and smallest next measurement

There is no evidence-backed code or model change to make. The smallest
prospective discriminator is one static physical center-to-center
measurement, in millimeters, between the specifically identified base side
fastener aperture and base-servo output cylinder. The CAD prediction is
`54.6237 mm`.

- If the measured distance disagrees materially, the physical feature
  correspondence or SO-101 hardware/CAD revision is wrong; do not change the
  scene assembly.
- If it agrees, retain these correspondences and next measure one
  base-attached feature's signed 3D offset from the mounting plate origin to
  isolate the mount transform.

This audit used no hardware motion, policy, task execution, paid compute, or
Brev resource.
