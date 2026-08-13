# OR156 source-clock provenance and frame-association audit

OR156 is a read-only reproduction of an already inspected timing result. The
retained physical rows expose two same-process software timestamps:
`sample_completed_monotonic_seconds`, which owns the frozen video schedule and
replay timeline, and the immediately preceding
`follower_position_read_completed_monotonic_seconds`. The audit asks whether
substituting the latter would materially change the apparent gripper-closure
timing or choose different C922/D405 frames.

GPT Pro and Fable 5 Extra independently inspected exact pushed commit
`0a38cea05da0667b6869f1ad9380f2fa37615729`. Both reject every retained-data-only
task replay because no unexhausted factor has both admissible fit rows and an
untouched validation cohort. GPT Pro explicitly permits a static read-only
association diagnostic. Fable identifies the already-frozen OR9 fresh static
validation acquisition as the smallest route that could later reopen spatial
registration; it is outside this no-new-hardware slice.

OR156 reads all 531 retained rows and 1,236 camera callbacks, preserves the
frozen nearest-host-time association rule, and recomputes each binding under
both row clocks. It may report direct clock distance, elapsed-time distortion,
and frame-index changes. It cannot mutate a timestamp or action, step or replay
dynamics, render, fit a phase, change the camera, open hardware, identify
exposure or actuator-application time, select a correction, or open a successor.

The numbers were inspected locally before the contract was frozen. The result
is therefore permanently a known-result diagnostic. Its only value is to
eliminate or retain this exact software-clock explanation; it cannot prove a
calibration, task success, simulator fidelity, promotion, or transfer.
