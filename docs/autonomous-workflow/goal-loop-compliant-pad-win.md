# Goal loop: compliant-pad evaluator win

Status: `ACTIVE — B2-02 COMPLETE; B2-02A IN PROGRESS`

Authority:
[`configs/sail/grasp_retention_normal_compliance_v1.json`](../../configs/sail/grasp_retention_normal_compliance_v1.json)

This loop continues B1's exact terminal negative. It may claim a win only when
the frozen evaluator admits a compliant-pad candidate under the byte-identical
C2 action array and the candidate survives the prescribed regression gates.

## Milestones

| Milestone | State | Exit evidence |
| --- | --- | --- |
| B2-00 | complete | hypothesis, source identities, 18 candidates, original gates, budgets, and stop rules frozen |
| B2-01 | complete | compliant segment bodies/joints implemented; 20 focused tests and 254 legacy subtests pass |
| B2-02 | complete, terminal negative | all 18 C2 actions matched; zero passes; every candidate failed retention, aperture, and transport |
| B2-02A | in progress | edge-contact diagnosis frozen into a separate 18-candidate cap-footprint/compliance family before execution |
| B2-03 | pending | at most four C2 winners evaluated on the three declared sentinels without task regression |
| B2-04 | pending | at most one frozen composite evaluated on all eleven episodes and separately promoted or rejected |
| B2-05 | pending | receipts, report, Studio evidence, full tests, resource audit, and commit complete |

## Immutable win vector

- C2 action SHA-256:
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
- Bilateral contact loss is absent before source index 401.
- Absolute loaded-aperture bias is no more than 0.5 degrees.
- C2 lift-and-transport remains true.
- Post-grasp slip improves by at least 10% against the bound V3 witness.
- Sentinel task counts do not regress; all trace/collateral gates remain
  evaluator-owned and unchanged.

## Stop conditions

Reject action drift, evaluator drift, aperture-only fits, decorative compliant
geometries, and post-result family expansion. Training and robot authority stay
closed even if this simulator mechanism wins.

## B2-02 result and next causal branch

The first compliant family did not produce a qualified win. Its strongest
candidate lifted the pawn but lost the moving side at source frame 316. At
loss, fixed-pad contacts reached about 6.45 mm along a modeled 6.5 mm
half-width; the preceding moving load pair reached about 6.30 mm along its
6.5 mm half-width. This edge loading predicts peel-off even with normal
compliance. B2-02A therefore tests the distinct missing-footprint hypothesis in
a separately frozen campaign bound to the complete B2-02 receipt.
