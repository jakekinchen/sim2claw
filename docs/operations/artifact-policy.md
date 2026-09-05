# Artifact ownership and retention

This map adds no new user-confirmation requirement. The owner's existing
cleanup authorization remains valid. Agents can establish ownership, activity
and source bindings through repository/process evidence and proceed with
authorized reversible work. A descriptive path map alone cannot establish
those facts or classify a mixed directory as disposable.

[The artifact policy](../../configs/operations/artifact_policy.v1.json) records
how to interpret local artifact homes. It is descriptive metadata, not a cleanup
command or an execution grant. It neither changes the operations scanner nor
moves, deletes, resets, stages or untracks files.

The default is **preserve until the owner classifies the artifact**. Apply these
rules before interpreting a directory name:

1. Preserve protected and evaluator-owned boundaries without inspecting their
   contents. Do not follow symlinks or cross nested repositories.
2. Tracked or staged files and receipt-bound evidence retain their exact paths
   and bytes, even under an ignored generated root.
3. Preserve active work and anything whose owner or activity is unknown. A
   process snapshot or missing lock cannot prove that an artifact is idle.
4. Preserve user data. Treat only explicitly identified projections as
   potentially rebuildable, after the preceding rules are satisfied.

| Home | Meaning | Retention |
| --- | --- | --- |
| `outputs/operations/journal.sqlite` and its SQLite sidecars | Durable human annotations | Preserve; rebuilding the index cannot recover these notes |
| `outputs/operations/index.sqlite` and its SQLite sidecars | Derived search index bound to the repository root | Rebuildable from admitted sources after the owner confirms it is idle; no reset is authorized here |
| `outputs/operations/report.html` | Saved view of the indexed evidence | Preserve until the owner checks its handoff value; regeneration produces a current view, not necessarily the same historical snapshot |
| `outputs/operations-audit/` | Review and verification receipts | Preserve exact referenced bytes and paths |
| `dist/` | Built Python distributions | Ignored at the repository root; preserve existing release snapshots until their release references are resolved |
| `test-results/` | Local browser QA output | Ignored at the repository root; preserve any referenced QA evidence |
| `runs/`, `outputs/`, `output/`, `artifacts/`, `datasets/`, `checkpoints/`, `tmp/` | Mixed experiment inputs, outputs, media, releases and temporary files | Preserve pending classification; specific entries above explain known exceptions |

SQLite sidecars belong to their live database. Do not reset a cache by deleting
the containing operations directory: the adjacent journal is user data. The
existing [storage documentation](README.md#coverage-storage-and-retrieval-limits)
describes how the index and journal differ.

The September 5 metadata audit found 76 tracked files beneath Sim2Claw's ignored
`runs/` root. That is an example of why Git tracking wins over an ignore rule;
the count is an observation, not a permanent policy condition. Artifact byte
totals describe logical file sizes, not reclaimable space or deletion candidates.

The maintenance inventory retained at
`outputs/operations-audit/maintenance-inventory-20260905.json` records metadata
for 134,195 regular files across these local homes, with two excluded boundaries
and no reported inventory errors. This is a non-atomic September 5 snapshot:
other tasks can create or change files during or after the scan. It includes
128,739 files in `runs/`, 4,800 in `outputs/`, and 484 in `datasets/`.
`checkpoints/` was absent and `test-results/` empty. No artifact contents were
read for this inventory; activity and untracked receipt bindings remain unknown.

The three entries in `dist/` were two built distributions and their generated
ignore file. Root ignore rules now protect future distribution and browser QA
output without depending on a build tool creating its own ignore file. Existing
files were neither moved nor deleted. The inventory provides concrete groups
for a future artifact-owner review; it is not a reclaim plan or proof that all
historical work has been archived. The [maintenance report](../refactor-opportunities.md)
records the bounded code and verification improvements separately.

Keep standalone receipt bundles, including their frozen source snapshots and
manifests. Git stores identical content blobs once, so repeated source paths in
receipts do not by themselves increase Git object storage. Consolidating those
paths can break receipt bindings and make a bundle harder to inspect independently.
Matching hashes establish source identity, not semantic validation or task success.

A later cleanup or archival implementation must present exact targets, ownership
and activity checks, proof-binding checks, a preservation or rollback path and
measured verification. This document supplies no such implementation. The native
campaign and training authorities remain separate from the organization plan.

The lightweight operations CI also freezes the accepted workspace adapter v1
schema and its 30-case fixture pack. Their digests are deliberately fixed in
`tests/test_operations_contract_freeze.py`. A change to the shared contract needs
an explicit versioned successor and bilateral agreement; updating a failing hash
assertion is not routine test maintenance. Keep the existing v1 files available
when introducing a successor. Each repository retains its native validator and
runtime.
