# Reviewer message 006: significant action-frozen RMS advancement

We continued the hardware-free campaign without changing the teleoperation
policy actions. The largest residual was a negative, pose-dependent elbow error
that was strongest in stationary/load-bearing phases. A frozen bounded
simulator response experiment therefore tested joint-specific deadbands plus an
elbow load-bias term active only inside the elbow deadband.

Four whole-episode folds reduce pooled joint RMS from 1.2955577 to 1.2118497
degrees (6.461%) and EE RMS from 12.9364 to 11.3437 mm (12.312%). All folds
improve, source action hashes are byte-identical, and a deterministic paired
10,000-replicate whole-episode bootstrap gives a 4.398--8.540% 95% interval for
relative joint-RMS improvement. The interval is entirely above zero, although
its lower bound is below the 5% materiality threshold; 91.62% of bootstrap
replicates exceed 5%.

All 11 episodes come from one retained acquisition session. The bootstrap is
therefore a conditional retained-episode uncertainty audit, not evidence of
independent-session or physical-population generalization.

The selected load-bias coefficient is -1.5, exactly the frozen grid's lower
boundary in every fold. We therefore claim support for a bounded load-response
model class, not an identified coefficient, physical torque model, firmware
behavior, gravity compensation, or compliance calibration.

Target-piece consequences do not justify promotion. Contact remains 11/11,
lift regresses from 2/11 to 1/11, two episodes finish inside the destination
instead of zero, mean final target distance improves from 76.884 to 47.310 mm,
and strict success remains 0/11. This is a significant action-frozen simulator
trace-fidelity advancement only. It is not a grasp improvement, physically
calibrated simulator, working policy, training admission, or sim-to-real
transfer result.
