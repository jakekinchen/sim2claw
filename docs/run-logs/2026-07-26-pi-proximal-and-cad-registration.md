# Pi proximal-link calibration and CAD registration

Date: 2026-07-26
Proof class: `physical_static_two_link_and_cad_projection_diagnostic_only`

## Outcome

The transaction added an independent proximal tag constraint, corrected the
distal tag's CAD body assignment, and rendered the exact simulated follower
geometry into a torque-on Pi frame. It did not promote simulator parameters or
run a policy/task command.

The strongest training-only result is that tag 2 belongs to `left_wrist`
(before `left_wrist_roll`), not `left_gripper` (after wrist roll):

- leave-one-pose-out tag-2 RMSE: `11.3679 px` for `left_wrist`;
- leave-one-pose-out tag-2 RMSE: `28.3764 px` for `left_gripper`;
- full two-link training RMSE improved from `14.8526 px` to `6.9131 px`; and
- all joint offsets moved off their `±8 degree` bounds.

This is a substantial model correction but not parity. Fresh heldout pose L
decoded both tags and rejected at `20.8052 px RMSE / 31.6699 px max`.

## Physical captures

| Pose | Role | Result |
|---|---|---|
| G | training candidate | stopped safely during camera hold; no Pi still; not retried |
| J | training | admitted; unique tags 1 and 2 |
| H | heldout | admitted capture; later rejected at `22.5389 px RMSE` |
| I | training | admitted; unique tags 1 and 2 |
| K | heldout | admitted capture; automatic detector found neither required tag; terminal reject |
| L | wrist-frame heldout | admitted; unique tags 1 and 2; terminal metric reject |

Every completed capture used 361 exact motion samples and 80 torque-on hold
samples. C922 and D405 containers had zero inferred gaps. Every invocation
closed with follower torque off and no device configuration rewrite.

## Camera and fit diagnostics

Eleven training tag-square views produced a constrained IMX708 focal estimate
of `655.0848 px` with `0.6095 px` OpenCV corner RMS, versus the official-FoV
seed of `932.8712 px`. This camera-only improvement did not close the robot
gap: the wrong gripper-attached model remained at `14.8526 px` training RMSE
and saturated shoulder/elbow offsets.

The wrist-attached candidate:

- candidate:
  `runs/pi-link-tag-calibration/20260726-dual-link-fit-v4-wrist-body/candidate.json`;
- candidate SHA-256:
  `9f8a77685a2c0bfb82b95eec48dfa20e450be75bcd4389f6389b94ec4c52df8b`;
- pose-L evaluation SHA-256:
  `54a793aec57b7a3aed0e14a1a46f740cea002cc08d219d7a0bdb3e44e61911b4`.

No candidate was promoted.

## Dense CAD bootstrap

`tools/render_pi_cad_overlay.py` projects the exact MuJoCo meshes/primitives at
the receipt-bound physical joint state through the fitted Pi camera. Pose L
output:

- image:
  `runs/pi-link-tag-calibration/20260726-dual-link-fit-v4-wrist-body/pose-l-cad-overlay.png`;
- image SHA-256:
  `1a187cc4b1cc1b5129fdc09800cf2d3771ace080b01d9640fcb424d4d2e3b458`.

The overlay is close enough for a dense, visibility-aware next step, but it is
not itself a fit or metric validation. Brief 046 freezes the next method:
rendered depth/body IDs, silhouette and edge-distance losses, optional tag
reprojection, encoder priors, explicit occlusion/out-of-frame handling, and a
fresh heldout before promotion.

### Corrected visual/tag overlay

The initial projection was visually misleading for two implementation reasons:
it omitted the candidate's fitted joint-zero offsets and drew collision proxy
hulls together with the visual STL meshes. The corrected renderer now applies
the offsets, projects visual mesh geoms only, and includes the actual virtual
tag36h11 textures at the modeled tag-1 and tag-2 mounts. It also detects tag 0
on the crossing arm and marks it as excluded.

Pose L corrected output:

- image:
  `runs/pi-link-tag-calibration/20260726-dual-link-fit-v4-wrist-body/pose-l-visual-cad-virtual-tags-v3.png`;
- image SHA-256:
  `3e259e070a629ba8acd1f9a744e24b7da2c3eaf5d14ad0267e4348d17b945f83`;
- initial two-tag corner error:
  `20.8052 px RMSE / 31.6699 px max`; and
- bounded per-frame camera-only error:
  `6.2838 px RMSE / 10.7943 px max`.

The required per-frame camera change was large (`7.0646 degrees`,
`0.1601 m`), so this is useful correspondence evidence but not a replacement
for one fixed global Pi calibration. A training-only comparison also rejected
the visually plausible `left_lower_arm` assignment for tag 2: its mean
leave-one-pose-out RMSE was `14.0305 px`, versus `11.3679 px` for
`left_wrist`. The next fit therefore keeps tag 2 on `left_wrist` and adds dense
visual-link residuals instead of selecting a body from this one picture.

## Verification and terminal state

- `44 passed`: native dual camera, physical gateway, wrist-view reposition.
- Both new tools pass Python bytecode compilation.
- Final follower preflight passes.
- Follower torque is off.
- No policy, task, teleoperation, training, provider, paid compute, or Brev
  action was run.
