# Executor session 095 — OR23 contact-consequence discriminator

Decision: `STOP`

Evidence anchor: `100`

## Result

The prospectively frozen samples `210–300` discriminator returns
`MECHANISM_NOT_IDENTIFIABLE`. It does not select a correction.

The simulator and retained physical source agree at the available coarse event
resolution:

- simulator unilateral contact sample `231` is inside physical contact
  samples `228–232`;
- simulator orientation onset sample `248` is inside the physical lift window
  `247–260`;
- simulator sustained support loss sample `260` equals physical definite carry
  start `260`.

All four predeclared mechanism branches fail closed because the retained
physical episode cannot directly distinguish them:

- off-center contact moment lacks a metric contact point and physical pawn
  orientation path;
- jaw/pawn slip lacks resolved contact state and relative contact velocity;
- support transition lacks a visible or metric support-contact state;
- downstream collision lacks a named physical collision witness before the
  orientation divergence.

A final frame review did not justify weakening those gates. The C922 contact
region is occluded by the wrist assembly. The D405 view appears qualitatively
consistent with an upright pawn between the jaws, but the dark pawn, board,
and gripper housings merge; there is no accepted pawn-base observation or
calibrated D405 extrinsic from which to recover a metric 3D orientation.

OR24 therefore has no independently constrained correction family and OR25
has no replay prerequisite. Both are `NOT_RUN_PREREQUISITE_FAILED`. This is the
complete retained-data result, not a mapping or transfer claim.

## Verification

```text
uv run --locked pytest -q tests/test_contact_consequence_mechanism_discriminator.py
2 passed

artifact_sha256
0e8dbd6dffa341a7f6cd26745c8a2ed93835a31bca654166dded4ec0cd1c38f0
```

No camera, serial bus, gateway, hardware motion, paid compute, parameter fit,
simulator replay, promotion, or task attempt was opened.
