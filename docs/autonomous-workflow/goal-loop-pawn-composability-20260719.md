# Eight-Hour Pawn Composability Goal Loop

## Mission

By 2026-07-19 08:37 America/Chicago, advance `sim2claw` from a collection of
promising manipulation slices into a coherent, reviewer-ready hackathon and
research repository centered on one defensible thesis: reproduce the physical
system's observed endpoint imperfections in simulation, determine whether
forward/reverse skills correct, preserve, or amplify those imperfections, and
only then evaluate corrections.

## Source Of Truth

Use these sources in descending authority:

1. The owner's 2026-07-19 endpoint, replay, system-identification, composition,
   correction, and eight-hour orchestration request.
2. `AGENTS.md` and the clean-room/cost-control rules.
3. `GOAL.md`, `docs/autonomous-workflow/project_state.json`, and accepted
   decisions, after reconciling them against the live checkout and current
   evidence.
4. Frozen task/evaluation contracts, raw-data hashes, evaluator outputs,
   checkpoint identities, and current test results.
5. The live worker handoffs recorded in `.factory/orchestration-ledger.md`.

Historical receipts, memories, thread summaries, catalog labels, and ignored
outputs are evidence leads only. They do not override current repo state or
grant training, promotion, physical, gateway, or paid-compute authority.

## Intended Outcome

The repository contains a reproducible B--G bidirectional pawn evaluation,
recorded-action replay and staged calibration machinery, held-out validation,
composition and correction experiments where the required evidence exists,
and a clear research/hackathon narrative. Every unsupported phase fails closed
with a precise missing-input manifest instead of simulated or physical claims.

## Acceptance Criteria

- Exactly 12 directed B--G skills are versioned and scored with separate task,
  coarse, composable, and precision grades.
- Endpoint artifacts include signed x/y error, center distance, base-in-region
  fraction, upright/stable state, mean bias, covariance, initial-to-final
  offset regression, trajectory repeatability, and precondition-envelope
  support. Missing pose evidence cannot silently become a zero or a pass.
- The complete admissible recorded cohort is hash-bound and classified by
  train, calibration, counterexample, held-out, and visual-only eligibility.
- Recorded-action replay initializes each episode from its measured state,
  replays exact commands, aligns clocks, and exports synchronized real/sim
  joints, end-effector, gripper, pawn, contact, and endpoint observables where
  those observables actually exist.
- System identification separates geometry, timing/control, and contact/object
  parameter groups; uses robust residuals and bounded/multi-start optimization;
  freezes whole-episode train/held-out splits before fitting; and reports a
  nominal fit, near-equivalent fits, correlations, and uncertainty ranges.
- Calibrated parameters improve held-out observables relative to the frozen
  baseline or the result is explicitly terminal-negative.
- Closed-loop ACT or GR00T replay runs only after held-out-improving staged
  calibration and when a real compatible checkpoint, preprocessing contract,
  observation contract, and evaluator are available.
- Alternating cycles feed each actual terminal state into the next transition
  and report drift and envelope survival after 1, 2, 5, 10, and 20 moves.
- Correction comparisons cover the unmodified policy, endpoint-bias
  compensation, and retargeted placement where supported. Synthetic
  goal-conditioned training is attempted only after calibration fidelity and
  data-admission gates pass.
- Studio and submission artifacts present the same bounded claims as the code
  and evidence. RGB/3DGS remains visual context, not metric or collision truth.
- Focused tests, the full suite, formatting/static checks, build, and the Mac
  golden path are run in proportion to the final diff. Results and unrelated
  baseline failures are separated.
- Verified slices are integrated in reviewable commits without overwriting
  unrelated user work. No push, PR, merge, or release is assumed without owner
  authority.
- If Brev is used or was depended on, authenticated inventory and ownership are
  checked. Unowned idle resources are stopped/deleted; an owner-explicitly
  reserved workspace remains reserved for its declared window even while idle
  and is reported rather than countermanded. Historical empty-inventory proof
  is not reused as current.

## Evidence Standard

Before claiming a phase complete, record changed files, input and contract
hashes, exact commands, test/metric outputs, generated artifact locations,
proof class, limitations, and the smallest unresolved blocker. Reports must
distinguish implementation readiness, synthetic fixtures, simulation/replay
evidence, learned-policy evidence, physical read-only evidence, physical task
evidence, and promotion authority.

## Decision Status

### Confirmed Requirements

- B--G forward/reverse endpoint composability is the immediate product
  benchmark requested by the owner.
- Actual terminal state, never nominal square center, feeds the next skill.
- Physical recordings may calibrate only observables they actually contain.
- Simulator calibration targets observed imperfections before corrections.
- Held-out episodes and evaluator behavior freeze before fitting or training.
- Physical validation cannot be claimed while the robot is unavailable.

### Assumptions And Defaults

- Local edits, tests, and focused commits are authorized; public mutation is
  not yet authorized.
- CPU/fp32 is the verdict surface. Mac CPU/MPS may perform diagnostics and
  training; paid GPU work requires an explicit bounded campaign. The separate
  owner-directed NemoClaw workspace is reserved for a 20-hour deployment lane
  and is not governed by the no-new-GR00T decision in this study.
- One writer owns each checkout. Existing shared-checkout work is drained and
  integrated before new implementation workers receive isolated worktrees.

### Resolved Inputs And Current Blockers

- The recovered physical payloads provide timestamped commanded/measured joint
  positions and gripper state plus videos. They do not provide admitted pawn,
  end-effector, contact, grasp/release, or board-coordinate trajectories. Visual
  fiducial/contact-center markers have owner qualitative image-space review but
  cannot fill those metric observables.
- No compatible B--G ACT checkpoint exists in this repository. The retained
  `chess_rook_lift_v1` checkpoint proves only its narrow contract and cannot be
  relabeled as a bidirectional pawn placement policy. The 18 current B--G
  recordings are human leader/follower teleoperation sources, not learned ACT
  rollouts.
- Brev authentication was available for the already-authorized bounded GR00T
  run. Training completed 1,000 steps, the sole frozen C8→A6 development
  rollout was terminal negative (0 mm lift, 125.724 mm final XY error), held-out
  remained sealed, the compact archive was retained, and authenticated
  inventory returned empty after worker deletion.
- Available per-skill initial-offset variation is insufficient to identify all
  affine transition matrices. The current endpoint package therefore reports
  zero admitted poses, zero supported regressions, and no composition result.
- Canonical replay input audit found the physical-to-simulator joint mapping is
  not yet calibration-safe: 2,255/7,741 measured rows and 2,231/7,741 command
  rows fall outside current MuJoCo limits. The integrated implementation now
  forbids clipping and requires measured initial velocity, units, object-state
  binding, immutable splits, and observable/sensitivity gates. All 18 episodes
  still fail readiness, so exact physical replay and every system-ID fit remain
  blocked.
- Eleven physical catalog task labels remain inconsistent with folder labels.
  A leave-one-column-out split cannot treat those column assignments as frozen
  authority until the append-only adjudication queue is reviewed.
- The owner reports rubber bands wrapped approximately four to five times
  around each gripper tip. This likely changes contact geometry, friction,
  compliance, grip force, and release behavior, but remains an unmeasured
  hardware prior until dimensions and episode/session applicability are bound.

### Integrated Evidence At 2026-07-19 04:27 CDT

- `36f1ebc` implements the 12-skill product-v2 endpoint/composability contract,
  evaluator, CLI, tests, and authority reconciliation.
- `c24ddec` implements complete-corpus evidence preparation and records the
  fail-closed 18-episode/36-panel result.
- `70493fe`, `bdd2bea`, `fb95de4`, `db4df36`, and `c93e66a` preserve the
  owner's visual corrections and bind the exact 26-marker qualitative review.
  They do not admit any metric pose.
- The recovered corpus has 13 folder-label product candidates covering 12/12
  skills, five retained off-scope rows, seven owner-reviewed qualitative
  folder-label corrections, and zero admitted pawn poses. The 25-test focused
  suite passes. The accepted product-sheet, decoded-pixel, and marker-manifest
  SHA-256 values begin `8a2ae402`, `11b02ee1`, and `c8076c59`; the fail-closed
  summary remains `43141d8a`.
- `ef495f0` freezes the protocol-only research inference overlay and the
  canonical replay-range audit. Claim eligibility is disabled pending a new
  coverage-validated protocol; all 18 recordings fail the legacy joint-range
  gate and no fit was run.
- `7646ddf` records the no-new-GR00T launch gate and the unmeasured rubber-band
  fingertip hardware prior. That gate does not control the separately
  owner-reserved NemoClaw deployment workspace.
- Commits `40c2fa6` through `c257409` integrate prospective GR00T dataset,
  checkpoint, Python-3.10 runtime, import, process, task, and evaluator identity
  gates. They do not repair the completed run's missing live handshake or
  restore its checkpoint weights.
- Commits `17f5391` through `4e58245`, plus lineage repair `42572a1`, integrate
  recorded-action replay and staged system-ID contracts. The canonical input
  report is a fail-closed 0/18 readiness result at SHA-256 `5676b3db...`; no
  physical replay, fit, calibration, held-out comparison, or promotion
  occurred.
- `9f0a862` and `792ff95` integrate the evidence-bound Studio calibration view,
  verified Robo Scanner visual release, two-level hackathon presentation, and
  read-only proposal-versus-reviewed-geometry boundary.
- `b5b2f93` freezes the exact 12 B--G language semantics, two deterministic
  training prompt forms per semantic, group-before-expansion leakage rules, and
  zero-source-group no-launch snapshot. Prompt rows add no behavioral evidence.
- `254bed9` preserves the owner-confirmed Studio simplification: no generic
  grid, rulers, crosshair, axes, boundary, or default reviewed-geometry overlay.
- The first rook-lift rubber-tip receipt was rejected because snapshot bytes
  were not rehashed before deserialization. Commit `893f7ac` closes that
  bypass, and a fresh authenticated rerun accepts only ancillary simulated
  contact-prior sensitivity. It remains unrelated to B--G policy evidence or
  physical calibration.
- `d0c4491` integrates the reviewed NemoClaw repository/deployment contracts.
  Runtime deployment remains stopped, and its Brev lifecycle follows the
  owner's explicit 20-hour reservation rather than coordinator teardown
  defaults.

## Execution Rhythm

1. Inspect the current checkout, raw evidence, worker state, and paid-resource
   state.
2. Choose the smallest dependency-ready slice with a concrete proof target.
3. Assign exactly one writer in an isolated checkout or execute locally when
   no independent worker lane is safe.
4. Record the assignment and proof result in the orchestration ledger.
5. Review code, evidence, claims, and clean-room boundaries before integration.
6. Reconcile `GOAL.md`, `project_state.json`, Studio, and submission copy only
   after the underlying proof is stable.
7. Recheck workers about every five minutes and intervene only for drift,
   overlap, repeated failure, unsafe authority, or missing proof.
8. Continue until every acceptance criterion is evidenced, terminal-negative,
   or reduced to a precise external blocker.

## Progress Ledger

Use `.factory/orchestration-ledger.md` as the live durable status surface.

```text
Current state:
Completed:
Evidence:
Remaining:
Blockers:
Next step:
```
