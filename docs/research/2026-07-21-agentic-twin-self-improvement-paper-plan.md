# ClawLoop: Evidence-Gated Agentic Digital Twins for Low-Data Robot Self-Improvement

**Status:** proposed paper thesis and execution plan; no robot motion, new
capture, paid compute, training admission, simulator promotion, or physical
claim is authorized by this document

**Date:** 2026-07-21 America/Chicago

**Builds on:**
[`physics-loop-closure-practicality-ranking`](2026-07-21-physics-loop-closure-practicality-ranking.md),
[`zero-new-data-implementation-split`](2026-07-21-zero-new-data-implementation-split.md),
[`publication-closeout-and-real2sim-agent-benchmark`](2026-07-19-publication-closeout-and-real2sim-agent-benchmark.md),
and the current
[`force-retention/fixed-pad diagnostic`](../run-logs/2026-07-21-pawn-bg-force-retention-fixed-pad.md)

**Algorithmic core:** the more precise novelty and methods specification is
[`SAIL: Structure-Adaptive Interventional Loop Closure`](2026-07-21-sail-structure-adaptive-interventional-loop-closure.md).
`ClawLoop` names the end-to-end system; `SAIL` is the proposed paper's central
inference contribution.

## Decision

The most powerful coherent paper is not a collection of every available idea.
It is a three-part method with one downstream proof:

1. **Agentic physics loop closure.** Coding and multimodal reasoning agents
   maintain an explicit belief graph over geometry, timing, actuator,
   compliance, gripper, contact, object, camera, and observation mechanisms.
   When a newly implemented mechanism explains a residual better than an old
   proxy, the system re-opens the connected parameter block and retroactively
   refits it against immutable real replay anchors.
2. **A predictive twin-worthiness gate.** A simulator is not accepted because
   it looks realistic, lowers one RMS, or succeeds on its own reward. It must
   predict held-out trajectory, event, task-consequence, and, when enough
   candidates exist, policy-ranking differences under unchanged actions.
3. **Evaluator-gated self-improvement.** Only after passing that gate may the
   frozen twin generate action candidates, domain-posterior variations, and
   synthetic training episodes. A separate evaluator—not an LLM, trainer, or
   simulator reward—admits data and policy generations.
4. **Low-data SO-101 demonstration.** Starting from the retained overhead-view
   teleoperation corpus, show whether the gated twin enables a goal-conditioned
   ACT policy and a pretrained VLA challenger to improve first in sealed
   simulation and then, if authorized, in an independently identified related
   physical workcell.

The concise research claim is:

> A coding-and-perception agent can turn sparse robot traces into a
> task-predictive digital twin more efficiently and with less path-dependent
> calibration than sequential tuning; once the twin earns predictive trust, a
> sealed synthetic-data flywheel can improve a robot policy without allowing
> simulator error, LLM judgment, or training loss to self-promote.

The working paper title is:

> **ClawLoop: Evidence-Gated Agentic Digital Twins for Low-Data Robot
> Self-Improvement**

The strongest one-sentence novelty is:

> The agent does not merely tune a simulator or improve a policy: it maintains
> revisable causal beliefs about the reality gap, must pass a downstream
> predictivity test before the simulator becomes a training environment, and
> then improves the policy through evaluator-admitted simulation experience.

## Novelty determination

A scoped search of the closest primary literature did not find a single paper
that combines all of the following in one evaluated manipulation system:

- a coding/VLM agent that proposes **model structure**, not only continuous
  parameter values;
- an immutable intervention ledger and correlated mechanism belief graph;
- **physics loop closure**, where adding a mechanism can retract and refit an
  earlier compensating explanation;
- unchanged-action sim/real replay with phase-aligned vector residuals;
- an explicit gate measuring whether the twin predicts task consequences and
  policy ordering, not only parameter or trajectory fit;
- posterior-conditioned synthetic action generation and data admission; and
- a recursively improved policy whose generations cannot edit or promote
  their own evaluator.

This is a scoped novelty assessment, not proof that no related unpublished or
unindexed work exists. The closest works cover important subsets:

| Work | What it already covers | What remains distinct here |
| --- | --- | --- |
| [BayesSim](https://arxiv.org/abs/1906.01728) and [SimOpt](https://arxiv.org/abs/1810.05687) | Posterior/adaptive simulator parameter distributions from real behavior | No coding/VLM model-structure agent, graph loop closure, or evaluator-gated recursive policy/data pipeline |
| [COMPASS: What Went Wrong?](https://proceedings.mlr.press/v229/huang23c.html) | Causal graph over simulator parameters and trajectory discrepancy | The graph is learned for parameter pruning; it does not provide an immutable agent ledger, retroactive explanation retraction, twin-worthiness gate, and policy flywheel |
| [ASID](https://arxiv.org/abs/2404.12308) | Active real exploration for sample-efficient physical-property identification | No coding-agent calibration graph or downstream evaluator-gated synthetic policy improvement |
| [Vid2Sid](https://arxiv.org/abs/2602.19359) | Foundation perception plus a VLM that diagnoses paired sim/real video and proposes physics updates | No demonstrated causal loop closure, policy-predictivity admission gate, or recursive synthetic policy training |
| [ASIA](https://arxiv.org/abs/2605.10480) | Autonomous coding agent for model-class, training, and hyperparameter search in system identification | Not a contact-rich digital-twin/policy pipeline; its own discussion highlights leakage, transparency, and reproducibility risks that our sealed evaluator addresses |
| [RialTo](https://arxiv.org/abs/2403.03949) | Low-data digital twins, inverse distillation, and simulation RL for robust manipulation | Does not make agentic, revisable system identification and predictive twin admission the central mechanism |
| [ReBot](https://arxiv.org/abs/2503.14526) | Real-to-sim-to-real video synthesis for adapting VLAs with automated synthetic data | Focuses on data/video synthesis rather than evidence-gated physical-model calibration and consequence predictivity |
| [SIMPLER](https://proceedings.mlr.press/v270/li25c.html) and [REALM](https://arxiv.org/abs/2512.19562) | Simulators validated by correlation with real policy behavior and ranking | Evaluation environments, not an agentic calibration-to-self-improvement system |
| [WorldEval](https://arxiv.org/abs/2505.19017) | World-model policy and checkpoint ranking | Learned video-world evaluation, not explicit action-frozen physics diagnosis and digital-twin calibration |
| [RISE](https://arxiv.org/abs/2602.11075) | Self-improving VLA policies through imagined rollouts and a value model | Assumes a useful learned world model; it does not diagnose and certify a low-data physics twin before self-improvement |

The paper must compare against these components rather than claiming that
agentic system identification, posterior fitting, digital twins, simulated
policy evaluation, synthetic VLA data, or self-improvement are individually
new.

## Why this combination is stronger than the alternatives

### It attacks the actual scientific failure mode

The present project already demonstrates that lower training loss and lower
open-loop action error do not imply closed-loop task success. It also shows
that a simulator change can significantly lower joint and end-effector RMS
without improving grasp, transport, or strict success. The missing concept is
not another optimizer. It is a rule for deciding when the simulator has become
predictive enough to support downstream learning.

### It turns the current small dataset into a contribution

The retained physical corpus is too small and internally imperfect to support
a broad claim that a VLA learned chess manipulation. It is well suited to a
low-data calibration study because it contains synchronized actions, measured
joint traces, overhead video, multiple task directions, successful and failed
labels, and action-frozen simulator replays. The method should explicitly
measure how much useful twin and policy improvement can be extracted per real
episode.

### It remains publishable if the final physical policy result is modest

The paper can still contribute:

- a seeded-fault agent benchmark;
- a prospective and retrospective physics-loop-closure evaluation;
- a task-predictive simulator admission protocol; and
- the SO-101 case study with truthful negative or partial transfer results.

A physical baseline-to-candidate success improvement would make the paper much
stronger, but the methods paper must not collapse if one small VLA experiment
fails.

## The full gated pipeline

```text
retained real teleoperation and video
  -> immutable evidence compiler
  -> phase-aligned residual tensor
  -> mechanism belief graph and structural particles
  -> coding/VLM hypothesis and probe proposals
  -> deterministic bounded fitting and action-frozen replay
  -> physics loop closure and retroactive connected-block refit
  -> frozen twin-worthiness evaluator
       | fail: abstain, collect a discriminating measurement, or revise model
       | pass
       v
  -> posterior-conditioned simulator ensemble
  -> deterministic geometric/IK/trajectory teacher search
  -> strict replay and data admission
  -> real-anchored ACT training + pretrained VLA challenger
  -> sealed posterior/counterexample simulation evaluation
  -> admit or reject policy generation
  -> repeat synthetic improvement until budget/plateau stop
  -> freeze baseline and candidate
  -> identify independent related physical workcell
  -> paired physical evaluation with overhead policy input
     and wrist/side evaluator-only sensing
```

The calibration lane and the policy-improvement lane must be separate. During
calibration, every physical source action remains byte-identical across
simulator variants. Geometric action generation, IK, trajectory optimization,
corrective suffixes, or VLA changes begin only after the twin gate and can
never be presented as evidence that the original simulator gap was closed.

## Stage 0 — Freeze the scientific contract

Before further simulator tuning or policy training, freeze:

- the primary hypothesis and the three contributions above;
- `retired_workcell` versus `new_related_workcell` identities;
- data roles: fit, grouped validation, regression-only, sealed simulation,
  and future physical evaluation;
- task outcomes and phase metrics;
- the agent tool tiers and per-case budget;
- the predictive twin gate;
- the policy-generation and data-admission rules;
- the physical baseline/candidate comparison; and
- the main analyses and ablations.

Do not choose the paper metric after seeing which intervention wins. The
current frozen evaluator can remain immutable for historical comparability,
while a separately versioned publication evaluator adds better phase and
retained-grasp diagnostics. Neither version may be silently rewritten.

## Stage 1 — Compile the retained evidence

### 1.1 Evidence identity

Every episode, action array, frame stream, simulator candidate, runtime,
metric implementation, and evaluator receives a content identity. Preserve:

- commanded and measured joint positions;
- velocities and available motor effort/current;
- command, observation, and camera timestamps;
- overhead frames and any additional source views;
- estimated object trajectories with uncertainty;
- contact, closure, lift, retention, slip, release, and placement events;
- strict successes, failures, and disputed labels; and
- missing or unqualified fields rather than inferred substitutes.

### 1.2 Phase-aligned residual tensor

For each action-frozen real/sim pair, retain curves rather than only scalar
minima:

- per-joint position and velocity residual;
- end-effector position and orientation residual;
- end-effector-to-pawn and pawn-to-destination distance;
- gripper command, measured position, simulated aperture, and contact state;
- object XY/Z trajectory and velocity;
- acquisition, lift, transport, release, and settle timing;
- bilateral contact retention, contact force diagnostics, and slip; and
- task consequence and collateral displacement.

Align both by wall time and by observable task phase. A scalar RMS is useful
but cannot own model selection because timing and contact failures can average
away.

### 1.3 Multimodal extraction

Use deterministic vision first: camera calibration, AprilTag/ChArUco corners,
segmentation, optical flow, pawn keypoints, and uncertainty propagation. Give
the multimodal model synchronized frame strips, plots, and metadata—not an
unbounded raw video—and require typed outputs:

- event interval and confidence;
- visible geometric discrepancy;
- competing physical explanations;
- which observation could discriminate them; and
- `abstain` when the view is occluded or non-metric.

VLM annotations remain hypotheses or noisy observations until a deterministic
measurement or evaluator admits them.

## Stage 2 — Build and calibrate the digital twin

### 2.1 Belief graph

Represent five kinds of variables separately:

1. **Static embodiment:** link geometry, mass/inertia priors, collision meshes,
   jaw topology, and joint semantics.
2. **Installation/session:** board-to-base transform, camera calibration,
   joint zeros, firmware/controller profile, and clock offsets.
3. **Actuation:** latency, zero-order hold, servo response, deadband,
   hysteresis, load-dependent bias, backlash, and compliance.
4. **Interaction:** aperture mapping, rubber pad geometry, contact/friction,
   pawn mass/inertia/COM, board contact, and release dynamics.
5. **Episode state:** initial joint state, pawn center/pose, destination,
   distractors, and observation quality.

Keep genuinely different model structures as particles. Do not force missing
compliance, incorrect gripper topology, and a friction coefficient into one
continuous posterior.

### 2.2 Governed agent loop

At each iteration:

1. A residual router produces ranked mechanism hypotheses with calibrated
   abstention.
2. A coding/reasoning agent may propose a new mechanism implementation, graph
   edge, parameter block, or discriminating simulator/physical probe.
3. The proposal is schema-checked, bounded, linted, unit-tested, and evaluated
   for expected information gain and cost.
4. Deterministic code runs fitting and action-frozen replay.
5. A separate evaluator compares the predeclared residual vector and
   consequences.
6. The graph posterior and intervention ledger are appended, never rewritten.
7. Repeatedly supported proposals can become reviewed deterministic plugins.

The LLM does not numerically fit unconstrained parameters, edit evaluation
thresholds, admit training examples, or command the physical arm directly.

### 2.3 Physics loop closure

When a new mechanism is introduced:

1. find the graph-connected parameters that previously compensated for it;
2. predict which old parameters should move and in which direction;
3. jointly refit only that block using the same data roles;
4. replay every affected frozen episode with identical source actions;
5. compare against no-loop-closure and shuffled-tuning-order baselines; and
6. preserve both branches if the evidence cannot discriminate them.

The method wins if it reduces path dependence and simulator evaluations while
improving frozen vector fidelity. Recovering a plausible physical coefficient
is secondary because several parameterizations may be observationally
equivalent in this dataset.

### 2.4 Value-of-information scheduling

Rank each next intervention by:

`expected evaluator-relevant uncertainty reduction / (rollouts + tokens + wall time + physical risk)`

Available actions include:

- reuse a cached sensitivity;
- run one bounded simulator perturbation;
- implement and test a model structure;
- ask a multimodal model to inspect selected frames;
- request a read-only future measurement;
- propose one operator-gated micro-identification action; or
- return `requires_new_measurement`.

The fixed-pad/force-retention family should be the first prospectively native
intervention family; the minimum historical campaign spine should be backfilled
for retrospective loop-closure tests.

## Stage 3 — Earn the right to use the twin for learning

The twin should pass a ladder, not one scalar threshold.

| Gate | Required evidence | Present status |
| --- | --- | --- |
| G0 Action integrity | Same source actions, shape, dtype, values, ordering, and hashes across calibration variants | Implemented for the active action-frozen lane |
| G1 Trajectory fidelity | Material grouped held-out improvement in joint and EE traces with no important phase regression | A significant retained-session RMS gain exists |
| G2 Interaction fidelity | Better acquisition, bilateral retention, lift/transport/release timing, pawn trajectory, and strict consequences | Not passed; current fixed-pad result changes distance but not task counts |
| G3 Predictive fidelity | Sim predicts real action/episode outcomes and, with enough policies/checkpoints, their relative ordering and failure modes | Not established with a sufficient independent paired cohort |
| G4 Robustness | Gains persist across posterior samples, episode groups, solver/timestep checks, and predeclared structural alternatives | Partial diagnostics only |

The publication gate should require at minimum G0–G2 before generating
training data and G3 before claiming that simulation selects a better real
policy. With at least three meaningful policy/checkpoint candidates, report
rank correlation and a SIMPLER-style rank-violation metric. With fewer
candidates, report paired consequence agreement and uncertainty instead of an
unstable ranking claim.

The current project is **not ready to treat the twin as a publication-grade
policy-learning environment**. It has passed a trajectory-fidelity milestone
but not the grasp/consequence or policy-predictivity gates. Infrastructure for
the downstream loop can be built now; results must remain synthetic-only until
the gate passes.

## Stage 4 — Generate simulator actions after the gate

Do not ask the LLM to emit raw joint targets at every control tick. Use it to
propose strategy, phase structure, goal constraints, or failure corrections;
use deterministic robotics tools for motion.

### 4.1 Teacher hierarchy

Generate candidates in this order:

1. replay admitted real teleoperation and constructive source trajectories;
2. retarget object- and destination-relative phase templates;
3. solve bounded IK and collision-free connecting motion;
4. use local joint-coordinate or trajectory optimization around the template;
5. search gripper timing and phase duration inside declared limits; and
6. let the agent propose a new correction primitive only when residual and
   failure evidence justify it.

Every candidate must satisfy joint, velocity, acceleration, workspace,
collision, and controller-interface limits before simulation.

### 4.2 Strict data admission

A candidate enters `D_sim(g)` only if a separate replay verifies:

- target identity and destination identity;
- collision and collateral gates;
- acquisition and minimum lift;
- retained transport;
- release and stable placement;
- action/controller conformance; and
- reproducibility across the required posterior/seed set.

Failed rollouts are useful as evaluator negatives and counterexamples, not
positive behavior-cloning examples. For counterexample repair, a failed prefix
may condition a separately verified corrective suffix, but the failed prefix
must not be relabeled as a successful demonstration.

### 4.3 Posterior domain randomization

Randomize from the calibrated posterior and its retained structural particles,
not from broad hand-written boxes. Separate:

- identified uncertainty to sample during policy training;
- epistemic alternatives that require robust success across particles;
- visual nuisance variation for the overhead stream; and
- out-of-support stress tests reserved for evaluation.

Domain randomization must not hide a known calibration error or widen until
the policy succeeds by chance.

## Stage 5 — Policy learning strategy

### Primary policy: goal-conditioned ACT

Use the existing state/goal ACT architecture as the primary scientific policy
because it is inexpensive, interpretable, and makes the effect of accepted
simulation data easier to attribute. Inputs should be robot state, selected
piece pose, destination pose, object descriptors, and observable skill state;
outputs remain the declared six absolute SO-101 joint targets.

Train and compare:

- real-only;
- uncalibrated-sim-only;
- real plus uncalibrated simulation;
- real plus calibrated, posterior-randomized simulation;
- calibrated simulation without the agent/loop-closure mechanism; and
- the full gated flywheel.

### VLA challenger: GR00T N1.7

Use GR00T N1.7 as the first pretrained VLA challenger because the project
already has a LeRobot/GR00T path and the public implementation supports a
custom embodiment and modality configuration. Configure the main policy with
exactly the consistent observation interface available in the source corpus:

- one named overhead RGB stream;
- SO-101 proprioceptive state;
- language instruction; and
- the same six-joint action semantics used at deployment.

The official GR00T implementation makes video keys part of the custom modality
configuration, so a single overhead stream is technically valid. It should be
measured against the lightweight ACT baseline rather than assumed to win
because it is pretrained. OpenVLA/OFT is a reasonable secondary challenger,
but adds another dataset/runtime surface and commonly expects on the order of
roughly 100 target-domain demonstrations; it should not be the critical path.

Use source-balanced minibatches and report the exact number of independent
real episodes separately from simulated frames. Frame count, augmented views,
and simulator variants do not increase the real-world sample size.

### Recursive generation loop

For policy generation `g`:

1. freeze policy `P_g`, twin posterior `T_k`, evaluator `E_k`, and budget;
2. roll `P_g` over task, posterior, and counterexample distributions;
3. cluster failures by phase/residual fingerprint;
4. ask the agent for bounded strategy or teacher-search proposals;
5. generate and strictly replay correction candidates;
6. append evaluator-admitted examples to a versioned dataset;
7. train candidate `P_(g+1)` from the same declared base/recipe family;
8. evaluate both policies on sealed sim cases and regression episodes;
9. promote only on a predeclared multi-metric rule; and
10. stop on budget, no accepted data, no significant gain, or evaluator drift.

The loop may recursively improve policies. It may not recursively relax the
task, rewrite its evaluator, select on the physical test set, or treat simulator
reward as proof.

## Camera and sensor policy

### Main-policy observation contract

Keep the primary learned-policy comparison **overhead-only**. This is the only
camera modality consistently represented in the main physical source set and
can be rendered consistently in simulation. The future physical test should
keep an overhead policy-input stream so the policy comparison does not change
its observation contract at deployment.

### The one wrist/side episode

Use the isolated extra-view physical episode as privileged system-identification
and evaluator evidence, not as a normal multi-view training episode. It can
help:

- validate camera timing and cross-view synchronization;
- inspect jaw/pawn occlusion and contact/release intervals;
- estimate hand-eye geometry if the calibration is recoverable; and
- test whether overhead-only contact annotations are systematically biased.

One episode cannot establish the visual distribution required for a reliable
wrist-camera policy. Do not duplicate the overhead image into a wrist slot,
fabricate missing real wrist images, or silently mix inconsistent modalities.

### Future wrist camera

In the related-workcell retest, record overhead and wrist (and side, if easy)
for every trial, but initially keep wrist/side **evaluator-only**. This gives a
stronger ground-truth view of acquisition, retention, slip, release, and
collateral motion without confounding the main policy comparison.

After enough consistent multi-view episodes exist, run a separate secondary
ablation with:

- explicit modality masks;
- camera dropout during training;
- calibrated view identity and timestamps; and
- separate overhead-only versus overhead-plus-wrist evaluation.

Synthetic wrist images may be used for auxiliary representation learning only
with a measured real-domain check. They should not be presented as equivalent
to consistent physical wrist demonstrations.

### Highest-signal future probes

Before full task trials, prioritize:

1. a measured board-to-base transform using a dimensionally checked metric
   target or contact landmarks;
2. a visible LED/electrical event for camera/controller clock alignment;
3. repeated empty gripper closes for aperture, hard-stop, current, and latency;
4. slow free-space reversals for deadband/backlash and load response;
5. a controlled pawn pinch/lift with wrist or side visibility; and
6. only then the three predeclared manipulation scenarios.

These probes are higher information than another unconstrained task video.
They require separate hardware authority and gateway review.

## Agent harness and tool surface

Use Inspect AI/Inspect SWE as the reproducible experiment shell and the
repo-native Learning Factory/evaluator as authority. The harness should freeze
model, reasoning setting, prompt, skills, tools, budget, environment, and
transcript for each case.

Expose the agent to narrow tools:

- `evidence.query`: retrieve hash-bound episode/phase residuals;
- `trace.compare`: real/sim curve alignment and bootstrap summaries;
- `vision.inspect`: synchronized frame strips, segmentation, flow, and tags;
- `graph.query`: mechanisms, dependencies, posteriors, and invalidations;
- `sim.probe`: one bounded perturbation or declared experiment family;
- `sim.replay`: action-frozen replay with typed receipt;
- `mechanism.scaffold`: create a bounded simulator adapter and tests;
- `fit.run`: deterministic optimizer over an approved block;
- `eig.rank`: rank experiments by predicted information gain and cost;
- `evaluator.submit`: read-only verdict, with no threshold access;
- `teacher.search`: post-gate trajectory/IK candidate generation; and
- `dataset.propose`: submit examples for independent admission.

Keep distinct roles:

- **perception agent:** proposes observations from frames/plots;
- **structure agent:** proposes mechanisms, graph edges, and experiments;
- **deterministic fitter:** estimates bounded numerical parameters;
- **sealed evaluator:** owns all verdicts;
- **policy trainer:** consumes only admitted data; and
- **hardware gateway/operator:** owns any future robot execution.

Benchmark coding models at frozen tool tiers and budgets. The primary agent
metric is evaluator improvement per rollout/token/minute with invalid-claim and
test-leakage penalties, not how persuasive the written explanation sounds.

## Experimental design

### Research questions

**RQ1 — Calibration efficiency.** Does agentic belief-graph loop closure reach
equal or better held-out vector fidelity with fewer simulator evaluations than
sequential tuning, black-box optimization, posterior fitting alone, or a
VLM-only tuner?

**RQ2 — Explanation stability.** Does loop closure reduce tuning-order
dependence and correctly retract compensating parameter explanations when a
missing mechanism becomes available?

**RQ3 — Twin predictivity.** Do improvements in the proposed twin gate better
predict real task consequences and policy/checkpoint ordering than trajectory
RMS, visual similarity, or simulator reward alone?

**RQ4 — Policy value.** Does evaluator-admitted data from the gated calibrated
twin improve sealed-simulation and related-workcell physical outcomes over
real-only and naive-simulation training?

**RQ5 — Agent value.** Does the coding/VLM agent improve mechanism discovery,
experiment efficiency, or abstention beyond deterministic search given the
same budget?

### Calibration baselines

- the current sequential one-coordinate campaign;
- random search and coordinate descent;
- CMA-ES or Bayesian optimization over the same approved parameters;
- BayesSim/SimOpt-style posterior parameter fitting;
- COMPASS-style causal parameter pruning;
- Vid2Sid-style VLM proposals without graph loop closure;
- proposed graph without loop closure;
- proposed graph without the agent; and
- full ClawLoop.

Use seeded sim-to-sim faults for ground-truth mechanism recovery and the
retained SO-101 data for real-anchor fidelity. Report these proof classes
separately.

### Policy baselines

- source policy or pretrained model without task fine-tuning;
- real-only fine-tuning;
- uncalibrated simulation data;
- real plus uncalibrated simulation;
- real plus calibrated simulation without posterior randomization;
- real plus calibrated posterior-randomized simulation;
- gated flywheel without LLM proposals; and
- full gated flywheel.

### Ablations

- scalar RMS versus phase/vector residuals;
- no belief graph;
- no physics loop closure;
- no structural particles;
- no multimodal input;
- VLM annotations versus deterministic computer vision only;
- uniform domain randomization versus posterior randomization;
- no twin-worthiness gate;
- trainer-owned versus sealed data admission;
- overhead-only versus privileged wrist evaluator; and
- ACT versus GR00T at the same admitted-data boundary.

### Metrics

Calibration:

- joint, EE, pawn, gripper, and event-timing residuals with uncertainty;
- consequence agreement and calibrated success probability;
- seeded mechanism localization and parameter recovery;
- tuning-order/path dependence;
- simulator evaluations, tokens, cost, wall time, and failed proposals;
- abstention correctness and invalid physical claims.

Twin predictivity:

- paired success/failure agreement;
- failure-mode agreement;
- policy/checkpoint rank correlation and rank violation when sample size
  permits;
- calibration curves/Brier score for predicted task success; and
- whether selecting the simulated winner selects the real winner.

Policy:

- strict success;
- acquisition, retained lift, transport, release, stable placement;
- final pawn error and collateral motion;
- safety/controller violations;
- results by task direction and initial-state group; and
- exact independent physical-trial counts with intervals.

## Future physical evaluation

The old workcell cannot be recreated. The future robot/chessboard setup must
default to `new_related_workcell` unless every identity requirement in
`configs/hardware/similar_scene_revalidation_v1.json` is independently met.
Different lighting, background, camera mount, or board pose are useful transfer
tests, but they are not continuations of the retired evidence.

Use the future session in this order:

1. record static identity, camera, transform, board, gripper, firmware, and
   clock evidence;
2. collect the high-information calibration probes above;
3. fit only the new installation/session nodes while preserving shared
   embodiment priors;
4. freeze the twin and both policies;
5. run the three predeclared scenarios with baseline/candidate order blocked or
   randomized;
6. keep overhead as the policy input and wrist/side as evaluator evidence;
7. score consequences with an evaluator frozen before execution; and
8. do not train on these primary test trials.

An optional post-evaluation adaptation phase may use new physical data, but it
must be reported as a second experiment with a new split and policy generation.

## Publication success ladder

### Minimum publishable result

- seeded GapBench faults show useful agent diagnosis under fixed budgets;
- retrospective loop closure reduces path dependence or evaluations;
- at least one prospectively logged mechanism forecast is tested;
- retained SO-101 action-frozen fidelity improves on a predeclared vector gate;
- the system truthfully abstains where the old evidence is non-identifying.

### Strong result

Everything above, plus:

- the twin predicts held-out real episode consequences better than scalar RMS
  and black-box calibration baselines;
- calibrated simulator data materially improves ACT on sealed simulation; and
- the improvement is robust across posterior and counterexample sets.

### Best result

Everything above, plus:

- the simulated policy ordering predicts the related-workcell ordering;
- the frozen candidate improves strict physical success over the real-only
  baseline across the three predeclared scenarios; and
- the coding/VLM agent reaches the result with fewer calibration trials than
  deterministic and VLM-only baselines.

## What not to make the paper about

- **Not “LLMs discover the true physics.”** Sparse observations can support
  several equivalent explanations. Claim better predictive models and better
  calibrated abstention.
- **Not “the VLA self-improves because simulator reward increases.”** The
  sealed real-aligned evaluator must own admission.
- **Not a multi-camera VLA paper.** The main real corpus does not support that
  claim.
- **Not broad domain randomization.** Randomize the posterior only after
  identifiable mismatch is addressed.
- **Not raw LLM joint control.** Deterministic IK/trajectory tools should own
  dense motor actions.
- **Not a fleet/meta-twin claim.** There is one retired workcell and, at best,
  one future related setup.
- **Not a claim that lower RMS already closed grasp physics.** Current task
  consequences do not support it.

## What to do first

### Immediate milestone: freeze and implement the twin-worthiness contract

The first implementation should not be another VLA run. It should be a
versioned `TwinWorthiness.v1` contract that answers, mechanically, whether the
current simulator may produce policy-training evidence.

Complete these tasks in order:

1. freeze paper RQs, baselines, metrics, data roles, and workcell identities;
2. add the prospective sidecar to the active fixed-pad/retention thread;
3. ingest the fixed-pad family as the first graph-native intervention;
4. backfill the ten minimum historical campaign milestones;
5. implement the residual tensor, belief graph, structural particles, and
   connected invalidation;
6. implement G0–G4 with explicit `pass`, `fail`, and
   `requires_new_measurement` results;
7. run the first retrospective physics-loop-closure experiment plus shuffled
   order and no-loop-closure controls;
8. freeze and prospectively score the next simulator hypothesis;
9. build the overhead-only ACT and GR00T data interfaces and the post-gate
   teacher/admission loop, but keep training evidence disabled; and
10. prepare the future related-workcell identity/probe/evaluation packet.

The go/no-go boundary is simple:

> Do not spend scarce VLA training compute until the simulator materially
> improves grasp/consequence fidelity under unchanged actions and the proposed
> twin gate says which claims the available paired data can support.

This ordering makes the next simulator advance directly useful to the paper,
prevents the self-improvement loop from exploiting an untrusted contact model,
and preserves a credible fallback publication if hardware or VLA results are
limited.
