# AI Build Run Log: Pawn Bidirectional Composability Evaluation

Request: implement the B–G bidirectional pawn endpoint, self-centering, and
composition evaluation described by the owner

Repo/path: `/Users/kelly/Developer/sim2claw`

Started: 2026-07-19 America/Chicago

Completed: 2026-07-19 America/Chicago

Owner constraints: clean-room implementation; physical, replay, simulation,
learned-policy, and promotion proof remain separate; no held-out leakage; no
paid compute left running

## Acceptance Criteria

- Preserve the historical 16-case A–H v1 contract byte-for-byte while marking
  it superseded rather than rewriting prior evidence.
- Freeze the 12-operation B–G endpoint/composability contract as product v2.
- Consume reviewed base-center poses in metric board coordinates or through a
  hash-bound homography; reject bounding-box centers.
- Write endpoint metrics, bias, covariance, A/b/residual regression,
  precondition-envelope, trajectory-repeatability, composition-stability, and
  board-overlay artifacts.
- Grade task/coarse/composable/precision outcomes separately.
- Use actual preceding endpoints in the empirical alternating-move diagnostic.
- Fail closed on absent poses, conflicting labels, insufficient regression
  support, and missing upright/stable state.
- Provide a runnable CLI and focused tests.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Contract and implementation | Codex | Fresh repo-native evaluator design and code | Owner evaluation text, live repo contracts | JSON contract, Python evaluator, CLI |
| Metric math | NumPy 2.2.6 | Least squares, covariance, trajectory normalization, Monte Carlo | Reviewed board-coordinate poses | A/b/epsilon, envelopes, repeatability, stability |
| Homography | OpenCV 4.13 | Fit and verify pixel-to-board transform | Hash-bound grid correspondences | Metric base-center poses and RMS |
| Inspection surface | Repo-native SVG/HTML writer | Show initial/final offsets without adding a plotting dependency | Per-episode offsets | 12 SVG overlays and HTML index |
| Verification | pytest | Exercise empty, synthetic, homography, and rejection paths | Synthetic fixtures only | Focused test result |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Historical diagnostic contract | Fresh repo-native JSON | Owner's prescribed metrics and proof boundaries before product replacement was selected | `configs/evaluations/pawn_bidirectional_composability_v1.json` | Superseded; retained as history |
| Product v2 contract | Fresh repo-native JSON | Owner-selected replacement for the A–H consequence benchmark | `configs/evaluations/pawn_rank12_bidirectional_v2.json` | Authoritative product question; 12 B–G directed skills |
| Annotation template | Fresh repo-native JSON | Fail-closed empty evidence template | `configs/evaluations/pawn_rank12_bidirectional_annotations_template_v2.json` | Catalog and unaccepted visual proposals explicitly are not pose evidence |
| Evaluator | Fresh repo-native Python | Deterministic endpoint and affine-composition analysis | `src/sim2claw/pawn_composability_eval.py` | Uses already-adopted NumPy/OpenCV dependencies |
| Evidence preparation | Fresh repo-native Python | Inventory every catalog row, retain duplicate/off-scope/conflicting episodes, and extract hash-bound pre/post frames | `scripts/prepare_pawn_rank12_evidence.py` | Does not admit a pose annotation; product-skill coverage is reported separately from total episode inventory |
| Recovered-corpus preparation | Silicon payloads plus preparation script | 18 raw episodes recovered and retained; 36 evidence frames generated | `outputs/pawn_composability/recovered_corpus_v2/` | Ignored local evidence; the pre-acceptance 36-panel source artifact is preserved, 26 product markers have owner-reviewed qualitative image-space acceptance, and all approximate millimeter offsets remain unreviewed proposals |
| Fail-closed product run | Evaluator CLI | Empty reviewed-annotation set while proposals await acceptance | `outputs/pawn_composability/recovered_corpus_v2/evaluation/` | `base_center_annotations_pending_review`, not a learned-policy result |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Focused unit/contract/preparation tests | `uv run --frozen pytest -q tests/test_pawn_composability_eval.py tests/test_pawn_rank12_evaluation.py tests/test_prepare_pawn_rank12_evidence.py` | 25 focused tests passed; includes proof-class/provenance gates, outcome completeness, collinear regression rejection, duplicate retention, append-only owner label review, qualitative-marker/metric-boundary enforcement, proposal-calibration boundaries, grid-remapped retarget non-admission, and the panel-specific final-C2/final-E2 redos | Test output |
| Earlier full repository suite | `uv run --frozen pytest -q` | 169 passed, 30 subtests passed before product-v2 replacement patch | Test output; not represented as post-v2 full-suite proof |
| JSON syntax | `jq empty` on the contract, template, and project state | Passed | Tracked JSON files |
| Patch hygiene | `git diff --check` | Passed | Working tree diff |
| Recovered payload integrity | Catalog-bound receipt/sample/video SHA-256 verification | All 54 hashes matched across 18 episode directories | `configs/data/physical_pawn_move_catalog_20260719.json` plus ignored raw payloads |
| Recovered-corpus fail-closed run | `uv run --frozen sim2claw pawn-composability-eval --annotations configs/evaluations/pawn_rank12_bidirectional_annotations_template_v2.json --output outputs/pawn_composability/recovered_corpus_v2/evaluation` | Exit 2; `base_center_annotations_pending_review`; every required artifact written | `outputs/pawn_composability/recovered_corpus_v2/evaluation/summary.json` |
| Physical evidence rejection tests | Missing catalog+SHA+recording ID; proposed pose marker; unreviewed homography; drifted catalog hash; unknown proof class | All rejected before metric evaluation; only the exact `synthetic_test_fixture` class bypasses physical lineage | `tests/test_pawn_composability_eval.py` |
| Outcome-completeness rejection test | 60 otherwise complete synthetic endpoints with no `ordinary_square_success` | `incomplete_missing_outcome_annotations`; ordinary success rate remains null | `tests/test_pawn_composability_eval.py` |
| Collinear-regression rejection test | Five collinear initial offsets in both B directions | Both affine fits remain unsupported and B composition `move_statistics` is null | `tests/test_pawn_composability_eval.py` |
| Corpus inventory preservation | Generated frame selection and append-only adjudication queue | 18/18 unique recording IDs, 36/36 frames, duplicate C2→C1 count 2, 12/12 candidate skills, 12 adjudication entries | `outputs/pawn_composability/recovered_corpus_v2/` |
| Historical product-contract immutability | Focused SHA-256 assertion | A–H v1 remains `f3dac8b86cd7b0252153d25c0d5c09204079003ac9780642992fd10bc08e0d43` | `tests/test_pawn_rank12_evaluation.py` |
| Product v2 binding | SHA-256 | B–G v2 is `8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3` | `configs/evaluations/pawn_rank12_bidirectional_v2.json` |

## Current Evidence Result

- Tracked physical catalog entries: 18.
- Folder/receipt-consistent task labels: 7.
- Raw payloads recovered read-only from `jakekinchen@silicon`: 18 episode
  directories, 144 files, 290,956,583 bytes.
- Catalog-bound hashes verified: 54/54.
- All recovered catalog rows retained: 18/18 unique recording IDs. There are
  13 folder-label candidate product episodes covering 12/12 directed skills;
  C2→C1 has two separate recordings and every other product skill has one.
- Hash-bound before/after evidence extracted: 36 frames / 36 review panels.
- Task-label adjudication queue: 12 rows total, comprising seven in-scope
  candidate rows with conflicting metadata plus five off-scope rows. The queue
  preserves review history by recording ID and admits none of these rows.
- Owner correction: the large far/top-right projected circular shape is the
  board-contact base, while the smaller near/bottom-left feature is the
  projected upper pawn/head. The earlier categorical rejection was withdrawn.
- The owner identified a second detector failure: a shared contrast threshold
  worked better on beige squares than brown squares. The regenerated proposal
  sheet uses a 12-luma beige threshold and a 5-luma brown threshold against the
  paired empty-square frame.
- Red crosses remain nominal square-center references. Cyan rings are compact
  tone-adaptive dark visual fiducials. Cyan crosses are contact-center
  proposals obtained by subtracting the mean initial visual offset
  `[-0.7945, +3.2636] px`, based on the owner's centered-initial observation.
  That observation is recorded as an unreviewed proposal prior, not an endpoint
  measurement and not evidence of policy self-centering.
- Eight owner-directed visual retargets are recorded with their original
  coordinates, directional pixel delta, radius scale, and exact recording ID.
  The owner corrected the target interpretation after commit `70493fe`: every
  directive moved exactly one generated-sheet row upward in the same column.
  Runtime validation binds both sides to the generated layout and rejects drift,
  duplicate targets, or a nonconforming row/column shift. All eight remaps were
  unambiguous; these remain directional proposals pending exact acceptance.

| Prior mistaken panel | Corrected panel one row above |
| --- | --- |
| R3C1 `2a332ab7 initial C1` | R2C1 `fd7005f3 initial B2` |
| R3C4 `af661460 final C1` | R2C4 `052d5137 final C2` |
| R4C2 `bf91502b final C1` | R3C2 `2a332ab7 final D2` |
| R4C3 `34bff0dd initial D1` | R3C3 `af661460 initial C2` |
| R5C3 `5ab5603f initial D2` | R4C3 `34bff0dd initial D1` |
| R5C4 `5ab5603f final E1` | R4C4 `34bff0dd final D2` |
| R7C2 `1ee203e8 final F1` | R6C2 `66894edc final E2` |
| R8C4 `0c7e3d86 final F1` | R7C4 `0e058ca2 final E1` |

- After inspecting the remapped R6C2 result, the owner rejected its inherited
  down-left/expanded ring as completely off. The final E2 visual fiducial was
  redone at `[413.5, 219.5] px`, radius `12.1000 px`, using the best
  distance-regularized paired-frame-difference compact Hough candidate. This
  panel-specific redo remains an unreviewed proposal and supersedes only that
  inherited directive.
- The owner then rejected the inherited down-right expansion on
  `052d5137 final C2`. The final-C2 ring was restored to the strongest compact
  paired-frame-difference candidate at `[462.5, 189.5] px`, radius
  `9.6000 px`, and the panel metadata was corrected from the contaminated
  luminance classification to the known beige C2 square with threshold 12.
  The regenerated close-up visibly centers the compact ring on the pawn base.
- After that required redo, the owner accepted the current product-scope set as
  sufficiently accurate for qualitative review. The append-only review record
  binds 13 product episodes, all 26 initial/final markers, 12/12 directed skill
  coverage, exact frame hashes, pixel centers/radii, inferred contact-center
  proposals, single-owner unquantified uncertainty, and review lineage. Seven
  conflicting product task labels are separately recorded as owner-reviewed
  folder-label corrections. The five out-of-scope rows remain retained,
  deferred, and excluded.
- The proposal-only pixel-to-board homography is identified as
  `c922_board_grid_homography_proposal_20260719_v1`, hash-bound to its matrix and
  reference frame, and explicitly prohibited from evaluator calibration. Every
  displayed millimeter offset is labeled approximate/unreviewed.
- Product-scope visual review is complete in image space, but none of the 26
  accepted markers is admitted as a metric pose. The homography has no frozen
  held-out validation, propagated uncertainty, or independent point review;
  the research-inference overlay therefore remains disabled.
- Acceptance is bound to the exact deterministic 26-panel product sheet, its
  decoded pixels, and the ordered 26-marker identity manifest. The corresponding
  SHA-256 values are `8a2ae4029d2c89c3dee5a085f8cea835fe4f686de5f42e0c214467620dcea5f9`,
  `11b02ee135fc0a0204757eef6896cef2c74b25c83c2399abcbff45f964d57369`,
  and `c8076c59ebc070b5b3104030f2620d1f3add54830d169433a8bdbf657ab590c8`.
- In a later qualitative review, the owner reported that the base in the
  focused `66894edc` folder-labeled final-E2 screenshot is fully inside the
  square, visibly off-center by a substantial amount, and close to touching an
  edge. This is owner-supplied qualitative base-containment/square-membership
  context for that visual frame only. It is not admitted as
  `ordinary_square_success` because the folder label conflicts with the
  catalog/receipt task (`e1` to `f1`), and it provides no metric center,
  stability, upright, or composability annotation.
- Reviewed pawn base-center annotations: 0.
- Covered product skills by reviewed metric pose: 0/12.
- Supported per-skill A,b regressions: 0/12.
- Held-out rows opened: 0.
- Training rows admitted: 0.
- Policies promoted: 0.
- Product-scope source recordings with receipt `outcome_label=success`: 13/13.
  These are retrospective human-teleoperation operator labels, not learned-policy
  or simulator successes.
- Compatible learned B-G policy checkpoints present: 0.
- Canonical recorded-action replay readiness: 0/18 episodes. The integrated
  input receipt remains fail-closed on the unapproved physical-to-simulator
  transform and joint-range violations; no replay, sysid fit, limit expansion,
  transform change, or closed-loop policy claim was attempted.
- Brev instances created or used: 0.
- Recovered frame-selection SHA-256:
  `20c5dbdef2306f79cd24ed2bf7fae2353fa38a94a409ac3ca152014614aca0ea`.
- Proposal review-sheet SHA-256:
  `837042097d2bb3a7d64c32502a89a0a6c667a90064c965e65bda9cf9e0d440de`.
- Product-scope split review-sheet SHA-256:
  `8a2ae4029d2c89c3dee5a085f8cea835fe4f686de5f42e0c214467620dcea5f9`.
- Out-of-scope split review-sheet SHA-256:
  `83b0a734a24fa98f98b7655b7d9782ad352437cc236ef6c7cbe8a5302e8c5f71`.
- Task-label adjudication queue SHA-256:
  `709081cd5b6efe450e08635885c82e48fa8e349614f564ea78e8f1a487e0c3f2`.
- Product-scope owner visual-review SHA-256:
  `3fab56dbf83e1a152f44f0daf88c0d43c44bfbc0ce3c23c0c2e0aa603797101e`.
- Owner review-config SHA-256:
  `7be42682f63747ae382c65bd4ee26ed5076dbfd9649d74a190fcfcfa859603fb`.
- Fail-closed summary SHA-256:
  `43141d8aa65930342b14d292ddb5d83d1fcb61ddd46690bbe8013e98529deefc`.

## Known Gaps

- Product-scope visual markers have single-owner qualitative acceptance, but
  their pixel uncertainty is unquantified and there is no second independent
  annotator.
- Metric evaluation still requires a frozen, held-out-validated homography,
  independently reviewed board correspondences, and propagated pose
  uncertainty. The current matrix remains proposal-only.
- Seven product label conflicts have owner-reviewed folder-label corrections.
  Five off-scope rows remain retained, deferred, and excluded.
- Capture enough independent initial-offset variation per skill to identify A
  and b; repeated nominal-center starts cannot answer self-centering.
- Add synchronized real pawn/end-effector/contact observables before contact
  system identification.
- Keep whole episodes and held-out columns sealed before fitting simulator
  parameters or correction policies.

## Follow-Up Queue

- Add independent calibration/pose review and held-out board validation before
  populating a metric v2 annotation manifest or running the metric endpoint
  evaluator.
- Keep recorded-action replay blocked until the canonical input report moves
  from 0/18 readiness under a separately reviewed transform without joint-limit
  violations.
- Version the synchronized system-identification contract, enable MuJoCo's
  optional official `sysid` dependencies, and fit geometry → timing/control →
  contact/object groups with held-out validation.
- Recover or train a compatible B-G checkpoint before any closed-loop policy
  comparison; none exists in the current checkout. Only after the calibration
  and replay gates pass should alternating-cycle or correction comparisons run.
