# Full SO-101 visual-model registration

Date: 2026-07-26
Proof class: `physical_static_full_cad_projection_diagnostic_only`

## Outcome

The Pi overlay now renders the complete follower visual model instead of a
hard-coded moving-link subset. The previous allowlist omitted the base,
shoulder-side base geometry, and wrist camera mount even though those assets
were present in the compiled MuJoCo scene.

The renderer now discovers every follower body containing an original
group-2 visual mesh. The bound receipt inventories:

- 8 visual bodies;
- 18 visual mesh geoms;
- `left_base`, `left_shoulder`, `left_upper_arm`, `left_lower_arm`,
  `left_wrist`, `left_gripper`, `left_camera_mount`, and
  `left_moving_jaw_so101_v1`; and
- zero omitted visual bodies.

`left_edge_clamp` is listed separately because it is a simulator fixture made
from primitive collision geoms, not part of the original SO-101 visual mesh.
The source is hash-bound to
`third_party/mujoco_menagerie/robotstudio_so101/so101.xml` at SHA-256
`5ad49f2b45c083baac9ffe5d4d3213a5da7eac8039095bb2df177a697aae8308`.

## Three-pose physical sweep

Three admitted follower-only captures held shoulder pan, shoulder lift, elbow
flex, wrist flex, and gripper approximately fixed while sweeping wrist roll:

| Capture | Final wrist roll | Pi image SHA-256 |
|---|---:|---|
| positive | `60.7033 deg` | `d2381245a8a768bbdadd31536d799a756a61be6259cb0d25a8244607f1bb6c61` |
| zero | `0.8352 deg` | `60cfcd904cb8eae899276bcfc5e9696bfe40873d3a718eda371c05074f9f717a` |
| negative | `-59.2088 deg` | `c27d3b31813254edbc7db96b8a5c0ec98f0c021a0a38716fe0d304089da5ddc7` |

Each successful capture used 361 exact float64 motion samples, an 80-sample
torque-on hold, dual-camera capture, a receipt-bound IMX708 still, and a
torque-off close.

One camera transform was fitted on the zero-roll image and reused unchanged
on both roll endpoints. Tag-corner residuals stayed consistent:

| Split | Tag-corner RMSE | Tag-corner max |
|---|---:|---:|
| fit zero | `12.0783 px` | `19.0129 px` |
| heldout positive | `12.1543 px` | `17.5819 px` |
| heldout negative | `12.7213 px` | `18.4096 px` |

This confirms that the complete CAD model and wrist-roll motion are being
projected consistently. It does not establish parity: the shared projection
still places the base and jaw silhouettes visibly away from their physical
counterparts.

## Rejected automatic adjustments

The CAD-surface-constrained two-tag fit reduced training ambiguity but failed
its frozen gates:

- training: `14.7241 px RMSE / 29.8787 px max`;
- heldout H: `17.736 px RMSE / 26.683 px max`;
- heldout L: `21.009 px RMSE / 31.636 px max`; and
- numerical rank: `16 / 17`, with zero sensitivity to wrist-roll zero.

The three sweep images expose red jaw tips, but a direct red-tip-to-CAD
diagnostic also remains rejected. The projected jaw-tip centers are displaced
by roughly 100 pixels after the tag-derived camera registration, so fitting a
wrist-roll offset alone would compensate for a larger camera, upstream
kinematic, tag-mount, or jaw-geometry error. No wrist offset was promoted.

## Next calibration transaction

Do not add more free image-space link shifts. The next fit should jointly use:

1. exact-mode IMX708 intrinsics including lens distortion;
2. fixed-base CAD landmarks or a segmented base silhouette to constrain the
   global camera independently of moving tags;
3. CAD-surface tag mounts and the two link tags;
4. red jaw-tip observations across the three roll poses; and
5. leave-one-pose-out verification with one shared camera and connected
   kinematics.

The follower preflight passed after capture and reported
`physical_follower_torque_enabled: false`. No policy, task, teleoperation,
training, paid compute, or Brev action ran.
