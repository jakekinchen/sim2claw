# Run evidence and runtime corpus audit

Audited 2026-09-05 at repository HEAD `9a91ba850149270685076ceade762bb367808f31`.
This is a read-only operations synthesis and local text inventory, not a new
simulation, hardware, policy, or scientific evaluation. Historical measurements
below are reported by the cited records; they were not rerun for this audit.

## Current boundary

`uv run --locked sim2claw check --profile agent` and the Reviewer role packet
both passed at audit start. The current campaign is OR156, with no active card,
`execution_admitted=false`, and an external-input boundary. The historical
development loop is closed by its retained terminal packet despite its committed
candidate state saying `active`. The operations work must not reactivate it.

The actual OR156 closeout demonstrates why “PASS” cannot be an overall success
badge: its scientific outcome is an accepted source-clock falsification with no
task advancement, and no successor is admitted. Its 0.0392 ms direct clock shift
and 1.1423 ms relative elapsed rebind at closure leave the selected camera frames
unchanged; exposure and actuator application times remain unidentified
(`configs/decisions/observable_registration_source_clock_provenance_audit_v1_closeout.json:4-21,54-85`).

## Coverage and exclusions

The ignored machine-readable inventory is
`outputs/operations-audit/run-coverage.json`. It records every enumerated file's
path, byte count, tracked/untracked membership and coverage disposition; scanned
text additionally has its SHA-256 and line count. JSON/JSONL parsing records
invalid input explicitly. The inventory is a point-in-time snapshot, not a live
watcher or proof that all content was semantically reviewed by a person.

| Local corpus | Files inventoried | UTF-8 text scanned | Oversize text skipped | Other payloads metadata only |
| --- | ---: | ---: | ---: | ---: |
| `docs/run-logs` | 167 | 166 | 0 | 1 |
| `configs/decisions` | 259 | 259 | 0 | 0 |
| `outputs`, excluding this audit's own outputs | 4,760 | 3,463 | 125 | 1,172 |
| `runs` | 128,741 | 4,454 | 189 | 124,098 |
| `.factory` | 2 | 2 | 0 | 0 |
| `.inspect_ai` | 462 | 429 | 0 | 33 |
| `output` | 123 | 26 | 0 | 97 |
| `artifacts` | 26 | 12 | 0 | 14 |
| `tmp` | 20 | 6 | 0 | 14 |
| `.codex` | 1 | 0 | 0 | 1 |
| **Total** | **134,561** | **8,817** | **314** | **125,430** |

The enumerated files total 34,937,806,375 logical bytes. The text cap was 5 MiB
per file. There were no directory-walk, stat, UTF-8 decoding, or read errors and
no missing roots in this snapshot. Of 7,127 scanned `.json` files, 7,126 parsed;
`runs/transfer-oriented-brown-plan/constrained-v2.stdout.json` did not. Scanned
JSONL had no invalid records. This does not establish validity of the 314
oversize text files.

All 165 Markdown run logs were scanned, as were the one JSON run log and all
259 decision JSONs. Their conclusions and failure/status headings were extracted
for corpus-wide triage; the causal findings below received closer source review.
Session, Reviewer and Manager log synthesis is covered by the companion audit;
this inventory's denominator is explicitly the roots listed above.

All 332 simple `runs/` or `outputs/` path references recursively extracted from
decision JSON values existed locally. Existence is not checksum verification:
some strings name directories, references repeat, and this count does not cover
Markdown links, embedded commands, absolute paths or external material. Seventy-six
files under `runs` are tracked, so treating every `runs` file as ignored loses
evidence. Conversely, ignored outputs are local availability, not portable
repository evidence.

Excluded from content scanning: media and binary payloads, datasets, checkpoints,
environments, vendored dependencies, archive repositories and global Codex
sessions. The discovered `.claude/worktrees/sim2real-so101-pawn-fidelity-9c75a2`
is a separate historical checkout with 34,598 files; it was inventoried to
identify the duplicate-repository boundary, not merged into current authority or
read as a second implementation source. `.codex` contains one visualization,
not a local agent transcript store. No credentials were read. No hardware,
provider API, training or paid compute was used.

## Findings that should shape the tool

### 1. Reuse the existing governed pipeline and give it one evidence index

Learning Factory already recorded stage inputs, outputs, verdict owner, proof
class, cleanup, implementation identities, content-addressed outputs, recoverable
leases and campaign/generation namespaces. Its real component campaign admitted
source data, trained locally, independently rejected the policy and produced no
callable package. That is successful infrastructure with a negative task result,
not an unfinished factory or a successful policy
(`docs/run-logs/2026-07-19-learning-factory-buildout.md:5-30,62-107,133-145`).

The missing operations layer is a joined, searchable representation of those
records: source -> contract -> attempt -> artifact -> evaluation -> independent
review -> next admitted transition. Each edge needs its source location and
expected hash. A SQLite cache can index these edges without replacing existing
contracts. If a receipt is missing, stale or invalid, display that state rather
than synthesizing a fresh authoritative result.

### 2. Store several outcome axes; never count passing words

The task orchestrator contains 35 attempt receipts with 24 `failed`, 10
`completed_command_cycle_unverified_task_outcome`, and one
`stopped_after_failed_forward_checkpoint`. These are attempt receipts, not the
separate `final.json` session documents and not 10 task successes. For example,
`runs/task_orchestrator/owner_directed_base_loop/20260719T202758Z-7845842b/attempt_receipt.json:341`
uses the explicit unverified command-cycle status.

Keep `process_outcome`, `review_outcome`, `scientific_outcome`, `task_outcome`,
`proof_class`, `authority`, and `claim_boundary` separate. Missing means unknown.
Preserve the raw status string because many legacy schemas encode valuable
meaning there. Report corpus counts as artifact counts, not independent trials;
copies and generation links can otherwise inflate apparent evidence.

### 3. Optimize the bottleneck only after freezing an equivalence check

OR76 rejected a renderer that looked nearly complete: 11/12 gates passed, but
the manifest held 18 unique assets against a contract expectation of 19, and the
implementation made 36 reads. Its concrete successor was a manifest-derived
unique-asset cache
(`configs/decisions/observable_registration_host_native_mesh_zbuffer_renderer_capability_v1_closeout.json:30-55`).

OR79 then reported identical raster pixels and depth-update/occlusion counts
while reducing one raster stage from 22.0645 s to 0.03558 s, a reported 620.1x
stage speedup. The receipt explicitly denies full-timeline verification,
MuJoCo equivalence and fidelity claims
(`configs/decisions/observable_registration_native_rasterizer_byte_equivalence_v1_closeout.json:28-62`).

This is a useful repeatable optimization recipe: measure stage wall time and
I/O count, derive cache keys from source identity, freeze a reference, optimize
the hot loop, then compare exact outputs where equivalence is required. Record
end-to-end timing separately; a stage speedup is not an application speedup.

### 4. Prevent stale verification from consuming another full run

The 81 retained development-loop test receipts include three failed receipts.
Two broad runs spent approximately 1,181 and 1,197 seconds before failing the
same Learning Factory component test. The earlier exception was a project-state
hash mismatch, not a simulated task failure
(`outputs/dev-loop/final-test-receipts/full/1bc27e0984a697d7856a7442e6c1c4f07b701385e334df4dc1ef635b5b7b98c3/test.log:481-497`;
`outputs/dev-loop/final-test-receipts/full/9713ed4c74360f9aac509f8a31284651a89fee7371fbedf21c23d114c34f2dfd/test.log:497-498`).

A third broad run took approximately 1,341 seconds and failed a publication
evidence pairing assertion
(`outputs/dev-loop/studio-simulator-twin-31e5ead/full-repository/51f0da43dc759b6769ddfb7bfd4a172cd0d51951e1ee1bc40caf278e220d7104/test.log:70-80`).

An operations preflight should verify changed source/receipt identities and run
the previously failing relevant test before requesting the expensive broad
gate. Test reuse must include commands, dependency/compiler identity, source
hashes, environment and relevant authority inputs. Do not hide a failure by
automatically rebinding a frozen hash; a reviewed reproduction owns that change.
The stored leases include two `orphaned` records. They are historical lifecycle
states, not evidence that processes are alive now.

### 5. Make finalization a transaction with independent post-commit evidence

The D6 closeout was corrected after independent review found a self-referential
claim: a commit cannot already contain successful tests, remote equality and
review of its own final hash. The solution kept committed state as a candidate
and put terminal authority in a generated post-push packet binding exact HEAD,
test tiers, review, clean tracked files and zero live leases
(`docs/run-logs/2026-07-22-autonomous-dev-loop-d6-closeout.md:19-49`).

The operations tool should show candidate, verification, review and terminal
packet as separate states. A new note, audit report, lesson approval or status
badge cannot close the campaign. The same log reports zero escaped seeded
defects for independently receipt-gated review versus 9/9 and 8/9 for configured
alternatives; this supports the narrow seeded control design, not a general
claim about agent intelligence (`...d6-closeout.md:51-71`).

### 6. Treat clock ownership and media progress as different signals

Recorder hardening already separated growing source bytes from process liveness,
used a bounded grace and stall watchdog, recorded staged shutdown and retained
failure even if a partial container was readable
(`docs/run-logs/2026-07-24-d405-capture-reliability.md:63-82`). C922 v4 retained
the startup gap as warm-up and qualified only the frozen steady callback window;
it did not claim exposure continuity, synchronized clocks or calibration
(`docs/run-logs/2026-07-24-avfoundation-c922-callback-delivery-v4-terminal-verified.md:14-32,56-66`).

Expose process heartbeat, artifact byte growth, newest valid source sample,
source-clock provenance and last completed evaluation independently. A spinner
or `running` JSON state cannot prove healthy progress. Historical `running`
attempts should say “last recorded running; liveness unchecked” until an
identity-validated process probe establishes current liveness.

### 7. Record falsified hypotheses and discriminating prerequisites

Workcell V3 reduced trace residuals while losing contact/lift consequences; its
later correction also disclosed that jointly changed joint offsets broke an
action-frozen comparison. The record correctly retained different kinematic and
physics candidates and treated previously opened evaluation episodes as
confirmation (`docs/run-logs/2026-07-20-pawn-workcell-fit-v3.md:9-41,66-83`).

External actuator validation improved pooled joint RMS by 3.6098% but rejected
the candidate because the frozen bootstrap interval crossed zero. Strict task
success stayed 0/11 (`docs/run-logs/2026-07-23-actuator-external-validation.md:30-47`).

Camera/base registration repeatedly converged to a boundary solution; that did
not establish identifiability or a metric anchor. No future unopened heldout
pose existed (`docs/run-logs/2026-07-26-current-c922-board-base-registration.md:19-37,50-76`).

A useful lesson therefore carries a mechanism family, intervention, frozen
invariants, evidence split, failed gate, confounders, attempted fixes, falsified
scope and minimum new observation required. Similar historical failures should
be retrieved before proposing a sweep. Retrieval may suggest a prerequisite;
it must never invent permission to execute it.

### 8. Preflight platform assumptions once and retain a runnable recipe

GapBench's preserved setup failures were concrete: Docker's non-executable
temporary mount, incomplete tool parameter documentation and insufficient
supervisor capabilities to inject files then drop privileges. The corrected
recipe bounded these assumptions and left actual agents non-root. Mock model
submissions scored zero; successful harness execution was not model quality
(`docs/run-logs/2026-07-19-inspect-gapbench-buildout.md:55-87,115-120`).

An environment recipe should record observed runtime, package lock, executable
identity, filesystem capabilities, allowed network/devices, smoke command,
failure signature and teardown evidence. Preserve a minimal reproduction rather
than embedding environment repair in each new experiment.

### 9. Give humans the same evidence graph as agents, plus an intent inbox

Studio already proposed coequal researcher and agent lanes, the same proof
classes and prerequisites, and deterministic read-only projections. It also
failed closed on stale state binding or invalid receipts
(`docs/run-logs/2026-07-24-studio-project-map-agent-access.md:10-24,35-55`).

The new CLI should add the missing operations history: what changed since the
last scan, what is known or stale, which mechanism failed before, what the agent
is doing now, which evidence closes its current gate, and exactly what input is
needed from the owner. Human notes and preferences belong to a timestamped
append-only operations journal with explicit non-authorizing semantics. Any
campaign action still routes through the existing reviewed contract/gateway.

## Minimum normalized record

```text
source: relative path, line range, sha256, size, tracked membership,
        discovery root, indexed timestamp, coverage status, parser version
identity: campaign, card, role, attempt, generation, implementation, environment
outcome: process, reviewer, scientific, task, raw status, proof class
evidence: referenced paths/hashes, observed presence, freshness, claim boundary
lesson: mechanism, trigger, attempted change, invariants, failed gates,
        confounders, validated scope, minimum new input, confidence, citations
operation: current authority source, admitted next transition, resource lease,
           progress timestamps, cleanup, human note and acknowledgement
```

Unknown fields remain null and extracted statements remain reported claims.
Generated source indexes and this audit are derived views, never authority.

## Acceptance evidence for the operations layer

1. Scans disclose every chosen root, skipped/missing/unreadable source and byte
   cap; incremental results agree with a clean rebuild, including same-length
   edits, deletions and symlink boundaries.
2. Every lesson has source locations and hashes; changed or missing evidence
   makes the lesson stale rather than silently current.
3. Search and inspection preserve raw statuses and proof classes; neither
   `PASS` nor completed command cycles become task-success claims.
4. A read-only snapshot and human-readable report work without Studio, hardware,
   cloud accounts or a model API. Human notes never mutate campaign authority.
5. The current OR156 boundary and historical dev-loop closure survive a scan,
   a note, a UI interaction and cache deletion/rebuild unchanged.

The useful target is measurable reduction in repeated discovery, duplicate
experiments, stale verification and unexplained waiting. This audit does not
establish a perfect system or prove those future efficiency gains.
