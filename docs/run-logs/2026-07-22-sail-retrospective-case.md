# SAIL Retired-Workcell Retrospective Case Run Log

Date: 2026-07-22

Milestone: P1-12

The development-informed retrospective case compiles 12 historical
intervention/candidate/verdict triads without relabeling any row as prospective
or fresh held-out. Five findings expose the load-bias boundary, improved RMS
with a lift reversal, a bounded timestep sensitivity win, friction retention/
endpoint gains with unchanged task counts and an EE guard failure, and union
coverage that no single simulator achieves.

Frozen influence discovery selects `intervention:fidelity-rms-closeout` and
`intervention:load-bias-boundary` at 1.0 precision/recall. Both sparse graph
edits bind the original intervention, candidate, verdict, path, and SHA-256.
Chronological, seeded shuffled-order, no-revisit, full-batch, and SAIL
reconstructions are preserved. The fixture comparison recomputes 2/8 decisions
for SAIL versus full batch with negligible score loss; it is explicitly not a
physical-parameter fit.

The current certificate is `TW-REPLAY`. G0/G1 pass; G2 is not evaluable because
physical contact state/force and metric object trajectories are absent; G3/G4
are also not evaluable. TW-DATA, training, and policy selection stay closed.

Final identities: config
`5611100e6f3ef940afa3b4c90f21b872ff995266449d011a1f2ac04628dbc087`;
case `df0985e767d7d7a9501642f0149aad890e83ba7f53f38a82469acaa3972ed7d0`;
certificate `726966d4275c6133420f9b79a2768a1e9455f0dc008dde4762318fd7d10fafad`;
certificate digest
`86799523c2b93aaa8cc08871f5d75f2ea5dedc2299f75d868cb2dbfcf54e4a3f`;
history figure
`8cf592ba93646a415924155c47255f0cecd98e5a1921dbf07bf283df3bb3f1a9`;
comparison figure
`61bcf969931a629c888dd46736273bd283e5cd00febbc6b4e6753e34506f5be7`;
receipt `e455ef16e16cf8d9043caed8c8b01cd9454b609c722ec607c47160f71baa0e95`;
receipt digest
`cb26464d26a7ccb939e538f84d09082ad9238e23a56bfa2438b38815dcb27ff4`.

Focused validation is 26/26, SAIL validation is 132/132, the repaired Learning
Factory acceptance test is 1/1, and the final repository gate is 736 tests plus
328 subtests with three expected skips. The canonical project contract now
binds the final P1-12 `project_state.json` hash. No provider, hardware,
training, policy, or physical authority was used.
