# Physics Loop Closure and Transferable Twin Research Ranking

**Status:** implementation-ranked research roadmap; no new physical motion,
paid compute, policy modification, or capability promotion authorized

**Date:** 2026-07-21 America/Chicago

## Decision

The highest-leverage next research contribution is not another independent
parameter sweep, a generic LLM tuning loop, or broader domain randomization.
It is a **retroactive calibration belief graph** built over the action-frozen
interventions and vector residuals already retained in sim2claw.

The graph should support **physics loop closure**: when a newly introduced
mechanism explains a residual better than an earlier proxy, the system must
revisit the correlated parameter block, reallocate attribution, and re-evaluate
all affected frozen episodes. It must preserve every physical trace and every
simulator intervention while keeping physical evidence, simulator evidence,
and evaluator authority separate.

The most credible short-term paper extension is therefore:

> Given a frozen set of real replay anchors and action-identical simulator
> interventions, can a governed calibration graph predict which mechanism to
> test next, revise earlier parameter attribution when a better mechanism is
> introduced, and reach the same or better held-out fidelity with fewer
> simulator evaluations than sequential one-variable tuning?

This is implementable with the current repository and retained data. A
fleet-conditioned meta-twin is the strongest longer-term direction, while
Q-value/world-model inversion is an interesting but mismatched extension for
the present ACT/VLA evidence.

## Workcell availability correction

The original physical workcell cannot be recreated and no additional evidence
from that scene can be collected. A robot-and-chessboard setup may be available
after several days, but lighting, background, and possibly the measured
board-to-robot transform will differ. It must therefore default to a
`new_related_workcell` evidence identity under
`configs/hardware/similar_scene_revalidation_v1.json`.

This does not block the P0 implementation. The intervention ledger, belief
graph, retrospective loop-closure benchmark, residual routing, information-gain
scheduler, governed agent, and promotion flywheel can all be built and tested
today from retained and synthetic evidence. New physical data are required to
validate new-session invariance, populate missing observables, run safe probes,
or make any replication/transfer claim.

The operational split is specified in
[`2026-07-21-zero-new-data-implementation-split.md`](2026-07-21-zero-new-data-implementation-split.md).

## Scope and claim boundary

This ranking folds overlapping ideas from the recent research discussions into
distinct implementation units. Scores describe practical value **for the live
sim2claw project**, not the general importance of each research area.

The current evidence contains one small retained acquisition session, opened
confirmation data, simulator interventions, and no accepted physical policy
execution. Consequently:

- current-data work can establish retrospective simulator-diagnosis and
  calibration-method evidence;
- a similar future hardware setup can establish new replay-anchor and probe
  evidence, but not continuity with the original scene unless re-measured;
- multiple workcells or partner datasets are required for fleet-transfer
  claims;
- simulator reward, lower RMS, contact, lift, or a fitted posterior cannot
  self-promote to physical transfer;
- source policy actions remain byte-identical across evidence-bearing simulator
  variants.

## Scoring rubric

The overall score is out of 10 and is specific to the present project state.
It combines:

- **Buildability (30%):** how much required machinery already exists;
- **Data fit (25%):** whether retained evidence can support a meaningful test;
- **Scientific leverage (25%):** likely contribution to diagnosis, fidelity,
  or publication differentiation;
- **Falsifiability (20%):** whether a frozen evaluator can reject the idea;
- an external-dependency penalty for unavailable hardware, multiple workcells,
  unsafe exploration, or a mismatch with the current policy class.

Priority labels mean:

- **P0 — build now:** current data and CPU/Mac execution are sufficient;
- **P1 — next bounded extension:** useful after P0 or with one similar-scene
  session;
- **P2 — partner/fleet research:** requires new cells, datasets, or sustained
  collection;
- **Defer:** conceptually interesting but poorly matched to the current proof.

The proposed **standardized workcell-twin compiler** is an umbrella product
thesis rather than an independent mechanism, so it is not double-counted in
the table. Its present-project score is **8.8/10** if scoped to the existing
trace, graph, evaluator, and plugin layers. A fully autonomous continuous
calibration service is closer to **6.5/10** until longitudinal physical and
multi-workcell evidence exists.

## Ranked practical ideas

| Rank | Practical implementation unit | Score | Priority | Current fit and verdict |
| ---: | --- | ---: | --- | --- |
| 1 | Immutable intervention ledger and vector residual tensor | **9.8** | P0 | Much of the raw material already exists in run logs, receipts, action hashes, telemetry, interaction events, and per-episode metrics. Normalize it into one typed evidence surface before adding intelligence. |
| 2 | Calibration belief graph with correlated parameter blocks | **9.5** | P0 | The repository already separates geometry, timing, reset, deadband, load bias, gripper, contact, and rubber mechanisms. Represent their dependencies and posterior correlations instead of treating campaign winners as independent truths. |
| 3 | Physics loop closure and retroactive refitting | **9.4** | P0 | This directly addresses the observed failure of sequential tuning: a proxy parameter can temporarily lower RMS until a better mechanism appears. Re-open only the connected graph block and replay its frozen dependents. This is the most distinctive mechanism. |
| 4 | Residual fingerprints and discrepancy-to-mechanism routing | **9.2** | P0 | Current campaigns already expose phase-specific joint, EE, contact, lift, slip, and consequence signatures. Convert those patterns into typed mechanism hypotheses with calibrated abstention rather than free-form LLM guesses. |
| 5 | Interventional invariance scoring | **9.1** | P0 | Reward explanations that remain stable across existing episode, phase, speed/timing, load-bias, and contact interventions. Current evidence is too narrow for physical invariance, but it is sufficient for a retrospective method benchmark. |
| 6 | Task- and failure-boundary fidelity with counterexample-guided refinement | **8.9** | P0 | GapBench, corrective interventions, strict evaluators, and retained failures already provide the skeleton. Optimize agreement near contact/lift/transport decision boundaries, not visually global or unweighted trajectory accuracy. |
| 7 | Task-aware value-of-information scheduler | **8.8** | P0 | Rank the next simulator evaluation by expected reduction in evaluator-relevant uncertainty per unit cost. Include abstention and the option to declare that only a new physical measurement can discriminate the remaining hypotheses. |
| 8 | Governed model-structure agent | **8.7** | P0 | Inspect/LLM tooling exists. The agent should propose mechanisms, graph edges, and discriminatory probes; deterministic code should fit parameters, calculate uncertainty, replay episodes, and own verdicts. The agent never promotes itself. |
| 9 | Promotion flywheel from discoveries to deterministic plugins | **8.6** | P0 | Learning Factory receipts, recursion, corrective artifacts, and promotion boundaries are already present. Repeatedly successful agent hypotheses should become reviewed parameter blocks, probes, fingerprints, estimators, and regression tests. |
| 10 | Canonical synchronized trace and safe-probe schema | **8.5** | P0/P1 | Commanded/measured joints, effort, timestamps, frames, object trajectories, contact, grasp, latency, and outcomes are substantially modeled. Finish one canonical schema now; execute new physical probes only in a separately authorized P1 session. |
| 11 | Engine-independent physical parameter ontology and adapters | **8.3** | P0 | The current configuration surface is fragmented by experiment. Define conceptual mechanisms—latency, backlash, compliance, jaw aperture, collision shape—then compile them to MuJoCo settings. Do not pretend coefficients have identical meaning across engines. |
| 12 | Structured multimodal posterior and model-structure particles | **8.1** | P0 | Preserve several plausible explanations when geometry, pawn centers, rubber geometry, and contact properties are observationally equivalent. Start with a small discrete set of structural branches plus continuous parameter blocks, not an unconstrained neural posterior. |
| 13 | Parameter timescale separation and drift model | **7.9** | P0/P1 | Separate static build geometry, installation calibration, object-specific properties, episode initial conditions, and time-varying wear/temperature. Retained data can test the schema; actual drift estimates require new longitudinal evidence. |
| 14 | Cached sensitivities, local Hessians, and connected replay | **7.8** | P0 | Cache per-episode residual summaries and finite-difference responses so only graph-connected factors are recomputed after small changes. This reduces compute and reasoning cost, although it is an enabling systems contribution rather than the headline. |
| 15 | Sparse-reality statistical correction of an imperfect simulator | **7.7** | P1 | A guarded residual model could correct systematic prediction error without claiming that its latent variables are physical. Current data are enough for a tiny, cross-validated residual baseline, but not for a high-capacity learner. |
| 16 | Constrained learned discrepancy model | **7.2** | P1 | Useful only if the residual is low-capacity, uncertainty-bearing, held-out evaluated, and prevented from absorbing identifiable physics. It should be a challenger to explicit mechanisms, not an unrestricted patch that wins training loss. |
| 17 | Design a physical calibration kit for identifiability | **7.2** | P1 | AprilTags, cameras, robot telemetry, known masses, surface coupons, compliant fixtures, and optional force/current sensing can create high-signal probes. It is a strong future addition, but it cannot improve the already-collected dataset retroactively. |
| 18 | Normalize reality toward a calibrated reference cell | **7.0** | P1 | Fixtures, stops, tag mounts, replaceable jaw pads, known board geometry, and controller profiles can reduce deployment variance. Treat normalization actions as measured interventions, not as evidence that the simulator was physically correct. |
| 19 | Safe micro-identification actions before or during a task | **6.8** | P1 | Small reversible squeezes, taps, reversals, or free-space motions could expose latency, backlash, compliance, and grip state. This requires a reviewed gateway, explicit safety limits, and separate authority; it must not contaminate action-frozen policy evidence. |
| 20 | Continuous drift monitoring from production traces | **6.8** | P1 | The recorder and trace surfaces make this architecturally feasible. A useful test needs new time-separated data and known interventions so wear is not confounded with scene reset or object placement. |
| 21 | Workcell-family model and compact workcell fingerprint | **6.7 now / 9.0 with cells** | P2 | This is the strongest platform thesis: learn shared discrepancy modes and infer a low-dimensional fingerprint for each installation. One workcell and one acquisition session cannot validate transfer across cells. |
| 22 | Leave-one-workcell-out calibration benchmark | **6.5 now / 9.2 with partners** | P2 | The decisive metric is whether each added workcell reduces calibration trials for the next. It needs several comparable cells or external datasets; synthetic “cells” can test infrastructure only. |
| 23 | Fleet-posterior domain randomization | **6.4** | P2 | Eventually randomize from a posterior learned across real cells, conditioned on each workcell fingerprint and task boundary. Today there is no fleet posterior, so broad randomization would mostly hide calibration error. |
| 24 | Committee of simulators/world representations | **6.0** | P2 | Comparing rigid-body, kinematic, learned residual, and visual world models can reveal disagreement. The immediate project has one primary physics engine and sparse physical outcomes, making a large committee costlier than improving the evidence graph. |
| 25 | Foundation model of sim-real discrepancy | **5.2** | P2 | GapBench can generate synthetic training examples, but a model trained primarily on seeded faults may learn the benchmark generator rather than real discrepancy structure. Pursue only after multi-cell evidence exists. |
| 26 | Goal-conditioned critic bank as implicit system identification | **4.9** | Defer | Diverse rewards over position, velocity, contact, slip, energy, and grasp stability could probe dynamics, but the present ACT/VLA policies are behavior-cloning action generators without the required multi-goal Q-functions. |
| 27 | P-learning-style inversion from Q-values to a world model | **3.8 now / 7.0 in a new RL study** | Defer | Mathematically interesting and potentially publishable as a separate study. It requires accurate Q-values, known rewards, state coverage, sufficient goal diversity, and assumptions not established by the retained pawn data. It should not be advertised as an immediate ACT inversion method. |

## What to build now

### P0.1 — Intervention ledger

Create a versioned `CalibrationEvidence.v1` contract with these entities:

- immutable physical episode and source-action identity;
- simulator candidate and parent identity;
- mechanism block and conceptual parameter identity;
- implementation, scene, runtime, and evaluator identities;
- per-episode, per-phase residual vectors rather than only minima or one score;
- contact, lift, retention, slip, transport, destination, and strict consequence;
- evidence class and authority flags;
- selection role: fit, grouped validation, regression-only, or sealed evaluation;
- intervention cost and wall-clock/runtime receipt;
- missing observables and explicit non-identifiability statements.

The initial ledger should ingest the retained geometry, timing, reset,
deadband, load-bias, timestep, base-height, gripper, rubber, and retention
campaigns. It must not reinterpret simulator parameter values as measured
physical properties.

### P0.2 — Calibration belief graph

Use a small, typed factor graph rather than a general graph database:

```text
physical traces
  -> episode/phase residual factors
  -> mechanism blocks
       geometry and frame
       reset and joint reference
       timing and actuator response
       load, compliance, and backlash
       gripper aperture and collision geometry
       contact, pawn, and surface dynamics
  -> simulator candidates
  -> frozen evaluator verdicts
```

The graph should store dependencies, posterior covariance or local curvature,
observability warnings, structural alternatives, and which evidence would be
invalidated or recomputed by a change. Continuous parameters may use bounded
Gaussian/Laplace approximations initially; genuinely distinct mechanism
classes should remain separate particles.

### P0.3 — Physics loop closure

Implement one falsifiable example using retained evidence:

1. Fit an intentionally incomplete timing/control model that allows damping or
   response terms to compensate for a missing delay/load mechanism.
2. Add the omitted mechanism later.
3. Identify the graph-connected correlated block;
4. use cached local response information to predict how earlier parameters
   should move;
5. jointly refit only that block against the same frozen fitting roles;
6. run the separate evaluator on identical validation roles;
7. preserve both model branches and reject the new mechanism unless vector
   fidelity, plausibility, and held-out evidence improve.

Success is not “the new branch lowers one RMS.” Success is that the system
correctly revises earlier attribution, predicts the direction of retuning,
and improves frozen vector fidelity without changing source actions.

### P0.4 — Decision and routing layer

For every open residual mode, calculate:

- candidate mechanisms and posterior probability or score;
- observability and parameter-correlation warnings;
- expected information gain of each bounded simulator intervention;
- expected evaluator relevance;
- runtime and reasoning cost;
- whether existing data can discriminate the candidates;
- whether the correct outcome is `abstain_requires_new_measurement`.

An LLM may explain the residual, propose a missing mechanism, or author a
bounded adapter patch. It receives concise graph diagnostics and returns a
typed proposal. Numerical fitting and promotion remain deterministic and
separately owned.

## Minimum viable retrospective benchmark

The current dataset can support a publication-grade method experiment without
pretending to provide new physical evidence.

### Benchmark cases

Construct cases from retained campaign families:

1. geometry/frame versus actuator tracking;
2. delay versus first-order response;
3. reset/reference versus apparent geometric offset;
4. deadband/hysteresis versus damping;
5. load bias/compliance versus joint-zero compensation;
6. gripper aperture/collision geometry versus friction;
7. contact retention versus timestep/solver behavior;
8. pawn/board registration versus final target distance.

Where real identifiability is unavailable, use seeded synthetic faults only as
mechanism tests and label them synthetic. Do not use the seeded target as a
claim about the real pawn scene.

### Baselines

Compare:

- chronological one-coordinate tuning;
- random bounded search;
- best observed candidate selected post hoc, labelled as an oracle upper bound;
- flat Bayesian optimization over all parameters;
- block-aware posterior search without loop closure;
- the proposed graph with loop closure, structural particles, and
  value-of-information routing;
- the same graph without the LLM model-structure proposer.

### Primary metrics

- number of simulator evaluations needed to reach a fixed held-out fidelity;
- held-out joint, EE, object, contact, and consequence-vector improvement;
- sign and rank accuracy when predicting an intervention's effect;
- parameter/model recovery on seeded synthetic faults;
- calibration-path invariance under shuffled intervention order;
- posterior coverage and abstention calibration;
- rate of correctly rejecting score-improving but guardrail-breaking variants;
- LLM calls, tokens, wall time, and marginal benefit over deterministic routing;
- action hash equality and proof-class correctness.

### Required negative controls

- an oracle with access to seeded synthetic faults to prove harness reachability;
- a score-only optimizer expected to overfit or violate vector guardrails;
- an unconstrained residual learner expected to absorb explicit mechanisms;
- a broad domain-randomization baseline expected to mask calibration error;
- a shuffled evidence/parameter routing control;
- a loop-closure-disabled ablation;
- a leaked-held-out case that the evaluator must reject.

## Similar-scene extension

If the SO-101 hardware is set up again, the best use of the session is not to
recreate the old chess scene by eye. Build a compact identification battery:

- tag-anchored board and camera registration;
- known free-space joint reversals at several speeds;
- known payload and arm-orientation holds;
- slow jaw close around known gauges or compliant coupons;
- known surface and pawn surrogates;
- synchronized command, measured joint, effort/current, RGB, and event clocks;
- repeated probe blocks before and after the task session for drift checks.

The session should create independent evidence factors that distinguish
geometry, latency, backlash, load, aperture, compliance, and contact. It should
not be used merely to add more task demonstrations to an underidentified
calibration problem.

## Fleet extension

The longer-term research program becomes compelling when several comparable
cells are available.

For workcell `i`, infer a compact fingerprint `z_i` and uncertainty from the
standard probe battery. Separate:

- robot-family and controller behavior shared across cells;
- installation-specific geometry and latency;
- replaceable-tool and object properties;
- drifting wear and environmental state;
- episode-specific initial conditions.

Freeze one cell at a time as held out. Train the shared discrepancy basis on
the others, provide only the standard probes from the held-out cell, and
measure:

- physical trials required to compile a useful twin;
- trace and task-outcome agreement;
- policy-ranking correlation;
- failure-boundary overlap;
- posterior coverage and OOD detection;
- agent-escalation rate;
- reduction in calibration burden as the number of prior cells grows.

The decisive fleet claim is a downward calibration-cost curve for later cells,
not merely a lower pooled loss.

## Position of world-model inversion

The Q-value inversion idea should be preserved as a separate research branch,
not merged into the immediate simulator-calibration claim.

A future study could train goal-conditioned critics over deliberately diverse
objectives—position, velocity, contact, displacement, slip, energy, overshoot,
and retention—and ask whether their joint value structure constrains an
implicit transition model. That extracted model could be audited against
MuJoCo and measured traces.

For the present project, three boundaries are decisive:

1. ACT and the retained VLA policies do not expose the required multi-goal
   Q-functions;
2. a critic trained only in the imperfect simulator cannot independently
   identify the real transition model;
3. value-equivalent dynamics may remain physically non-identifiable even when
   they support similar task values.

The immediate belief graph can later host critic-derived factors, but it should
not depend on them.

## Recommended sequencing

1. **Now:** normalize the existing intervention ledger and residual tensor.
2. **Now:** implement the typed calibration graph and small structural-particle
   posterior.
3. **Now:** demonstrate one retrospective physics loop closure with shuffled
   tuning-order and loop-closure-disabled controls.
4. **Now:** add deterministic information-gain routing and then measure the
   marginal value of an LLM structure proposer.
5. **Publication extension:** evaluate the method on synthetic GapBench faults
   plus the explicitly partial B--G retained case study.
6. **Next hardware session:** collect a tag-anchored identification battery,
   not an unfocused demonstration batch.
7. **Partners/fleet:** run leave-one-workcell-out fingerprint adaptation.
8. **Separate future study:** introduce goal-conditioned critics and test
   world-model inversion under assumptions designed for that question.

## Stop conditions

Stop or demote the direction if any of these hold:

- the graph cannot outperform a simple block-aware optimizer on held-out
  fidelity or evaluation count;
- loop closure changes attribution but not held-out prediction;
- results depend materially on intervention order despite joint refitting;
- uncertainty fails to cover retained outcomes and the method does not abstain;
- the LLM adds cost but no statistically supported routing or structure value;
- a learned residual wins only by absorbing explicit mechanisms;
- the method requires opened held-outs to select its graph or hyperparameters;
- simulator-only improvements are being narrated as physical calibration;
- action invariance or evaluator ownership is weakened to obtain a win.

## Final recommendation

Build the **intervention ledger → calibration belief graph → physics loop
closure → information-gain router** stack first.

It is the best combination of immediate feasibility, conceptual novelty,
compatibility with the retained evidence, and evaluator-owned falsifiability.
It converts the project's many bounded simulator interventions from a sequence
of tuning attempts into a reusable calibration landscape and gives the LLM a
high-value role—proposing missing physical mechanisms—without making it the
numerical optimizer or the authority.

The workcell-family/meta-twin thesis should frame the longer-term vision. The
world-model inversion idea should remain a clearly separated, higher-risk
research branch until the project has goal-conditioned critics and appropriate
real evidence.
