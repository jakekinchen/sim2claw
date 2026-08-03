# OR73 development initial-frame shared 3D camera fit

OR73 isolates camera geometry from timing, action, contact, and appearance. It
uses only frame zero from each of the four development videos and corresponding
state traces. The physical evaluator frames receive the acquisition mode's
known `hflip,vflip` orientation; this does not alter candidate pixels.

One seven-parameter look-at camera is shared across every episode: target XYZ,
azimuth, elevation, distance, and vertical field of view. A deterministic,
seeded differential-evolution search evaluates at most `336` candidates at
`160×120`, ranking the mean of a frozen `0.8` tolerant-edge / `0.2` full-frame
linear-pixel objective over all four development frames. Four `320×240` final
candidate images are emitted from the selected shared vector.

Candidate pixels remain projections of the frozen 3D scene and state only.
Physical pixels are evaluator targets and cannot be composited, textured, or
otherwise included in the candidate. Appearance, timing, state, and physics are
fixed. Validation and evaluator-heldout roles remain unopened. A pass only
freezes a development-selected static camera for a subsequent full-timeline
development evaluation.
