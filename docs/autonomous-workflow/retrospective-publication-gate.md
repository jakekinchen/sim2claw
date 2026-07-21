# Retrospective publication gate

Status: `IMPLEMENTED_AND_OFFLINE_VERIFIED`

## Objective

Close the retired-workspace evidence loop without inventing measurements or
silently upgrading old source recordings. Preserve the real physical corpus as
immutable replay anchors, fit only quantities present in the recordings, and
freeze the provider benchmark before any paid calls.

## Accountable task ledger

- [x] Re-audit the local corpus after the cloud workspace teardown.
- [x] Verify all catalog-bound sample, receipt, and overhead-video hashes.
- [x] Create a strict per-episode replay-anchor contract with no timestamp,
  index, range, or transform repair.
- [x] Re-run the existing evaluator-owned replay-input audit.
- [x] Fit an episode-level physical tracking-observation posterior in recorded
  source units.
- [x] Fit a separately labeled qualitative image-space offset distribution.
- [x] Keep the unreviewed homography projection out of metric calibration.
- [x] Preserve the full Inspect/API factorial as an archival, unexecuted design.
- [x] Freeze the active low-cost pilot at three systems, three nonredundant
  cases, one attempt per case, zero retries, and a USD 1 incremental-cost cap.
- [x] Keep subscription-native Codex and Claude results labeled as system
  comparisons because Inspect cannot reuse their interactive subscriptions.
- [x] Require all nine typed outputs before revealing deterministic host scores
  or matched unchanged/random/heuristic/oracle controls.
- [x] Generate deterministic no-secrets, no-provider-call receipts.
- [x] Add tamper, authority, determinism, unit, and terminal-negative tests.
- [x] Preserve blocked calibration and transfer gates as reportable results.

## Terminal conditions

This loop is complete when the offline receipt is deterministic and makes all
of the following distinctions:

1. A replay anchor proves retained bytes and replay intent; it is not an exact
   simulator replay result.
2. The tracking posterior describes observed physical command-following and
   sample timing; it is not a posterior over MuJoCo dynamics.
3. Owner-reviewed endpoint crosses are qualitative image-space evidence; they
   are not metric board pose.
4. A frozen subscription pilot is a specification; it is not a model result,
   bare-model comparison, subscription-use authorization, or spend authority.
5. No retrospective artifact supplies a new held-out physical transfer result.

## Commands

```bash
uv run python scripts/run_retrospective_publication_gate.py
uv run python scripts/freeze_corrective_subscription_pilot.py
uv run python scripts/score_corrective_subscription_pilot.py  # only after all 9 outputs exist
uv run pytest -q tests/test_retrospective_publication.py tests/test_subscription_pilot.py
```

The generated receipts live below `runs/publication-gate/` and remain ignored
by Git because they bind local ignored physical artifacts.
