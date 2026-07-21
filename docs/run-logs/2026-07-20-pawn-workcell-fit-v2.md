# AI Build Run Log: Pawn Workcell Fit V2

Request: Continue lowering the retained pawn event error using an actionable
simulator parameter family while preserving the frozen evaluator boundary.

Repo/path: `/Users/kelly/Developer/sim2claw`

Started: 2026-07-20

Completed: 2026-07-20

Owner constraints: select from train-only evidence; do not retune on the
already-open evaluator episodes; do not promote a diagnostic simulator fit into
physical calibration, exact replay, training admission, or transfer proof.

## Acceptance Criteria

- Add only robot-base roll, pitch, and height as new bounded simulator parameters.
- Require at least 2% lower train event RMS than Stage D.
- Preserve zero clipping, at least 9/11 train contact, and at least 1/11 train lift.
- Keep evaluator episodes out of candidate selection and tuning.
- Preserve deterministic receipts, tests, and explicit claim boundaries.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Experiment design and implementation | Codex | Add and audit the Stage-E parameter family | Frozen Stage-D evidence | V2 contract, fitter, tests |
| Numerical fitting | SciPy least-squares | Fit bounded base pose jointly with existing workcell parameters | 22 train events | Stage-E candidate |
| Physics consequences | MuJoCo and frozen pawn scorer | Check clipping, contact, lift, endpoint, and success | 11 train source replays | Train acceptance gates |
| Confirmation | Existing evaluator episode partition | Report Stage D/E side by side without selection | 2 already-open evaluator episodes | Confirmation receipt |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Train fit | Retained physical train rows | `scripts/run_pawn_bg_workcell_fit_v2.py` | `runs/pawn-bg-workcell-fit-v2/train_fit.json` | Diagnostic simulator parameters |
| Confirmation | Frozen candidate and existing evaluator episodes | Same runner | `runs/pawn-bg-workcell-fit-v2/confirmation.json` | Post-selection confirmation only |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Stage-E fit | `uv run python scripts/run_pawn_bg_workcell_fit_v2.py` | Rejected: train event RMS 17.4139 to 17.4067 mm (0.0415%); lift fell 1/11 to 0/11 | `runs/pawn-bg-workcell-fit-v2/train_fit.json` |
| Confirmation | Same command | 23.5493 to 23.5381 mm (0.0476%); no selection change | `runs/pawn-bg-workcell-fit-v2/confirmation.json` |
| Receipt SHA-256 | `shasum -a 256` | fit `9989dcf22c9905f53d22ab2badc9c4abe7808a8d8833d06693dd4047ebd82d4c`; confirmation `8c9e343e1d2a3ea41d62e5b123602a18a4c238f99a997ed24f4f84aa841dc938` | Ignored receipts |

## Known Gaps

- Base pose is inferred from sparse task-labeled event targets, not measured by
  a metric physical calibration fixture.
- The evaluator episodes were opened during the prior Stage-D study and cannot
  serve as untouched model-selection data.
- Lower event error is insufficient unless replay consequences remain stable.

## Follow-Up Queue

- Stage E failed. Stage D remained the physics-replay candidate.
- The next train-residual family was board square pitch, recorded separately in
  `docs/run-logs/2026-07-20-pawn-workcell-fit-v3.md`.
