# OR81 development board-grid camera geometry fit

OR81 replaced the background-heavy OR73 objective with four frozen physical playing-surface quadrilaterals and the scene's exact board corners. It fit one shared seven-parameter look-at camera by board reprojection only, then rendered four full-mesh development opening frames.

The result is a useful terminal negative. Static edge F1 improves `0.291565→0.386835`, and every static visual guard passes, but board reprojection remains `22.51 px` RMS / `29.55 px` max against `4/8 px` gates. The optimizer does not converge and hits both elevation and FOV bounds.

Visual review shows the board and robot now occupy the correct broad sides of the image, confirming the geometric mechanism, while the board orientation cannot be matched. The frozen look-at model has target, azimuth, elevation, distance, and FOV but no optical-axis sensor roll. The smallest legitimate successor adds that one camera degree of freedom; no appearance, timing, state, validation, or held-out expansion is justified.
