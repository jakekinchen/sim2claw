# Causal-Closure Terminal Application Package

Status: `COMPLETE_RECEIPT_BACKED_EXTERNAL_HARDWARE_BOUNDARY`

Branch: `codex/bidirectional-transfer-goal-loop-20260728`

Physical task attempts: `0/10`

REAL->SIM successes/attempts: `0/0`

SIM->REAL successes/attempts: `0/0`

## Outcome

This sprint did not achieve bidirectional pawn-task transfer. It produced a
stronger engineering result than an unqualified robot demo: an autonomous
coding-agent loop built causal observability, corrected a categorical
coordinate error, validated one bounded cross-domain wrist trajectory,
diagnosed a degraded actuator with exact recorded telemetry, and refused to
execute when the prospectively frozen safety search found no collision-free
task family.

The stopping point is a hardware/external-state boundary, not a planning or
tooling pause. The final Fable defect check independently challenged the
collision logic and returned no material in-scope proof defect.

## Three camera-verifiable exhibits

### 1. Admitted bounded correspondence

- Physical action SHA-256:
  `6872ca20a7b31cba8b014c23ed7f11cf845b4d5e88da28e6304464e7786ddf1d`
- Held-out contract SHA-256:
  `607a4b8c8a2eecc086bfa08b65e1d1c19012e1546aa0e4ecb2dca930ea8735e6`
- Evaluator implementation identity:
  `feedf3ede2c7aa723f209157254c4c904a81a778c0dae57d909e16a8ba52899b`
- Held-out receipt SHA-256:
  `16b7896c45904c7563d00f8b8386cddf3892de9deec70c77c0a2c9ff087294c6`
- `90` detected D405 frames;
- normalized shape correlation `0.985523`;
- normalized RMSE `0.073090`;
- normalized maximum error `0.144659`;
- physical and simulated wrist peaks both `2.725275 deg`;
- no parameter fit and no depth channel.

The existing Studio comparison/timeline surface can present the physical D405
video and the measured-versus-simulated normalized trajectory as separate
lanes. It must label camera exposure synchronization and metric depth as
missing and must not call the chart a task replay.

### 2. Hardware truth

- CC03E contract SHA-256:
  `0bc1fdcd4fc6455b563e0174842e7ea9aa2b6ef37065b527d38e0a6490912976`
- Executor SHA-256:
  `8201f67662e90221fa5c79552970f44c4cf215874f5754e59bb3deddd8c2c843`
- Receipt SHA-256:
  `876cc47862b21f719646b7797b3e67c5dc8ec7e654735e984f4ee09265da666b`
- Closeout SHA-256:
  `f9c5d8fac4c2b50eb46dcc0e566f076f216dd6925c121712b9f2675f3ea685a8`
- `217/217` exact rows;
- `67` D405 frames and zero large gaps;
- elbow response `1.58--1.76 deg` for a `5 deg` request in both directions;
- matched wrist response `4.84 deg`;
- peak raw current/load `24/196`;
- status `0`, torque readback `1`, temperature `25--26 C`;
- one torque cycle with no recovery;
- torque off at close.

The result is a mechanical-resistance signature, not proof of a broken part.
The negative direction labels a lower requested joint angle and the positive
direction labels the equal return; neither label is a gravity diagnosis.

### 3. Refused temptation

- CC03K contract SHA-256:
  `852dfc133f4c74e6ee25728610b4b77b73a76f63f237e7243ec6997fa430902b`
- Static implementation SHA-256:
  `0f542a9bbd517f37a2a202f0f84e9bf6756512097d41691906547d442faa0706`
- Receipt SHA-256:
  `f8bb0e86f61fbdb380a337d2f565d163534e37ce16acb9157e45f931750bb094`
- Closeout SHA-256:
  `ca107505f7a1b43da1c5776cf9c8c627bf4b9dac87809ed967548b258afce034`
- `576` prospectively frozen cells across `48` families;
- `504` IK rejects and `72` compiled static rejects;
- `51` valid selected-pawn contacts at `45.339--52.080 mm`;
- `0/72` collision passes;
- `0` eligible families in both directions;
- no dynamics, evaluator freeze, pawn contact, or physical task attempt.

The receipt field `selected_actions_exactly_constant:false` is vacuous when the
selected action set is empty. It does not mean a selected action changed;
there are no selected actions or action files.

## Mechanisms that jointly contributed

1. Canonical rank orientation and occupancy-parity checks prevented a
   categorical coordinate-frame error from reaching the task layer.
2. Exact float64 action hashing and requested/mapped/sent/applied separation
   prevented silent action repair.
3. `ObservableEpisode.v2-min` and first-divergence surfaces separated action,
   joint/link, contact, object, and outcome channels.
4. Frozen direct-target and `0.11 s` ZOH simulator paths tested timing
   sensitivity without claiming calibrated latency.
5. A gauge-fixed calibration graph and sealed held-outs admitted only the
   bounded wrist channel the data supported.
6. Camera-enclosed telemetry localized the active hardware boundary.
7. Prospective finite geometry searches and immutable negative receipts
   prevented outcome-informed gate weakening.
8. The iterative Fable review independently challenged both the diagnosis and
   the terminal geometry result.

## Deferred cards

CC04--CC12 are not marked successful. They are closed behind the documented
hardware prerequisite:

- restore and requalify a responsive elbow, or introduce a separately reviewed
  physically reachable actuator/tool;
- then freeze a new action family prospectively;
- only then approve task-scope mapping, freeze the evaluator, attempt both
  transfer directions, collect object/contact traces, and run the
  policy-screening/TaskWorldBundle/variation cards.

Because the paired physical task sample is zero, policy ranking is
`INSUFFICIENT_PHYSICAL_SAMPLE`, not predictive.

## Exact application wording

> I built an autonomous, receipt-gated sim-to-real engineering loop that
> corrected a board-frame error, validated a bounded real/sim wrist trajectory
> on a sealed held-out, localized a degraded elbow through exact camera-
> enclosed telemetry, and independently proved when no collision-safe task
> action remained. The sprint did not achieve task transfer; its result is a
> reproducible causal diagnosis and an honest hardware boundary with every
> attempted proof transition hash-bound.

Do not shorten this into “bidirectional transfer achieved” or “sim-to-real
solved.”

## Closeout verification

- Campaign-focused graph, historical-lineage, CC03E, and CC03K tests:
  `10 passed`.
- Current graph rebuild equals the tracked graph; JSON parsing and
  `git diff --check` pass.
- Autonomous-workflow audit: clean.
- Fresh reviewed gateway preflight: passed; follower torque readback is
  `false`; no alignment motion or configuration rewrite occurred.
- No dual-camera recorder, Pi camera recorder, elbow probe, or robot-gateway
  process remains. The user-facing Studio servers on ports `4173` and `4175`
  remain intentionally available and have no robot authority.
- `brev ls`: no instances in the organization.
- Unrelated untracked `tools/build_fiducial_sheet.py` remains untouched and is
  excluded from the closeout commit.

The full repository suite was attempted, but it is not a green release gate:
after the one stale historical active-pointer assertion was updated to inspect
the preserved historical node, the next fail-fast result was an unrelated
pre-existing frozen-hash mismatch in
`test_bidirectional_pawn_push_v2_sim_rehearsal.py` (`197 passed`, `4 skipped`,
`10` subtests before that failure). A non-fail-fast attempt also reached a
legacy OpenCV evaluation and terminated with a native segmentation fault.
Neither failing implementation is modified by this closeout. The scoped
campaign tests and graph audit are green; the repository-wide suite limitation
is disclosed rather than relabeled as a pass.
