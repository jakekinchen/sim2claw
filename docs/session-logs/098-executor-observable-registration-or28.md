# Executor session 098 — OR28 prior-evidence aperture composition

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

The one prospectively frozen replay changed only the physical-to-model gripper
zero offset from the OR19 canonical baseline `-0.17453 rad` to the
independently fit OR6 value `0.04948239306868429 rad`. The `531×6` action
tensor, timestamps, row order, body mapping, OR18 scene, reset, contact
parameters, object parameters, and natural-contact dynamics were unchanged.

This nearly eliminates the bad consequence channels:

- final tilt falls from OR19's `102.106°` to `0.000696°`;
- final height error falls from `14.539 mm` to effectively zero;
- collateral displacement falls from `11.451 mm` to effectively zero.

But transport also disappears:

- first contact moves from sample `231` to `244`;
- signed D2 progress falls from `47.513 mm` to `2.660 mm`;
- final D2 error is `52.241 mm`;
- the frozen `36.025 mm` progress gate fails.

The result is a causal channel advancement, not task success. The two prior
aperture endpoints now bracket the desired behavior: one transports while
tipping, the other remains upright without transport. The next card may derive
one static enclosure candidate from the physical sample-232 event, but may not
search dynamic outcomes.

No camera, serial bus, gateway, hardware motion, paid compute, parameter fit,
simulator promotion, task-success claim, or transfer claim was opened.
