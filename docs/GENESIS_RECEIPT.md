# Documentation-Only Genesis Receipt

Recorded: 2026-07-17 America/Chicago

## Repository split

| Role | GitHub repository | GitHub node | Commit |
| --- | --- | --- | --- |
| Preserved full repository | `jakekinchen/sim2claw-imported-archive` | `R_kgDOTbOOGw` | `798491ecb1a88b64b96875634ad63397a55ab846` |
| Fresh documentation-first repository | `jakekinchen/sim2claw` | `R_kgDOTcEV1A` | `1d5f7c4058d59943030524fb2e30d2d0678fe98d` |

Both repositories are private. The preserved repository was renamed; it was
not deleted, rewritten, or marked archived. The new repository was created
with a new Git history and a new root commit.

## New-repository boundary

- Tracked file count at root commit: 135
- Imported reference-document count: 126
- Imported source bytes: 727,055
- Imported manifest SHA-256:
  `fed169bc8eaa4920983a76aded67d4218f5fb5d3d6e210dd0637536c431e8630`
- Imported-document hash mismatches: 0
- Non-document implementation files: 0
- Source code copied: no
- Runtime/configuration implementation copied: no
- Outputs, datasets, checkpoints, caches, or virtual environments copied: no
- Historical authority transferred: no

The nine non-imported files in the root commit are fresh active governance,
index, goal, build-plan, ignore, license, and boundary documents.

## Access continuity

Write invitations were created on the new repository for the working-team
accounts that had access or a pending invitation on the old working
repository:

- `Aishwarya0811`
- `jeffpape`
- `mahataabhinav`

Invitations remain pending until each user accepts. Existing permissions and
the earlier pending Aishwarya invitation remain attached to the preserved
repository after its rename.

## Interpretation

This receipt proves the repository split and document-byte transfer only. It
does not prove a simulator, runtime, model, evaluator, gateway, NVIDIA host, or
robot capability in the fresh repository. Those systems must now be built and
verified manually under the active clean-room rules.


## Addendum — clean-room boundary tightened (2026-07-17 evening)

The owner tightened the boundary the same evening: direct copies of
prior-project files are not retained in this repository at all, including the
reference documents this receipt originally sanctioned. The imported tree
(`docs/reference/imported/`, 126 files) was removed and replaced by two
freshly authored documents, `docs/reference/ARCHIVE_INDEX.md` and
`docs/reference/PRIOR_RESULTS_SUMMARY.md`, which restate the needed facts in
new prose and point into the archive repository for everything else. The
root `LICENSE` was freshly written for this project. A clean-room audit of
the new implementation found no copied files; two small helper blocks that
matched prior-project code modulo renames were rewritten with independent
structure. Working-tree file timestamps were refreshed in the same pass;
git records no file timestamps, and both root commits postdate the boundary
time. Archive material remains consultable read-only; bringing commits or
patches over from it (`cherry-pick`, `am`, `format-patch`) is prohibited
because those carry original author dates.
