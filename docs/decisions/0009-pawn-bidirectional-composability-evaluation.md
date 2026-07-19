# Decision 0009: Bidirectional Pawn Composability Evaluation

Status: v2 product benchmark implemented; current physical-data run awaits
reviewed base-center annotations

Date: 2026-07-19 America/Chicago

Machine-readable product contract:
`configs/evaluations/pawn_rank12_bidirectional_v2.json`

Annotation template:
`configs/evaluations/pawn_rank12_bidirectional_annotations_template_v2.json`

## Decision

Treat each B–G rank-1/rank-2 skill as a state-conditioned stochastic transition,
not as one half of an exact inverse pair. The evaluator measures all 12 directed
operations:

- B1→B2 through G1→G2; and
- B2→B1 through G2→G1.

The owner-selected v2 contract replaces the 16-case A–H v1 contract as the
product question because the recovered physical corpus covers these 12 B–G
directions. The v1 contract remains byte-identical historical evidence at its
frozen hash. The earlier B–G diagnostic v1 also remains immutable, but it is
not current product authority.

This benchmark is non-promoting when populated from retrospective source
recordings. A future learned checkpoint still requires separately frozen
trials and the evaluator-owned CPU/fp32 promotion path.

## Evidence input

Every episode needs reviewed initial and final pawn **base-center** positions.
The evaluator accepts either metric board coordinates or a hash-bound image
base-center annotation plus a reviewed pixel-to-board homography. It rejects a
visual bounding-box center because perspective on a tall pawn makes that point
an unsuitable board-plane measurement.

Pixel calibration requires at least four board correspondences and must stay
under the frozen 3 mm board-coordinate RMS. The board axes are explicit:
positive X follows files A→H, positive Y follows ranks 1→8, and the playing-area
A1 outer corner is the origin. The current board uses a 355.6 mm playing side,
44.45 mm squares, and a 13.8 mm physical pawn-base radius.

The tracked physical catalog is routing metadata, not pose evidence. Conflicting
folder/receipt task labels are rejected unless the annotation carries an
append-only reviewed correction with reviewer and timestamp lineage. Operator
success notes, LLM/VLM guesses, and nominal square centers cannot fill missing
poses.

## Endpoint and transition outputs

For every episode the evaluator writes:

- initial offset from the source-square center;
- signed final file/rank error and Euclidean destination-center distance;
- percentage of the circular pawn base inside the central tolerance region;
- center-inside and full-base-secure-inside destination-square geometry;
- upright, stable, and ordinary square-success annotations;
- coarse, composable, and precision grades; and
- whether the terminal offset lies in the measured reverse-policy input
  envelope, when enough evidence exists to define that envelope.

Per skill and per direction it fits

`delta_final = A * delta_initial + b + epsilon`.

At least four episodes with a rank-3 design matrix are required before A and b
are reported. Fewer samples or repeated centered starts produce
`insufficient_offset_variation`; the evaluator never substitutes zeros. The
classification is self-centering, self-centering with bias, offset-preserving,
mixed state-conditioning, or large-residual/unmodeled. Fewer than ten episodes
remain explicitly limited-sample evidence.

## Grading

- **Task failure:** the base is not securely inside the destination square, or
  the pawn is not upright and stable.
- **Coarse success:** the entire 13.8 mm-radius base is securely inside the
  destination square.
- **Composable success:** coarse success plus center error at most 6 mm.
- **Precision success:** coarse success plus center error at most 3 mm.

The ordinary “pawn is in the requested square” result remains a separate
reported field. It cannot hide poor placement quality.

## Composition diagnostic

When both directions in a column have supported regressions, the evaluator
forms the empirical forward/reverse pair:

`D(delta) = F_reverse(F_forward(delta)) - delta`.

It reports the pair transition matrix, bias, eigenvalues, spectral radius,
fixed point when identifiable, and 5,000 deterministic Monte Carlo alternating
rollouts at 1, 2, 5, 10, and 20 moves. Every move starts from the preceding
model endpoint. The outputs include expected/p95 center offset, secure-square
probability, empirical next-policy-envelope probability, and eventual-leave
probability.

This is an affine endpoint-model diagnostic. It is not closed-loop ACT replay,
calibrated MuJoCo evidence, or physical validation.

## Relationship to replay and system identification

The existing `physical_sim_replay.py` already asks the first bounded replay
question: how the current MuJoCo joints respond to the recorded physical
commands. It remains joint-response-only and does not prove pawn/contact
dynamics. The next separately versioned calibration slice must add synchronized
real pawn/end-effector/contact observations, split whole episodes before any
fit, and fit geometry, timing/control, then contact/object parameters in that
order. It must validate on held-out episodes, preferably leave-one-column-out,
before closed-loop ACT or correction comparisons are opened.

The pinned MuJoCo 3.10 package contains the official `mujoco.sysid` module, but
this repository currently installs the base MuJoCo dependency rather than its
optional `sysid` extra. No optimizer is invoked by this endpoint evaluator.
Enabling and adopting that extra requires a separate dependency record and a
real synchronized trajectory contract; installing an optimizer without valid
observations would not make the present data sufficient.

## Run

Fill a copy of the annotation template, preserving raw hashes and review
lineage, then run:

```bash
uv run --frozen sim2claw pawn-composability-eval \
  --annotations /path/to/reviewed_annotations.json \
  --output outputs/pawn_composability/reviewed_run
```

Exit code `0` means all 12 skills have endpoint coverage and supported A,b
regressions. Exit code `2` means the diagnostic artifacts were still written,
but evidence is incomplete or insufficient. Data errors fail immediately.

## Current result

The 18 cataloged recording directories were recovered read-only into the
ignored `datasets/` root. All 54 catalog-bound receipt, sample, and video hashes
match. The preparation run retained all 18 unique episodes and selected one
source/final frame pair for each, yielding 36 hash-bound review panels. Thirteen
folder-label candidates cover all 12 directed product skills; C2→C1 has two
recordings, and five retained rows are currently off-scope.

The corrected review sheet distinguishes two points:

- the red cross is the nominal square-center reference;
- the compact cyan ring is a tone-adaptive visual fiducial proposal; and
- the cyan cross is an inferred board-contact center proposal, obtained from
  that fiducial with an owner-centered initial-position prior.

The earlier categorical claim that the red cross fell on the pawn head was
withdrawn after full-resolution review. The large far/top-right projected
circle is the pawn-base footprint; the smaller near/bottom-left feature is the
upper pawn/head. The proposal detector now uses separate beige- and brown-square
tone thresholds, but its fiducial and inferred contact center remain proposals,
not measured poses.

All 36 cyan fiducial/contact proposals therefore remain
`proposed_pending_human_review`, and none enters the evaluator. The centered
initial-position observation is recorded only as an unreviewed proposal prior;
it cannot establish an initial pose, endpoint pose, or self-centering result.
The current run returns
`base_center_annotations_pending_review`, covers 0/12 skills metrically, opens
zero held-out rows, admits zero training rows, promotes no policy, uses no Brev
resource, and creates no physical authority. Even after exact coordinate
review, the available per-skill initial-offset variation is insufficient to
identify all 12 affine transition regressions or claim repeated-composition
stability.
