# Brief 013: Tag-anchored scale and action-frozen fidelity

Decision: `TERMINAL_NEGATIVE_CONTACT_RETENTION_AND_TRANSPORT_UNDERIDENTIFIED`

## Goal

Execute the approved publication-safe hardware-free fidelity plan while
holding every teleoperation action byte-identical. First determine whether the
visible AprilTags and real 3DGS source video can discriminate the registered
355.6 mm board from the 301.3 mm train-trace fit.

## Accepted result

The source-bound evaluator detected tag36h11 id 0 in `frame-000001.jpg`, fit
the visible 9-by-9 playing grid, and back-projected it through the fixed
IMG_5349 SfM intrinsics. Conditioned on the source PDF's nominal 80 mm detected
tag border and a declared 16--25 mm board-above-tag-plane sensitivity, the mean
playing side is 356.2--361.5 mm. The all-edge envelope is 336.5--373.6 mm and
the roughly 19 mm opposite-edge disagreement is explicitly retained.

The registered 355.6 mm hypothesis needs a 0.2--1.6% nominal tag rescale and
lies inside the conservative edge envelope. The 301.3 mm event-fit hypothesis
needs a 15.4--16.7% shrink and falls below the envelope. This admits the narrow
conclusion that 355.6 mm is physically plausible and 301.3 mm is a confounded
trace-fit compensation under the declared nominal-print model.

## Non-claims

The printed tag was not measured after printing. The plane-height upper bound
is a sensitivity endpoint. The boundary fit has perspective/systematic
disagreement. The monocular 3DGS binds scene identity but is not a ruler.
Therefore physical metric scale, physical calibration, simulator parameter
promotion, policy promotion, and physical transfer all remain false.

## Executed mechanism result

The replay audit found a one-sample semantic error: legacy code applied row 0,
integrated one nominal interval, and then compared that state with the physical
row-0 sample. Timestamp-aligned record-then-ZOH replay plus a grouped-CV 110 ms
simulator-side delay reduced joint RMS from 2.563 to 1.461 degrees and EE RMS
from 20.843 to 16.417 mm. A constrained lift/elbow servo-deadband model selected
2 degrees in every fold, reaching 1.296 degrees joint RMS, 12.936 mm EE RMS,
69.6% lift flat-response reproduction, and 58.9% elbow reproduction.

All variants used the same contiguous float64 action arrays with identical
SHA-256 values, ordering, and no clipping, IK, offsets, or assistance.

## Consequence and stopping decision

Timing plus deadband improves action-frozen consequence from 9/11 to 11/11
contact and 0/11 to 2/11 lift, but remains 0/11 strict success. The existing
frozen rubber-tip ensemble spans only 2--3 lifts and always 0 strict successes.
Because the video evidence provides appearance intervals rather than admitted
contact/retention/transport labels, no contact variant is selectable.

The publication gate therefore accepts the timing and actuator model as
diagnostics, rules reset semantics out as a primary gap, rejects simulator
composite promotion, keeps training disabled, and identifies contact geometry,
retention/slip, and transport observability as the remaining underidentified
mechanisms.
