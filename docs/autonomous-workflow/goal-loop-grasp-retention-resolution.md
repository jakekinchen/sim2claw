# Goal loop: physical-trace-anchored grasp-retention resolution

Status: `COMPLETE — TERMINAL NEGATIVE; DIRECT PAD FORCE/DEFORMATION MEASUREMENT REQUIRED`

Authority: [`configs/sail/grasp_retention_resolution_v1.json`](../../configs/sail/grasp_retention_resolution_v1.json)

This loop continues after the terminal-negative project application. It uses
the retained C2 physical video and joint/current telemetry to constrain a
simulator mechanism without changing the source action array. The physical
recording is diagnostic and unqualified; it can establish that the real jaw
stayed mechanically loaded and the pawn remained held, but it cannot identify
force, rubber friction, or exact 3D pad geometry.

## Milestones

| Milestone | State | Exit evidence |
| --- | --- | --- |
| B1-00 | complete | source hashes, metrics, budgets, and stop rules frozen and tested |
| B1-01 | complete | C2 video, mapped joint state, action, current, and release sequence synchronized |
| B1-02 | complete | unilateral fixed-pad placement, actuator overclosure, and rigid-cap limitation localized |
| B1-03 | complete | eight frozen campaigns and 98 C2 candidate replays completed with identical actions |
| B1-04 | complete, not opened | zero anchor passes; sentinel and all-eleven promotion evaluation correctly stayed closed |
| B1-05 | complete | terminal negative; direct jaw force and rubber deformation named as the remaining measurement |
| B1-06 | complete | receipt chain, report, Studio manifest, tests, resource audit, and commit completed |

## Current mechanism prediction

During the physical closed interval, the recorder's normalized command is
about 1.07% while measured position remains about 4.39%; in mapped joint units,
the medians are -0.15401 and -0.09017 radians. The baseline simulator closes
about 3.12 degrees past that loaded mapped position. Its fixed rubber geom is centered
at local z -0.1205 m, while the rigid fixed-jaw box that actually carries the
C2 load is centered at -0.0727 m. The predicted repair must therefore restore
both a blocked/load-bearing aperture and two-sided rubber contact; friction
alone or an unloaded actuator-zero shift is insufficient.

## Non-negotiable invariants

- C2 action SHA-256 remains
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
- No IK, action offset, action clipping, corrective suffix, or assistance.
- Every follow-on family was frozen and source-bound before execution; no
  campaign expanded its own grid after results were visible.
- Existing task/evaluator thresholds and 1% trace guards remain binding.
- The retained video does not create fresh holdout, calibrated force, or robot
  authority.

## Stop rule

The second stop lane fired. The best loaded-aperture model is within 0.03
degrees and the best retention model reaches source frame 399 versus the
release onset at 401, but neither preserves transport and slip. Box and capsule
rigid pads both fail. The residual is the real cap's force-dependent deformation
and distributed contact patch versus jaw force. That cannot be recovered from
the retained overhead video and cached 5 Hz current stream. The result is a
terminal negative, not a promoted repair.
