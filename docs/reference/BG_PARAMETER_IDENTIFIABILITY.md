# B--G Parameter Identifiability Ledger

This ledger prevents an optimizer from converting a lower residual into a
physical claim when the retained observations do not identify the mechanism.

| Parameter or mechanism | Observable evidence | Identifiability | Permitted use |
|---|---|---|---|
| Board playing side | nominal-print-conditioned AprilTag frame; separate photo/Polycam estimate | 355.6 mm plausible; no metric authority | freeze as declared simulator hypothesis |
| 301.3 mm board fit | sparse event residual optimizer | confounded; inconsistent with nominal print by 15.4--16.7% | retain as optimizer-compensation evidence only |
| Board center/yaw | mapped-encoder event residuals | diagnostic, correlated with joint zero/tool point | bounded candidate only |
| Lift vertical correction | phase z residuals and pan dependence | correction identifiable; physical cause unresolved | mechanism-discriminating ablation |
| Base height/lift zero/tool point | same sparse event instants | not jointly separable | do not fit together |
| Application delay | timestamped command/measured traces | 110 ms simulator-side delay accepted by grouped episode CV; not physical latency calibration | frozen timing diagnostic |
| Reset/reference | first command, first measured, model default | first commanded is only 0.002% better; below materiality | retain first measured; ruled out as primary gap |
| Joint response/deadband | command/measured position, derived velocity, stall rows | 2 degree lift/elbow model class accepted in all four folds; not a firmware parameter | frozen actuator diagnostic |
| Stationary elbow load response | phase- and pose-conditioned residual; paired fold predictions | bounded model class lowers pooled CV joint RMS 6.461% and EE RMS 12.312%; selected coefficient -1.5 is the frozen lower grid boundary, so magnitude and physical cause remain unidentified | retain as trace-response diagnostic; do not call torque, firmware, gravity compensation, or compliance calibration |
| Motor effort | cached quantized raw current proxy | not calibrated torque; low independent signal | descriptive/covariate ablation only |
| Gripper aperture event | commanded/measured plateau and video phase | interval-level hypothesis | compare event intervals |
| Contact/friction | frozen rubber-tip ensemble; endpoint appearance intervals | underidentified: 2--3 lifts, 0 strict successes, no admitted physical retention label | sensitivity ensemble only; no selection |
| Pawn mass/inertia | no direct retained measurement | not identifiable | prior/sensitivity only |

Promotion rule: a candidate must improve the relevant observable in grouped
training-episode validation, retain action bytes, survive the frozen composite
evaluation, and carry an explicit authority statement. A task reward or lower
event RMS alone cannot change a row's identifiability state.

2026-07-21 closeout: the load-response row satisfies the predeclared
trace-fidelity RMS lane and a positive whole-episode bootstrap interval, but it
does not survive the grasp/transport vector. Contact is unchanged, lift is
2/11 to 1/11, and strict success remains 0/11. Composite promotion stays false.
