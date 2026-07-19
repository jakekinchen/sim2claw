# Pawn Skill Composability: Endpoint Dynamics Before Correction

Status: active study; endpoint instrumentation implemented, physical pose review
and calibration inputs incomplete

Date: 2026-07-19 America/Chicago

## Abstract

A forward pawn move and its reverse are not assumed to be mathematical inverse
functions. Each skill is modeled as a state-conditioned transition with a
distribution of terminal poses. This study freezes a 12-skill B--G benchmark,
separates ordinary task success from composable placement quality, and defines
the replay, system-identification, alternating-cycle, and correction sequence
needed to test whether placement error contracts, persists, or grows.

The current result is deliberately incomplete rather than falsely precise. All
18 catalog-bound physical recordings were recovered and exposed as 36
hash-bound review panels, but no pawn base-center pose has been admitted. The
endpoint evaluator therefore reports zero supported transition regressions and
no drift classification. Separately, an isolated bounded GR00T fine-tune
completed 1,000 steps, but its sole frozen development rollout was terminal
negative. A canonical read-only audit also found that the legacy replay path
silently clips commands: 2,231 of 7,741 command rows and 2,255 of 7,741 measured
rows exceed current MuJoCo actuator ranges under the legacy mapping. Its
replacement remains isolated and review-blocked, so the repository grants no
exact-replay or calibration authority.

**Built:** a canonical fail-closed 12-skill endpoint evaluator.

**Learned:** the existing recordings cannot identify self-centering, and the
bounded GR00T challenger did not lift the pawn.

**Did not prove:** drift stability, calibrated replay, or correction efficacy.

**Highest-value next experiment:** reviewed poses plus deliberately varied
starting offsets.

## Research Question

For each column and direction, let the measured pawn offset from square center
be `delta`. The endpoint transition is

`delta_final = A * delta_initial + b + epsilon`.

The hypotheses are:

- **Self-centering:** `A` is near zero and `b` is near zero.
- **Systematic bias:** `A` is near zero and `b` is nonzero.
- **Offset preserving:** `A` is near the identity.
- **Unmodeled or noisy:** residual RMS exceeds the frozen 6 mm boundary; the
  label is not inferred from covariance alone.
- **Composition stability:** the forward/reverse pair contracts offsets toward
  a stable fixed point rather than amplifying them.

The frozen point thresholds are `||A||F <= 0.35`, `||A-I||F <= 0.35`,
`||b|| <= 3 mm`, residual RMS greater than `6 mm`, and pair spectral-radius
boundaries `0.95` and `1.05`. Point estimates do not become claims unless their
uncertainty intervals remain wholly inside the relevant predeclared region.
The study never substitutes a nominal square center, folder label, visual-box
center, or LLM estimate for a reviewed board-plane pawn pose.

## Frozen Evaluation

The current product contract is
`configs/evaluations/pawn_rank12_bidirectional_v2.json`, SHA-256
`8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3`.
It covers B1↔B2 through G1↔G2: six columns and two directions, for 12
directed skills.

For each admitted episode, the evaluator reports:

- signed file/rank endpoint error and center distance;
- circular base overlap with the central tolerance region;
- full-base security inside the destination square;
- upright, stable, and ordinary square-success outcomes;
- task, coarse, composable, and precision grades;
- bias, covariance, affine offset sensitivity, and residuals when identifiable;
- trajectory repeatability and membership in measured input support, explicitly
  not policy-validity evidence; and
- alternating composition statistics only when both directional regressions
  are supported.

The frozen engineering contract can compute an affine solution from four
rank-sufficient initial offsets, and labels results below ten episodes as
`limited_sample`. That is algebraic identifiability, not scientific support.
Research claims are additionally governed by
`configs/evaluations/pawn_transition_inference_readiness_v1.json`, SHA-256
`9751397d91efcffc54c0507611c8b7b74910da539542e15fc8a1eda860812645`.
That overlay does not mutate the frozen v2 engineering outputs. It defines:

- **Fit-computable:** at least four independent episodes and rank-3 design;
  algebraic output only.
- **Exploratory:** at least ten independent episodes, centered-design condition
  number at most 50, and initial-offset span at least four times pose
  uncertainty.
- **Claim-eligible:** disabled in v1. Twenty independent episodes is only a
  candidate episode floor. Re-enabling requires a frozen small-cluster
  coverage/power study and a new protocol version that fixes a defensible
  independent-session floor, non-vacuous leave-one-session-out coverage, and
  an uncertainty method with demonstrated coverage.

These episode, condition-number, and span ratios are conservative engineering
heuristics, not a power analysis or a guarantee of adequate inference. They
apply per directed skill. An independent episode is one distinct execution
with a unique episode ID and source-action payload; weighted copies, augmented
views, and replays of the same actions count once. Same-session executions are
one cluster for uncertainty resampling.

The exact diagnostics are frozen in the overlay. Briefly, the centered design
standardizes each initial-offset axis by the larger of its sample standard
deviation and pose uncertainty, then uses the two-norm singular-value condition
number of `[Zx, Zy, 1]`. Offset span is twice the least-excited principal-axis
standard deviation and is divided by the maximum per-episode 95% radial pose
uncertainty. A future claim protocol must use leave-one-session-out stability,
must predeclare a nonzero eligible omission count and fraction, and must retain
supported held-out prediction RMS at most 6 mm. A studentized wild
cluster-bootstrap-t procedure with 10,000 resamples and seed 190719 is recorded
only as a candidate; it is not authorized until a frozen study demonstrates
adequate small-cluster coverage. V1 does not define multiplicity-adjusted
cross-skill intervals or tests, so family-wide inferential claims are forbidden
and any 12-skill summary is descriptive. One transition estimate uses exactly
one proof class and domain; physical and simulated episodes cannot be pooled.
The population is limited to the frozen policy, robot/gripper, workspace,
observation pipeline, sessions, and measured initial-offset support.

Frozen v2 does not load this overlay; its point labels are engineering outputs.
The overlay is a manual review protocol until a separate readiness evaluator
emits a passing receipt. Its claim tier is additionally disabled until a new
protocol version satisfies every enabling requirement. Therefore no current
transition or composition output is claim-eligible, including a zero or
apparently favorable point estimate.

Repeated nominal-center starts do not identify `A`. Even if every current
product candidate were admitted, eleven skills would have one episode and
C2→C1 would have two; no transition matrix is presently identifiable.
Retrospective episodes populate only a descriptive scorecard. Checkpoint
promotion requires separately frozen trials and a separately owned CPU/fp32
evaluator.

## Evidence Inventory

| Evidence | Current count | Authority |
| --- | ---: | --- |
| Catalog-bound physical recording directories | 18 | Physical read-only source |
| Catalog receipt/sample/video hashes verified | 54/54 | Integrity only |
| Hash-bound pre/post review panels | 36 | Visual proposal surface |
| Folder-label product candidates | 13 | Candidate routing only |
| Directed skills represented by folder labels | 12/12 | Candidate coverage only |
| Retained off-scope episodes | 5 | Preserved, non-admitted |
| Pending task-label adjudications | 12 | Eleven metadata conflicts plus one catalog-consistent off-scope transition |
| Reviewed pawn base-center poses | 0 | No metric endpoint authority |
| Supported skill regressions | 0/12 | No self-centering result |
| Opened held-out rows | 0 | Sealed |
| Admitted training rows from this benchmark | 0 | Non-promoting |

The red crosses in the review sheet are nominal square centers. Compact cyan
rings are tone-aware visual fiducial proposals, and cyan crosses are inferred
board-contact-center proposals. Owner-directed retargets remain directional
visual proposals pending exact acceptance. None is an evaluator input.

Seven of the eleven metadata conflicts affect B--G product candidates. Folder
names and videos may route review, but only an append-only adjudication can
establish the task identity used by an evaluator or split.

## Results Matrix

| Evidence lane | Result | Interpretation |
| --- | --- | --- |
| Canonical endpoint contract and evaluator | Integrated and fail-closed | Engineering artifact generation and pose-admission rejection are implemented; research-inference readiness remains protocol-only |
| Recovered-corpus endpoint run | Incomplete: 0 admitted poses | Self-centering, bias, covariance, and drift remain unknown |
| Legacy canonical replay | Invalid for exact-replay claims | It clips initial state and commands and does not preserve the requested/applied distinction |
| Replacement replay/sysid | Isolated, repaired after first review, fresh review pending | Not integrated; grants no canonical replay or calibration authority |
| Geometry calibration | Blocked | No admitted EE/board/object pose observations |
| Timing/control calibration | Blocked pending joint-map correction | Limit forces would confound gains, damping, and latency |
| Contact/object calibration | Blocked | No admitted pawn/contact/grasp/release trajectories |
| Isolated GR00T challenger | Terminal negative for this bounded served process only | Off-product C8→A6 smoke case: 0 mm lift, 125.724 mm final XY error; not a GR00T-model-class or B--G result; held-outs sealed |
| Closed-loop B--G ACT replay | Unsupported | No compatible checkpoint exists |
| Alternating-cycle stability | Unsupported | No paired claim-eligible endpoint regressions; this blocks affine composition. Calibrated closed-loop policy replay is a separate unavailable lane |
| Bias compensation / retargeted placement | Not opened | Correction must not precede measurement and calibration |

## Replay And Calibration Validity Gates

A replay is exact only when the command applied by MuJoCo equals the recorded
command. Requested and applied controls, range violations, interpolation,
latency, and clipping must be explicit in the receipt. A physical-to-simulator
joint transform must bind joint identity/order, units, sign, scale, and zero
offset. It cannot be inferred silently from feasibility.

Every optimizer stage must also prove identifiability. A parameter is eligible
only when a configured observable depends on it and finite perturbations
produce a nontrivial, sufficiently conditioned sensitivity. A flat objective is
an unidentifiable parameter, not a successful fit.

Before any future fit, whole episodes must be frozen. Deterministic and
leave-one-column-out splits must be recomputed and verified on load; unresolved
task-label conflicts cannot become column authority. Held-out performance must
improve against the frozen nominal simulator before a calibrated model is
accepted.

The same uncertainty rule applies to endpoint inference. A calibration is
claim-eligible only with more than four spatially distributed correspondences;
the overlay freezes eight as the minimum, with board-quadrant coverage, lens
distortion control, repeated independent annotation, held-out or leave-one-out
board-coordinate RMS at most 1.5 mm, and propagated pose uncertainty. Pairwise
annotator disagreement above 1.5 mm excludes the point until a third annotator
and named reviewer resolve it append-only. Four points can
determine a homography, making their in-sample RMS non-diagnostic. The current
maximum allowed engineering RMS is 3 mm, equal to the precision and small-bias
boundaries. Claim-level interpretation of precision, small bias, or
self-centering must therefore abstain for the affected metric and episode
whenever its confidence region overlaps the 3 mm boundary. A per-skill
transition claim requires every included episode to be pose-eligible. Frozen v2
does not enforce this overlay and may still emit an engineering point
classification; that output is not a research claim.

The board playing side is 355.6 mm and each square is 44.45 mm. The frozen
contract uses a 13.8 mm pawn-base radius, but the independent measurement record
for that radius is still missing; full-base geometry must abstain until its
provenance is reviewed. `upright` means the pawn is not toppled and its base
remains the board-contact surface. `stable` requires at most 1 mm base-center
motion across a one-second post-release window sampled at 20 Hz or faster, with
no visible rocking or toppling.
`ordinary_square_success` is the reviewer-reported destination-square outcome,
kept separate from center precision. Trajectory repeatability is
progress-normalized geometric path repeatability, not timing or controller
repeatability.

## Composition Claim Boundary

The 5,000 alternating rollouts are samples from an affine Gaussian endpoint
model, not independent robot executions. They assume stationary, linear,
Markov transitions and Gaussian residuals. A valid exploratory report must:

- stop and mark `unsupported` when a rollout exits measured input support;
- treat categorical task, upright, or stability failure as absorbing;
- propagate episode-level parameter and pose/calibration uncertainty; and
- report spectral-radius uncertainty rather than promote a point estimate.

This diagnostic does not estimate physical execution survival or demonstrate a
policy precondition envelope. It measures only membership in observed input
support. At claim level, support is the convex hull of reviewed initial offsets
with no margin expansion, and a query is supported only when its entire 95%
pose-confidence region lies inside that hull. Frozen v2's expanded axis-aligned
box is an engineering diagnostic, not demonstrated policy support.

## GR00T Terminal-Negative Result

The bounded challenger dataset contained 73 unique simulation sources, 96
weighted episodes, and 41,088 synchronized frames. Only one admitted
current-geometry pawn source was present, repeated 24 times in the weighted
mixture. Training completed 1,000 steps. The sole predeclared C8→A6 development
rollout used 71 policy queries and 562 model-owned actions, but the pawn did not
rise or move meaningfully toward the target. That far-side case lies outside
the brown-pawn B--G ranks-1-and-2 product surface. No held-out case was opened
and no pawn, physical, or sim-to-real authority was granted.

The compact evidence archive was retained and the paid worker was deleted.
Checkpoint weights were intentionally not retained after the terminal negative.
The completed run also lacked a cryptographic served-checkpoint handshake, so
its consequence is attributable only to the served model process by convention,
not independently to a retained checkpoint payload. Future runs require a
hash-bound runtime identity before the first query.

## Most Informative Next Evidence

The next useful data is not more nominal-center success video. It is:

1. exact human-reviewed base/contact centers for every retained pre/post frame,
   with a reviewed pixel-to-board calibration;
2. append-only resolution of the 11 folder/receipt task-label conflicts;
3. at least 10 well-spread independent episodes across three sessions per
   directed skill for exploratory analysis; the candidate 20-episode claim
   floor remains disabled pending a coverage study and new protocol version;
4. a reviewed physical-to-simulator joint coordinate transform;
5. synchronized end-effector, pawn, contact, grasp, and release observations;
   and
6. a compatible B--G policy checkpoint with frozen preprocessing and evaluator
   identities.

The experiment sequence is intentionally staged:

1. After reviewed poses and sufficient offset variation, run the affine
   endpoint diagnostic; it does not require a simulator or checkpoint.
2. After joint-transform validation, run exact joint/timing replay with
   requested and applied controls preserved separately.
3. Only after synchronized object/contact evidence and held-out simulator
   improvement should closed-loop policy cycles run.
4. Compare corrections in order: unchanged policy, deterministic bias
   compensation, retargeted placement, then synthetic goal-conditioned
   training.

Every cycle must consume its actual terminal state. No LLM may assume a nominal
center or compose skills open-loop.

## Reproducibility And Claim Boundary

As-of snapshot: `2026-07-19T02:20:00-05:00`.

| Item | Identity |
| --- | --- |
| Canonical HEAD | `fb95de4865a9d93caa0180864bce04fcffb75428` |
| Integrated endpoint commits | `36f1ebc`, `c24ddec`, `70493fe`, `bdd2bea`, `fb95de4`; `bdd2bea` remaps the eight proposal targets and `fb95de4` supersedes only the final-E2 proposal for recording `66894edc` |
| v2 contract | `8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3` |
| Inference-readiness overlay | `9751397d91efcffc54c0507611c8b7b74910da539542e15fc8a1eda860812645` |
| Physical catalog | `7eb770b5be222ef970b97e1c1128f604121d324bb573672b9f8ef9b40a36a15e` |
| Frame selection | `8bd8e37751b8c6032b12265e74264ea75bed8e5f355c019c194a46c5d7d62a98` |
| Review sheet | `42aeb310061a0c4c7c0610ec7d9be932cb4ab979a2e680e4572b4623d8987da8` |
| Adjudication queue | `718f155a40c301058291b597938a0a10e74380ae152f15f9e33850ecaab4c516` |
| Fail-closed summary | `43141d8aa65930342b14d292ddb5d83d1fcb61ddd46690bbe8013e98529deefc` |
| Endpoint plus research-overlay focused verification | `24 passed` |
| Replay range audit | `docs/reference/PHYSICAL_REPLAY_JOINT_LIMIT_AUDIT_20260719.json`, SHA-256 `f54e7dfafe2a9eded31516e20426113d54166c137a5a0020d64b3c228773bd42`; the historical generation lock remains recorded, and a post-integration rerun under the current lock reproduced the same semantic core: 2,255/7,741 measured and 2,231/7,741 command rows outside ranges |
| Isolated GR00T branch | `codex/groot-multisource-100mm-v2`; commits `b8a4988`, `c977431`, `c0305e6`, `9671d78`; final identity hardening under independent review |
| External GR00T archive | `sim2claw-groot-n17-multisource-v2-20260719T060030Z`; archive SHA-256 `0cc871b19ea009c4aae43abd1d2d408096fe27637b820190b4d0b8f818adf0f7` |
| Isolated replay/sysid branch | `codex/recorded-replay-sysid-foundation`; base commits `dff9fa7`, `a32f6e7`, `4c5d78a` plus repair commits `4d0fb09`, `aaadce2`; exact initial-velocity parsing remains review-blocked and nothing is integrated |

Tracked contracts, code, tests, decisions, and run logs belong in Git. Raw
recordings, generated panels, synchronized trajectories, videos, checkpoints,
and optimizer outputs remain ignored and are referenced by hashes. Visual,
simulation, replay, learned-policy, physical read-only, and physical task
evidence are separate proof classes. Training never promotes itself, the LLM
never composes skills open-loop, and Studio remains an inspection surface rather
than physical control authority.

The central thesis is therefore testable and unchanged:

> First reproduce the imperfections of the real system. Then determine whether
> those imperfections self-correct, remain bounded, or compound. Only then
> optimize them away.
