# Workspace data and evidence release — 2026-07-28

Release:
`https://github.com/jakekinchen/sim2claw/releases/tag/workspace-data-20260728-v1`

This public, checksum-bound release makes the reusable source episodes, action
traces, camera footage, raw sensor captures, transfer runs, calibration
observations, receipts, and selected analysis outputs from the current
sim2claw workspace available without putting generated data in Git history.
The release is bound to commit
`3649574499d3716287666c1628e8739a06904223` on
`codex/geometric-microtransfer-20260727`.

## Download and hydrate

From a clone of the repository:

```bash
python3 scripts/download_workspace_data.py --list
python3 scripts/download_workspace_data.py \
  --destination workspace-data-20260728
```

The downloader uses the public GitHub API, verifies every asset against
`WORKSPACE_DATA_MANIFEST.json`, and recreates the original repo-relative
directory layout. Set `GITHUB_TOKEN` only if anonymous GitHub API rate limits
are a problem. Hydration requires `tar` and `zstd`.

Fetch a smaller analysis slice by repeating `--component`:

```bash
python3 scripts/download_workspace_data.py \
  --component source-episodes \
  --component bidirectional-registration \
  --destination workspace-data-20260728
```

## Corpus boundary

The release preserves the proof class recorded by each source or run. In
particular, a recording, motion trace, calibration observation, or
contact-free geometric transfer is not relabeled as task success, evaluator
admission, bidirectional task transfer, or six-domain Twin fidelity.

The source-episode component contains the reusable physical recordings and
action/state traces. At publication time, the main manipulation corpus had 29
receipt-bearing episodes, 13,800 samples, 688.91 seconds of action data, C922
footage for all 29 episodes, and paired D405 wrist RGB for nine. Direct
recomputation matched the recorded `samples.jsonl` SHA-256 for all 29. These
episodes remain unqualified sources pending separate replay and evaluator
admission.

## Intentional exclusions

The release is broad, but not a blind copy of the 23 GB working directory.
It intentionally excludes:

- credentials, `.env` files, dependency clones, locks, caches, and runtime
  binaries;
- `evaluator_privileged_state*` files;
- the still-sealed V03 registration heldout images, whose publication would
  invalidate the heldout gate;
- incomplete teleoperation attempts that never became source episodes;
- duplicate transfer archives and existing release assets already available
  from the 2026-07-19 and Phase A releases;
- regenerable simulator search frames, Playwright screenshots, test-process
  receipts, and other bulk derivatives that do not add a new observation.

`WORKSPACE_DATA_MANIFEST.json` is the authoritative machine-readable inventory.
It lists every published component, asset size and SHA-256, proof boundary,
source path, and every excluded class.
The tracked copy is
[`WORKSPACE_DATA_RELEASE_20260728.json`](https://github.com/jakekinchen/sim2claw/blob/codex/geometric-microtransfer-20260727/docs/reference/WORKSPACE_DATA_RELEASE_20260728.json).

## Public-data notice

The repository and this release are public. The published camera media was
collected from the robot workcell. The external `IMG_5431.MOV` source was
visually checked as workcell-only before inclusion. Hardware identifiers and
historical local paths may remain in hash-bound raw receipts where changing
them would break provenance.

Repository-authored material is distributed under the repository's MIT
license. No additional rights are granted for third-party models, software,
or media that are not included in this release.
