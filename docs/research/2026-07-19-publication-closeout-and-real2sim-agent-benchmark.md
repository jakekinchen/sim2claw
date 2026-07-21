# Publication Closeout and Active Real2Sim Agent Benchmark

Status: proposed final project shape; no physical motion or new paid training authorized

Date: 2026-07-19 America/Chicago

## Decision

End the project as an evidence-gated benchmark and case study, not as a claim
that the present B--G policy solved sim-to-real transfer.

The strongest publishable thesis is:

> Given a small real dataset, a policy, and an imperfect simulator, can a
> coding/reasoning agent identify the task-relevant reality gap, choose
> informative measurements, repair the simulator, and improve how well
> simulator evaluation predicts policy behavior under a fixed evidence and
> experiment budget?

The working title is:

> **Sim2Claw GapBench: Active Reality-Gap Diagnosis for Low-Data Robot
> Manipulation**

The paper should present three contributions:

1. a benchmark for agents that diagnose and repair seeded simulator faults;
2. an evidence-gated tool and evaluation protocol that separates visual fit,
   trajectory fit, policy predictivity, and physical transfer; and
3. a low-data SO-101 pawn case study showing that better in-sample imitation
   can coexist with complete closed-loop failure when dataset and simulator
   state/visual domains are misaligned.

This shape is more compelling and more defensible than spending the remaining
time collecting enough demonstrations to imply a broad manipulation result.
It makes the current negative result scientifically useful, creates many
repeatable benchmark instances without inventing more physical evidence, and
tests a timely capability that ordinary coding benchmarks do not measure.

This document is a planning artifact. It changes no frozen evaluator, held-out
split, checkpoint promotion decision, replay admission, or robot authority.

## Current Evidence Ledger

The publication must preserve these proof classes.

| Result | Current evidence | Permitted interpretation |
| --- | --- | --- |
| Clean-room simulation and evaluation foundation | MuJoCo scene, frozen tasks, CPU/fp32 evaluator contracts, deterministic receipts | Reproducible simulation/evaluation infrastructure |
| Fixed rook-lift ACT result | One narrow held-out simulation success | One accepted simulation task only; not B--G or physical authority |
| Physical B--G source corpus | 18 hash-bound teleoperation episodes, 7,741 frames, 54/54 assets verified | Low-data physical source and qualitative review surface |
| Metric endpoint evidence | Zero admitted pawn poses; 0/12 supported skill regressions | No self-centering, bias, drift, or physical transition claim |
| Exact replay readiness | 0/18 episodes admitted by the fail-closed replay preflight | The legacy physical source cannot currently calibrate the simulator |
| Exploratory GR00T optimization | Checkpoint 5000 improves in-sample open-loop action MSE by 44.86% and MAE by 27.15% versus checkpoint 2000 | Optimization and representation evidence only |
| Counterfactual language probe | Correct instructions reduce checkpoint-5000 MSE by 14.95% and MAE by 8.17% versus deterministic wrong instructions | Controlled in-sample language sensitivity only |
| Frozen B--G closed-loop evaluation | 0/12 task success, 0/12 selected-piece contact, 12/12 collateral-gate failures | Terminal negative for this checkpoint, preprocessing, reset, visual domain, simulator, and evaluator tuple |
| Training-aligned bridge smoke | Collision-free but no selected-piece contact or lift | Diagnostic assistance; not frozen policy success |
| Physical policy evidence | None | No physical-policy or automatic-transfer claim |

The central empirical observation is not merely `0/12`. The checkpoint emits
finite, unclipped actions, while the simulator reset differs radically from
the physical training-state distribution. The low training loss and open-loop
imitation gains therefore do not predict closed-loop consequence. GapBench
turns that failure mode into the target of evaluation.

The paper may state that the project received community recognition only as an
owner-reported presentation outcome unless a public award or selection receipt
is added to the release evidence.

## Publication Package

The minimum release should contain four linked artifacts:

1. **Paper or technical report.** The benchmark, protocol, model/tool
   ablations, and pawn case study.
2. **Benchmark repository slice.** Public development faults, hidden-test
   builder, evaluator, container/runtime lock, task schema, and example agent
   trajectory. No private credentials, generated checkpoints, physical
   recordings without release permission, or evaluator-held secrets.
3. **Interactive evidence viewer.** Synchronized real/sim frames, actions,
   joint state, transforms, contact events, residuals, hypotheses, and receipts.
4. **Model and experiment ledger.** Exact model IDs, endpoint/provider,
   reasoning mode, harness version, tool surface, token usage, latency, dollar
   cost, seeds, faults, output patches, and evaluator verdicts.

If release rights for the physical videos are uncertain, publish hashes,
derived non-identifying traces, selected consented stills, and the complete
synthetic benchmark. Do not delay the benchmark on a video-release question.

## Benchmark Object

Each task gives an agent:

- a versioned dataset or summarized evidence package;
- a frozen policy endpoint or replayable policy trace;
- an imperfect MuJoCo simulator and editable configuration/code surface;
- a task contract and public development evaluator;
- a bounded terminal, Python, plotting, image, and simulator tool surface;
- a fixed experiment, token, dollar, and wall-clock budget; and
- a declaration of which active probes are simulated, physical read-only, or
  operator-gated physical actions.

The agent must produce:

1. a ranked causal hypothesis ledger;
2. the next experiment and its expected information gain;
3. a simulator or calibration patch when justified;
4. before/after receipts on public development cases;
5. a prediction for hidden policy consequences; and
6. an explicit claim boundary and abstention when the evidence is insufficient.

The hidden evaluator owns promotion. Agents never edit the hidden seeds,
reference traces, score thresholds, or real-anchor verdicts.

### Tracks

| Track | Agent access | What it measures |
| --- | --- | --- |
| A. Offline diagnosis | Existing videos, traces, configs, code, and plots only | Can the agent localize a gap without new interaction? |
| B. Simulator repair | Track A plus editable simulator/calibration parameters | Can it reduce hidden trajectory and consequence error? |
| C. Active identification | Track B plus a menu of priced probes | Can it choose high-information experiments efficiently? |
| D. Policy predictivity | Frozen policies and paired sim/real outcomes | Does the repaired simulator rank or predict policy behavior? |
| E. Operator-gated physical | A tiny predeclared safe-probe menu | Can active measurement improve the twin without expanding motion authority? |

Tracks A--C can be released even if Track D has only a small real anchor and
Track E remains disabled. The benchmark must not require a successful physical
manipulation policy to be useful.

### Fault Families

Create many benchmark instances by applying one or two reviewable seeded
faults to an accepted reference scene. Each fault has a public development
version and a separately generated hidden version.

| Family | Example seeded faults | Identifying evidence |
| --- | --- | --- |
| Coordinate frames | axis sign swap, near-180-degree board fit, wrong joint order, zero offset | Labeled landmarks, joint traces, contact-probe positions |
| Camera | wrong extrinsics, focal length, distortion, crop, latency, color response | ChArUco reprojection, fixed views, timestamp event |
| Reset and support | initial joint state outside dataset support, wrong object pose, wrong board origin | Dataset state histograms, board/object observations |
| Control | frequency, latency, action hold, damping, requested/applied mismatch | Timestamped command/state traces and step response |
| Contact | gripper width, fingertip geometry, friction, compliance, release timing | Binary contact, current/load signal, object trajectory |
| Object dynamics | pawn mass, center of mass, inertia, table/board friction | Deliberate push or free-response probe |
| Observation pipeline | channel order, normalization, camera selection, resize/crop | Frozen preprocessing handshake and image comparison |
| Policy serving | wrong checkpoint, stale processor, lost reasoning/history state, horizon mismatch | Cryptographic identity and deterministic query receipt |

Seeded faults provide scale without pretending that synthetic cases are real
episodes. Scores must report synthetic/semi-synthetic and real-anchor domains
separately.

### Hidden Evaluation

The hidden evaluator should compute:

- **fault localization:** top-1 and top-3 family accuracy;
- **parameter recovery:** normalized error against hidden seeded values;
- **trajectory fit:** held-out joint, end-effector, and object residual change;
- **policy predictivity:** success/failure agreement, policy ranking
  correlation, and calibration of predicted success probability;
- **repair success:** fraction of hidden cases improved without breaking
  already-passing cases;
- **experiment efficiency:** improvement per probe, simulator rollout, token,
  dollar, and minute;
- **evidence discipline:** invalid claim, hidden-test contamination, or
  unqualified-parameter penalties; and
- **reproducibility:** deterministic rerun rate and complete receipt rate.

One compact primary score can be used for the leaderboard:

`score = 0.20 * localization + 0.30 * heldout_residual_gain + 0.30 * policy_predictivity + 0.10 * efficiency + 0.10 * evidence_discipline`

Every component must also be reported individually. The weights are a proposed
benchmark design, not a validated scientific result; freeze them before model
runs and perform a sensitivity appendix over reasonable alternate weights.

### Low-Data Statistics

Use Sim2Val's control-variate idea for paired real evaluation: simulation is
useful when it correlates with real outcomes, even when it is biased. Estimate
and report the correlation and variance reduction; do not assume them.

For the pawn case study:

- treat distinct physical executions as the independent units;
- keep same-session runs clustered for uncertainty;
- never inflate sample size with alternate camera views, prompt paraphrases,
  augmented frames, replays, or weighted copies;
- report bootstrap or exact intervals appropriate to the tiny sample;
- keep per-skill summaries descriptive when the frozen inference-readiness
  contract abstains; and
- use simulation as a control variate only after its real correlation is
  measured on a predeclared paired subset.

## Agent Tool and Perception Surface

Tool access is part of the treatment and must be frozen as carefully as the
model. The benchmark should expose cumulative tool tiers.

### T0: Text and Code

- terminal and bounded filesystem access;
- repository search and patch tools;
- simulator build/run command;
- structured trace and receipt readers;
- numerical analysis in Python; and
- no image or active-probe access.

### T1: Plots and Programmatic Vision

- joint/action/support histograms;
- residual and sensitivity plots;
- real/sim frame differencing;
- optical flow and tracked landmark trajectories;
- segmentation or object masks with provenance;
- ChArUco/AprilTag detection and reprojection diagnostics; and
- synchronized event and contact timelines.

### T2: Multimodal Evidence Viewer

Build one Rerun recording with:

- physical and simulated RGB frames on the same timeline;
- depth only when calibrated and available;
- camera intrinsics/extrinsics and transform tree;
- six-joint measured state, requested actions, and applied controls;
- gripper command and width;
- end-effector, selected-pawn, and target frames;
- contact/current/load events;
- per-step residuals and dataset-support flags;
- the agent's hypothesis/experiment ledger; and
- direct links to immutable receipts.

The viewer is diagnostic infrastructure, not metric authority. A VLM's visual
description, 3DGS, phone video, or Studio rendering cannot silently become a
board pose, collision model, or physical-control input.

### T3: Active Simulated Probes

- perturb one parameter at a time and compute finite-difference sensitivity;
- choose from a priced library of joint, camera, contact, and object probes;
- use predictive sampling or information-gain heuristics to pick a next probe;
- fork candidate simulators without changing the frozen baseline; and
- spend a predeclared rollout budget.

### T4: Operator-Gated Physical Probes

This tier remains disabled until the reviewed gateway and operator enable an
exact predeclared probe. The agent may propose; it does not directly command
the robot.

## Highest-Signal Sensor Plan

The best first sensor is not an expensive tactile array. It is a simple,
repeatable event sensor that turns ambiguous pixels into a timestamped
geometric constraint.

### P0: Contact Stylus and Synchronized Light Event

Use a rigid or lightly spring-loaded gripper stylus with a normally-open
microswitch or electrical-continuity tip. Under slow, operator-gated motion, it
touches eight or more named board/workcell landmarks. Record:

- exact joint encoder state at contact;
- contact event timestamp;
- fixed-camera frames;
- board landmark identity; and
- requested versus applied motion.

This cheaply identifies the robot-base-to-board transform, board plane, joint
sign/zero errors, and timing alignment far more directly than another wide RGB
video. It is a calibration probe, not a manipulation policy run.

Add a software-triggered LED visible in every camera, ideally paired with a
logged electrical edge. A single flash or pulse sequence exposes camera,
control, and logging latency without asking a vision model to infer timing.

No physical probe is authorized by this plan. The hardware and trajectory must
be reviewed, motion-limited, and executed through the existing gateway.

### P1: Fixed Metric Vision

- mount the existing camera rigidly;
- use a printed, dimensionally checked ChArUco board spanning the work area;
- collect repeated views and held-out landmark checks;
- control lens distortion and focus;
- report propagated pose uncertainty; and
- add a second fixed view only after the first view is calibrated and stable.

ChArUco combines the robust ID of markers with chessboard-corner precision.
AprilTags are useful for object or fixture identity, but a metric board should
own calibration.

### P2: Contact Magnitude

Before buying a vision-based tactile sensor, test whether existing motor
current and gripper-width telemetry can distinguish free motion, first contact,
grasp, slip, and release. If it cannot, add one small load cell or force-sensitive
resistor at the gripper/fingertip fixture. Binary contact plus even a coarse
normal-force signal is likely to identify more of the current failure than a
new uncalibrated depth stream.

### P3: Depth and Tactile

The D405 can help with board/object geometry after its extrinsics, depth scale,
and temporal alignment pass a held-out calibration. It remains a measured mass
payload, not current geometric authority.

DIGIT/TACTO is a strong future path for contact-rich manipulation, but it adds
hardware, calibration, rendering, and policy-observation work. It is not the
fastest route to a defensible closeout result.

## External Resource Audit

The clean-room rule is to adopt methods and public dependencies deliberately,
not to import another project's implementation or inherit its claims.

| Resource | Useful mechanism | Verdict for Sim2Claw |
| --- | --- | --- |
| [SIMPLER](https://github.com/simpler-env/SimplerEnv) | System identification, visual matching, variant aggregation, action-space checks, policy-ranking correlation/MMRV | **Adopt the evaluation pattern.** Port only reviewed concepts to the current MuJoCo/SO-101 task; it is not a drop-in environment. |
| [Sim2Val](https://nvlabs.github.io/sim2val/) | Simulation as a control variate for lower-variance real evaluation | **Adopt for the low-sample real anchor.** Benefit is conditional on measured sim/real correlation. |
| [Rerun](https://github.com/rerun-io/rerun) | Time-aligned images, transforms, 3D, tensors, and dataframes | **Prototype as the evidence viewer.** Complete license/dependency review before adding it to the runtime lock. |
| [OpenCV ChArUco](https://docs.opencv.org/4.x/df/d4a/tutorial_charuco_detection.html) | Metric camera calibration and pose from identified chessboard corners | **Adopt at P1.** Printed dimensions and held-out error remain required. |
| [EasyHeC](https://ootts.github.io/easyhec/) | Markerless differentiable-render camera pose and joint-space exploration | **Borrow the active-calibration idea.** Validate on this arm and retain ChArUco as an independent reference. |
| [SPI-Active](https://github.com/LeCAR-Lab/SPI-Active) | Fisher-information-driven active system identification | **Borrow the experiment-selection formulation.** Current code/task embodiment is not directly reusable. |
| [SiPE](https://github.com/NVlabs/sim-parameter-estimation) | Simulation parameter estimation from trajectories | **Method reference only.** Its older Python/MuJoCo stack should not enter the project runtime. |
| [MuJoCo MPC](https://github.com/google-deepmind/mujoco_mpc) | Predictive sampling and trajectory planning for informative probes | **Optional T3 planner.** Treat as a research prototype and isolate from evaluator authority. |
| [REALM](https://martin-sedlacek.com/realm/) | Real-to-sim policy ranking, trajectory/control alignment, perturbation suites | **Adopt comparison metrics and perturbation taxonomy.** Do not inherit its benchmark score claims. |
| [Phys2Real](https://phys2real.github.io/) | Vision-language physical priors followed by interaction-based uncertainty updates | **Use as the closest research precedent.** Our distinct contribution is coding-agent repair plus evidence gates and low-data policy predictivity. |
| [RialTo](https://real-to-sim-to-real.github.io/RialTo/) | Digital twin, inverse distillation, and RL robustification | **Reference in related work.** Too training-heavy for closeout and not evidence that the current checkpoint transfers. |
| [TACTO](https://github.com/facebookresearch/tacto) / [DIGIT](https://digit.ml/digit.html) | Simulated and physical vision-based tactile sensing | **Defer to P3.** Valuable follow-on, not the shortest path to the paper. |
| [real2sim-eval](https://github.com/kywind/real2sim-eval) | Rendering and physics evaluation for reconstructed scenes | **Reference for reconstruction metrics.** Keep rendering fit separate from task/policy fit. |
| [LeRobot](https://github.com/huggingface/lerobot) | Dataset and policy ecosystem used by the source/export path | **Retain as ecosystem compatibility.** Dataset conformance does not imply replay or policy admission. |
| [MLGym](https://github.com/facebookresearch/MLGym) | Budgeted open-ended research tasks and trajectory inspection | **Borrow benchmark packaging.** Review task licenses individually; many tasks are non-commercial. |
| [ResearchGym](https://github.com/Anikethh/ResearchGym) | Containerized long-running research tasks with objective score improvement | **Borrow the fixed-budget agent loop.** Robotics faults/evaluators remain repo-native. |
| [EmboCoach-Bench](https://arxiv.org/abs/2601.21570) | Code-as-interface engineering tasks in embodied systems | **Strong related work.** GapBench emphasizes dataset-to-simulator diagnosis and policy predictivity. |
| [RoboTwin](https://github.com/robotwin-Platform/robotwin) | Large dual-arm digital-twin tasks and data generation | **Do not port for closeout.** Wrong embodiment and excessive scope; cite as scale context. |
| [RoboMIND](https://x-humanoid-robomind.github.io/) | Large real-robot dataset and digital-twin program | **Dataset context only.** It does not solve this low-data admission problem. |
| [WorldEval](https://worldeval.github.io/) | World-model evaluation of downstream policies | **Future challenger only.** The current benchmark should use explicit MuJoCo state and consequences. |
| [Foxglove](https://foxglove.dev/product/visualization) | ROS/MCAP-centered multimodal visualization | **Second choice behind Rerun.** Prefer it only if the release becomes ROS/MCAP-first. |
| [CVAT](https://www.cvat.ai/) / [FiftyOne](https://github.com/voxel51/fiftyone) | Annotation and dataset-quality review | **Use only if annotation volume grows.** The present high-value need is metric calibration, not bulk boxes. |

No source above authorizes copying code or artifacts from the read-only
sim2claw archive. Any adopted dependency needs its source, pinned version,
license, and reason recorded before integration.

## Model Benchmark

### Verified Model Availability on 2026-07-19

| User label | Exact callable model | Access and control | Listed price |
| --- | --- | --- | --- |
| GPT-5.6 Sol | `gpt-5.6-sol` (`gpt-5.6` alias) | OpenAI Responses API and Codex; `none`, `low`, `medium`, `high`, `xhigh`, `max`; `ultra` is a multi-agent treatment | $5/MTok input, $0.50 cached input, $30/MTok output |
| Claude Fable 5 | `claude-fable-5` | Claude API; 1M context; adaptive thinking is always on; manual thinking budget and disabling thinking are unsupported | $10/MTok input, $50/MTok output |
| Kimi K3 | `kimi-k3` | Kimi API; 1M context; launch API defaults to max effort; low/high are announced for later | $0.30/MTok cached input, $3/MTok uncached input, $15/MTok output |
| “Qwen Max 3.8” | No official exact match found | Use current documented `qwen3.7-max`; thinking and non-thinking modes, 1M context, OpenAI-compatible API | Region-dependent CNY pricing; official pages currently show promotional discounts |

The last row is a correction, not a silent substitution. Freeze the exact
Qwen snapshot and region after account catalog preflight.

### Fair Experimental Shape

Do not put all rows on one chart as though “reasoning depth” is the same
control for every provider. Run two analyses.

**Analysis 1: within-Sol scaling curve**

- `gpt-5.6-sol` at low, medium, high, xhigh, and max;
- identical task, tools, prompt, token cap, wall clock, and seed schedule;
- exclude `ultra` from this curve because it introduces multiple agents;
- optional separate `ultra` row labeled as a multi-agent system treatment; and
- plot success, cost, latency, probes, and invalid claims against effort.

**Analysis 2: cross-model native operating point**

- Sol at the best predeclared single-agent operating point from the development
  set, not selected on hidden cases;
- Fable 5 with always-on adaptive thinking;
- Kimi K3 at its current max-effort default;
- Qwen3.7-Max in thinking mode;
- Qwen3.7-Max non-thinking as a within-Qwen ablation; and
- a cheap model or scripted optimizer baseline to show whether frontier
  reasoning is actually needed.

Use one neutral API harness and one tool schema where provider APIs allow it.
If K3 requires Kimi Code to preserve thinking history reliably, report that as
a separate harness condition rather than mixing it into a nominally
apples-to-apples model score. Pass provider-specific reasoning/history blocks
back exactly as documented. Do not enable fallbacks or silent model
substitution.

### Run Protocol

1. Freeze 12 development and 24 hidden fault instances for the pilot release;
   expand only if power/cost analysis justifies it.
2. Use three independent agent seeds per model-condition-task cell.
3. Give each cell the same simulator-rollout and wall-clock cap.
4. Set a dollar cap as a guardrail, but report token counts because equal
   dollars and equal tokens answer different questions.
5. Capture the complete agent trajectory, patches, commands, images requested,
   tool errors, hypotheses, and abstentions.
6. Score only immutable evaluator outputs; use no LLM judge for task success.
7. Use a blinded human rubric only for hypothesis quality and claim discipline,
   with two reviewers on a subset and disagreement reported.
8. Pilot all providers on two non-hidden tasks before committing the full
   budget. Record real token/cost distributions and revise only the public
   budget, not the evaluator.

The minimal paper table is model by tool tier. The most informative plot is a
Pareto frontier of hidden repair success against total cost and time.

## Priority Experiments

### E0: Freeze the Current Case Study

- bind the checkpoint-5000 manifest, processor, simulator, evaluation runner,
  0/12 report, bridge-smoke report, and current run log;
- preserve the 18 physical episodes as unadmitted source;
- do not overwrite the 11 folder/receipt conflicts;
- do not open held-out data to improve the story; and
- produce one dataset-to-open-loop-to-closed-loop gap figure.

### E1: GapBench Fault Generator and Evaluator

- implement the eight fault families above as small versioned patches;
- create public development and sealed hidden instances;
- prove each fault is detectable by at least one allowed evidence/probe path;
- establish scripted oracle and random-search baselines; and
- test that training/agent code cannot edit evaluator state.

### E2: Synchronized Evidence Viewer

- export one current failed episode and one accepted simulation episode to
  Rerun;
- show real/sim RGB, joint/action traces, transform tree, pawn/target, contact,
  dataset support, and residuals;
- add a hypothesis/experiment timeline; and
- produce a static screenshot/video for the paper and an interactive release.

### E3: Tool Ablation and Sol Scaling

- compare T0, T1, T2, and T3 using the same Sol effort and tasks;
- run the Sol effort ladder at the best affordable tool tier;
- measure whether more reasoning substitutes for or complements better
  sensing/visualization; and
- predeclare which development tasks choose the cross-model operating point.

### E4: Cross-Model Leaderboard

- run Sol, Fable 5, Kimi K3, and Qwen3.7-Max under the protocol above;
- include exact version/catalog receipts and no fallback;
- publish failures and patches, not only the aggregate score; and
- disclose any donated credits or vendor support.

### E5: Tiny Prospective Real Anchor

Only if release timing and physical authority allow it:

- collect 6--12 operator-gated calibration/probe traces, not a new large policy
  dataset;
- prioritize spatially distributed contact-stylus touches and synchronized
  timing events;
- freeze the paired subset before looking at model-specific repaired results;
- quantify whether simulator correlation enables a Sim2Val variance reduction;
  and
- keep physical task runs separate from calibration probes.

This experiment can strengthen the paper, but it is not required for the
benchmark release. If it does not pass the gateway or pose-admission gate,
publish the blocked/negative result and stop.

### E6: One Bounded Policy Rescue Attempt

Run only if E1--E5 produce an evaluator-admitted state/observation bridge that
places the selected pawn in contact under a frozen development case without
collateral failure. Evaluate checkpoint 5000 again without retraining.

Do not launch more GR00T training merely because API-agent results are
interesting. The present failure is upstream of optimizer step count. A new
paid training run requires newly admitted data or a demonstrably repaired
observation/state contract, a frozen development question, a cost cap, and a
retained served-checkpoint handshake.

## Paper Figures and Tables

1. **Hero figure:** dataset + policy + imperfect simulator → agent hypotheses →
   active probe/repair → hidden policy-predictivity evaluator.
2. **Evidence waterfall:** 18 episodes / 7,741 frames → improved in-sample
   imitation → wrong-instruction sensitivity → 0/12 closed-loop and root-state
   mismatch.
3. **Fault taxonomy:** frame, camera, reset/support, control, contact, dynamics,
   preprocessing, serving.
4. **Tool ablation:** T0--T3 hidden score and cost.
5. **Reasoning curve:** Sol effort versus success/cost/latency.
6. **Cross-model Pareto:** hidden repair success versus dollars and wall time.
7. **Viewer panel:** synchronized physical/sim frame, transform tree, actions,
   contact, and residuals for one fault.
8. **Real-anchor panel:** sim/real correlation and confidence interval, with
   Sim2Val variance reduction if observed.

The main results table should include complete-case counts and abstentions.
Never replace missing physical results with an LLM score or visual similarity.

## Claim Ladder

Permitted after E0:

- a 5,000-step exploratory GR00T fine-tune improved in-sample open-loop action
  error and exhibited controlled in-sample language sensitivity;
- the same bound checkpoint/evaluator tuple failed all 12 frozen B--G
  closed-loop simulation tasks; and
- the diagnostic exposes a state/visual distribution mismatch that open-loop
  training metrics did not reveal.

Permitted after E1--E4 if supported:

- a named model/tool configuration diagnoses and repairs seeded simulator
  faults at a measured hidden-task rate;
- tool access and reasoning effort change sample/cost efficiency by the
  reported amount; and
- the benchmark is reproducible under the released task/runtime contract.

Permitted after E5 only if supported:

- simulator outcomes correlate with a bounded paired real probe/task cohort;
- simulation reduces estimator variance by a measured amount; and
- one repaired simulator improves held-out prediction for the predeclared
  physical cohort.

Not permitted without new evidence:

- the current policy works on the physical robot;
- the simulator is physically calibrated;
- the 18 recordings identify endpoint dynamics or self-centering;
- language sensitivity is compositional generalization;
- better rendering implies better transfer;
- active probing autonomously controls the robot; or
- any LM automatically bridges the sim-to-real gap.

Prefer this wording:

> The agent produces candidate transferable repairs by reducing task-relevant
> dataset-to-simulator mismatch. Frozen replay, policy-predictivity, and
> operator-gated physical evaluation decide whether those candidates transfer.

## Compute and Credit Routes

### Fastest Plausible Routes

| Program | Current offer | Fit and caveat |
| --- | --- | --- |
| [Modal for Academics](https://modal.com/academics) | Up to $10,000 compute credits for graduate students, labs, and researchers | Best near-term GPU application if the team is eligible; ideal for bounded inference/eval, not an excuse for more ungated training |
| [Hugging Face Community GPU Grant](https://huggingface.co/docs/hub/spaces-gpus) | Free GPU upgrade for selected public Spaces; ZeroGPU offers shared burst inference | Strong for the interactive public demo, weak for long GR00T training |
| [OpenAI Researcher Access Program](https://openai.com/form/researcher-access-program/) | Up to $1,000 API credits; quarterly review | Frame around reliable, evidence-disciplined AI agents and unsafe overclaiming in embodied systems; approval is not immediate |
| [Anthropic External Researcher Access](https://support.anthropic.com/en/articles/9125743-what-is-the-external-researcher-access-program) | Normally $1,000 API credits; monthly review | Only a fit if the question is genuinely AI safety/alignment, such as calibrated abstention and evidence discipline; do not relabel ordinary robotics work |
| Direct model-vendor benchmark support | Request API credits from OpenAI, Anthropic, Moonshot, and Alibaba under one neutral protocol | Potentially fastest outreach; preregister metrics, accept no result veto, disclose support, and guarantee equal publication treatment |

### Institution-Dependent Routes

| Program | Current offer | Eligibility/timing caveat |
| --- | --- | --- |
| [AWS Cloud Credit for Research](https://aws.amazon.com/government-education/research-and-technical-computing/cloud-credit-for-research/) | Student awards up to $5,000; faculty/staff awards uncapped | Accredited research institution; rolling review typically 90--120 days |
| [Google Cloud for Researchers](https://research.google/programs-and-events/faculty-engagement/) | Research credits and training | Faculty, postdocs, nonprofit-lab researchers, and PhD students; affiliation required |
| [Azure Research Credits](https://www.microsoft.com/en-us/azure-academic-research/) | Research cloud credits through application/contact | Work or school identity and institutional research context |
| [NVIDIA Academic Grant Program](https://www.nvidia.com/en-us/industries/higher-education-research/academic-grant-program/) | Calls describe up to 30,000 H100 80GB hours or hardware | Full-time faculty at a PhD-granting institution; regional pages conflict on whether submissions are currently open, so verify before planning around it |

Alibaba's Coding Plan is not a benchmark-compute loophole: its documentation
forbids automated scripts and non-interactive batch/backend use. Use normal
Model Studio pay-as-you-go or an explicit written grant. The current Kimi API
page advertises a top-up voucher promotion, not a research-credit program.

### Neutral Vendor Pitch

Send the same one-page request to every model vendor:

> We are releasing an open, evaluator-scored benchmark for coding/reasoning
> agents that diagnose seeded and low-data real-to-simulator faults in robot
> manipulation. We request $1,000--$3,000 in API credits to run three seeded
> repetitions under a provider-neutral tool and budget protocol. Exact model
> IDs, costs, failures, trajectories, and all results will be published. Credit
> support will be disclosed and grants no influence over metrics, analysis, or
> publication.

Attach the community-selected presentation evidence if available, the frozen
benchmark schema, a two-task pilot, the cost estimate, and the release date.
This is a credible exchange: vendors receive a difficult, reproducible robotics
agent evaluation; the project receives bounded compute without selling the
result.

## Budget and Stop Rules

Before full model runs:

- pilot two development tasks per provider;
- measure actual input, output, tool, and cache usage;
- set a full API cap, initially proposed at $1,000;
- set GPU inference/evaluation cap, initially proposed at $250;
- require explicit owner authorization before spending either cap; and
- stop any worker immediately after its bounded task and verify provider
  inventory.

Stop a model condition early only under a predeclared rule such as repeated
harness incompatibility, not because its first scores are unattractive.

No additional GR00T training is in the closeout budget. CPU/Mac MuJoCo,
existing checkpoint inference, and API reasoning should carry the benchmark.

## Ten-Day Closeout

| Day | Deliverable | Exit condition |
| ---: | --- | --- |
| 0 | Frozen E0 evidence bundle and release manifest | Current positive/negative evidence hashes verify |
| 1--2 | GapBench schema, 12 development faults, 24 hidden faults, scripted baselines | Faults are detectable and evaluator is isolated |
| 3 | Rerun evidence viewer and paper screenshot/video | One accepted and one failed episode replay deterministically |
| 4 | Two-task provider pilot and actual cost model | Exact model/catalog/harness receipts pass |
| 5 | T0--T3 tool ablation and Sol reasoning curve | Predeclared cells complete or record terminal harness failures |
| 6 | Cross-model native-setting runs | All models receive equal task/tool budgets; no fallback |
| 7 | Statistical analysis, uncertainty, and reviewer rubric subset | Hidden scores, cost, latency, abstentions, and claim penalties frozen |
| 8 | Optional operator-gated real calibration probes | Run only if gateway/pose protocol passes; otherwise record blocked |
| 9 | Paper, artifact README, model cards, demo, and reproducibility pass | Clean clone reproduces the public benchmark |
| 10 | Public release candidate and final evidence audit | Claims map one-to-one to receipts; paid resources verified stopped/deleted |

If twelve development and twenty-four hidden cases are not achievable in the
time box, release six and twelve respectively and call the result a pilot
benchmark. Do not fabricate scale with prompt paraphrases.

## Project-Finished Definition

The project is complete when:

1. the current sim/policy/physical evidence is frozen with correct proof-class
   labels;
2. GapBench v0.1 has a deterministic public task set, sealed test generator,
   evaluator, baseline, and clean-clone instructions;
3. at least one reasoning-effort curve, one cross-model comparison, and one
   tool ablation have complete cost and trajectory receipts;
4. the interactive or recorded evidence viewer is publishable;
5. the report clearly explains the open-loop-improvement/closed-loop-failure
   case study;
6. physical claims either pass their independent gates or explicitly abstain;
7. datasets/checkpoints/credentials remain outside Git and release permissions
   are documented;
8. every paid worker and API experiment is bounded, and compute inventory is
   verified stopped/deleted; and
9. the paper, repository release, demo, and evidence ledger agree.

Completion does not require a successful physical pawn move. A rigorous
benchmark, a reproducible negative transfer case, and an honest account of
what additional sensing repairs are most informative are a publishable end to
this project.

## Primary Sources

Model availability and pricing were checked against official pages on
2026-07-19:

- [OpenAI GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 release](https://openai.com/index/gpt-5-6/)
- [Anthropic model overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Kimi K3 release](https://www.kimi.com/blog/kimi-k3)
- [Kimi API platform](https://platform.kimi.ai/)
- [Alibaba Model Studio model list](https://help.aliyun.com/en/model-studio/text-generation-model/)
- [Alibaba Model Studio pricing](https://help.aliyun.com/en/model-studio/model-pricing)

External method links and compute-program links are embedded in the audit
tables above. Their continued availability, eligibility, pricing, and licenses
must be rechecked at the time of application or integration.
