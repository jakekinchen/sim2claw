# OR90 reject-only fresh-validation global monotone response

OR90 evaluates the exact OR82 camera, OR84 workcell transform, and OR89 global monotone response on the two fresh-validation episodes frozen by OR88. No parameter, candidate, threshold, geometry, timing, state, action, or physics value may be fitted or selected on these pixels.

The evaluator renders both complete state timelines at `5 Hz`, applies bias `24`, low-intensity slope `0.85`, high-intensity slope `0.25`, and fixed input knot `128` identically to every BGR sample, then applies the unchanged six visual gates with the original validation edge minimum `0.4`.

Any failed metric or integrity gate rejects the candidate. Final evaluator-heldout positions `10-11` remain sealed unless OR90 passes in full.
