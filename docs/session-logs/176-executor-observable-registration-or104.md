# Executor session 176: OR104

- Started from admitted active card `OR104`; the agent profile and executor
  context passed before the write turn.
- Froze 25 shared shoulder-lift gain/offset pairs, three deterministic samples
  per episode, seven development episodes, and four conditionally opened
  no-refit validation episodes.
- Rendered all 525 exact full-mesh development candidates. The identity pair
  reproduced the bound OR95 sampled metrics with maximum absolute error `0.0`.
- Selected gain `0.8`, offset `-5 degrees`. Outside-board edge F1 improved
  `0.347274 -> 0.358729` (`+0.011455`), below the frozen `+0.02` gate; `12/21`
  samples gained at least `0.01`, below the required `14/21`.
- Board-edge regression (`-0.005502`) and full-frame change (`+0.001051`) were
  within bounds, but the two primary development gates failed. Validation was
  therefore not decoded or rendered.
- All 11 integrity gates passed. No pixel warp/composite, simulator replay,
  action/state/dynamics/timing/contact mutation, hardware, or paid compute was
  used. This is a legitimate terminal negative, not kinematic or physics proof.
- Visual review of the frozen montage shows a more basic appearance residual:
  the scene manifest renders every robot mesh neutral gray, while the physical
  robots contain distinct light structural and dark servo materials, plus
  exogenous cables and operator hands. OR105 audits that material-semantics
  collapse before any new renderer parameter is frozen.
