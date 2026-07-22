# Goal loop: compliant-pad evaluator win

Status: `PAUSED — B2-02W COMPLETE; B2-02X INCOMPLETE AT 17/18 AND SUPERSEDED BY LIVE SAIL OPERATOR`

The open-ended family search was paused by the user before B2-02X produced a
complete screen receipt. Its 17 artifacts remain preserved as work-in-progress
diagnostics and are excluded from completed-campaign counts. Do not restart
this loop unless a later authority surface explicitly reopens it.

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
| B2-02G | complete, terminal negative | 100% rubber aperture/slip frontier reaches frame 339; moving contact exits at two footprint edges |
| B2-02H | complete, terminal negative | overhang earns rubber-only retained transport but rigid-skin energy makes aperture/slip invalid |
| B2-02I | complete, terminal negative | high-stiffness 2.25 ms pads unstable; stable frontier loses at frame 329 |
| B2-02J | complete, terminal negative | stable 0.5 ms pad retains through release with valid aperture/slip but misses transport |
| B2-02K | complete, terminal negative | coverage-axis offsets change the sleeve footprint but not the vertical pawn contact point |
| B2-02L | complete, terminal negative | vertical offsets preserve the same pawn-relative manifold; force bifurcation dominates |
| B2-02M | complete, terminal negative | ramp removes most launches; best valid branch still makes 688 target transitions and misses transport |
| B2-02N | complete, terminal negative | phase gate cuts chatter to 5 transitions and exposes loss at source 385 |
| B2-02O | complete, terminal negative | constant force eliminates chatter but no aperture-valid retained transport exists |
| B2-02P | complete, terminal negative | unilateral range fixes 3x overtravel; flat boxes still lose before transport |
| B2-02Q | complete, terminal negative | only 3 mm capsule contacts; transport branch loses at 318 with aperture mismatch |
| B2-02R | complete, terminal negative | compiled normal offsets are dynamically absorbed by slide-mounted pads |
| B2-02S | complete, terminal negative | stiction changes regimes; transport branches still lose early with aperture mismatch |
| B2-02T | complete, terminal negative | bounded flexure finds a retained/slip branch, but no valid task transport; 4 mm branch never releases and is rejected for 0.310 m rise |
| B2-02U | complete, diagnostic negative | near-exact measured state has 1.1 mm EE RMS but only fixed-pad C2 contact, zero bilateral span, and 6.1 mm rise |
| B2-02V | complete, terminal negative | jaw zero changes contact regimes; best aperture/slip branch loses at 377 and reaches 1.8% transport progress |
| B2-02W | complete, terminal negative | timing is bifurcated; 120 ms is aperture/slip valid but loses at 385, while 100 ms launches to 0.318 m |
| B2-02X | paused, incomplete | 17 of 18 moderate sliding/torsional release artifacts preserved; no complete receipt |
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

B2-02G removes core bypass successfully. Its force 0.022 / fixed coverage 1.1
candidate passes loaded-aperture bias (-0.24 degrees), slip reduction (24.9%),
lift, and 100% rubber-load gates, but loses at frame 339 before transport. The
last stable moving contact lies at 5.89 mm of a 6 mm coverage half-length and
4.99 mm of a 5 mm width half-span. B2-02H expands only those moving-cap
dimensions while retaining the now-valid fixed skin and torque branch.

B2-02H prevents the moving-edge exit. Force 0.024, coverage 0.36, and width
1.33 retain and transport with 100% rubber participation through frame 418,
but loaded aperture is +7.39 degrees and maximum slip is physically unstable.
This is the remaining rigid-skin approximation. B2-02I keeps that corrected
footprint and crosses 0.25--1 mm normal travel with 3--12 kN/m springs and
near-critical damping at both the aperture-valid and retained-transport force
frontiers.

B2-02I rejects the high-stiffness branch: MuJoCo reports bad qpos/qvel/qacc in
multiple 12 kN/m cases, and the stable 3 kN/m / 0.25 mm frontier loses at frame
329 without transport. B2-02J records simulator warning counters in every
episode and makes zero unstable warnings an explicit anchor gate. It reduces
the replay step from 2.25 ms to 0.5--1.5 ms and uses 0.3--1 kN/m springs whose
natural timescale is resolvable at those steps.

B2-02J isolates a one-gate frontier: its 0.5 ms, 0.3 kN/m baseline has zero
bad-state warnings, 100% rubber load pairs, contact loss at source index 402,
-0.262 degrees loaded-aperture bias, and 59.3% less slip, but it misses the
transport predicate. The pawn first crosses the 40 mm lift plane at source
index 280 and drops back below it at 289 while bilateral contact continues to
402. Its first qualified contact is 39.1 mm above the pawn center. B2-02K tests
whether placing the modeled rubber band 2--20 mm farther along the fingertip
lowers contact toward the historical ~33 mm transport region. It crosses only
the local 0.0215--0.0225 contact-force neighborhood; actions, controls,
compliance, timestep, collision path, and acceptance stay frozen.

B2-02K proves that the assumed axis was wrong: moving the sleeve 2--20 mm
along its coverage axis leaves the contact height and outcome byte-for-byte
unchanged while the sleeve continues to overlap the pawn. A 0.0215 force
branch improves aperture bias to +0.075 degrees, retains contact to source 407,
and extends the lift-plane window by three source frames, but maximum transport
progress while lifted remains only 5.8%. B2-02L records each jaw geom's
world-frame basis at contact so the next frozen family can shift the rubber
along the actual vertical width axis with the correct sign per jaw.

The B2-02L baseline replay reports world-Z projections of +0.809 for fixed-jaw
local width and -0.809 for moving-jaw local width. Therefore matched downward
motion is fixed negative and moving positive. The frozen family crosses
1--20 mm symmetric shifts around the aperture-valid 0.0215 force point, with a
narrow 0.02125/0.02175 force check at 3, 5, and 8 mm. All other parameters and
all acceptance gates remain fixed.

B2-02L confirms that translating the wide collision sleeves does not select a
lower pawn-relative contact manifold. More importantly, force 0.02125 produces
a 0.314 m numerical launch and transport while force 0.0215 produces a normal
0.057 m rise. The code changes actuator force range discontinuously from 100%
to about 2.1% on any jaw/pawn contact and back on separation. B2-02M replaces
that optional switch with a bounded linear ramp over 2.5--200 ms. It also adds
a 0.1 m maximum-rise rejection; this tightens, rather than relaxes, the frozen
C2 gates and prevents an energy-injection artifact from being promoted.

B2-02M removes the launch for most candidates and exposes a valid one-gate
frontier at force 0.0215 / ramp 20 ms: contact loss 406, +0.496 degrees aperture
bias, 14.2% slip improvement, and 12.3% transport progress, but no transport
pass. The episode still makes 688 force-target transitions. Those transitions
start when the open jaw brushes non-target pawns. B2-02N optionally arms the
load limit only after the immutable source gripper command crosses a frozen
closure threshold. It crosses threshold, latch dwell, and ramp duration without
changing the action or control arrays, and retains the excessive-energy gate.

B2-02N reduces force-target transitions from 688 to five at threshold 0 rad and
short latch dwell, with valid aperture and improved slip. Once chatter is
removed, however, contact ends at source 385 and transport progress is zero.
This demonstrates that the apparent late retention in the hybrid model was an
energy artifact. B2-02O removes the contact trigger entirely: the actuator has
one constant force range throughout replay, as a fixed motor current/torque
limit would. The frozen 0.04--0.30 absolute multiplier sweep is centered on
0.0645, equal to the prior 3.0 nominal multiplier times the 0.0215 loaded
multiplier, and crosses bounded joint damping only.

B2-02O confirms zero force-target transitions across the family. Force 0.10
retains to release source 401 but over-closes by 3.31 degrees and does not
transport; force 0.08 / damping 2.0 transports but loses contact at 355 and
over-closes by 1.59 degrees. Inspection of the compliant-pad trace reveals that
the nominal 1 mm pads can extend roughly 3 mm because their slide ranges are
symmetric and softly limited. B2-02P makes the fixed pad compress only in the
negative local-normal direction and the moving pad only in the positive
direction, each from its undeformed zero. It gives the joint limit an explicit
0.5--4 ms response and crosses 0.5--1 mm travel, 0.2--0.5 kN/m stiffness, and
the clean constant-force frontier.

B2-02P reduces worst recorded pad displacement from about 2.99 mm to
0.8--1.4 mm. Its aperture-valid 0.5 mm / force 0.07 candidate still loses at
source 324 and never transports. The physical rubber band is rounded and
conformal, whereas the current sleeve remains a box with face/edge transitions.
B2-02Q uses the existing deterministic capsule path with 2--6 mm radii. It
crosses constant force 0.06--0.08 and compares unilateral 0.5 mm mounting
compliance with rigidly mounted rounded rubber, retaining all tightened gates.

B2-02Q finds no rounded-surface composite: radius 3 mm / force 0.06 transports
but loses bilateral contact at source 318 and over-closes by 1.59 degrees; other
radii usually miss opposing contact. B2-02R models the reported rubber-band
thickness directly by translating both opposing surfaces into the grasp gap.
At first qualified contact, fixed local +X aligns with its jaw-to-pawn normal
while moving local +X is opposed, so matched inward motion is fixed positive
and moving negative. The frozen family crosses 0.25--4 mm paired offsets and a
0.06--0.08 constant-force neighborhood on the aperture-valid unilateral pad.

B2-02R changes compiled geom-local normal positions by 0.25--4 mm but produces
identical action-frozen trajectories at each force, so slide-mounted pad motion
absorbs the offset and the lever is non-identifying. B2-02S targets rubber
stiction directly. The current model uses zero MuJoCo no-slip iterations. The
frozen family crosses 1--50 no-slip passes, friction improvement ratios,
Newton/CG/PGS solvers, and elliptic/pyramidal cones while holding geometry,
constant motor force, unilateral travel, actions, controls, and gates fixed.

B2-02S does not solve the gap. Its pyramidal 5-iteration branch transports but
loses contact at source 322 and over-closes by 3.22 degrees; high-impratio
elliptic contact is aperture-valid but loses at 301. B2-02T interprets the
earlier ~3 mm motion as effective wrapped-band flexure rather than permitting a
soft 1 mm joint to overrun. It explicitly freezes unilateral travel at
1.5--4 mm and crosses constant force 0.07--0.12. Thus any larger pad motion is
bounded, recorded, and physically interpretable as a different contact model.

B2-02T finds no composite pass. Force 0.09 / 3 mm retains through release and
reduces slip by 63.2%, but the pawn falls below the 40 mm lift plane before
transport progress. Force 0.10 / 4 mm satisfies retention, aperture, and the
raw transport predicate only because the pawn remains pinched when the robot
returns upward, reaching a rejected 0.310 m rise. B2-02U freezes a two-member
causal upper bound: the non-launching 0.09 / 3 mm contact model normally, then
with measured joint state forced. The latter is explicitly non-promotable and
can only determine whether arm-response mismatch blocks the task consequence.

B2-02U rejects arm-response tuning as the next lever. Forcing measured joint
state reduces EE RMS to 1.1 mm and gripper bias to effectively zero, yet the
pawn rises only 6.1 mm. During physical closure the simulated fixed pad touches
C2 but the moving pad never does, so bilateral span remains exactly zero.
B2-02V therefore tests a bounded -6 to +2 degree moving-jaw kinematic zero
across the retained 0.09 / 3 mm, interpolated 0.095 / 3.5 mm, and aperture-valid
0.10 / 4 mm branches. Unlike B2-02U, every B2-02V candidate is a normal dynamic
replay and can advance only by passing the unchanged composite gates.

B2-02V changes the contact regime but yields no composite. Its best calibrated
branch, force 0.095 / travel 3.5 mm / jaw zero -3 degrees, has +0.405 degrees
aperture bias and 39.5% less slip but loses contact at source 377 and reaches
only 1.8% transport progress. B2-02W moves to phase alignment: prior retained
telemetry fitting estimated 105 ms gripper, 115 ms elbow, 120 ms shoulder-lift,
and 105 ms shoulder-pan/wrist-flex delays. The frozen family crosses 80--120 ms
gripper delays and those empirical joint-delay combinations on both the clean
retained and aperture-valid contact branches.

B2-02W is terminal negative and confirms a timing bifurcation. At 120 ms the
0.09 / 3 mm branch has -0.333 degrees aperture bias and 13.4% less slip but
loses at source 385; at 100 ms it launches to 0.318 m. B2-02X instead targets
the unreleased 0.10 / 4 mm branch's excessive low-load friction. It crosses
sliding friction 0.4--3.5 and lower torsional friction at 1.2, 1.8, and 2.6,
and tightens the evaluator with a required-release gate. Staying attached to
the gripper can no longer satisfy the campaign even below the energy ceiling.
