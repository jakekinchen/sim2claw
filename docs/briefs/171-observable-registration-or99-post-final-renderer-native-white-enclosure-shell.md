# OR99 — post-final renderer-native white-enclosure shell

## Decision

Execute one preregistered scene-native shell candidate on the initial frame of all eleven already-open episodes.

## Rationale

OR97 isolates persistent static scene content as the dominant outside-board residual. OR98 shows that removing the entire legacy photo-background and mug regresses outside-board edge F1, which means the coarse wall carries useful structure even though its window, blind, sill, bar, and mug details do not describe the retained physical white enclosure.

## Frozen intervention

- Preserve the exact OR95 baseline candidate.
- For the shell candidate, retain only body `6` geom `rear_wall` from the legacy background and remove every other body `6` geom plus every body `7` geom.
- Do not change the retained rear-wall primitive, any other scene geometry, camera, workcell or robot transforms, response, action, state, or timing.
- Do not fit, search a family, decode a new cohort, composite pixels, warp pixels, replay the simulator, touch hardware, or use paid compute.

## Acceptance

Require mean outside-board edge F1 of at least `0.37`, a mean gain of at least `0.02` over the exact baseline, at least `8/11` episode gains of `0.01`, and no worse than `-0.01` board-edge or full-frame similarity regression. All integrity gates must pass.

## Claim boundary

This is post-final retrospective static-scene diagnostic evidence only. It cannot establish same-video equivalence, camera or kinematic fidelity, event or physics parity, prospective generalization, physical transfer, task transfer, or simulator promotion.
