# Fixed-Data Interaction Analysis for Publication Closeout

## Result in one sentence

The retained corpus supports a deterministic, phase-conditioned diagnostic of
where the physical controller departs from its command and where the gripper
shows a mechanically loaded closure signature, but it does not contain the
paired exact simulator trace or contact/object ground truth needed to claim
that the simulator gap has been measured or closed.

## Frozen analysis population

| Partition | Independent episodes | Rows | Moves | Event candidates | Visual strips |
|---|---:|---:|---|---:|---:|
| Development | 15 | 6,486 | frozen whole-episode train partition | 90 | 15 |
| Evaluator-owned held-out | 3 | 1,255 | E1-F1, C2-C1, G1-G2 | 18 | 3 |
| Total | 18 | 7,741 | 9 unique move IDs | 108 | 18 |

Every row is assigned exactly one of five ordered phases. The six event
candidates per episode are deterministic functions of measured gripper
position and frozen thresholds; they are not manual contact labels.

## Strongest retrospective signal

All 15 development episodes and all three held-out episodes satisfy the frozen
mechanically-loaded-closure proxy: median cached raw current is higher in the
closed interval than in the open baseline, and the median absolute gripper
command-measurement gap is positive.

| Episode-level statistic | Development median (n=15) | Held-out median (n=3) |
|---|---:|---:|
| Closed-interval flat-response fraction | 86.7% | 82.1% |
| Closed gripper command-measurement gap | 5.107 percentage points | 3.682 percentage points |
| Closed-minus-open cached raw current | +16 raw units | +9 raw units |

This is the best high-signal use of the existing telemetry because it repeats
on whole held-out episodes and aligns with the visible grasp interval. It is
still a mechanical-load proxy, not proof of object contact: the current stream
is a cached nominal 5 Hz device value, and the corpus lacks an empty-gripper
hard-stop baseline that could separate object loading from jaw end-stop load.

## Phase-conditioned control result

The phase compiler exposes errors that an episode-wide average would hide.
Across development episodes, median shoulder-lift tracking RMSE rises to
4.252 degrees during release and remains 3.983 degrees during retraction. The
three held-out episodes show the same late-episode pattern: 3.666 degrees at
release and 4.792 degrees during retraction. During the closed-transport
candidate, median gripper tracking RMSE is 4.609 percentage points in
development and 3.635 in held-out.

These are actionable simulator-fitting targets: fit and validate control/timing
by phase before changing friction or training a policy. They do not identify a
physical latency constant, because the trace lacks separately timestamped
command issue and actuator-response events.

## Training-ablation shape

Interaction-heavy phases contain 35.49% of the 6,486 development rows. The
frozen 1/4/3/4/1 phase weights move their expected sampling mass to 64.86%
without editing or duplicating a source row. A valid ablation is therefore:

1. original episode/row sampling;
2. phase-balanced sampling with identical source bytes, optimizer budget, and
   seeds; and
3. phase-balanced sampling plus a separately admitted simulator correction.

Evaluation must remain evaluator-owned and episode-level. Weighted draws are
not new demonstrations, and the manifest itself grants no training admission.

## Multimodal role

The nine-frame 1920 x 1560 strip presents initial, pre-closure, closure,
post-closure, transport-midpoint, pre-release, release, post-release, and final
context. A matched Codex/Claude Inspect task can annotate finite-enum visible
occupancy, overlap, co-motion, and release cues while preserving ambiguity and
occlusion. The receipt outcome is hidden from the annotation prompt and no
model judges another model.

The publication-safe use of this lane is an annotation agreement/coverage
study and qualitative evidence figure. A multimodal model cannot recover a
metric contact point, force, or 3D object trajectory from this camera view.

## Real-versus-simulator gate

The comparison implementation exists and has positive/rejection fixture tests,
but execution is blocked for 18/18 episodes. The reviewed transform remains
provisional, the legacy replay clips recorded states/commands, and there is no
retained row-aligned exact simulator trace. A prior source-fit diagnostic
reported 17.41 mm development event RMS and 23.55 mm held-out event RMS, but
its missing ignored receipts and non-calibration authority prevent using it as
the new comparison input.

The next admissible step is to review and hash-bind joint identity, order,
units, sign, scale, and zero offsets, then prove no-clipping replay over every
row. Widening limits, clipping commands, or reconstructing approval from a run
log would make the headline stronger and the science weaker.

## What this contribution is and is not

The defensible addition to Sim2Claw is a trace-native reality-gap compiler:
it converts sparse physical demonstrations into immutable event lineage,
phase-conditioned metrics, synchronized visual evidence, model-auditable
annotations, and an exact-replay-gated simulator comparison. It is a useful
benchmark substrate for reasoning agents because agents must preserve evidence
boundaries while identifying which simulator mechanism to test next.

It is not yet evidence that an LLM closed the sim-to-real gap. That stronger
claim requires a frozen provider campaign, an approved exact replay, a
separately admitted policy-training ablation, and new physical validation on a
clearly identified old or related workcell.
