# OR89 expanded-development global monotone response fit

OR89 tests whether one shared, monotone, two-slope camera-response curve can retain the renderer's structural edges while closing the global photometric gap. The input knot is fixed at intensity `128`; the only fitted values are one bias, one low-intensity slope, and one high-intensity slope, applied identically to all BGR channels, pixels, frames, phases, and seven expanded-development episodes.

The OR82 camera, OR84 workcell transform, renderer, timeline, state traces, actions, and physics remain fixed. Selection requires all six original temporal visual gates and a stricter pooled edge F1 of at least `0.42`. Fresh-validation positions `8-9` and final-heldout positions `10-11` may not be decoded or scored.
