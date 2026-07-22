# SAIL: Structure-Adaptive Interventional Loop Closure

**Status:** proposed formal method and publication methodology; no robot motion,
new capture, paid compute, policy training admission, simulator promotion, or
physical claim is authorized by this document

**Date:** 2026-07-21 America/Chicago

**Relationship to the system:** SAIL is the proposed algorithmic core inside
the broader ClawLoop system described in
[`2026-07-21-agentic-twin-self-improvement-paper-plan.md`](2026-07-21-agentic-twin-self-improvement-paper-plan.md).

## Decision

The paper should be reorganized around one algorithmic contribution rather
than around the complete end-to-end stack:

> **SAIL is a structure-adaptive simulator-calibration algorithm that detects
> compensating explanations through intervention-specific invariance,
> introduces candidate physical mechanisms, retroactively reopens only their
> historical influence set, and reallocates explanatory credit before
> revalidating task predictions.**

The larger system then contributes two supporting abstractions:

1. a **physical-mechanism plugin ABI** that packages a mechanism together with
   its identification, invariance, simulator, uncertainty, and validity
   contracts; and
2. an **evidence-gated twin-to-policy loop** that prevents an untrusted twin,
   reasoning agent, simulator reward, or trainer from promoting itself.

The proposed paper hierarchy is therefore:

```text
Algorithmic contribution
  SAIL: structure-adaptive interventional loop closure

Systems contribution
  Mechanism ABI + immutable evidence graph + sealed certification

Robotics result
  Low-data SO-101 calibration and downstream policy improvement

Optional extension
  Choose among simulator repair, new probe, policy adaptation,
  physical normalization, or abstention
```

This framing is stronger than claiming that autonomous simulator calibration,
VLM-guided tuning, active system identification, digital twins, synthetic VLA
data, or recursive policy improvement are individually new.

## Novelty assessment

The individual ingredients have strong precedents:

- NIST proposed standardized physical/simulation robot tests and simulator
  tuning in 2007;
- SiPE provides simulator-parameter-estimation benchmarks and workflows;
- BayesSim, SimOpt, and related methods fit simulator parameter distributions;
- ASID actively selects informative physical exploration;
- CAPTURE predicts parameter updates from adjustment histories;
- COMPASS learns causal parameter-to-discrepancy structure;
- Vid2Sid uses a VLM to diagnose paired video and propose physics updates;
- ASIA uses a coding agent for system-identification model search;
- invariant causal prediction and active invariant causal prediction use
  cross-environment stability and intervention selection;
- factor graphs support incremental re-estimation and changing contact states;
- ASPIRE accumulates validated program repairs into reusable robot skills; and
- Nautilus uses typed contracts and validation to compose policies,
  simulators, benchmarks, and robots.

The potentially defensible novelty lies in the update operator and decision
criterion formed by their combination:

| Proposed mechanism | Novelty potential | Required proof |
| --- | --- | --- |
| Structure-adaptive physics loop closure | **High** | Define influence-set discovery, sparse structural update, credit reallocation, acceptance, and computational advantage over full batch refitting |
| Intervention-specific invariance for anti-compensation | **High** | Show it selects the correct missing mechanism and predicts held-out task consequences better than residual loss, model evidence, or Fisher information alone |
| Structural-discrimination acquisition | **Medium-high** | Select probes for disagreement between model structures, not merely uncertainty in a fixed parameter vector; beat ordinary active SysID on probes required |
| Compensation debt and structural-surprise trigger | **Medium-high, proposed here** | Show that boundary pressure, prior departure, and cross-environment drift predict omitted physics and improve mechanism-discovery timing |
| Physical-mechanism plugin ABI | **Distinctive systems contribution** | Demonstrate backend reuse, explicit validity envelopes, and reduced bespoke agent work on later mechanisms/workcells |
| Self-normalizing workcell action arbitration | **Interesting follow-on systems contribution** | Show useful choices among simulator change, probe, policy adaptation, physical normalization, and abstention under a shared cost/risk objective |
| Full calibrated-twin-to-policy flywheel | **Strong composition** | Demonstrate that certification prevents negative transfer and that admitted simulator data improves a sealed downstream policy evaluation |

No novelty claim should rely on the name “physics loop closure” alone. The
paper must implement and ablate the precise inference behavior below.

Closest primary resources checked for this determination include
[NIST robot-simulation physics validation](https://www.nist.gov/publications/robot-simulation-physics-validation),
[SiPE](https://arxiv.org/abs/2011.08985),
[ASID](https://arxiv.org/abs/2404.12308),
[CAPTURE](https://arxiv.org/abs/2410.20357),
[COMPASS](https://proceedings.mlr.press/v229/huang23c.html),
[Vid2Sid](https://arxiv.org/abs/2602.19359),
[ASIA](https://arxiv.org/abs/2605.10480),
[Active Invariant Causal Prediction](https://arxiv.org/abs/2006.05690),
[interventional identifiability for dynamical systems](https://arxiv.org/abs/2311.18048),
[incremental contact factor graphs](https://arxiv.org/abs/1712.05873),
[ASPIRE](https://arxiv.org/abs/2607.00272), and
[Nautilus](https://yufengjin.github.io/projects/nautilus/).
This is a targeted novelty audit, not proof of universal absence across
unindexed papers, patents, theses, or private systems.

## Formal problem

Let the immutable evidence archive contain episodes or probes

\[
\mathcal D = \{(u_i, y_i^{real}, e_i, p_i, a_i)\}_{i=1}^{N},
\]

where:

- \(u_i\) is the hash-bound physical command sequence;
- \(y_i^{real}\) is the available synchronized physical observation trace;
- \(e_i\) is the intervention/environment identity;
- \(p_i\) is the task phase and observation-availability structure; and
- \(a_i\) records evidence authority, split role, and missing observables.

A simulator structure \(S\) is a set of physical-mechanism plugins. Its
prediction is

\[
\hat y_i = F_S(u_i; \bar\theta, \delta_{e_i}, z_i),
\]

with:

- shared parameters \(\bar\theta\);
- declared environment/session/object deviations \(\delta_e\); and
- episode nuisance state \(z_i\).

The objective is not to recover one supposedly true parameter vector. It is to
select or preserve structures that:

1. predict frozen real traces and task consequences;
2. use parameters that remain stable across interventions where the mechanism
   claims they should be invariant;
3. express legitimate variation at the correct timescale;
4. reduce compensatory distortion in unrelated parameters;
5. retain uncertainty when the evidence is non-identifying; and
6. require the fewest costly simulator, reasoning, and physical experiments.

## Core method

### 1. Typed residual field

Convert each action-frozen real/sim pair into a phase-aligned residual field:

\[
r_i = [r_{joint}, r_{EE}, r_{pawn}, r_{gripper}, r_{contact},
r_{timing}, r_{consequence}]_i.
\]

Keep curves and event intervals. Do not collapse the field to one RMS or one
success score. Each residual factor records which observables are physical,
derived, simulated, unavailable, or uncertain.

### 2. Structural-surprise trigger

SAIL should open model-structure search when one or more of these occur:

- an important residual fingerprint remains after bounded parameter fitting;
- a fitted parameter repeatedly hits a bound;
- a parameter departs implausibly far from its prior;
- one explanation requires the same nominal parameter to change across
  interventions where it should remain invariant;
- a parameter improvement on one phase or episode group reverses elsewhere;
- tuning order materially changes the selected explanation; or
- posterior predictive error is under-dispersed near a task boundary.

Define **compensation debt** for a structure as a declared combination of prior
departure, boundary pressure, intervention-specific drift, and task-local
regression:

\[
CD(S) =
\sum_b w_b
\left[
d_{prior}(\theta_b)
+ \eta_1 B_b
+ \eta_2 D_b^{inv}
+ \eta_3 R_b^{cross}
\right].
\]

This is not evidence that a parameter is physically wrong. It is a trigger
that the current structure may be forcing that parameter to absorb omitted
physics.

### 3. Candidate mechanism proposal

Candidate structures may come from:

- a deterministic residual-signature router;
- an existing mechanism plugin;
- a coding/VLM agent given the local graph neighborhood and selected
  multimodal evidence;
- a small enumerated model family; or
- a human-authored hypothesis.

The proposer returns a typed `StructureProposal`, not arbitrary prose:

- claimed phenomenon and phases;
- required latent state and parameters;
- predicted residual signature;
- expected invariant and variant intervention axes;
- confounders and discriminating probes;
- parameter bounds and priors;
- affected simulator components;
- predicted metric directions;
- computational/physical cost; and
- explicit rejection and abstention conditions.

### 4. Historical influence-set discovery

For a proposed mechanism \(m\), determine the smallest historical subgraph that
could have compensated for its absence.

The initial approximation combines:

1. graph reachability from the residual factors the plugin claims to explain;
2. residual-signature similarity;
3. finite-difference sensitivity of affected factors to a small plugin
   activation;
4. cross-Hessian or posterior-covariance coupling with existing parameters;
5. shared task phases and observations;
6. parameter boundary hits and prior departure; and
7. implementation dependencies such as solver, collision, actuator, and
   camera paths.

One practical rule is:

\[
I(m) =
\{f: sim(r_f, q_m) > \tau_r\}
\cup
\{b: |H_{m,b}| > \tau_H\}
\cup
\{b: Cov(m,b) > \tau_C\}
\cup
\operatorname{Ancestors}(f,m),
\]

where \(q_m\) is the mechanism's predicted residual signature. For a previously
absent discrete mechanism, use a bounded local activation or synthetic
adapter to estimate the sensitivity terms.

SAIL reopens only \(I(m)\), plus regression factors required by evaluator
policy. Full batch refitting remains a baseline and a safety fallback.

### 5. Mechanism-specific interventional invariance

Not every parameter should be globally invariant. Each plugin declares its
expected parameter scope and invariance axes.

Examples:

- command delay should remain stable across payload, pose, and board location,
  but may change with firmware or controller frequency;
- Coulomb friction may remain stable across command frequency but legitimately
  change with material/surface identity;
- board-to-base transform should remain stable within a mounted session but
  change after the board or camera is moved;
- jaw compliance may be stable across piece location but change after pad
  replacement or wear.

For mechanism \(m\), use a hierarchical parameterization

\[
\theta_m^{(e)} = \bar\theta_m + \delta_m^{(e)},
\quad
\delta_m^{(e)} \sim \mathcal N(0, \Sigma_m^{scope}),
\]

where the ABI specifies which deviations are allowed. Score candidate
structures with:

\[
J(S) =
L_{heldout}(S)
+ \lambda_{inv} D_{invalid\ drift}(S)
+ \lambda_{prior} D_{prior}(S)
+ \lambda_{complex} C(S)
+ \lambda_{task} L_{boundary}(S).
\]

`D_invalid drift` penalizes only parameter changes across intervention axes
where the plugin says the parameter should be invariant. This prevents the
method from calling legitimate session or surface changes “non-physical.”

The anti-compensation test is:

> Does the new mechanism improve held-out predictions while reducing
> unexplained variation or prior distortion in the old proxy parameters?

### 6. Structural-discrimination experiment selection

Ordinary active system identification often maximizes information about a
fixed parameter vector. SAIL should instead choose experiments that separate
competing structures and change a downstream certification decision.

For candidate action/probe \(a\):

\[
U(a) =
I(S;Y_a \mid \mathcal D)
+ \alpha I(G;Y_a \mid \mathcal D)
+ \kappa \mathbb E[\Delta CD \mid a]
- \lambda C_{compute}(a)
- \mu C_{hardware}(a)
- \rho R_{safety}(a),
\]

where:

- \(I(S;Y_a)\) is information about model structure;
- \(I(G;Y_a)\) is information about the twin-worthiness gate;
- \(\Delta CD\) is expected compensation-debt resolution; and
- costs and safety are explicit.

The useful probe is often the one where latency, damping, compliance, and
contact candidates predict different *shapes*, not the one with the largest
raw motion.

### 7. Sparse structural loop closure

For each candidate mechanism:

1. freeze the current graph, posterior, evaluator, and proposal receipt;
2. insert the plugin's variables and factors into a new graph branch;
3. reopen the historical influence set;
4. jointly refit the new mechanism and connected proxy parameters;
5. relinearize/replay only connected factors, then all required regressions;
6. compute held-out vector, invariance, compensation, task, and cost changes;
7. compare counterfactual explanatory credit before and after the update;
8. accept, reject, or retain the branch as unresolved; and
9. append the complete loop-closure receipt without rewriting history.

Counterfactual explanatory credit can be reported by refitted ablation:

\[
Credit(m) =
L(S \setminus m, \hat\theta_{-m}^{refit})
- L(S, \hat\theta_S).
\]

When a new mechanism is correct, its credit should rise while credit previously
assigned to compensating parameters declines or becomes more stable across
interventions.

### 8. Structural acceptance rule

A new structure is promotable only if all predeclared conditions pass:

- source action identity is unchanged;
- no split or evaluator leakage occurred;
- held-out vector prediction improves materially;
- task-boundary prediction improves or does not regress;
- invalid cross-intervention parameter drift decreases;
- compensation debt decreases or the remaining debt is explicitly explained;
- complexity and cost are justified by the gain;
- uncertainty is not spuriously collapsed;
- required regression episodes pass; and
- the result is not dependent on a solver-sensitive isolated point.

If structures remain indistinguishable, preserve particles and select the next
discriminating intervention. `Requires_new_measurement` is a correct outcome.

### 9. Twin-worthiness certification

SAIL improves and explains a simulator. It does not authorize downstream
training. A separate `TwinWorthiness.v1` evaluator decides whether the current
twin is predictive enough for:

- replay diagnosis;
- bounded trajectory generation;
- policy-training data;
- policy ranking; or
- physical transfer claims.

The current Sim2Claw twin may support trajectory diagnosis but does not yet
support publication-grade policy-training or policy-ranking claims because
grasp/consequence and independent paired-predictivity gates remain open.

## Physical-mechanism plugin ABI

The plugin is the unit that lets agent discoveries compound into deterministic
capability. A `PhysicalMechanism.v1` package should contain:

```text
identity
  mechanism_id, version, implementation hash, dependencies

physical claim
  phenomenon, latent state, parameters, units, timescale

activation
  residual fingerprints, task phases, trigger thresholds

invariance contract
  axes expected invariant, axes allowed to vary, hierarchy

observability
  required signals, missing-data behavior, confounders

identification
  safe probes, expected signatures, estimators, priors, bounds

simulation adapters
  engine-neutral semantics, MuJoCo implementation,
  optional Isaac/Bullet mappings, backend caveats

validation
  seeded faults, held-out traces, task-boundary tests,
  negative controls, uncertainty and calibration checks

validity envelope
  supported workcells, objects, speeds, loads, contacts,
  known-invalid regimes and abstention rules

maintenance
  drift indicators, revalidation triggers, replacement/repair signals
```

The distinctive abstraction is the coupling of physical semantics,
identification protocol, simulator implementation, invariance expectations,
and validity certificate. A generic software adapter or agent skill does not
provide that whole contract.

## Self-normalizing workcell controller

After SAIL has calibrated posterior beliefs, a higher-level decision layer can
choose among:

```text
change simulator structure or parameters
run another simulator experiment
request a physical identification probe
adapt the policy inside a certified twin
physically normalize or repair the workcell
abstain because the task is outside the validity envelope
```

The decision objective is:

\[
a^* = \arg\max_a
\mathbb E[\Delta \text{certified task confidence} \mid a]
- C_{compute}(a)
- C_{hardware}(a)
- R_{safety}(a)
- C_{downtime}(a).
\]

Examples of physical normalization include reseating a fixture, re-indexing a
camera, cleaning a contaminated surface, replacing a worn pad, or registering
a firmware change. These are measured interventions, not evidence that the
previous simulator was correct.

This controller should be an optional system contribution or follow-on paper.
Making it a core claim now would dilute the more defensible SAIL algorithm and
requires physical maintenance choices that the retained dataset cannot test.

## How the mechanisms synergize

```text
residual fingerprint + compensation debt
  -> structural surprise
  -> plugin candidates
  -> influence-set discovery
  -> competing structural particles
  -> intervention-specific invariance predictions
  -> structural-discrimination probe
  -> sparse physics loop closure
  -> explanatory-credit reallocation
  -> twin-worthiness certification
  -> posterior-conditioned data generation
  -> sealed policy improvement
```

The important feedback paths are:

- failed invariance identifies a proxy and opens structure search;
- a plugin's invariance contract tells the experiment selector what to vary;
- the selected intervention changes structural posterior weights;
- an accepted structure retroactively changes prior parameter attribution;
- the loop-closure receipt becomes a validation case for the plugin;
- repeated validation promotes the plugin into the reusable library;
- the certification gate determines whether policy improvement may begin; and
- downstream policy failures create new task-boundary residual factors but do
  not self-promote simulator changes.

## Evidence lanes for Sim2Claw

### Lane A — seeded synthetic benchmark now

Create rich oracle simulators, then deliberately remove one mechanism from the
agent-visible simulator:

- command delay;
- first-order actuator response;
- deadband/backlash;
- load-dependent compliance;
- jaw collision/pad geometry;
- contact compliance/friction state;
- camera latency/extrinsic offset; and
- object COM/inertia or support contact.

This lane can establish ground-truth structure recovery, sparse-update
correctness, active-probe efficiency, and plugin promotion. It proves the
method and harness, not physical transfer.

### Lane B — retained retired-workcell evidence now

Use immutable real traces and the historical simulator campaigns to test:

- graph ingestion and missing-observable behavior;
- tuning-order path dependence;
- historical influence sets;
- compensation-debt triggers;
- retrospective loop closure;
- prediction of already-run intervention effects; and
- truthful abstention.

Episode direction, speed, pose, pan, phase, and board location can form
retrospective **consistency strata**. They are not controlled physical
interventions, so this lane cannot by itself establish causal invariance or
correct physical mechanism recovery.

### Lane C — prospectively graph-native simulator work now

Before each new simulator run, freeze:

- parent structure and parameters;
- structural hypothesis and influence set;
- predicted residual/consequence directions;
- invariance expectation;
- expected information gain and cost; and
- accept/reject/abstain conditions.

The fixed-pad/force-retention family is the first graph-native family. Future
simulator experiments should be selected by the deterministic router before
testing the LLM proposer.

### Lane D — new related physical workcell later

The changed lighting, background, camera geometry, and possibly board pose do
not invalidate the study. They create an independent environment for three
separate questions:

1. **mechanism transfer:** does the same mechanism structure explain the new
   workcell?
2. **parameter transfer:** does the old posterior predict it before refitting?
3. **adaptation efficiency:** does warm-starting from the old graph require
   fewer probes than a cold start?

Run a small factorial identification battery before task trials:

- low versus high command frequency/speed;
- forward versus reverse motion;
- several load-relevant arm orientations;
- empty gripper versus controlled close/contact;
- free space versus known board/contact landmark; and
- unchanged versus deliberately re-indexed installation state where safe.

The overhead camera remains the main policy interface. Wrist/side views are
privileged observation channels for contact, slip, release, and annotation.

## Experimental methodology

### RQ1 — Does SAIL recover missing structure?

On seeded faults, compare mechanism localization, structural posterior,
parameter recovery, and held-out vector/task prediction.

### RQ2 — Does invariance reject compensation?

Construct pairs where two structures fit one trajectory but diverge under
frequency, load, direction, orientation, or contact interventions. Measure
correct model selection and parameter drift.

### RQ3 — Does loop closure improve calibration history?

Measure whether adding a mechanism revises the correct historical parameters,
reduces compensation debt, and improves held-out prediction with fewer
replays than full batch recalibration.

### RQ4 — Does structural acquisition save physical probes?

Compare ordinary Fisher-information parameter selection, residual-maximizing
probes, random probes, and SAIL structural-discrimination utility.

### RQ5 — Does the agent add value?

Compare a deterministic plugin router, an oracle candidate set, a VLM-only
tuner, and the governed coding/VLM proposer under identical tools and budgets.

### RQ6 — Does certification prevent negative policy transfer?

Compare downstream policy learning from:

- an uncalibrated twin;
- a lower-RMS but gate-failing twin;
- a SAIL-calibrated gate-passing twin; and
- real-only data.

The decisive outcome is whether the gate predicts when simulator-generated
data helps or hurts sealed real-aligned task performance.

## Baselines and ablations

Baselines:

- chronological one-coordinate tuning;
- random search, CMA-ES, and Bayesian optimization;
- BayesSim/SimOpt-style fixed-structure posterior fitting;
- COMPASS-style causal parameter pruning;
- active SysID with parameter Fisher information;
- VLM-only parameter proposals;
- static factor graph with full batch refitting; and
- full batch structural model selection.

Ablations:

- no compensation-debt trigger;
- no intervention-specific invariance;
- global invariance instead of plugin-declared scope;
- no influence-set sparsification;
- no counterfactual credit reallocation;
- no structural particles;
- no task-boundary term;
- no coding/VLM proposer;
- no twin-worthiness gate; and
- generic code plugin instead of the mechanism ABI.

## Metrics

Algorithmic:

- top-1/top-k mechanism recovery;
- held-out joint, EE, object, contact, timing, and consequence error;
- cross-intervention invalid parameter dispersion;
- compensation debt and its change after closure;
- tuning-order/path dependence;
- structural posterior calibration and abstention;
- influence-set precision/recall against seeded ground truth;
- sparse update versus full-batch runtime and replay count;
- probes, simulator runs, reasoning calls, tokens, wall time, and cost; and
- regression/guardrail rejection rate.

Robotics:

- acquisition, bilateral retention, lift, transport, release, stable place;
- strict success and collateral motion;
- sim/real failure-mode agreement;
- policy/checkpoint ordering when sample size supports it; and
- warm-start versus cold-start physical calibration trials.

## Falsification criteria

SAIL is not supported if:

- ordinary full-batch model selection matches it at similar cost;
- invariance fails to distinguish true mechanisms from proxies;
- influence sets omit necessary history or approach full-graph size;
- loop closure changes explanations without improving held-out predictions;
- compensation debt does not anticipate omitted structure;
- the LLM proposer adds no value beyond the deterministic candidate library;
- the twin gate does not predict whether synthetic data helps; or
- the retained real case cannot support anything beyond a post-hoc narrative.

These are acceptable negative outcomes. The paper should report which part of
the method fails rather than collapsing everything into one benchmark score.

## Implementation sequence

### M0 — Freeze contracts

Implement and version:

- `CalibrationEvidence.v1`;
- `InterventionEnvironment.v1`;
- `PhysicalMechanism.v1`;
- `StructureProposal.v1`;
- `CalibrationGraph.v1`;
- `LoopClosureReceipt.v1`; and
- `TwinWorthiness.v1`.

### M1 — Evidence compiler

Import the V3 baseline, fixed-pad family, and the minimum historical campaign
spine. Preserve action identities, proof classes, missing data, splits, runtime
identities, and full residual vectors.

### M2 — Deterministic graph core

Build graph branches, structural particles, influence-set routing, connected
invalidation, cached sensitivities, batch fallback, and append-only receipts.

### M3 — Seeded SAIL benchmark

Implement delay, response, deadband, load/compliance, collision/pad, contact,
and camera faults with known ground truth. Run deterministic baselines first.

### M4 — Invariance and acquisition

Implement plugin-declared scope, hierarchical fits, compensation debt,
structural-discrimination utility, and active-probe comparison.

### M5 — Governed agent

Expose only residual summaries, local graph state, multimodal evidence bundles,
plugin schema, bounded adapter scaffolding, and read-only evaluator verdicts.
Benchmark the agent's marginal value over deterministic routing.

### M6 — Retained-real case study

Run the retrospective scale/transform/timing/deadband/load loop-closure case,
shuffled tuning orders, fixed-pad prospective family, and abstention analysis.

### M7 — Related-workcell replication

Measure new identities, run the factorial micro-probe battery, compare warm and
cold calibration, and freeze the physical task evaluation.

### M8 — Downstream self-improvement

Only after `TwinWorthiness.v1` passes the appropriate authority level, generate
strictly admitted simulated episodes, train ACT and the overhead-only GR00T
challenger, iterate counterexamples, and evaluate frozen candidates physically.

## First implementation boundary

The first code change should end at M1/M2 and produce one deterministic result:

> Given the current baseline and fixed-pad evidence, construct a typed graph,
> report which factors and parameter blocks would be reopened by a pad/contact
> mechanism proposal, and emit the current twin-worthiness verdict without
> changing any simulator parameter or policy action.

Do not put the LLM, VLA, hardware, or self-normalization controller in the
first implementation milestone. The proposed novelty must first exist as a
deterministic, testable update operator.
