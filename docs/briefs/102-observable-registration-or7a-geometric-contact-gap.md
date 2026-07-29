# Brief 102 — Observable registration OR7A geometric contact gap

Decision: REDIRECT. Evidence anchor: 100.

## Slice

At each exact applied state from physical contact candidate sample `228`
through first carried-motion sample `260`, evaluate the selected pawn against
all named left fixed/moving jaw collision geometries under the C6 and OR6
mapping. Do not integrate physics.

## Acceptance

- bind exact C6 applied states, row order, timestamps, initialization, and OR6
  candidate identity;
- set the selected pawn to the unchanged physical initial XY, simulator support
  height, and reviewed upright orientation;
- use MuJoCo forward kinematics and signed geom distance only;
- report per-sample minimum jaw-pawn distance, nearest named geom pair, jaw-tip
  midpoint, pawn center, and midpoint-to-pawn vector;
- report values at `228`, `232`, and `260`, plus the minimum over `228–260`;
- report the C6-to-OR6 differential without fitting or selecting a parameter;
- classify whether aperture mapping materially closes the spatial gap;
- keep camera, global mapping, pad geometry, joint mapping, contact, object,
  action, plant, and task outcome unchanged;
- no dynamic replay and no hardware.

## Stop

OR7A may localize the next static mechanism family. It cannot fit the
mechanism, approve mapping, or run another outcome replay.
