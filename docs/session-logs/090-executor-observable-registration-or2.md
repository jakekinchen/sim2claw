# Executor log 090 — Observable registration OR2

Date: `2026-07-29`

## Outcome

OR2 is a prospective terminal negative for the four-parameter robot-to-board
rigid family. The fit used six jaw poses under the frozen OR1 camera and hit
the positive `150 mm` X-translation bound. It still left `16.324 px` tip RMS
and `12.347 px` midpoint RMS. The four non-overlapping known-outcome validation
poses were scored without refitting and reproduced the error at `16.302 px`
tip RMS and `12.318 px` midpoint RMS.

## Residual localization

The observed jaw opening averages `32.279 px` in fit and `32.371 px` in
validation. The current modeled jaw averages only `11.071 px` and `11.140 px`.
Fixed and moving tip residuals point in opposite directions and have comparable
RMS. The approximately `21.2 px` aperture underprediction is therefore not
repairable by a common robot-board rigid transform.

This makes jaw geometry or gripper mapping a prospective causal candidate. It
does not authorize that mechanism before the sealed physical episode is
compiled and its contact timing is evaluated.

## Evidence

- freeze commit: `54011f2`;
- receipt SHA-256:
  `436cd9f629b780e5f8a08e9f00708659c4fa416a5362fe603bfee6f1f6484c3a`;
- artifact SHA-256:
  `3151318a6c58ad0d56b8b01376b29e964c1da2df0972e4c5b397ca2fcc9b4292`;
- task-bounded jaw mapping accepted: false;
- global mapping accepted: false.

## Validation

- `uv run pytest tests/test_observable_robot_jaw_mapping.py -q` — `2 passed`;
- fit/validation membership does not overlap;
- camera, joints, jaw geometry, contact parameters, and sealed task outcome
  remained unchanged;
- the authoritative receipt rebuild is deterministic.

## Boundary

This result is a model-family rejection, not a claim that all mapping is
impossible. It does not approve camera intrinsics, full jaw pads, wrist,
silhouette, floor/support, contact dynamics, task transfer, or hardware.
