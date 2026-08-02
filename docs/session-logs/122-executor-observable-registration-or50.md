# OR50 executor session

Date: 2026-08-02

OR50 refined only the OR49 fixed-pad longitudinal coordinate over 25 frozen
positions from `-113.12` through `-112.88 mm`. The raw 531-row measured-state
trajectory and every other simulator parameter remained unchanged. Candidate
`-112.98 mm` passes the unchanged natural-dynamics task evaluator and then
reproduces with an identical result digest in a separate no-refit run.

The selected result reaches D2 with `4.260 mm` final planar error, `0.0039 deg`
final tilt, effectively zero height error, stationary other pieces, and all
seven terminal gates passing. No object pose was injected, no latch or support
projection was used, and no action/state row was repaired.

The result does not close the event-shape divergence. Contact begins at sample
`229`, but motion begins at `244` and sustained support loss at `243`, three and
four samples early relative to the frozen physical intervals. No bilateral
named-jaw contact is detected, and sample-260 tilt is `26.115 deg` before the
pawn later settles upright. Therefore this is a successful, physics-driven,
outcome-informed exact-episode diagnostic—not canonical geometry, held-out
validation, approved mapping, simulator promotion, or transfer evidence.

Focused verification: `2 passed`.
