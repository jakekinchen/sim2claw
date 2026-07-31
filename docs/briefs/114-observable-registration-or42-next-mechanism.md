# Brief 114 — OR42 evidence-safe next mechanism

## Decision

Close the retained-video directional-play lane. Do not run another pawn replay
or fit another simulator contact mechanism from OR40/OR41. The next admissible
step is a deliberately observed, no-object load-side gripper calibration
packet. Software compilation and static preflight may proceed without hardware
authority; physical capture remains separately gated.

## Evidence reconciliation

The owner-requested ChatGPT Pro research thread
`https://chatgpt.com/c/6a6c7f5b-bff8-83ea-a324-f821c2964104`
inspected repository commit
`43d2a513ba5c1255cf6eedda288bc0f449891192`. Its memo rejected metric aperture
and camera calibration from the retained task RGB, recommended exactly one
scale-free directional-play estimand, and specified a fail-closed boundary:
after insufficient opening/closing excitation, lag confounding, a zero/bound
candidate, or negative no-refit validation, execute no replay. Its minimal
honest next observation was a no-object bidirectional sweep with repeated
reversals, RealSense sensor/exposure timestamps, and load-side metric aperture
sensing or depth.

Repository evidence now satisfies that failure branch:

- OR40 accepts `25` task-clip pad frames but selects `0.0°` play, has no closing
  validation frames, validates at `2.281 px`, and has `0.986` play/lag
  correlation.
- OR41 tests the already-retained full-range cycle before requesting new data.
  Its wall-facing view admits only `4/41` pad frames, again selects zero play,
  and produces `54.737 px` no-refit error on OR40.
- Both cards execute zero simulator replays and preserve all prior natural
  dynamics negatives.

The second live GPT Pro follow-up could not be submitted after the OR41 push
because no in-app or default browser connection remained available. This does
not weaken the decision: the completed memo's preregistered failure branch
directly covers both immutable results, and repository evidence remains the
authority.

## OR43 capture contract

Compile one bounded packet with:

1. The jaw clear of the board, pawn, cable, and every exclusion volume.
2. At least three repeated opening/closing reversals through the shared
   `5°–30°` task aperture interval, plus one wider diagnostic cycle.
3. Immutable requested, sent, and measured gripper traces with host timestamps.
4. D405 RGB and metric depth when the device exposes it, retaining device
   timestamp, exposure, arrival, and frame-counter metadata.
5. A load-side metric aperture observation independent of the servo encoder.
   Preferred order:
   - D405 metric stereo depth with validated scale and two visible jaw markers;
   - a fixed camera plus a metric fiducial rigidly associated with each jaw;
   - a secondary load-side encoder or displacement gauge.
6. A static visibility/depth preview and fail-closed association audit before
   torque is enabled.
7. Zero pawn contact, zero task attempt, zero task outcome, and zero simulator
   replay.

The packet passes only if both jaw surfaces have metric observations on at
least five frames per direction in both fit and validation partitions; device
association is bounded independently of outcome; play and lag are full-rank
and conditioned; the no-refit validation improvement is at least `30%`; and
the fitted value remains away from its declared bound.

## Successor boundary

OR43 may implement the capture, metadata, depth/marker, partition, and static
preflight surfaces now. It may not move hardware until a current role packet
explicitly grants calibration motion. A successful OR43 mapping would admit a
separate prospectively frozen one-replay successor based on OR36S. A failed
OR43 mapping closes directional play and requires a different independently
measured contact/load mechanism; it does not authorize more outcome-driven
simulation search.
