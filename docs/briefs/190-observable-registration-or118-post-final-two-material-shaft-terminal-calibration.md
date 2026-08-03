# OR118: two-material shaft/terminal calibration

OR118 evaluates the preregistered `4x4` development material grid on the exact
OR116 geometry. The selected edge-eligible pair is shaft `[138,136,132]` and
terminal `[55,48,43]`. It improves full-frame similarity by `0.000543` on
development and `0.000584` on validation without refit, while retaining about
`0.0445` outside-board and `0.734` local edge gains.

The card validates only one retained same-episode static-object calibration.
The frozen pair must survive all timeline frames before it can contribute to a
broader same-video assessment.
