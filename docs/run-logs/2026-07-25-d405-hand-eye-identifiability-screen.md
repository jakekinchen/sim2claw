# D405 hand-eye identifiability screen

Date: 2026-07-25

Proof class: `offline_pose_plane_hand_eye_identifiability_screen_only`

Verdict for the current repository prerequisite state:
`diversity_passed_kinematic_camera_frame_contract_missing` when a synthetic
receipt set clears the observation-diversity gates. No extrinsic was fitted.

## Repository prerequisite audit

The repository does not currently provide both contracts required to turn
joint-pose/plane observations into a physical hand-eye calibration:

- an approved, hash-bound physical six-joint-to-robot forward-kinematics
  contract with an authoritative wrist frame;
- an approved D405 optical-frame-to-wrist-mount frame contract.

The existing system-identification references label the physical joint
transform provisional/unapproved and measured end-effector orientation
unavailable. Simulator FK and camera names are not substitutes for the missing
physical frame contracts.

The evaluator therefore seals those exact prerequisites. It never introduces a
new kinematic model, borrows simulator FK as physical truth, or invents a
wrist-camera transform.

## Implemented screen

For every bounded pose-plane capture receipt, the evaluator verifies:

- the exact pose-plane receipt schema and calibration-setup-only proof class;
- a passing bounded-capture verdict with all authority bits false;
- no pre-existing camera-to-robot fit claim;
- finite six-joint terminal-hold means;
- finite unit plane normals and metric offsets;
- stable camera identity and accepted calibration receipt across the set.

It then reports:

- centered joint-pose singular values, rank, and retained-subspace condition;
- maximum per-joint pose span;
- centered plane-normal singular values, rank, and condition;
- maximum plane-normal angular separation;
- plane-offset span;
- a normalized combined observation-space screening rank and condition;
- within-pose normal and offset stability.

The combined screening rank is explicitly not labeled a calibration-Jacobian
rank. True hand-eye identifiability remains false until the missing physical FK
and mount-frame contracts make that Jacobian definable.

## Outcomes

- Observation gates fail:
  `insufficient_observations`; no fit or held-out residual exists.
- Observation gates pass but current prerequisites remain absent:
  `diversity_passed_kinematic_camera_frame_contract_missing`; no fit or
  held-out residual exists.
- Identity/calibration lineage drift or malformed evidence:
  hard fail-closed evaluator error.

Every receipt preserves:

```text
fit.attempted=false
fit.wrist_camera_rotation=null
fit.wrist_camera_translation_m=null
fit.fixed_base_plane=null
fit.held_out_residuals=null
camera_to_robot_extrinsic_fitted=false
promotion_authority=false
```

## Synthetic verification

```text
.venv/bin/pytest -q \
  tests/test_d405_hand_eye_identifiability.py \
  tests/test_d405_pose_plane_capture.py \
  tests/test_d405_metric_surface_plane.py
.............                                                            [100%]
13 passed in 0.82s
```

The tests cover a repeated-pose insufficient set, a diverse set that clears
the screening gates but remains blocked by the two explicit frame contracts,
and camera-identity drift rejection. No camera or robot was accessed.
