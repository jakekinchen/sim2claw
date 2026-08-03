# OR100 — post-final bounded renderer-native enclosure-plane fit

## Decision

Test one physically legible, one-parameter 3D side-wall family after the consistent but insufficient OR99 shell gain.

## Frozen family

- Start from the OR99 shell: one unchanged rear-wall primitive, no legacy window/blind/mug detail.
- Add exactly one white box side-wall geom under body `6`.
- Freeze local y/z, orientation, half-size, material, every other scene geom, camera, workcell and robot transforms, response, actions, states, and timing.
- Search only nine global local-x centers from `-0.50` to `-0.30 m` on split positions `1-7`.
- If and only if the development gate passes, render the one selected x on positions `8-11` without refit or alternate selection.

## Acceptance

Development requires mean outside-board F1 at least `0.38`, a gain of at least `0.02` over OR99 shell, and at least `5/7` gains of `0.01`. Validation requires mean outside-board F1 at least `0.375`, a shell gain of at least `0.015`, and at least `3/4` gains of `0.01`. Board and full-frame mean regressions may not exceed `0.01`.

## Boundaries

No flexible mesh, per-episode geometry, pixel composite or warp, validation selection, simulator replay, physics mutation, hardware, paid compute, promotion, or transfer claim. The split is decision-isolated post-final evidence, not an untouched-pixel cohort.
