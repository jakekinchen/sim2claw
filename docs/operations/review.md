# Independent operations review

Review date: 2026-09-05. Final disposition: **PASS for the bounded software R1
source, proof-semantics, and CLI scope**. All reproduced code blockers below
were repaired and independently retested. No remaining blocking finding was
identified in that scope.

Browser runtime and visual acceptance are **unverified**: the Executor reports
that the available Browser Use URL policy prevented opening the local report.
This source review does not waive or pass that visual gate. It does not accept
the proposed future architecture milestones or a claim of an ideal complete
operations system.

## Scope and authority

Reviewed `src/sim2claw/ops/core.py`, `cli.py`, `view.py`,
`tests/test_ops.py`, and both operations catalogs. The review covers source and
proof semantics, corpus boundaries, retrieval, lesson citations, configuration
mapping, journal persistence, CLI exposure, and frontend interaction code. It
does not claim browser visual acceptance, simulation correctness, hardware
access, execution authority, or improvement in agent effectiveness.

The required campaign check and reviewer context were attempted. Both refused
the branch because the campaign requires `main` and this software task runs on
`codex/operations-atlas`. That is the expected campaign boundary, not an
operations failure and not permission to change the campaign manifest. The
user-authorized software operations lane is reviewed separately.

The initial exact source hashes are recorded in
`outputs/operations-audit/review-source-snapshot.json`. The core snapshot hash
was `50fc50f7102980506af7b31f9eba290efe277af63ba8b9c830c4496be96af3b2`.
Sources were being finalized concurrently during the first pass; initial
finding references below describe that candidate. The final acceptance is bound
to the frozen file identities in the next section.
This reviewer made no code/config changes and no commits. Its mutations were
limited to this review and ignored review evidence; adversarial repositories
were temporary and contained authored fixtures only.

## Final accepted source identity and independent evidence

The final adversarial review and focused tests completed with all seven source
identities unchanged before and after execution. Receipt:
`outputs/operations-audit/review-final-receipt.json`, SHA-256
`03baa087ebc644bce8fa99672b65d3a11d697e044bfe2e1dbb7180f1ddbec236`.

| Reviewed file | SHA-256 |
| --- | --- |
| `src/sim2claw/ops/core.py` | `6a43d5c5189d7f6cfe10e8e4841317b0ddb935d192b46cd8133067f5fd1c4317` |
| `src/sim2claw/ops/cli.py` | `53046c1701c2869f3e17f8fb38b01689fabc4daac4ae85ba0dacdb036054926a` |
| `src/sim2claw/ops/view.py` | `bbb99471333473441ac1414eb0919f0f56bfec9ac6c7f2a89061af32bfec6409` |
| `tests/test_ops.py` | `2c17219bbdd1dd39d2ab105b51f3ff1a12f943ea56f288e0d2ad2ba0778879c3` |
| `tests/test_ops_cli.py` | `92a9ba69de5561d26ee346b0d52662d0ed3275ba090e90f60d24579063b22159` |
| `configs/operations/architecture.v1.json` | `853f3cd81167f9435054cf69f4a27c0a44eba34aa43cf670732f66393ee7af17` |
| `configs/operations/lessons.v1.json` | `132b0457fad97579169c98b3ed936a3db352dcb3a89ce5a2ba9c4b629be6012d` |

Independent command:
`uv run --locked pytest -q tests/test_ops.py tests/test_ops_cli.py` — **68 passed
in 5.51 seconds**. The suite includes actual CLI command dispatch, JSON output,
bounded brief size including Unicode, bounded watch behavior, report destination
confinement, lightweight imports, hostile HTML payload handling, and terminal
escape rejection. These tests use isolated software fixtures.

The reviewer also separately recreated the original adversarial scenarios:

- A previously indexed source entering a nested checkout becomes
  `skipped_boundary`; its new bytes cannot be searched and retained spans are
  removed. A parent-tracked source inside a nested checkout is also refused on
  its first scan. The repair is in `core.py:164-173` and the scanner's admission
  check before content opening.
- An empty source cannot support lines 1–9. Boolean, float, and string values
  for either line boundary now need review and provide no accepted excerpt.
  Exact integer citations to real lines still verify. The repair is in
  `core.py:462-488`.
- A source just over 4 MiB admitted through an expanded scan cap is current
  immediately after indexing and stale after an edit. Read-time verification
  streams under the absolute 64 MiB bound in `core.py:370-390`.
- A controlled source mutation immediately after the hash computation cannot
  substitute new text under the old digest. The final implementation hashes
  and extracts from the same bounded read in `core.py:462-488`; the test confirms
  that the mutation actually occurred and the excerpt remains the original
  verified content.

All 24 architecture nodes, 33 edge endpoints, 32 path references, 18 proposed
lessons, and 51 lesson source references were rechecked on the final candidate.
The live catalogs contain no missing implementation path or stale lesson
source. Catalog states remain advisory/descriptive, with later functionality
explicitly proposed.

The lesson citation navigation repair is present in `view.py:85-110`: selecting
a citation retains the exact excerpt, SHA, start/end lines, and an exact-span
CLI command. This was reviewed in code and structural tests only. Browser
interaction is still unverified.

## Initial blocking findings — all repaired

### R1-F01 — Enforce new nested-repository boundaries on retained sources (P1)

Anchor: `src/sim2claw/ops/core.py:163-187,244-255` in the initial snapshot.

`_discover()` detects a nested repository and excludes it from traversal, but
`scan()` unconditionally adds every old source back as a candidate. A source
indexed before its parent becomes a nested checkout is therefore still read.
The initial tracked-file candidate path also lacks the nested-repository check.

Independent reproduction: index `outputs/nested/data.log`, initialize a Git
repository at `outputs/nested`, and replace the source with a new marker. The
second scan lists `outputs/nested (nested repository)` in `excluded_boundaries`
yet indexes the new bytes. Search returns the new marker with `freshness:
current`. This contradicts the reported exclusion and can silently import
evidence from a checkout intentionally outside the source scope.

Required repair: apply current admission boundaries to every candidate,
including tracked paths and retained tombstones, before opening it. A boundary
change must remove searchable spans and retain an explicit excluded disposition
without reading new bytes. Test both a newly nested former source and a tracked
path inside a nested checkout.

### R1-F02 — Reject line references to an empty source (P2)

Anchor: `src/sim2claw/ops/core.py:407-426`, especially the conditional assignment
of `invalid_span` at line 420 in the initial snapshot.

Citation checking changes the state to `invalid_span` only if the source's line
list is truthy. For an empty file, a matching SHA-256 and a citation to lines
1–9 therefore produce both `freshness: current` and `evidence_state: current`,
with an empty excerpt. No cited line exists. This violates the lesson gate that
every supporting span verifies.

Required repair: once the source hash verifies, validate the line range even
when the source has zero lines; invalid ranges must set `invalid_span` and the
lesson must need review. Add empty-source and strictly typed line-number cases,
in addition to the existing nonempty out-of-range tests.

### R1-F03 — Use the admitted size policy when checking source freshness (P2)

Anchor: `src/sim2claw/ops/core.py:325-331` in the initial snapshot; CLI
`--max-bytes` is exposed by `src/sim2claw/ops/cli.py:26-27`.

The scanner permits an expanded `--max-bytes`, but `_freshness()` always rejects
files larger than the default 4 MiB as stale. Independent reproduction indexed
an unchanged file just over 4 MiB with an expanded cap; immediate search then
reported it stale. The label incorrectly signals identity drift and renders the
documented expanded-source path unable to return current evidence.

Required repair: bind the read policy to the indexed source/scan or compare
bounded streaming hashes against the recorded byte identity. Retain protection
against a source that grows after indexing. Tests must distinguish an unchanged
admitted large file, an edited large file, and a file that exceeds its admitted
bound after the scan.

The three reproductions are retained in
`outputs/operations-audit/review-adversarial-findings.json`. They do not depend
on the repository's original experiment receipts.

### R1-F04 — Bind the excerpt to the same bytes as its hash (P2, repaired)

The original `lessons()` implementation first called `_freshness()` and then
opened the source again with `read_text()`. An independently induced change
between those operations returned `new unverified content` with `freshness:
current` under the prior source SHA. The reproduction is retained in
`outputs/operations-audit/review-citation-race.json`. The final implementation
uses one bounded byte read for both digest and excerpt and passes the induced
mutation check described above.

## Checks and findings already closed

- The independent `tests/test_ops.py` run after the journal migration repair
  passed **32 tests in 2.34 seconds**. An earlier run during editing returned
  7 failures because the legacy SQLite connection was closed before its context
  manager exited. The author repaired it with `try/finally`; the passing rereun
  covers the corrected connection lifetime. This is a closed in-progress
  finding, not an outstanding failure.
- All **24 architecture nodes**, **33 declared edges**, and **32 declared path
  references** were checked. Every path exists and every edge endpoint resolves.
  The map labels later recipes, effectiveness evaluation, live event adapters,
  verified cross-record relationships, scheduling, and portability as proposed.
  Path existence alone is not a claim that the corresponding gate was executed.
- The actual curated catalog contains **18 proposed lessons** with **51 source
  references**. Every reference currently matches its whole-file hash and
  existing line range. All remain advisory. R1-F02 concerns malformed future
  citations, not a false source reference in this catalog.
- The CLI entry `uv run --locked sim2claw ops --help` executed successfully.
  Bounded brief and all other command exposure subsequently passed the final
  command-level suite above.
- Source text is inserted into the HTML DOM with `textContent`, and serialized
  snapshot JSON escapes HTML delimiters before entering its data script element.
  Terminal output escapes control and bidirectional formatting characters.
  Browser execution and visual interaction testing remain separately required.
- The source inventory is described as historical and unverified; the current
  authority surface calls the existing agent context compiler and defaults to
  denied admission when it fails. Historical PASS text, notes, and lesson
  citations do not become execution authority in the reviewed code.

## Acceptance limits and remaining verification

The existing tests exercise useful negative cases: source mutation with
unchanged size/time, missing files, oversized/invalid text, symlinks, initial
nested repositories, query escaping, proof-class preservation, source drift,
lesson citation drift, repository identity, journal isolation/durability, and
rebuild behavior. The initial suite did not catch the boundary cases above;
regressions were added and the final suite passed at the recorded identity.

Actual CLI commands for bounded brief, search/show, notes/events, watch, and
report, including error exit codes, passed. Report search/filter selection,
lesson citation navigation, structure edges, keyboard navigation, narrow
viewport readability, and hostile-text behavior remain to be exercised in a
real browser when a permitted local report surface is available.

The Executor separately reports final real-corpus coverage of 9,816 sources,
9,382 indexed, and 434 oversized JSON/JSONL sources, an approximately 599 MB
compressed index, a 12.366-second explicit warm full-hash scan, and a
5.055-second metadata poll. This reviewer did not independently repeat those
full-corpus timings. They are single observations, not a speedup distribution
or a guarantee for all hosts. The source explicitly labels metadata polling as
a change hint and always hashes bytes on an explicit index operation.

Runtime JSON search deliberately indexes narrative words rather than raw
numeric arrays; exact retained numeric spans remain available through `show`.
This storage tradeoff is disclosed in coverage metadata and frontend wording.
It limits numeric search coverage and does not establish a general analysis
query engine.

R1 is an evidence index, retrieval/context interface, proposed lesson catalog,
local journal, and interactive saved report. Its HTML explicitly says it is a
snapshot, and `watch` refreshes index/status rather than reconstructing every
agent action. Notes are annotations; there is not yet a live agent subscription
or cancellation interface. Cross-record semantic adapters and proof of improved
agent effectiveness remain proposed. A bounded R1 acceptance must not be
reported as an ideal complete operations system or as completion of every
future architecture milestone.


## Postcommit declarative closeout confirmation

Implementation commit inspected: `de2a94bee38aec33613b7e8f22d07813b3b7f2dc`
(`de2a94b`). The postcommit architecture delta changes only R1's state from
`implemented_pending_review` to `software_review_passed_visual_qa_unverified`.
The updated architecture SHA-256 is
`c7ebf71abdb265f7df3ae83cc497679e55362c15443fdbb5eb57178114b45a90`.
All other six files in the final review receipt remain byte-identical to their
accepted hashes. The plan and verification documentation accurately record the
scoped software PASS and leave browser interaction/layout unverified.

Disposition: **PASS for this declarative closeout delta**. No code or test
behavior changed, so tests were not repeated. The original immutable final
review receipt and its SHA-256 remain unchanged; this note records the separate
configuration-state update without rewriting prior evidence.
