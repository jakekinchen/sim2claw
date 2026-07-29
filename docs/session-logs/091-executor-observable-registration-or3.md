# Executor log 091 — Observable registration OR3

Date: `2026-07-29`

## Outcome

OR3 accepts a timestamp-bound `ObservableEpisode.v2-min` supplement for the
retained D1-to-D2 physical source. All 531 samples are associated to admitted
camera callbacks rather than the recorder-start video offset, which would have
misaligned the browser videos by their excluded warm-up interval.

The frozen visual schedule contains 49 samples. Two ordered review passes and
bidirectional optical flow accept 23 fixed-jaw, 23 moving-jaw, and 10
selected-pawn-crown observations. The pawn is definitely separate through
sample 224. Candidate contact is bounded to samples `228–232`
(`11.405–11.605 s`), with definite enclosure by 232. Definite carried motion is
visible from samples `260–390`, release is bounded to `400–407`, and the
existing metric endpoint evidence confirms the pawn upright at D2.

## Evidence

- schedule v1 negative preserved at freeze commit `30fe1cd`;
- schedule v2 freeze commit: `1413e0a`;
- observation freeze commit: `5f04dc5`;
- observation receipt SHA-256:
  `e8e76bf8f9d1f44789c647e967a313b57893770edb1d3570f3b4974cb4b94d1a`;
- artifact SHA-256:
  `0913aee74cfc08a491a6e17184fb9ecfbf7265208dcb354801ed8010d7c059b2`.

## Boundary

The two passes are the same Codex system in opposite review order, not two
independent humans. Wrist depth, metric object pose, force, instrumented
contact, exposure timing, and exposure synchronization remain unavailable.
This proves an observable physical action-to-physical-outcome sequence; it does
not yet prove the same action trajectory produces the matching simulator
outcome.
