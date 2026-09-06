# Maintenance executor — 2026-09-06

Owner instruction: advance feasible simulation improvements from retained data
and reconcile open code/checkouts into main.

## Delivered

- Integrated operations commits through `d7380ec`, resolving the main-branch
  authority mismatch without changing its manifest.
- Integrated optional home visual scene at `ebe3c66`. Fixed an existing adjacent
  caller-inventory regression using a separate hash-bound historical supplement.
- Reviewed and merged ClawStudio proposal PR #15 at `034e589`; it remains a
  proposal, not a new active product or scientific campaign.
- Committed native RGBD capture preparation at `deb3bd4`: explicit exact-profile
  D405 recorder, bounded build/pre-camera smoke helper, offline integrity
  validator, 50 synthetic rejection/acceptance tests, and acquisition guide.
- Audited 72 initial refs and 18 worktrees. Removed one clean merged worktree
  without ignored artifacts; preserved historical evidence/environments. All
  remaining unique branch dispositions are in the maintenance ledger.

## Verification

- Operations and capture-integrity suite: **380 passed**, zero skips/errors/
  failures/deselection, 27.96 seconds.
- Adjacent OR48/OR155/OR156 and home/cutover suite: **21 passed**, 3.67 seconds.
- Native C++ build: success; **six pre-camera help/argument checks passed**.
  The first build rejected warnings in vendor headers. Treating those headers
  as system includes preserves warnings-as-errors for authored code; the
  subsequent build passed. No camera enumeration or access was performed.
- The original home/cutover combined run had one pre-existing classification
  failure. The hash-bound supplement preserves the frozen manifest and labels
  the two later retained diagnostics; all 11 home/cutover tests then passed.
- Source, SDK header/library and log digests are recorded in
  `outputs/reconciliation-20260906/source-verification.json`.
- Frozen scientific/authority paths have no diff from initial main `9a91ba8`.
  Bound actuator, clock, closure-locus and OR48 receipt hashes match.
- GitHub Actions API reports disabled; no remote CI claim. Optional Ruff was
  unavailable in the project runtime; no lint pass is claimed.

## Scope boundary

No fresh simulation fit, scientific replay, held-out access, physical capture,
robot movement or paid compute occurred. This slice closes a native sensor-data
software gap; it does not demonstrate improved contact physics. Acquisition
still needs two independently measured rigid jaw landmarks, current hardware
readiness/leases, gateway clock association and fresh independent evaluation.

See `docs/operations/JAW_CALIBRATION_ACQUISITION.md` and the source-linked
reconciliation ledger for concrete next steps and retained branch decisions.
