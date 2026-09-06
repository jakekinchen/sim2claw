# Home workspace visual environment v1

`sim2claw.home_workcell` is the post-hackathon appearance layer for current
home-workspace comparisons.

It replaces the hackathon-only window, blinds, sill, antler mug, tripod, and
central two-tag sheet with an image-referenced countertop corner, backsplash,
large adjacent fiducial sheet, and small board-frame tag. The frozen
hackathon renderer in `sim2claw.scene` is not edited.

The task model remains the canonical `canonical_rank1_near_v1` workcell:
rank 1 is near the robot/operator, rank 8 is far, and board, piece, robot,
joint, actuator, collision, contact, and evaluator geometry are unchanged.
Tests compare canonical and home variants at the compiled MuJoCo state and
body-transform levels.

Use:

```python
from sim2claw.home_workcell import build_home_workcell_spec

model = build_home_workcell_spec().compile()
```

The added environment is visual-only. Its walls, fiducials, and apparent
camera relationship are not metric calibration evidence and must not be used
for collision, contact, camera-extrinsic, physics, task-success, transfer, or
physical-authority claims. The exact evidence and authority contract lives in
`configs/scenes/home_workspace_visual_v1.json`.
