# AI Build Run Log: Pawn Metric/Policy Concordance

Request: Test whether the retained pawn trace and expected-position metrics
improve together with simulator policy consequences, without using a VLA or an
LLM as the evaluator.

Repo/path: `/Users/kelly/Developer/sim2claw`

Started: 2026-07-20

Completed: 2026-07-20; deterministic diagnostic complete

Owner constraints: use the existing evaluator; do not substitute an unrelated
policy or promote diagnostic evidence into physical calibration or transfer.

## Acceptance Criteria

- Recompute the frozen train-side workcell candidate from retained source data.
- Evaluate the frozen candidate on the designated held-out episodes.
- Compare trace-fit changes with source replay and paired policy consequences.
- Use deterministic calculations only; provider calls and physical actions are zero.
- State explicitly whether a compatible pawn ACT checkpoint exists.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Experiment implementation | Codex | Bind the existing receipts and evaluator metrics into one comparison | Live contracts and retained reports | Compiler, test, run log |
| Train/held-out fit | SciPy and MuJoCo | Recompute bounded workcell fit and command-driven source replays | 13 product-scope physical episodes | Fit and held-out receipts |
| Consequence authority | Frozen pawn reward calculation | Score contact, lift, target distance, collateral, and success | Source and retained policy traces | Deterministic consequence metrics |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Train fit receipt | Retained physical train partition | `run_workcell_fit` | `runs/pawn-metric-policy-concordance-v1/workcell_fit_train.json` | Diagnostic simulator-frame candidate |
| Held-out receipt | Frozen candidate and designated evaluator episodes | `run_held_out_validation` | `runs/pawn-metric-policy-concordance-v1/workcell_fit_held_out.json` | Kinematic-only admission |
| Concordance report | Fit receipts and retained policy reports | `scripts/run_policy_trace_concordance.py` | `runs/pawn-metric-policy-concordance-v1/concordance_report.json` | No model judge |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Fresh fit | Project workcell fit functions | `stage_d_lift` selected; 11 train and 2 held-out episodes | Fit receipts |
| Concordance compiler | `uv run python scripts/run_policy_trace_concordance.py` | `partial_mechanism_specific_concordance`; logical digest `07c1af09ac075d09a58797427502f1ca7839ba6a473fe5509f967005a0b9f010` | Concordance report |
| Focused tests | `uv run pytest -q tests/test_policy_trace_concordance.py tests/test_pawn_bg_workcell_fit.py tests/test_interaction_events.py` | 15 passed in 11.87 s | Test output |
| Compile and whitespace | `compileall`; `git diff --check` | Pass | Tracked implementation |

## Result

- Train event RMS fell from `309.550 mm` to `17.414 mm`, a `94.37%`
  reduction. Train source replays changed from `0/11` to `9/11` episodes with
  selected-piece contact and from `0/11` to `1/11` with a lift; task success
  remained `0/11`.
- Held-out event RMS fell from `327.525 mm` to `23.549 mm`, a `92.81%`
  reduction. Held-out source replays changed from `0/2` to `2/2` contact, but
  lift and task success remained `0/2`. One final target distance worsened from
  `44.450 mm` to `326.099 mm`.
- In the one retained paired learned-policy case, the aligned bridge reduced
  maximum collateral displacement from `55.588 mm` to `0.000167 mm`
  (`99.9997%`) while selected-piece contact, lift, and success all remained
  false and final target distance remained about `44.450 mm`.
- Therefore the sparse event metric is concordant with reach/contact geometry
  and collateral safety, but not with lift or end-task performance. It is a
  useful component metric, not a sufficient agent reward or policy-predictivity
  proxy by itself.

## Known Gaps

- No compatible B--G pawn ACT checkpoint exists in retained storage. The rook
  ACT checkpoint is a different task/schema and is intentionally not substituted.
- Only one paired baseline/aligned pawn policy case exists, so correlation or
  policy-ranking calibration cannot be estimated.
- Exact recorded-action replay and physical calibration remain unavailable.
- The retained paired learned-policy probe is GR00T N1.7, not ACT. It is used
  only as already-recorded simulator consequence evidence; no new VLA inference
  or model judging occurred.

## Follow-Up Queue

- Add a compatible pawn ACT cohort with at least three frozen baseline/candidate
  pairs before estimating correlation or policy ranking.
- Give any coding agent a vector objective—event fit, no clipping, contact,
  lift, final target distance, and collateral—instead of optimizing event RMS
  alone.
