# OR83 board-anchored scene-composition residual attribution

OR83 formally reproduced the qualitative OR82 failure without rendering, fitting, replaying, or creating candidate pixels. Across all four development opening frames, the sensor-roll camera improves board-plus-margin edge F1 while regressing outside-board edge F1.

The mean board score rises `0.483231→0.551833`, while the mean outside-board score falls `0.302626→0.134933`. Both directions hold independently in every episode. This satisfies the frozen decision rule for a board-to-robot/world registration residual.

OR84 may therefore freeze one low-dimensional renderer-native workcell registration family around the board. It may not reopen camera, appearance, timing, state, physics, validation, or evaluator-heldout selection.
