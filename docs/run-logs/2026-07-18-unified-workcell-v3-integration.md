# Unified Workcell v3 Integration

Date: 2026-07-18  
Branch: `agent/antler-mug-prop`  
Physical authority: false

## Stable work combined

The branch now carries the stable, committed parts of the current workcell
effort in one linear history:

- the Antler mug visual prop and paired 100 mm board/fiducial registration;
- canonical source-episode and pawn-evaluator contracts for the current v3
  workspace while retaining the historical 72 mm contracts;
- the bounded 100 mm sim-to-real bridge and grip-probe receipts;
- the owner-measured SO-101 mass profile, D405 payload estimate, and explicit
  frozen-dynamics compatibility boundary.

The measured-mass change was previously isolated in PR #5. It is integrated
here with the current workspace sources and regenerated assets. PR #5 can be
closed as superseded after this unified branch is published.

The active source worktree had additional uncommitted camera/video-calibration
work at integration time. Those files were not copied or modified. They remain
owned by that active agent and can be rebased onto this stable integration after
they are committed and validated.

## Mug visibility proof

The wide `studio_overview` continues to show the full workcell, where the mug is
necessarily small. A new inspection-only `studio_mug` camera and committed
`studio-mug.png` asset provide a close view in which the white mug, handle, red
square, stylized A, and ANT/ER wordmark are visible on the left window sill.
The camera and poster are not training observations and grant no physical
authority.

## Validation

- `uv run pytest -q`: 95 tests and 27 subtests passed.
- `uv run sim2claw scene-info`: reported the 100 mm v3 board/fiducial pose,
  four Studio cameras, 907 g bare-arm mass, and 1,006 g left arm with D405
  payload.
- `uv run sim2claw grasp-probe`: passed with 0.0934 m piece rise and continuous
  lift/hold jaw contact under the current measured-mass default.
- `uv run sim2claw studio-assets`: regenerated four source-hashed posters.
- Visual inspection: `studio-mug.png` clearly shows the Antler mug and logo.
- `git diff --check`: passed for the integration commit.
