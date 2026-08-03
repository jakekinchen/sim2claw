# OR84 board-anchored workcell SE2 static development fit

OR84 tested one shared renderer-native planar rigid transform for the workcell group while holding the OR82 board camera, board, pawns, fiducial sheet, state, actions, timing, appearance, and physics fixed.

The selected vector is yaw `35.819°`, world-x translation `-0.3585 m`, and world-y translation `-0.5415 m`. All `14/14` gates pass under four exact full-source-mesh renders: whole-frame edge F1 rises `0.326581→0.452907`, outside-board edge F1 rises `0.134933→0.371255`, and every episode improves by at least `0.226`. Board F1 remains `0.542393`, and mean linear similarity is `0.754979`.

This is a development-only static scene-registration advance. OR85 must freeze the vector and evaluate all `423` development timeline samples without refit before validation can open.
