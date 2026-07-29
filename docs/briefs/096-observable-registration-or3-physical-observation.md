# Brief 096 — Observable registration OR3 physical observation

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Compile an `ObservableEpisode.v2-min` supplement for the retained physical
D1-to-D2 episode. Bind each of the 531 sample rows to its native C922 and D405
RGB timestamps. Before visual annotation, freeze a finite schedule spanning
approach, candidate grasp, lift, carry, release, and settle using only action,
measured-joint, and recorder timing fields.

Extract the corresponding frames deterministically. Record fixed/moving jaw
tips and selected-pawn crown/base or visible silhouette where available.
Every observation must include the source stream, frame index and timestamp,
two-pass coordinates or categorical labels, disagreement, visibility,
occlusion, and missingness.

## Acceptance

- source samples, videos, recorder receipt, and frame metadata are hash-bound;
- all 531 action/video timestamps are monotonic and within both streams;
- the event-window schedule is frozen before any event labels are opened;
- visual event gates require two-pass agreement;
- gripper command, current, deflection, and hold fields remain diagnostic
  channels and cannot establish contact alone;
- C922 board-plane coordinates are emitted only where the OR1 projection is
  valid;
- wrist observations remain two-dimensional because metric depth and a
  camera-to-wrist extrinsic are unavailable;
- grasp, lift, carry, release, and support events are intervals when frame
  cadence or visibility prevents a single instant;
- ambiguous and occluded rows abstain;
- no simulator, policy, hardware, camera device, or physical motion is opened.

## Stop

OR3 succeeds when the physical consequence is observable enough to bound the
first jaw/pawn interaction and object motion, even if metric depth remains
unknown. It cannot fit camera, robot, jaw, contact, or actuator parameters and
cannot claim transfer.
