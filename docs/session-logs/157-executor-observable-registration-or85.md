# Executor session 157: OR85

- Started from admitted active card `OR85`; profile and executor context passed.
- Reused OR80's timeline, metrics, acceptance gates, exact `423` samples, and full-source-mesh renderer.
- Held the OR82 camera and OR84 three-parameter workcell transform byte-stable; no parameter was refit.
- All six integrity gates pass, including byte-identical reproduction of the bound OR84 opening frame.
- Edge F1 rises to `0.426255` and passes. Mean `0.739669`, p10 `0.720109`, motion `0.688841`, phase, and per-episode similarity gates fail.
- A subsequent read-only `35`-point scalar gain/bias headroom probe found a gate-preserving development candidate near `(0.55, 48)`; this probe is recorded as non-admitted diagnostic evidence.
- Resource accounting: `423` physical comparisons and exact native renders, four videos, zero fits during OR85, zero validation/heldout reads, no hardware, and no paid compute.
- Reviewer decision: keep validation closed and freeze a shared two-parameter camera-response fit.
