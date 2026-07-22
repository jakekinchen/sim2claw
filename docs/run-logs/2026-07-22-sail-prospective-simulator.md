# SAIL Prospective Simulator Campaign Run Log

Date: 2026-07-22

Milestone: P1-13

The acquisition router's frozen rank-1 structural intervention,
`sim_load_frequency_discriminator`, ran as the preregistered four-trial
frequency/load factorial on retained recording
`20260719T030059Z-a26f8400`. The protocol and all six input bindings were
committed before execution. Each trial consumed the exact same contiguous
368x6 float64 action tensor with SHA-256
`c4acc4dca04e30c9d3031e326496a7c1d46777e7a1bd87b8d6968d2174e575bc`.

All four trials completed in the declared budget with zero retries, zero
undeclared trials, zero stopped trials, and no grid expansion. The unchanged-
frequency load intervention reduced overall joint RMS from 1.358824 to
1.298368 degrees and EE RMS from 12.9836 to 12.0061 mm on this single retained
trace. The halved-update-rate intervention increased dynamic elbow RMS by
3.404% and dynamic overall joint RMS by 18.927%. Timing matched 2/2 required
signatures (1.0); load matched stationary elbow RMS and signed-bias effects but
not locality (2/3). These are simulator consistency results, not physical
latency or compliance measurements.

Loop closure selected `sim_timing_rate_probe`, different from the just-executed
structural discriminator. The lowest-RMS load trial is frozen only as the
selected simulator diagnostic. All four trial artifacts remain queryable; the
combined trial did not meet the preregistered aggregate-improvement predicate
for compensating-fit rejection, so its vector regressions are disclosed rather
than post-hoc relabeled. Missing physical contact, force, metric object, and
instrumented grasp channels remain explicitly not evaluable.

Final identities: config
`46aaa7cbf0ba1a4293423c69892d9ec0e2bbb9ab03d41110b7dc49c8fa966d40`;
experiment `01972714591ec706033a114446509443c3f0626d4ea5362f41d9e876161debf5`;
experiment digest
`04ba7fbd9989e0f22f07f684658bb3e473551f8c5e79df7bfe7926e1b802251c`;
graph delta `863c463d88adf3ecef47fa5e6a49060441ab65f88c68b4b4b588842b367419ed`;
graph digest
`e6b8d797ae0c19e6ba8a73f0e391e802fc97857d11921b8b8602b2bb1cf36e95`;
Phase 2 freeze
`73510a0ab4e4d840576ea0de364e0a8f08064831fd2820ce8005de2b179baa4c`;
freeze digest
`22af57ebc3b03b145aee4f1f7339b6fa6abe7360e8590a44e7a72631cb1d9445`;
receipt `1054dde57e738668d4055841396b9f786abeec700f165d99212b15c9db30ac31`;
receipt digest
`3dbb3002e37b8a8595c8dab0dcf991a3732d9a125129ded763da6f563f0e74e3`.

Focused validation is 9/9, SAIL validation is 138/138, and the final repository
gate passes 745 tests plus 328 subtests with three expected skips. The canonical
project contract binds the final P1-13 `project_state.json` hash. No provider,
hardware, Brev, training, policy, physical observation, or downstream authority
was used.
