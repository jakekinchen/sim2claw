# OR70 — Ephemeral OSMesa renderer capability

Decision: `ONE_MINIMAL_CONTAINER_FRAME_THEN_SHUTDOWN`

Evidence anchor: `OR69`

The 11-episode state corpus is complete, but macOS CGL cannot create a renderer
in the current terminal session. The earlier Linux attempt synchronized the
whole project and failed while extracting unrelated CUDA packages. Test the
missing capability with a deliberately minimal local container.

## Required outcome

Start local Colima, run one auto-remove `python:3.12-slim` container with only
MuJoCo `3.10.0`, NumPy `2.3.5`, and OSMesa runtime libraries, mount the repository
read-only, and render exactly one `320×240` RGB frame from the tracked SO-101
example scene. Require a nonempty frame, hash every identity, then stop Colima.

## Frozen constraints

- No project lock sync, CUDA dependency, physical footage, state trace, camera
  fit, simulator replay, candidate video, or parameter fit.
- The probe container auto-removes and local Colima is stopped afterward.
- No paid compute, hardware, training, promotion, or transfer authority.

## Terminal rule

A nonempty hash-bound OSMesa frame opens a separate development-only workcell
renderer baseline card. It proves runtime capability only, not that the retained
workcell, camera, footage, events, physics, or pixel metrics match.
