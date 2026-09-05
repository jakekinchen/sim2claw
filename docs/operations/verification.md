# Operations atlas verification

Candidate date: 2026-09-05. Baseline: `9a91ba850149270685076ceade762bb367808f31`.
Branch: `codex/operations-atlas`. This verifies a software operations foundation,
not a simulator, learned policy, physical task, or future architecture milestone.

## Automated checks

```bash
uv run --locked pytest -q \
  tests/test_ops.py tests/test_ops_cli.py tests/test_agent_context.py \
  tests/test_dev_loop_state.py tests/test_dev_loop_lifecycle.py \
  tests/test_dev_loop_runner.py tests/test_dev_loop_bench.py
```

Result: **140 passed in 16.99 seconds**. Retained output:
`outputs/operations/validation.txt`.

The checks cover incremental content hashing, preserved timestamps, tombstones,
cap changes, symlinks and newly nested repositories, malformed text/JSON, literal
query handling, stale sources, recording/hash identifier lookup, same-byte
citations, bounded context and matching human annotations, byte accounting,
separate journal durability and migration, concurrent appends, metadata polling,
all CLI entry points, terminal controls, inert HTML data, report path confinement,
exact citation navigation and unchanged adjacent agent/dev-loop contracts.

Additional checks passed: `agent-goal --check` (49-line projection), main and
operations help paths, Python compilation, generated JavaScript syntax, and
`git diff --check`. Operations entry-point tests verify MuJoCo, NumPy and Torch
are not imported. No whole-repository test result is claimed.

The initial `check --profile agent` and exact role packets passed on baseline
main. The feature branch correctly triggers the existing campaign's main-branch
identity refusal. Six canonical campaign/authority files were compared byte for
byte to baseline and remained unchanged; hashes are retained at
`outputs/operations/campaign-preservation.json`. No campaign gate is bypassed.

## Actual corpus and measured samples

The final scan considered **9,816 text sources**, indexed **9,382**, and explicitly
skipped **434** sources over the default 4 MiB cap (259 JSON and 175 JSONL files).
All discovered Markdown, ordinary log, stdout/stderr and request files were
within the cap. The source content read totaled **3,060,388,847 bytes**.

The broader one-time audit inventoried 134,561 local files; its counts include
media and use a different 5 MiB text cap. The history audit covered all 527
nonempty briefs, session, review and manager documents. These denominators overlap
and must not be added together. Programmatic coverage plus contextual source
reading is not independent reproduction of historical experiments.

One cold compressed-index sample took **70.339 seconds**. A subsequent full
content rehash changed zero sources and took **12.366 seconds**. An unchanged
metadata poll took **5.055 seconds**, correctly returned `changed=false`, and the
CLI watch smoke emitted `status=unchanged` without full reindexing. The index
occupied **599,154,688 bytes** in this candidate, compared with the approximately
6.4 GiB uncompressed development attempt. The cache retains compressed exact
source text; runtime JSON full-text search omits raw numeric array terms.

Two successful Reviewer-source queries returned five hits each: `authority`
took 0.6432 seconds and `hash` took 0.0194 seconds. These are individual local
measurements with uncontrolled cache conditions, not a general speedup claim.
The literal Reviewer-only `lease` query returned zero hits; retrieval does not
infer stemming or synonyms. A `verification lease` brief included relevant
proposed lessons and the matching journal annotation within its 12,000-byte
serialized budget. All **18 lessons / 51 source ranges** verified against current
bytes, and all **24 architecture nodes / 33 edges** resolved.

Receipts: `outputs/operations/final-scan.json`, `performance.json`,
`search-performance.json`, `watch-once.json`, `example-brief.json` and the earlier
development scan records. Human milestone/decision annotations are retained in
the independent `journal.sqlite`.

## Human report validation boundary

The generated 10.4 MB offline report contains Sources, Lessons, Structure and
Activity views. It uses safe data embedding, text-only DOM insertion, exact
citation excerpts/commands, declared snapshot time, explicit coverage and a
refresh command. It connects to no network service.

Browser Use rejected the local-file opening with: “The browser URL policy blocks
this action.” Its tool result explicitly prohibited alternate browser/URL/CDP
workarounds. No workaround was attempted. Static JavaScript, command, escaping
and structural checks passed; interactive behavior and visual layout in a real
browser are **unverified**. The report remains available for the owner to inspect
at `outputs/operations/report.html`.

## Independent disposition and remaining scope

See [review.md](review.md) for source hashes, adversarial cases and the independent
Reviewer disposition. The delivered layer supports local discovery, collective
lesson proposals, bounded context, operator feedback and visible system structure.
Cross-record semantic adapters, measured learning-effectiveness trials, live
execution adapters, distributed scheduling and simulation recipe promotion remain
explicitly proposed gates in the architecture catalog. No claim of a perfect
system, general agent-efficiency improvement or simulation fidelity improvement
follows from this software release.
