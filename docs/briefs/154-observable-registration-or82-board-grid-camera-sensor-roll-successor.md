# OR82 board-grid camera sensor-roll successor

OR82 added exactly one optical-axis sensor-roll parameter to OR81's board-only camera objective. Board reprojection improves from `22.51 px` to `8.80 px` RMS, confirming roll was a real missing camera degree of freedom, but the unchanged geometric gates still fail and the optimizer hits the FOV bound.

Whole-frame static edge F1 falls from OR81's `0.386835` to `0.326581`. A subsequent evaluator-only region check explains the reversal: board-region edge F1 improves from roughly `0.57` to `0.63` across every development frame, while outside-board edge F1 falls from roughly `0.40` to `0.23`.

The camera improvement is therefore localized and real. The remaining conflict is between the board-anchored camera and the scene's robot/world composition. More camera fitting would ask one projection to compensate for board-to-robot registration error. OR83 must formalize that region attribution before any geometry fit.
