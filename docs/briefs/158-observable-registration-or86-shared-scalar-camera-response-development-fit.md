# OR86 shared scalar camera-response development fit

OR86 evaluated the frozen `7×5` grid of a single gain and bias applied identically to every BGR channel, pixel, frame, phase, and development episode. It opened no spatial, regional, per-channel, or per-frame appearance parameter.

Eight of `35` candidates pass all six unchanged temporal gates. The frozen selection rule chooses gain `0.55`, bias `48`: mean similarity `0.842264`, p10 `0.823387`, motion-union similarity `0.795477`, and edge F1 `0.403525`. Every episode mean and every phase mean also pass.

This reaches the requested numeric band only on development. OR87 is a reject-only render of the three frozen validation episodes with the camera, workcell transform, response, metrics, and gates unchanged. Evaluator-heldout remains sealed.
