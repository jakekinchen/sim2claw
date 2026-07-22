# SAIL Phase 1 Publication Freeze Run Log

Date: 2026-07-22

Milestone: P1-17 and Phase 1 exit

The final publication campaign freezes six research questions, ten required
ablations, nine paper slots, nine CSV tables, seven SVG figures, 25 exact source
bindings, paired seeded-case statistics, and 10,000 whole-episode bootstrap
resamples. The campaign config SHA-256 is
`7ad34cd30649395ad0b2424697489ef8d86b8bf901ffce9d886fa909092c4dc9`.
The deterministic compiler SHA-256 is
`7ee979df1969d469a6df3231cb793d156f50f6d8028ef301ef718cf4de2a5a30`.

The ignored package at `outputs/sail/publication-v1/` has publication package
SHA-256
`98173b9d5dca97c75ce8aa579fd727b02a32ff96474e3025283d590ebdd8f833`.
Its receipt SHA-256 is
`5067d9932503af14fb9a972037b006a51b23deed571137d78fff9fdffce017e0`
with digest
`7875b3880e00237279bd7423cf4f2098df6118f07d8822d3f2430ce25d7e808c`.
The receipt binds 24 generated outputs plus the config, compiler, and source
inventory. Publication regeneration made zero provider calls, consumed zero
new physical observations, pooled no provider results, and opened no training,
promotion, capture, motion, or transfer authority.

The Phase 2 operator contract SHA-256 is
`f79fd55bd00761b2920c2f4db9285e5280bab7ebcd44175e27e285959738f7c4`.
Its compiled packet SHA-256 is
`6fc0e4781e96337186531046ecbc90beccc35a6849e0adfe3eab4ebc39af591d`.
It freezes 13 required workcell identities, calibration/validation/held-out
roles, 11 static measurements, five empty probes, six interaction probes,
three prospective predictions, gateway requirements, and stop conditions. All
identity values remain missing and both capture and motion authority remain
false, so Phase 2 is executable without redesign but blocked external.

Verification results:

- focused publication/CLI: 14 passed in 0.42 seconds;
- automatic contract tier: 36 passed in 0.56 seconds;
- automatic synthetic tier: 58 passed in 2.09 seconds;
- automatic integration tier: 73 passed and 2 subtests passed in 27.57 seconds;
- JSON parsing, Python compilation, receipt regeneration, and
  `git diff --check`: passed;
- focused LF00-LF13 component rerun: 1 passed in 122.51 seconds;
- project-bundle/NemoClaw integrity: 71 passed in 2.22 seconds; and
- final broad repository gate: 787 passed, 3 expected skips, and 328 subtests
  passed in 1280.60 seconds.

The first broad run correctly failed closed in one Learning Factory component
case because its project template still bound the pre-P1-16 project-state
digest. No test was weakened. The final completed project state was frozen at
SHA-256
`67f4493378a737f9702ae3fe7f9a134828fc906cf27afe384e050a059c51a307`,
the template was updated to that exact digest, the failing case and all 71
bundle-integrity tests passed, and the complete broad suite was rerun cleanly.

Resource closeout was live-verified after compilation. Authenticated
`brev ls --json` returned `{"workspaces": null}` and `docker ps` returned zero
running containers. The campaign receipt records zero Brev instances,
containers, devices, and provider sessions created. No camera, serial, servo,
robot, credential, paid-compute, or hardware authority was opened.

Phase 1 therefore closes as a deterministic methods result with separately
labelled seeded synthetic, retained retrospective, prospective simulator,
agent, policy-terminal-negative, and future-physical lanes. It does not claim a
policy win, physical mechanism identification, simulator promotion, physical
transfer, or robot capability.
