---
name: estimate-correction
description: Infer a minimal task-space pregrasp correction from multiple transfer-observable residual estimates.
---

# Estimate Correction

1. Read `failure_packet`, `pose_residuals`, and `control_summary`.
2. Compare repeated translation estimates, use their center and spread, and
   distinguish a pose-centering error from joint-tracking error.
3. Keep the proposal in the `selected_object` frame and change translation only.
4. Submit one `pregrasp_centering_offset` hypothesis citing exact evidence IDs,
   a three-vector prediction, and calibrated confidence.

Do not infer evaluator-only state or convert the estimate into raw joint targets.
