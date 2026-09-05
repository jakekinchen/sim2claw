# Maintenance audit and verified improvements

Date: 2026-09-05. Baseline: `529b9a1` on `codex/operations-atlas`.
Rubric: Refactor Score v1. Coordinator decision: **accept the bounded changes**.

Three passes implemented faster history search, simpler workcell validation,
and one discoverable local/CI check. All 330 required inspection tests passed.
This closes a software maintenance slice, not every subsystem or artifact.

## Scope and architecture

The checkout was clean at entry. The native OR156 campaign has no active card;
its agent check and executor context compiler reject this feature branch because
the manifest expects `main`. That refusal remains intact. The owner's maintenance
instruction supplies this separate software scope; its tests grant no campaign,
training, evaluator, device, deployment or paid-compute authority.

The native CLI routes scene/replay, learning, evaluation, gateway and Studio
commands. `src/sim2claw/ops/` provides the evidence index, separate human journal,
terminal/report views, Git metadata, workspace exchange and workcell declarations.
See the [operations guide](operations/README.md) and
[30-component catalog](../configs/operations/architecture.v1.json).

Mapping covered 3,468 tracked paths and parsed the structure of 518 Python source
modules without importing them. Deeper review concentrated on operations core,
adapter, workcell, Git inspection, renderer, existing dev-loop runner, bootstrap,
lock, CI and related tests. A structure survey is not a semantic audit of every
module. Active MicroDuck processes and other worktrees remained undisturbed;
this pass changed only Sim2Claw.

## Ranked findings

| Finding | Score / priority | Confidence | Risk / effort | Decision |
| --- | --- | --- | --- | --- |
| R-P01: Rank paths without sorting compressed source bodies | 87 / P1 | High | Low after snapshot regression / small | Implemented |
| R-D01: Share exact local/CI checks and discoverable setup | 87 / P1 | High | Low; stricter coverage reporting / small | Implemented |
| R-Q01: Remove redundant fixed-gate graph state | 74 / P2 | High | Low / small | Implemented |
| R-O01: Classify build/QA homes and prevent accidental tracking | 68 / P2 | High for named homes | Low / small | Implemented; broad archival deferred |
| R-P02: Reduce scanning for document-only FTS matches | 55 / research | Medium | Medium / needs characterization | Deferred |
| R-Q02: Reuse repeated native-declaration AST parses | 55 / research | Medium | Medium / unprofiled | Deferred |
| R-D02: Redesign global discovery or split the native CLI | 50 / research | Low beyond structure | High / large | Deferred |

### R-P01: Fetch source bodies only as needed

- **Type / problem:** Performance. Search sorted compressed source bodies before
  Python could stop at the requested line count, and hashed documents whose
  query terms never appeared on the same line.
- **Implemented change / simplification:** In `ops/core.py`, sort the same rank/path
  candidates, retrieve bodies as consumed, and hash only sources contributing a
  citation. An explicit read transaction keeps ranking and body retrieval in
  one SQLite snapshot. No cache, dependency, migration or candidate-count limit.
- **Value / evidence:** Less work on a frequent evidence-retrieval path. Final
  paired measurements and exact result comparisons appear below. Eight added
  behavior cases include a concurrent-refresh reproducer that failed without
  the transaction and passed with it.
- **Safety / rollback:** Rank/path order, kind filtering, limits, Unicode word
  boundaries, hashes, stale state and line text remain covered. Reverting this
  source change requires no data migration. Persistent caching and early
  candidate truncation were rejected because they can weaken citations.
- **Forward value / judgment:** Keep the existing evidence store usable as history
  grows; measure other query shapes before optimizing them.
- **Score breakdown:** Impact 18, simplification 15, safety 14, evidence 15,
  forward value 7, effort-adjusted return 8, judgment 10; no cap. Accepted.

### R-D01: One exact inspection-check entrypoint

- **Type / problem:** Developer experience and reliability, including intentional
  behavior change. CI owned a private resolver and test list; README setup led
  through the full simulator and unrestricted pytest. Exit zero alone does not
  establish complete required coverage.
- **Implemented change / simplification:** `scripts/check_operations.py` owns named
  groups, derives versions/artifact hashes from `uv.lock`, diagnoses setup and
  observes pytest outcomes. CI reuses it; the linked [development guide](DEVELOPMENT.md)
  explains setup, targeted checks, worktrees and the existing dev-loop runner.
  CI's private resolver/copied command and one duplicate history link disappear.
- **Value / evidence:** Missing dependencies, skips, xfails, XPASS, deselection
  and zero tests cannot produce a passing required-suite summary. Nineteen tests
  cover actual small pytest sessions and failure paths. Checkout-shaped fixtures
  prove source selection from another directory despite inherited pytest options;
  a real invocation from `/tmp` passed both contract tests.
- **Safety / rollback:** No second dependency manifest, automatic installer,
  scheduler or receipt framework. Rollback is confined to script/CI/docs. The
  stricter coverage result is intentional; Windows/platform gaps stay visible.
- **Forward value / judgment:** One discoverable place for future operations
  tests; the native dev-loop runner still owns admitted campaign jobs.
- **Score breakdown:** Impact 16, simplification 18, safety 14, evidence 14,
  forward value 8, effort-adjusted return 8, judgment 9; no cap. Accepted.

### R-Q01 and R-O01: Small maintenance improvements

`ops/workcell.py` derived a separate ID set, rebuilt the input gate graph and
traversed it after already comparing every dependency list exactly with the
fixed supported graph. It now retains only a seen-ID set for duplicates.
Variable frame-cycle and exact prerequisite checks remain. Six added behavior
cases passed against both implementations; the final workcell slice has 80 tests.
No test was deleted. Score components: 12/14/15/13/5/8/7 in the order above,
with no cap. Reverting the source/test diff needs no contract migration.

The inventory recorded 134,195 regular artifact files, including 76 tracked
files under ignored `runs/`. Root ignore rules now cover `dist/` and
`test-results/`; the [artifact policy](operations/artifact-policy.md) distinguishes
built distributions and browser QA evidence. Both paths passed `git check-ignore`;
neither root contained tracked files. This prevents accidental future tracking
without moving evidence. Score components: 10/10/15/13/5/8/7, no cap.
Reverting the rules does not alter existing data.

The inventory is a non-atomic metadata snapshot, not a reclaim estimate. No
artifact was deleted or relocated. Historical bundles, untracked receipt bindings,
active/unknown work and the human journal still need preservation. The audit
has not converted a broad directory into disposable data.

## Measured search result

Final candidate includes the transaction fix. Medians of three alternating
baseline/candidate pairs on the resident index, with a 20-result limit:

| Query | Baseline | Candidate | Ratio |
| --- | ---: | ---: | ---: |
| `action` | 1.936 s | 0.0217 s | 89.2× |
| `contact timing` | 0.695 s | 0.0889 s | 7.81× |

All 12 trial outputs matched exactly as canonical JSON, including order, text,
hashes and freshness. This measures the search function with read-only SQLite
connection setup. It excludes CLI startup, write-capable initialization, indexing,
simulation and agent productivity. No page cache was flushed. Other host work
remained active; final load averages were about 6.2–6.8. Earlier measurements had
different load/code states and remain separate; the table uses the final receipt.

The database had 9,816 discovered rows, 9,382 indexed rows, 3,060,390,951 admitted
source bytes and 599,154,688 SQLite bytes. Discovered bytes including skipped
sources were larger. Main-file stat and a single monitored connection's
`PRAGMA data_version` stayed unchanged. The receipt binds baseline, candidate
and benchmark-harness hashes.

Reproduce with reviewed baseline code and a new receipt path:

```bash
git show 529b9a1:src/sim2claw/ops/core.py > /tmp/sim2claw-baseline-core.py
PYTHONPATH=src .venv/bin/python scripts/benchmark_ops.py \
  --baseline /tmp/sim2claw-baseline-core.py \
  --output outputs/operations-audit/performance-search-repeat.json
```

The harness refuses existing receipts. An index must already exist and match
checkout root/version; corpus or host changes can change the measurements.

## Verification and retained evidence

Coordinator integration ran the default check in a fresh isolated Python 3.12.12
environment, offline from cached packages: **330 passed in 24.51 seconds**, with
zero skips, failures, errors, xfails, XPASS or deselection. Only the twelve locked
pytest/jsonschema dependencies were installed; no MuJoCo, NumPy, Torch or Genesis.
All 22 recorded source/config/test/workflow/lock hashes stayed stable. This is
local macOS evidence; GitHub's Ubuntu workflow was not executed.

Additional checks: shared adapter CLI conformance **30/30**, generated goal
projection **49 lines/pass**, and `git diff --check`. Frozen workspace schema,
fixtures and workcell recipe remain unchanged. Native agent/context checks
still refuse the feature branch; that is not a passing campaign.

Local ignored evidence under `outputs/operations-audit/`:

- `maintenance-integration-20260905T224815Z.json`: exact command, package inventory,
  full output and before/after hashes; SHA-256
  `6b6ffe441be9f252696ee1fd0dc13cbfb0508d9ed305c350b69d24260c6c6023`.
- `performance-search-final.json`: final trials and identities; SHA-256
  `2e6a4f09f540c68d3c7bacceae192471c66a81d5519c0ca25e0004a421924cca`.
- `maintenance-inventory-20260905.json`: per-home/group metadata and structure
  survey; SHA-256 `5f28023dfa0a82cc19d4242c0ae61ab8f79dee06bdfdd8bdd42d5fde03cf0a74`.
- `quality-pass.md`, `dx-pass.md`, `performance-report.md`: detailed agent scores,
  scoped tests and rejected alternatives. Old receipts were not rewritten.

Coordinator review required a stable SQLite snapshot and WAL-aware benchmark
checks, corrected an incorrect new metadata-test expectation, and narrowed prose
that had called a whole generated directory disposable. Integration includes
those corrections. No further code changes followed the passing integrated run.

## Deferred work and limits

- Document-level FTS can still require scanning many lines for a same-line match.
  A `source clock` profile exposed this cost during overlapping host work; it is
  diagnostic evidence, not a paired speed claim. A replacement needs exact
  newline/Unicode/citation characterization.
- Repeated adapter AST parsing is unprofiled. Do not add persistent caching or
  unify parsers whose native semantics/proof boundaries differ.
- Large native CLI, teleop and system-identification modules are review candidates,
  not proven dead code. No broad rewrite, dependency upgrade, test deletion or
  complete scientific-suite discovery was justified by this pass.
- Renderer selection state, atomic report replacement, Git safety wrappers and
  schema/native semantic validation protect different behavior and were retained.
- Full artifact-owner classification/archival, Windows support, remote CI and
  comprehensive simulation/hardware verification remain open. No external or paid
  resource was used. Arm/duck contracts remain compatible declarations; this
  adds no shared physics or battery-service capability.

## Ownership and Git record

| Pass | Exclusive writes | Verification |
| --- | --- | --- |
| Quality | Workcell inspector and its test | 80 tests |
| Performance | Index core, its test and benchmark harness | 48 tests plus paired measurements |
| Developer experience | Check script/test, CI, guide and README navigation | 19 tests plus real 2-test invocation |
| Coordinator | Ignore rules, artifact policy and this report | Diff review, 330-test isolated integration, native read-only checks |

Reviewed changes are recorded locally on `codex/operations-atlas`; find this
report's commit with `git log -1 -- docs/refactor-opportunities.md`. Receipts remain
ignored. This slice does not merge the feature branch or change another checkout;
it does not claim a remote workflow result.
