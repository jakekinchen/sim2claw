# Executor session 167: OR95

- Started from admitted active card `OR95`; agent profile and executor context passed.
- Rendered all `1,210` fixed `5 Hz` states across all eleven retained episodes into eleven simulator videos with the exact frozen OR94 left/right base transforms; no fit, selection, threshold change, retry, or simulator replay occurred.
- Full-frame mean `0.836995`, p10 `0.822432`, motion mean `0.791643`, every phase, and whole-edge F1 `0.455012` pass.
- The structure-aware same-video gates reject the candidate: board mean is `0.571366 < 0.60`, outside-board mean is `0.359818 < 0.60`, outside p10 is `0.324553 < 0.45`, and no episode reaches outside-board mean `0.50`.
- All episode outside-board means cluster tightly in `0.347239-0.370328`, showing a persistent cross-episode residual rather than an isolated timeline failure.
- Reviewer decision: preserve the complete temporal negative and attribute the remaining robot/scene-content residual. All corpus pixels are open; no held-out, physics, transfer, or promotion claim is available.
