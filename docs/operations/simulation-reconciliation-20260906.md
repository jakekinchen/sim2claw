# Simulation evidence and checkout reconciliation — 2026-09-06

Owner request: proceed with all feasible simulation improvements from retained
data, and resolve open checkouts/code that should merge into main.

This is the current maintenance ledger for that request. It does not reopen the
closed OR156 scientific campaign or grant camera, serial, physical motion,
training, held-out access, paid compute, or simulator promotion authority.

## Milestones

1. **Complete: reconcile repository integration.** Inventory every local and
   origin branch and registered worktree; identify patch-equivalent history,
   review unique changes, preserve local evidence, merge justified changes, and
   verify local main equals origin/main with passing native authority checks.
2. **Complete for offline software: prepare the next measurable fidelity improvement.** Audit the
   current observation/import path against the OR48 missing measurements and
   OR155/OR156 findings. Complete useful offline software and acquisition
   preparation without inventing measurements or repeating exhausted fits.
3. **Complete: close out reviewed work.** Run scoped verification, record merge
   dispositions and exact remaining physical inputs, commit/push scoped work,
   and leave a clean canonical checkout.

## Acceptance evidence

- The initial checkout is clean at `d7380ec` on `codex/operations-atlas`, five
  commits ahead of fetched `origin/main` (`9a91ba8`). Native checks correctly
  reject that feature branch because the manifest expects `main`.
- The initial inventory contains 18 registered worktrees and one open draft
  PR, #15 (`codex/clawstudio-evidence-authoring`).
- Current scientific authority remains OR156, no active card, all external
  authority false. OR155 identifies a displaced simulated closure locus and
  non-named-mesh contact; OR156 exhausts only the retained software row-clock
  alternative. Neither supplies independent metric jaw geometry.
- Generated audit/verification receipts belong in
  `outputs/reconciliation-20260906/`, not Git.

## Decision rules

- Retain original raw data, action bytes, timestamps, frozen contracts, and
  historical receipts. Do not overwrite or relabel historical scientific wins.
- Merge current reviewed implementations and useful additive documentation;
  do not bulk-merge old snapshots or restore superseded authority files.
- An old branch not in main by ancestry may already be present by patch or
  file content. Record that distinction explicitly.
- Worktree removal requires no unique commits, no tracked/untracked changes,
  and no retained ignored artifacts. Preserve ambiguous checkouts.
- Physical acquisition is a separate explicit gateway operation. Missing
  independent observations and fresh validation remain real input boundaries.

## Progress

- Completed initial live authority, Git, PR, and historical-context reads.
- Integration review completed; branch dispositions are recorded below.
- The five operations commits are merged/pushed at `d7380ec`; all 330 required
  inspection checks passed. Native `check --profile agent` now passes on main.
- Home visual scene integrated at `ebe3c66`. Five home-scene tests passed; an
  adjacent pre-existing classification failure was repaired with a hash-bound
  supplement for two historical callers, preserving the original migration
  manifest and implementation bytes. All 11 home/cutover tests now pass.
- PR #15 merged at `034e589`. Its ClawStudio document remains explicitly a
  proposed product direction; no implementation or physical authority follows.
- GitHub Actions API reports `enabled: false`; no remote CI execution is claimed.
- Removed the clean, fully merged `db10` worktree and its merged local branch
  after confirming no ignored artifacts or open files. Other artifact-bearing
  worktrees remain intact.
- New offline finding: the OR44 native recorder saves depth only, whereas OR48
  requires paired RGB/depth, both exact-profile intrinsics and depth-to-color
  extrinsics. The older ROS-backed capture evaluator is a separate path. Prepare
  a versioned native RGBD recorder and offline integrity validator, preserving
  the old recorder and all frozen contracts. Compile/help/negative option tests
  must perform no camera enumeration or access.
- The new native RGBD recorder builds and passes six pre-camera smoke checks.
  Its standard-library integrity validator passes 50 synthetic positive/negative
  checks, preserves proof classes, and never admits calibration. See
  [acquisition preparation](JAW_CALIBRATION_ACQUISITION.md).
- Twenty-one adjacent OR48/OR155/OR156 and home/cutover tests passed. Existing
  actuator, clock, closure-locus and external-metric packet receipts retain their
  bound hashes. No frozen scientific source or authority configuration changed.

## Branch and checkout dispositions

The generated `branch-dispositions.json` covers all 72 initially inventoried
local/origin refs (including local/remote duplicates): 45 are in main by ancestry,
five are patch-equivalent, one has all four files integrated, one clean merged
local branch was removed, and 20 historical refs were retained without merging.
`git-inventory-initial.json` and `branch-file-comparison.json` retain exact
commit identities, dirty/ignored state, and per-file comparisons.

| Work | Disposition and reason |
| --- | --- |
| Operations atlas | Five commits fast-forwarded and pushed; native branch drift resolved. |
| Home visual workspace | Four additive source/config/doc/test files integrated at `ebe3c66`; current physics unchanged. |
| ClawStudio PR #15 | Reviewed proposal merged at `034e589`; no open PR remains. |
| Recorded replay/sysid, native recorder, Inspect Robots, GR00T multisource | Equivalent patches already in main; no replay of old commits needed. |
| Detached `bab0`/`f795` | Preserved. Timing-cohort and calibrated-range implementations are already represented in current `system_identification.py` and `recorded_replay.py`; remaining patches are equivalent. |
| Early clean-room/gateway roots and combined backup | Preserved alternate/snapshot history; no common merge base for the early clean-room lineage. Do not import a parallel architecture into current main. |
| Publication reorder backups | Preserve pre-rebase history; equivalent patches and later retained-event/mobile implementations already exist. |
| Old pawn fidelity and rubber-tip branches | Retain historical command-fit/frame diagnostics; they do not supply the independent metric jaw observations now missing. |
| Old canonical-source GR00T development branch | Retain bounded historical training/evaluation tools and evidence; its old benchmark/runtime is not the present jaw-calibration target. |
| Silicon recovery snapshot | All 38 changed paths already exist in main; preserve recovery history rather than overwrite later gateway, recorder and Studio fixes. |
| Claude game, public-demo grading, move-suite fit and data-analysis branches | Retain optional/historical investigations. They add different task products, old fits, or historical paper artifacts; none closes the current geometry/observation gap. |
| Claude graph, hackathon branding, deck and shot-plan branches | Retain dated presentation history; avoid restoring obsolete metrics/assets or generated paper/deck outputs into current code. |

Seventeen worktrees remain registered, including the canonical checkout. The
sixteen historical checkouts contain unique history, retained ignored artifacts,
or environments; they were clean of tracked/untracked edits and were preserved.
This is code reconciliation, not an archive-deletion or storage-cleanup task.

## Remaining boundary

The prepared software has no measured physics-fidelity result. Two independently
measured rigid jaw landmarks, current synchronized RGBD, gateway clock association,
new experiment authority and fresh independent validation are still required.
No robot, camera, fitting sweep, held-out source or paid compute was used.

## Closeout

- Capture preparation committed/pushed at `deb3bd4`.
- Final required suite: **380 passed**; adjacent science/scene suite:
  **21 passed**; native build/pre-camera smoke: **six passed**.
- Native `check --profile agent` and generated `agent-goal --check` pass on main.
- Maintenance review: `docs/reviewer-messages/maintenance-20260906-rgbd-reconciliation.md`.
- Executor evidence: `docs/session-logs/maintenance-20260906-rgbd-reconciliation.md`.
- Exact final Git/remote/authority state is retained after the closeout commit
  in `outputs/reconciliation-20260906/final-state.json`.
- The next active work requires the independently measured physical inputs
  listed in the acquisition guide. There is no admitted physics-fit successor.
