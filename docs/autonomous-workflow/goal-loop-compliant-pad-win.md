# Goal loop: compliant-pad evaluator win

Status: `ACTIVE — B2-02F COMPLETE; B2-02G IN PROGRESS`

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
| B2-02C | complete, terminal negative | direct 2x cap preserved C2 transport and 100% rubber load path but lost at frame 299 with 3.01 degree overclosure |
| B2-02D | complete, terminal negative | force-friction cross exposed contact-trigger chatter; no full pass |
| B2-02E | complete, terminal negative | latch earns retained transport through release at force 0.04 but fails aperture, slip, and rubber-path gates |
| B2-02F | complete, terminal negative | long wrap earns retained transport to frame 523 but overlapping rigid collision still bypasses rubber |
| B2-02G | in progress | rubber collision skin encloses collision-disabled core primitives; narrow torque cross frozen |
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

B2-02C proves that direct cap anchoring can preserve the task consequence: the
rigid 2x cap lifts and transports C2 with all observed post-lift load-pair sides
on rubber. Its remaining failures are early loss (frame 299), 3.01 degrees of
overclosure, and only 4.7% slip improvement. B2-02D crosses a contact-conditioned
force ceiling with bounded rubber friction on exactly that geometry, leaving
source actions and the gripper command unchanged.

B2-02D separates two sides of the target: force 0.02 / friction 3.5 passes
aperture, slip, and rubber-dominance gates but loses contact at frame 280 and
does not transport; force 0.05 / friction 2.5 retains past release to frame 407
but swings to a 5.58-degree aperture bias and mostly rigid loading. The current
force ceiling toggles with instantaneous contact, creating a discontinuity.
B2-02E latches only the actuator force ceiling after sustained bilateral
contact and releases it on the recorded opening command. It never overwrites
the action or simulator control target.

B2-02E validates the non-chattering actuator transfer: force 0.04 with a 20 ms
dwell retains and transports the pawn through release. It is not a certified
win because the loaded aperture is 6.13 degrees too open, slip worsens, and 92
of 93 post-lift load pairs use fixed box4 instead of rubber. Force 0.02 passes
aperture and slip with 97.7% rubber participation but loses at frame 280.
B2-02F covers the newly observed fixed box4 bypass with one continuous wrap
spanning the distal box4--box6 stack and searches only the narrow force range
around the aperture-valid branch.

B2-02F shows that the long wrap can retain and transport through the full replay
(force 0.024, contact through frame 523), but every post-lift pair still mixes
fixed plastic with moving rubber. The wrap geometrically encloses box4--box6;
the bypass occurs because both the soft skin and its overlapping rigid core are
collision-enabled. B2-02G keeps the skin rigidly attached to the jaw body but
disables the enclosed primitive collision geoms. This represents a backed
rubber collision surface without allowing the pawn to tunnel into a second
exposed contact layer.
