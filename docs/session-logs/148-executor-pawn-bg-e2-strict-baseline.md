# OR148 executor log — E2 strict baseline

Date: 2026-08-07

## Scope

Run one parameter-unchanged current full-step replay of retained recording
`20260719T031615Z-0e058ca2` and independently evaluate the exact `418×6`
float64 action SHA-256
`a8121830d7a3284094ca0e109d621b7585e4692b86fe33f3fe42cd5c1f412bcc`.
No mechanism candidate, parameter change, confirmation, render, action assistance,
or physical claim was authorized.

## Pre-execution

- Focused contract tests: `2 passed`.
- `sim2claw check --profile agent`: pass with OR148 execution admitted.
- Executor context: pass; no blockers; no external, physical, paid-compute,
  commit, or push authority.

## Execution and independent verdict

- Complete steps: `9,443` at `0.00225 s`.
- Requested action and expanded applied control: exact.
- Finite trace, no unstable MuJoCo warnings.
- Raw maximum rise: `42.694 mm`.
- Qualified opposing-pair dwell: `0 s`; qualified lift and carry: `0`.
- Upright failure: step `5,306`, `11.969379 s`.
- Tilt at first `40 mm` rise: `53.135°`.
- Maximum tilt: `101.730°`; final tilt: `97.795°`.
- Final E1 center error: `219.557 mm`.
- Strict wrong-contact steps: `22`.
- Maximum collateral translation: `0.479 mm`; orientation: `1.150°`.
- Strict pass: false.

The frozen verifier's per-jaw diagnosis found no robot-to-wrong-pawn contact.
A separate read-only body-ID decomposition of the already sealed trace, with no
simulator rerun, attributes the verifier's `22` wrong-contact steps to selected
E2 contacting D1 for `8` steps and A2 for `14` steps. This attribution explains
the verdict but does not modify it.

## Decision

Terminal strict negative. E2's raw lift is not a qualified upright carry, and
retention-only work cannot repair a pawn that has already exceeded the upright
gate before lift. D2 is independently closed by its pre-existing E2 collision;
F2 and C2 passive lanes are already closed. No simulator-only surface, friction,
offset, timing, force, or action search is admitted.

Reopening requires new independent metric evidence: two-sided fingertip shape
and jaw-frame registration, load-dependent deformation/contact patch, synchronized
jaw-to-board pose, pawn dimensions/base-contact pose, and a prospectively frozen
mechanism. No confirmation or video render ran.
