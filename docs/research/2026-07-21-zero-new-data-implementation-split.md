# Zero-New-Data Implementation Split

**Status:** execution triage for the physics-loop-closure roadmap; no physical
setup, capture, robot motion, paid compute, training admission, or promotion
authorized

**Date:** 2026-07-21 America/Chicago

**Governing protocol:**
[`../../configs/hardware/similar_scene_revalidation_v1.json`](../../configs/hardware/similar_scene_revalidation_v1.json)

## Constraint

The original robot workcell is retired and cannot be recreated. No new sample
can become a held-out episode from that physical session.

A setup using the robot and chessboard may become available after several
days, but:

- lighting will differ;
- the visual background will differ;
- camera placement and calibration may differ;
- the board-to-robot transform may differ or be unknown until measured;
- table, fixture, gripper-tip, firmware, and joint calibration identity must be
  checked rather than assumed.

The future setup is therefore a **new related workcell/session by default**.
Even if its measured board-to-robot pose is close to the retired scene, it is
an independent replication surface, not retroactive evidence from the old
workcell.

## Determination

The original scene is not needed to implement the leading software ideas.
What is unavailable today is **new physical discrimination and validation**,
not the retained evidence graph or simulator intervention surface.

The project should proceed in two explicit lanes:

```text
Lane A — start now
retained evidence -> intervention ledger -> belief graph
  -> retrospective physics loop closure -> frozen benchmark
  -> information-gain routing -> governed LLM ablation

Lane B — wait for new setup and separate authority
new related-workcell identity -> measured transforms and clocks
  -> static/read-only observations -> safe identification probes
  -> independent new-session validation -> hierarchical comparison
```

The lanes may share schemas and mechanisms. They may not silently pool source
rows, validation roles, calibration identities, or proof claims.

## Integration with the active gap-closing investigation

The recommended architecture is **hybrid**, not exclusively retrospective.

Do not stop the active action-frozen investigation until every historical
campaign has been backfilled. Instead, establish a cutover point and make every
new intervention graph-native while a bounded historical importer reconstructs
the minimum causal spine in parallel.

The current force-retention/fixed-pad investigation is an especially good first
native case because it already contains:

- a named V3/timestep parent candidate;
- a one-coordinate fixed-pad intervention;
- byte-identical source-action evidence;
- per-jaw contacts and simulated force/retention traces;
- joint, EE, lift, transport, strict-success, and target-distance metrics;
- a strong consequence-distance change without improved task counts;
- rejected friction, anchor, moving-pad, placement, and solver-sensitive
  branches;
- an explicit diagnostic/non-promotion verdict;
- a frozen-evaluator caveat about progress after falling below the lift gate.

That structure is more valuable to the graph than another unrecorded sweep. It
should become the first `prospective_native` intervention family. The graph
must preserve that fixed pad 0.9 reduced mean final target distance while lift,
transport, and success counts did not improve; it must not convert the result
into a physical jaw-thickness estimate or a promoted simulator composite.

### Prospective sidecar for the active thread

Before the next simulator intervention runs, freeze and record:

1. parent simulator candidate and complete parameter identity;
2. proposed mechanism and why the current residual fingerprint supports it;
3. exact coordinate/block being changed and its bounds;
4. source action hashes and evaluator/metric version;
5. episodes eligible for selection versus regression-only use;
6. predicted direction and approximate magnitude for each important metric;
7. expected information gain and runtime/reasoning cost;
8. predeclared accept, reject, and abstain conditions.

After the run, append observed residual vectors, consequences, uncertainty,
boundary hits, rejected hypotheses, artifacts, and verdict. Never overwrite the
forecast. This turns each new active-thread experiment into a prospective test
of the graph and router rather than another result explained after the fact.

### Minimum historical backfill

Physics loop closure needs history, but it does not need every raw grid point
before prospective operation starts. Backfill these authoritative milestones
first:

1. clean/V3 action-frozen baseline;
2. geometry/event fit and the confounded roughly 301.3 mm scale candidate;
3. nominal-tag-conditioned support for the retained 355.6 mm scale;
4. record-then-ZOH timing and delay family;
5. lift/elbow deadband family;
6. elbow load-response family and significant RMS result;
7. timestep 0.45 lift-count improvement;
8. base-height and measured-joint-state upper-bound negative controls;
9. rubber friction/geometry retention campaign;
10. dense force-retention traces and fixed-pad 0.9 diagnostic.

For each family, initially ingest:

- baseline, selected diagnostic candidate, and decisive rejection candidates;
- declared mechanism block and parameter bounds;
- selection/validation roles;
- action identities;
- full evaluator vector and phase summaries;
- implementation/config/artifact identities;
- authority and claim boundary.

Keep full grid artifacts addressable, but do not make thousands of candidate
nodes a prerequisite for the first graph. Import individual grid points only
when needed to estimate local response surfaces, covariance, or a benchmark
counterfactual.

### What is inherently retrospective

These evaluations require prior campaigns by definition:

- whether a newly introduced mechanism should cause earlier proxy parameters
  to move back;
- whether tuning order changed the selected explanation;
- shuffled-order and loop-closure-disabled baselines;
- residual-fingerprint learning from observed intervention responses;
- calibration of information-gain predictions against completed experiments;
- reconstructing which prior result was compensating for a missing mechanism.

Retrospective use must be labelled as such. A forecast reconstructed after the
outcome is known cannot count as prospective routing accuracy.

### What should be prospective from the cutover

These components improve the active thread immediately:

- immutable intervention/event logging;
- mechanism ontology and parent/child graph edges;
- pre-run effect forecasts;
- information-gain ranking of candidate next experiments;
- cached local sensitivities and connected invalidation;
- typed LLM structure proposals;
- abstention when only a missing physical observable can discriminate;
- promotion of repeated, evaluator-supported patterns into deterministic
  plugins and regression tests.

### Recommended operating sequence

```text
cut over active thread to graph-native receipts
  -> ingest the current fixed-pad/retention family
  -> backfill the ten historical campaign milestones
  -> fit the first residual router and correlated blocks
  -> freeze a forecast for the next active simulator probe
  -> run and score that probe prospectively
  -> separately run the retrospective loop-closure benchmark
```

This gives the publication both kinds of evidence:

- **retrospective:** the graph can reinterpret and reduce path dependence in
  the completed calibration history;
- **prospective:** frozen forecasts and experiment rankings help choose and
  predict new active-thread simulator interventions.

Without the prospective cutover, the method risks looking like an elaborate
post-hoc narrative. Without the minimum historical backfill, it cannot
demonstrate the loop-closure contribution. Both are needed.

## Top ideas: start-now versus wait split

| Idea | Start today without new data? | What can be completed now | What must wait |
| --- | --- | --- | --- |
| Immutable intervention ledger and vector residual tensor | **Yes — full P0 implementation** | Define the schema; ingest retained source identities, action hashes, simulator variants, phase metrics, consequences, roles, and authority labels; validate missing-data behavior. | Nothing for the software contract. New data only add new factors later. |
| Calibration belief graph and correlated blocks | **Yes — full P0 implementation** | Build mechanism, parameter-block, episode, residual, candidate, and evaluator nodes; represent dependencies, covariance/local curvature, and structural alternatives. | Physical posterior updating and cross-session validation. |
| Physics loop closure | **Yes — retrospective proof** | Reconstruct one compensation case from retained campaigns; introduce a better mechanism; predict and jointly refit the connected block; compare shuffled tuning order and no-loop-closure controls. | Claim that the revised explanation generalizes to a new physical session. |
| Residual fingerprints and mechanism routing | **Yes — bounded retrospective version** | Derive phase-aligned signatures from joint, EE, aperture, contact, lift, slip, transport, and consequence vectors; train or author a small router with abstention. | Calibration against independently labelled new physical mechanisms. |
| Interventional invariance scoring | **Yes — simulator/episode invariance only** | Score stability across retained episodes, phases, timing, load-bias, solver/timestep, gripper, and contact variants. | Cross-session, lighting, pose, payload, wear, or workcell invariance claims. |
| Failure-boundary/CEGIS refinement | **Yes — simulator and synthetic evidence** | Use GapBench faults, retained near-boundary grasp cases, corrective proposals, strict evaluators, and rejection receipts. | Confirmation that selected counterexamples correspond to future real failures. |
| Task-aware value-of-information scheduler | **Yes — full decision contract** | Rank simulator evaluations and reasoning calls by expected evaluator-relevant uncertainty reduction and cost; permit `requires_new_measurement` as a terminal answer. | Calibration of predicted information gain for actual physical probes. |
| Governed model-structure agent | **Yes — full bounded harness** | Give the model residual summaries and graph state; require typed mechanism/edge/probe proposals; compare providers or reasoning settings without letting them fit or promote results. | Physical execution of agent-proposed probes. |
| Promotion flywheel to deterministic plugins | **Yes — infrastructure and synthetic acceptance** | Turn repeated accepted hypotheses into versioned mechanism adapters, residual fingerprints, estimators, tests, and receipts; exercise on synthetic cases. | Promotion of a plugin as physically validated for the new workcell. |
| Canonical trace and safe-probe schema | **Yes for schema/importers** | Finish commanded/measured joint, effort, timestamp, camera, object, contact, latency, and outcome contracts; truthfully preserve unavailable fields. | Populating observables absent from the original recordings and validating physical event proxies. |
| Physical parameter ontology and MuJoCo adapter | **Yes** | Define engine-independent concepts and compile them into declared MuJoCo changes with hash-bound identities. | Cross-engine semantic validation or physical parameter identification. |
| Structural posterior/model particles | **Yes — small version** | Retain discrete geometry, timing, compliance, gripper, and contact explanations with bounded continuous blocks; add posterior/score and abstention behavior. | Reliable physical posterior weights when old evidence cannot distinguish branches. |
| Timescale separation and drift model | **Yes for schema, no for drift estimates** | Separate hardware-static, installation, object, session, episode, and time-varying nodes. | Multiple time-separated captures under a known setup. |
| Cached sensitivities and connected replay | **Yes** | Cache per-candidate residuals, finite differences, and graph dependencies; invalidate only affected factors. | No physical dependency. |
| Sparse learned discrepancy correction | **Limited today** | Implement a low-capacity, cross-validated challenger and negative controls using retained/synthetic cases. | Credible generalization or physical residual correction; the current corpus is too small for a strong learned-model claim. |
| Physical calibration kit | **Design only today** | Freeze probe definitions, fixtures, sensor requirements, tolerances, clocks, and authority gates. | Fabrication, setup measurements, capture, and motion. |
| Safe micro-identification actions | **Simulate/design only today** | Author parameterized probes, predicted observability, safety envelopes, simulator tests, and gateway preconditions. | Reviewed hardware authority and physical execution. |
| Workcell fingerprint/meta-twin | **Schema and synthetic test only** | Add a session/workcell latent identity and demonstrate synthetic recovery. | At least one new independently measured setup for a two-session test; several cells for a fleet claim. |
| Fleet-posterior domain randomization | **No empirical fleet claim today** | Define posterior-conditioned sampling and test it with synthetic workcell identities. | Multiple real workcells or partner datasets. |
| Q-value/world-model inversion | **Defer** | Only design a separate simulation study. | Goal-conditioned critics, known rewards, appropriate state coverage, and separately gathered evidence. |

## What should be implemented today

### ZD-1 — Freeze the evidence inventory

Build a read-only importer that materializes one manifest over all retained
campaigns relevant to the B--G gap:

- physical episode and source-action identities;
- geometry and scale candidates;
- reset/reference variants;
- timing and actuator response variants;
- deadband and load-bias variants;
- timestep and solver variants;
- gripper, rubber, contact, and retention variants;
- per-episode vector metrics and phase curves;
- grouped-fit, validation, regression-only, and synthetic roles;
- explicit missing observables;
- current proof class and evaluator verdict.

The importer must fail closed when an ignored artifact is missing unless its
tracked receipt contains a hash, regeneration path, and enough content to
reconstruct the declared metric. It must never infer an unavailable physical
measurement from a simulator result.

### ZD-2 — Implement `CalibrationEvidence.v1`

Suggested top-level entities:

```text
WorkcellIdentity
SessionIdentity
EpisodeIdentity
ActionIdentity
ObservationAvailability
MechanismBlock
ParameterCandidate
SimulatorIntervention
ResidualVector
EvaluatorVerdict
EvidenceFactor
```

Every new-session entity must have a distinct workcell/session ID. A link such
as `same_robot_hardware` or `same_board_physical_identity` is an observed
relationship, not permission to merge evidence.

### ZD-3 — Implement the graph and retrospective loop-closure case

Use the most defensible existing compensation story:

1. an unconstrained event fit preferred a roughly 301.3 mm board playing side;
2. source-frame tag plausibility strongly favored the retained 355.6 mm board
   hypothesis, while remaining nominal-print-conditioned rather than metric
   authority;
3. timing, deadband, and load-response mechanisms later explained substantial
   joint and EE residual structure without changing source actions;
4. the graph should mark scale, transform, delay, deadband, load response, and
   EE residual factors as correlated rather than freezing the early geometric
   proxy;
5. loop closure should reopen that connected block, retain multiple plausible
   structural branches, and compare their frozen vector predictions.

This is a retrospective attribution demonstration. It cannot establish the
physical board size or prove the selected actuator mechanism.

### ZD-4 — Build benchmark baselines and negative controls

Run the same evidence through:

- chronological one-variable tuning;
- chronological tuning under several shuffled orders;
- random bounded search;
- flat parameter optimization;
- block-aware optimization without loop closure;
- graph loop closure without an LLM;
- graph loop closure with the governed structure proposer;
- an oracle with seeded-fault access on synthetic cases only.

Measure held-out vector error, evaluation count, intervention-effect ranking,
path dependence, uncertainty coverage, abstention, guardrail rejection, and
LLM cost. All old confirmation material remains regression-only.

### ZD-5 — Make the information-gain router useful before hardware exists

The router's action space should include:

- run a bounded simulator intervention;
- jointly refit a correlated parameter block;
- compare structural particles;
- request an LLM mechanism proposal;
- compile/test a proposed adapter;
- stop because uncertainty is not evaluator-relevant;
- stop with `requires_new_measurement` and name the discriminating observable.

The final outcome is important: the system should be rewarded for recognizing
that no amount of simulator compute can recover a missing physical observable.

### ZD-6 — Add the agent only after deterministic baselines

The model receives:

- residual fingerprints and phase localization;
- current graph neighborhood;
- parameter correlations and boundary hits;
- structural particles and their held-out evidence;
- already-tried interventions;
- missing observables;
- a bounded proposal schema.

It may propose a mechanism, dependency edge, simulator adapter, or future
probe. Deterministic code owns numerical fitting, replay, evidence joining,
cost accounting, and promotion. Benchmark the agent against deterministic
routing so a model call is justified by measured marginal value.

## What cannot be recovered from the retired scene

No future setup can retroactively create:

- an unopened held-out episode from the original acquisition distribution;
- timestamps, force, current freshness, camera calibration, depth, or object
  poses that were not recorded in the retired session;
- independent metric validation of original qualitative markers;
- physical identification of the original rubber/contact parameters;
- an exact same-scene test of the fitted simulator candidate;
- proof that a future success would have occurred in the retired scene.

These remain permanent limitations and should be presented as such in the
publication.

## How to treat the future robot-and-board setup

### Identity rule

Apply the existing protocol literally. `same_workcell` requires independent
confirmation of every declared identity item. If any item is unknown, assign a
new `WorkcellIdentity` and `SessionIdentity`.

Do not use scene resemblance, similar camera framing, or a low image-alignment
error as identity evidence.

### Positioning branches

#### Branch A — board-to-robot transform differs or is unknown

This still supports:

- joint timing, tracking, deadband, current, and free-space load probes;
- gripper aperture and empty-close measurements;
- new scene calibration and task evidence under its own evaluator;
- a first test of whether mechanism classes transfer after conditioning on a
  new installation transform.

It does **not** support direct coordinate-wise comparison of old and new pawn
trajectories.

#### Branch B — transform differs but is measured accurately

This is scientifically useful. Store the transform as a session-specific
latent/observed factor and compare robot-, board-, object-, and target-relative
metrics after normalization. Deliberate measured variation is more informative
for interventional invariance than visually approximating the old setup.

#### Branch C — transform is independently measured to be close

Predeclare position and orientation tolerances before viewing task outcomes.
If the setup falls inside them, describe it as a **closely matched related
workcell**, not the original workcell. It can test warm-start transfer of the
old posterior and simulator candidates, but it remains independent-session
evidence.

## Lighting and background consequences

| Evidence surface | Effect of changed lighting/background | Required treatment |
| --- | --- | --- |
| Commanded/measured joint tracking | Usually low | Preserve hardware, firmware, calibration, clock, and payload identities. |
| Free-space timing/deadband/load probes | Usually low | Compare only after command/observation semantics and timestamps are verified. |
| Gripper aperture/current | Usually low to moderate | Control jaw hardware, gauges, temperature, current freshness, and close speed. |
| Tag/board metric registration | Moderate | Recalibrate camera intrinsics/extrinsics and report detection uncertainty. |
| RGB object trajectory extraction | High | Revalidate detector/segmenter, uncertainty, occlusion, and color/ISP sensitivity. |
| VLA or image-policy evaluation | Very high | Treat as a new visual domain; do not attribute failures solely to physics. |
| State-based ACT replay | Low visual effect | Geometry and state calibration still define a new workcell. |
| 3DGS or visual overlay | High | Visual corroboration only unless new metric anchors and camera recovery are admitted. |

The future setup should not spend effort matching background aesthetics unless
the experiment explicitly studies visual-domain transfer. Metric transforms,
timestamps, gripper hardware, controller identity, and observability are more
valuable than visual resemblance for the calibration-graph study.

## Minimum future collection, once separately authorized

### Phase N0 — static identity and read-only observations

- robot, servo, firmware, calibration, and joint-map identities;
- gripper-tip identity, photographs, dimensions, and measured aperture;
- board physical identity, dimensions, fiducial family, and measured tag size;
- camera identity, mode, intrinsics, extrinsics, mount, and timestamps;
- table/fixture geometry and wide setup photographs;
- measured board-to-base transform with uncertainty;
- stationary joint/current observations and clock-alignment target;
- board and object detections without motion.

### Phase N1 — empty-gripper identification

Only after motion authority:

- bounded free-space reversals at several speeds;
- orientation/load holds with known payload state;
- repeated empty open/close cycles;
- commanded and measured aperture, velocity, fresh current, command-write,
  bus-ack, observation, and camera timestamps;
- repeated pre/post blocks for short-term drift.

These probes are valuable even if the chessboard position differs.

### Phase N2 — board/object interaction

Only after separate task authority:

- known gauges or compliant coupons for jaw/contact observability;
- a small set of interior, edge, and horizontal pawn moves with newly measured
  coordinates;
- independently annotated contact/grasp/release outcomes;
- metric object keypoints or pose with uncertainty;
- frozen fit/validation/held-out roles before parameter fitting.

Do not optimize the new setup by repeatedly opening its held-out tasks.

## How new evidence joins the graph

Use a hierarchical relationship rather than pooled rows:

```text
shared robot-family mechanism
  ├── retired_workcell / original_session
  │     └── immutable retained factors and permanent missing observables
  └── new_related_workcell / new_session
        ├── new transform and camera factors
        ├── new visual-domain factor
        ├── new controller/gripper identity checks
        └── new fit, validation, and held-out roles
```

Test three questions separately:

1. **Mechanism transfer:** does the same mechanism class explain both sessions?
2. **Parameter transfer:** does the old posterior predict the new session before
   refitting?
3. **Adaptation efficiency:** does warm-starting from the old graph reduce new
   probes or simulator evaluations versus a cold start?

Only the third question begins to support the longer-term workcell-family
thesis. Similar final parameter values alone are not enough.

## Revised implementation priority

### Start today

1. Intervention ledger/importer.
2. `CalibrationEvidence.v1` and workcell/session identity model.
3. Calibration belief graph and structural particles.
4. Retrospective scale/timing/load loop-closure case.
5. Shuffled-order and no-loop-closure baselines.
6. Residual fingerprint router with abstention.
7. Information-gain scheduler over simulator/compute/reasoning actions.
8. Governed LLM structure-proposal ablation.
9. Plugin promotion path on synthetic and retrospective cases.
10. Future probe schemas and authority-gated capture contract.

### Wait for any newly instrumented setup

1. Static identity and clock validation.
2. New metric board/camera/robot registration.
3. Empty-gripper and free-space timing/load probes.
4. New-session posterior update and mechanism-transfer test.
5. Longitudinal drift estimation.

### Wait for measured board-to-robot comparability

1. Robot-/board-relative old-versus-new task trace comparisons.
2. Warm-start transfer of scene/task simulator candidates.
3. Task-boundary and consequence agreement across sessions.
4. Adaptation-efficiency comparison against a cold-start calibration.

### Wait for multiple workcells or partners

1. Workcell fingerprint learning.
2. Leave-one-workcell-out benchmark.
3. Fleet-posterior domain randomization.
4. Foundation discrepancy model.

## Publication framing

The paper can be completed in two stages:

1. **Now:** a retrospective and synthetic benchmark demonstrating governed
   loop closure, reduced path dependence, calibrated abstention, and simulator
   evaluation efficiency using the retained original-session evidence.
2. **Later:** an independently identified related-workcell replication testing
   mechanism transfer and warm-start calibration efficiency under changed
   lighting, background, and possibly geometry.

Failure to recreate the scene should not be hidden. It sharpens the research
question: can the calibration machinery preserve what was learned from a
retired workcell without pretending the next setup is identical?

## Final recommendation

Begin the top nine P0 software components now. Do not wait for the robot setup,
and do not spend the next few days trying to infer missing original-session
measurements from simulation.

When the hardware becomes available, prioritize independent metric transforms,
clocked proprioception, empty-gripper baselines, and a few discriminatory
probes. Exact visual recreation is neither achievable nor necessary. If the
board pose differs but is measured, that variation is useful evidence for the
belief graph. If it merely looks similar but is not measured, it provides
almost no calibration authority.
