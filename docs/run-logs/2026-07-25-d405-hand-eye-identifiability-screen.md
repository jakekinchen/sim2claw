# D405 physical-FK and hand-eye identifiability screen

Date: 2026-07-25

Proof class: `offline_pose_plane_hand_eye_identifiability_screen_only`

The screen now uses the versioned
`so101_left_arm_d405_hand_eye_fk_v1` contract. It binds the exact candidate
manifest and hash, the six physical-to-model joint transforms, the compiled
MuJoCo kinematic signature, `left_base`, and the explicit wrist/tool body
`left_gripper`. The D405 depth optical frame is right-handed with x right,
y down, and z forward. `wrist_from_d405_depth_optical` remains the unknown
being estimated.

The contract is limited to physical-calibration setup FK. Its source adapter
is still unapproved for replay or task authority; this contract does not widen
that authority.

The evaluator first applies the frozen observation-diversity gates. For a
passing set it deterministically separates train and held-out observations,
uses compiled-model FK to fit wrist-from-camera rotation against one fixed
base-frame plane normal, and checks the actual rotation Jacobian rank,
conditioning, and held-out normal-angle residuals.

Translation and the base-plane offset are then solved together. When their
design matrix is rank-deficient, the result is explicitly
`rotation_identifiable_translation_gauge_ambiguous`: rotation and its
held-out residual may be reported, while wrist-camera translation and base
plane remain null. A full-rank solution is still diagnostic-only and grants no
extrinsic-promotion, motion, policy, or task-success authority.

Synthetic tests cover insufficient diversity, identity drift, the
rotation-only gauge case, a fully determined consistent set, deterministic FK,
and compiled-model hash drift. No camera or robot was accessed.

## Offline next-view recommendation

`configs/calibration/d405_pose_plane_targets_from_anchor_v1.json` records six
ordered targets from the fresh torque-off anchor
`[-5.6264, -57.0549, 101.4945, -49.9780, -75.0330, 3.0879]`.
An 81-sample-per-stage sequential CPU MuJoCo preview introduced no new or
worsened kinematic contact, ended with no contact, and produced a 54.70-degree
maximum tool-orientation separation. This is simulation contact evidence only:
it does not prove physical safety, reach, tracking, or plane visibility. Every
physical stage must be regenerated from a fresh live anchor through the
existing guarded setup executor and closed torque-off.
