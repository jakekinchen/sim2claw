# IMG_5349 complete articulated-CAD fit

Date: 2026-07-26
Proof class: `retrospective_visual_pose_diagnostic`
Verdict: retained right-arm hypothesis, not promoted

## Outcome

The complete reviewed SO-101 visual tree, including the base, was evaluated
against the IMG_5349 Gaussian cloud with the tracked board Sim(3) and both
robot mounts frozen. Projection into frame 1 resolves the visible white
SO-101 as the simulation's right arm: the right base projects to
`(1055.67, 2617.23) px`, on the photographed base, while the left base
projects to `(48.84, 1940.01) px` without an independent SO-101 silhouette.
The left arm is therefore rejected rather than fit to the black stand/clutter.

A bounded six-joint fit over `5,337` neutral, opacity-filtered splats produced
this right-arm hypothesis:

```text
shoulder_pan   65.9230 deg
shoulder_lift -100.0000 deg
elbow_flex    -27.0937 deg
wrist_flex     95.0000 deg
wrist_roll    156.1968 deg
gripper        76.7201 deg
```

All exact simulation visual meshes were sampled, not a stick figure or a
partial arm. Median CAD-to-splat distances changed as follows:

| Body | Baseline | Candidate | Change |
|---|---:|---:|---:|
| base | 21.34 mm | 21.34 mm | 0.00 mm |
| shoulder | 37.10 mm | 45.86 mm | +8.76 mm |
| upper arm | 36.49 mm | 18.79 mm | -17.70 mm |
| lower arm | 23.47 mm | 12.15 mm | -11.32 mm |
| wrist | 67.53 mm | 10.12 mm | -57.41 mm |
| gripper | 85.52 mm | 20.07 mm | -65.45 mm |
| camera mount | 97.15 mm | 16.75 mm | -80.40 mm |
| moving jaw | 110.62 mm | 20.97 mm | -89.65 mm |

The images were not used by the cloud objective. On held-out early-component
frames 1-3, a grayscale, color-independent directed contour check over the
shoulder through gripper reduced half-resolution edge distance from
`37.39 px` to `25.38 px` median (`32.1%`), from `70.30 px` to `60.13 px` at
p75, and from `102.38 px` to `92.38 px` at p90.

## Why the angles are not promoted

The candidate is a useful alignment hypothesis, not recovered joint truth.
The right shoulder neutral-cloud median worsens by `8.76 mm`; shoulder lift
and wrist flex terminate at their MuJoCo limits; the 3DGS contains known
globally inconsistent camera segments and ghost geometry; and there is no
evaluator-owned measured joint/link landmark validation. The contour check
also does not model scene occlusion.

The result grants no metric geometry, joint calibration, collision, contact,
actuator/load-path, task, or physical-control authority.

## Reproduction

```bash
uv run python tools/evaluate_img5349_articulated_cad_fit.py \
  --output runs/3dgs-board-registration/20260726-articulated-cad-fit/receipt.json
uv run pytest -q tests/test_img5349_articulated_cad_fit.py
```

The focused test result was `2 passed`.
