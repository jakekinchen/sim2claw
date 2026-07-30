# Executor session 093 — OR22A Pi/action motion alignment

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

The frozen motion-curve method passes its development gate on `3/4`
contact-free tri-camera runs. It uses the first derivative of mean absolute
frame difference for Pi and C922, a host-timestamped joint-velocity-energy
corroborator, one constant lag per run, and leave-one-transition-out checks.

Accepted contact-free association widths are `33.318–43.319 ms`. The fourth
contact-free run fails closed on correlation and a `120 ms` visual/joint lag
delta.

The later guarded applications remain fail-closed:

- D1-to-D2 exact-v4 has a sharp Pi-to-C922 visual alignment at `0.965 s`,
  correlation `0.887833`, and distinct-peak margin `0.534514`, but the joint
  corroborator peaks at `0.845 s`. The `120 ms` delta exceeds the frozen
  `100 ms` gate.
- C2-to-C1 exact-v1 has a sharp `0.970 s` visual lag and `0.701674`
  correlation, but its outcome-excluded setup interval has only one independent
  motion/hold transition instead of three.

No task contact or task outcome entered either lag fit. Neither guarded-run Pi
stream is admitted as action-synchronized proof.

## Verification

```text
uv run --locked pytest -q tests/test_pi_action_motion_alignment.py
2 passed

uv run --locked python scripts/build_pi_action_motion_alignment.py
PASS_BOUNDED_PI_ACTION_INTERVAL_ALIGNMENT
```

## Next

OR22 should use the successful episode's actual C922 and D405 RGB streams as
primary evidence. The Pi curves remain useful for contact-free method evidence
and for visually inspecting later guarded runs, with their failed association
gates displayed explicitly.
