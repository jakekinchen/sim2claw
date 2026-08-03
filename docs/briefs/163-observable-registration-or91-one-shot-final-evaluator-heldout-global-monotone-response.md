# OR91 one-shot final evaluator-heldout global monotone response

OR91 is the single final evaluation of the frozen OR82 camera, OR84 workcell transform, and OR89 global monotone response on OR88 positions `10-11`. OR90 passed all fresh-validation gates, so this card may decode those two final physical videos exactly once.

The evaluator renders both complete state timelines at `5 Hz`, applies bias `24`, low-intensity slope `0.85`, high-intensity slope `0.25`, and knot `128` identically to every BGR sample, then applies the unchanged six gates. It permits no fit, selection, threshold change, retry, alternate candidate, geometry/timing/state/action/physics change, or development/validation read.

A full pass establishes only held-out renderer-native temporal visual similarity in the requested numeric band. It does not establish physics fidelity, causal event parity, physical transfer, task transfer, or simulator promotion.
