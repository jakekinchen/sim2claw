# Operations atlas

Use the terminal to retrieve prior work, prepare bounded agent context, inspect
the system structure, and leave feedback that subsequent briefs can include.
The offline report provides a second view over the same evidence model.

For local development and CI, use the [development guide](../DEVELOPMENT.md).
`python scripts/check_operations.py list` shows the exact named test groups;
`python scripts/check_operations.py check` runs them using that interpreter and
reports dependency drift, skips, failures, and zero-test runs explicitly. Its
inspection dependencies come from the existing `uv.lock`. A software-check pass
does not change native campaign admission.

```bash
uv run --locked sim2claw ops index
uv run --locked sim2claw ops search "authority" --kind review
uv run --locked sim2claw ops brief "verification lease" --max-bytes 12000
uv run --locked sim2claw ops lessons
uv run --locked sim2claw ops map
uv run --locked sim2claw ops watch --interval 5
uv run --locked sim2claw ops note --kind feedback --subject leases \
  "Show the prior failing receipt before proposing another verification run."
uv run --locked sim2claw ops events
uv run --locked sim2claw ops report
uv run --locked sim2claw ops adapter conformance
uv run --locked sim2claw ops workcell
uv run --locked sim2claw ops git-health
```

Global flags precede the command:

```bash
uv run --locked sim2claw ops --root /path/to/sim2claw --json status
uv run --locked sim2claw ops --json brief "byte equivalence"
uv run --locked sim2claw ops show docs/reviewer-messages/030-autonomous-dev-loop-d1-d3-checkpoint-stop.md --start 1 --end 40
```

Use `search` to obtain an exact discovered path for `show`.
The equivalent lightweight entry points are `sim2claw-ops` and
`python -m sim2claw.ops`. The operations dispatch does not import MuJoCo,
NumPy or Torch. Current-authority status uses the existing role-context compiler
and its existing jsonschema dependency. No dependency was added: Python's
SQLite/FTS5 provides transactional indexing and lexical retrieval; zlib stores
exact source text compactly. Both are bundled standard-library components.

## Daily operating rhythm

For repository organization and the future arm/duck environment, consult the
[shared workcell plan](SHARED_WORKCELL.md), [artifact policy](artifact-policy.md)
and [organization verification](organization-verification.md). `ops git-health`
reports Git tracking and new staged blob growth; add `--check` to make a review
signal return exit 1. Its defaults are 32 MiB total new staged blobs or 10 MiB
for one new blob. Existing evidence is retained. Run the same tool with global
`--root /path/to/microduck-rl-genesis` to inspect that repository separately.

`ops workcell --peer-root /path/to/microduck-rl-genesis` verifies the proposed
scene's direct native sources and displays the action schedule and unmet gates.
It constructs no scene and dispatches no commands. Without a peer root, those
source checks remain partial. Both commands run without simulator imports.

The [training dojo adapter](DOJO_ADAPTER.md) connects the Sim2Claw operations
tools with MicroDuck's native Duck Lab. It exchanges source-hashed metadata;
both projects retain their own robot interfaces, runtimes, queues and evaluators.
Use `ops adapter export` for JSON, `ops adapter check FILE --source-root ROOT`
to inspect a producer's exact declarations, and `ops adapter compare FILE
--peer-root ROOT` for compatibility and native ABI differences. Run
`ops adapter conformance` after either adapter changes. No capability command
from an envelope is executed.

1. Run the existing `check --profile agent` and exact role-context command.
   Read any refusal. The operations CLI does not change campaign admission.
2. Run `ops index`, then `ops brief "specific task terms"`. Inspect source
   freshness, relevant proposed lessons, matching human annotations and omitted
   counts. Use JSON output directly as a bounded agent input.
3. Choose an existing scoped contract, evaluator and test runner. Consult
   `ops map` for their locations, inputs, outputs and acceptance gates. The CLI
   does not run historical commands or promote the retrieved advice.
4. Use `ops watch` to see corpus changes and current status. It polls file
   metadata (including creation/change identity) before deciding to reindex;
   explicit indexing always rehashes admitted source bytes. `--count N` makes a
   watch bounded. Ctrl-C stops the watch without cancelling unrelated work.
5. Record feedback with `ops note --subject <topic>`. Matching annotations appear
   in later briefs and all recent notes appear in `ops events`. Notes remain
   advisory even when labeled `decision` or `milestone`.
6. Write the normal session/reviewer records, refresh the index, and regenerate
   `ops report` for the human-readable snapshot.

## What each record means

| Record | Meaning | What it does not prove |
| --- | --- | --- |
| Indexed source + SHA-256 | Exact historical bytes were captured within the declared scan limit | A receipt is semantically valid or a task succeeded |
| Search/show `freshness=current` | Selected source hash still matches at read time | All other indexed sources are current |
| Declared status/proof class | A structured source reports this value | Independent evaluation or execution admission |
| Lesson `proposed`, evidence `current` | The cited bytes and ranges match; advice is available to review | The technique improves a future task |
| Architecture node `existing` | A component is present at the declared path | It is currently authorized or active |
| Architecture node `implemented` | This release provides that operations surface | A future roadmap node is available |
| Human journal event | A durable local annotation with a sequence number | Authority to execute, train, spend, move hardware or merge |
| Current authority `unavailable` | The canonical compiler refused or could not verify state | Permission to use historical authority instead |

On `codex/operations-atlas`, the campaign compiler correctly reports branch drift
because the campaign manifest expects `main`. The software-operations work is
authorized by the owner's separate request. Campaign files and the validator
remain unchanged. This is visible in terminal status and the exported report.

## Coverage, storage and retrieval limits

The default inventory covers `docs`, `configs/decisions`, `outputs`, `runs`,
`.factory`, `.inspect_ai`, `output`, `artifacts`, and `tmp`, including tracked and
ignored local sources. Text extensions are `.md`, `.json`, `.jsonl`, `.log`,
`.txt`, `.stdout`, `.stderr`, and `.request`. The CLI accounts for unsupported
file extensions and excluded directory boundaries separately. It never follows
symlinks or crosses a nested repository, sealed/held-out directory or generated
operations output boundary. The atlas's own audit documents are excluded from
learning-source ingestion to avoid self-confirming feedback.

The default per-file cap is 4 MiB; `index --max-bytes` can raise it up to 64 MiB.
Oversized, missing, undecodable, unreadable and boundary-excluded sources remain
visible in coverage. JSON parse errors are metadata, not successful receipt
validation. Global Codex/Claude transcripts and deleted Git-history documents
are outside this release's repository-local corpus.

Documents and decisions have full-text search. Runtime JSON/JSONL indexes word
tokens and identifiers, including digit-leading recording IDs and hashes; raw
numeric array terms are omitted to keep the index compact. `show` retains exact
original spans, including numeric values. Search joins literal words with AND
on a source line and returns bounded excerpts. It does not infer synonyms or
causal equivalence. A brief can use individual meaningful terms when the joint
query has no hits; its exact included sources are inspectable.

`outputs/operations/index.sqlite` is a derived cache. Source bytes are compressed;
an explicit rescan hashes content even when file length and timestamps appear
unchanged. Deleting a source removes its searchable spans on the next scan and
retains a coverage tombstone. The index is bound to its repository's absolute
root and must be rebuilt after relocation. Concurrent scans are serialized by
SQLite transactions; this is not a distributed database.

**`outputs/operations/journal.sqlite` is user data. Preserve it.** It is separate
from the disposable index, serializes concurrent appends, and survives index
deletion/rebuild. Do not delete the whole operations directory when resetting
the cache. Generated reports and scan receipts live in the same ignored output
directory; none is added to Git.

The report is a saved, offline snapshot. It searches paths, metadata and the
first 600 characters of each source; the CLI searches the broader index and
checks selected hashes. Its Sources, Lessons, Structure and Activity views use
the same snapshot. No background server, hosted service or command execution is
hidden behind the page. Browser visual QA was blocked by the Browser Use URL
policy in this session; static JavaScript and adversarial rendering checks are
recorded separately from interactive verification.

## Audit, structure and next gates

- [History audit](history-audit.md): all 527 nonempty briefs/session/review/manager
  documents scanned, with contextual reading and source-backed lessons.
- [Runtime audit](run-audit.md): 134,561 local files inventoried, including
  receipts, scientific payloads, media and explicit content-scan caps.
- [Infrastructure audit](infrastructure-audit.md): current components, gaps,
  measured boundaries and reuse opportunities.
- [Implementation ledger](plan.md) and [independent review](review.md).
- `configs/operations/lessons.v1.json`: 18 proposed lessons, 51 source anchors.
- `configs/operations/architecture.v1.json`: 30 components, 48 typed edges,
  owners, paths, inputs/outputs, gates, next actions and five release milestones.

The next gates are schema-specific verification of cross-record relationships,
a frozen 20-question retrieval benchmark, measured lesson benefit, then live
event adapters and bounded execution through the existing runner. These remain
proposed in the map. Each must demonstrate an independently measured benefit
before becoming an automatic operating rule. This release does not claim a
perfect system or measured improvement in agent intelligence or simulation
fidelity.
