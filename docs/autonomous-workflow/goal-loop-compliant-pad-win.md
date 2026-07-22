# Goal loop: compliant-pad evaluator win

Status: `ACTIVE — B2-02B COMPLETE; B2-02C IN PROGRESS`

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
| B2-02A | complete, terminal negative | all 18 widened free-surface candidates matched actions; zero passed; one lifted without retained bilateral load |
| B2-02B | complete, terminal negative | one candidate lifted with 83.3% rubber load-pair participation but lost at frame 328; zero complete passes |
| B2-02C | in progress | caps anchored directly to fixed box6 and moving box3 with asymmetric core-matched footprints |
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

B2-02A showed that footprint without backing is insufficient: 17/18 candidates
did not lift, and the lone lift had no qualified post-lift load pair. B2-02B
now preserves the physical construction's rigid plastic core while making the
continuous cap large enough to enclose it. A new evaluator diagnostic requires
at least 90% of observed post-lift load-pair sides to be rubber geoms, preventing
the core from earning a decorative-pad pass.

B2-02B retained the plastic backing but still placed the fixed cap by offsetting
the historical box5 anchor. Its best result lifted, but 1/6 observed load-pair
sides bypassed rubber and contact failed at frame 328. B2-02C removes that
surrogate: the fixed cap is generated directly from box6 and the moving cap
from box3, with separate coverage and width scales matching their actual distal
cores.
