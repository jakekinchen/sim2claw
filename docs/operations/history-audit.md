# Operations history audit

Audit snapshot: `9a91ba850149270685076ceade762bb367808f31`, 2026-09-05.

The strongest opportunity is to connect existing evidence, decisions, failures,
and verification into one searchable operations interface. The history already
contains substantial workflow machinery. Rebuilding it from summaries would
repeat an observed failure: apparently complete components were bypassed by
manually selected experiments. A useful CLI should explain what changed, why a
step is proposed, which evidence supports it, what is still unknown, and which
existing command owns the next gate.

This is a retrospective software operations audit. Its proposals do not reopen
the simulation campaign. The live agent check and reviewer packet both passed;
the campaign was closed at OR156 with `active_card: null` and
`execution_admitted: false`. No simulation, hardware, paid resource, archived
implementation, or external agent session was used for this audit.

## Coverage and method

| Tracked source root | Content documents | Empty placeholders | Bytes | Lines |
| --- | ---: | ---: | ---: | ---: |
| `docs/session-logs` | 228 | 1 | 312,101 | 6,526 |
| `docs/reviewer-messages` | 91 | 1 | 92,990 | 2,047 |
| `docs/manager-log` | 8 | 1 | 16,673 | 388 |
| `docs/briefs` | 200 | 1 | 401,736 | 8,065 |
| Total | **527** | **4** | **823,500** | **17,026** |

`git ls-files` selected these four explicit roots. A program read every selected
file in full, recorded its SHA-256, byte/line counts, headings, and matching line
numbers for seven operational vocabularies. The generated inventory is
`outputs/operations-audit/history-coverage.json`; it contains all 531 paths and
explicitly excludes the four `.gitkeep` files from document counts. All eight
manager messages and representative source passages across early contracts,
review repairs, training, held-out corrections, renderer failures and
optimization, event analysis, and the final campaign closure were read in
context. The source anchors below identify the passages behind the conclusions.
Whole-corpus machine coverage is not a claim that every historical experimental
result was independently reproduced or every sentence was manually read.

Vocabulary matches occurred in 258 documents for stop/reject/failure terms, 386
for pass/completion, 250 for verification, 221 for authority, 112 for
time/compute/cost, 259 for hashes/identity, and 202 for context/handoff/drift.
These overlapping counts are **mentions, not outcome rates**. A passing unit
test, a successful terminal experiment, and a correctly enforced stop may all
appear in one document. The vocabulary and exact matching lines are retained in
the inventory so the counts are reproducible.

Scope exclusions: untracked local files; deleted files available only in Git
history; raw Codex/Claude sessions outside the repository; `docs/run-logs`, other
documentation roots, generated receipts, datasets, media, and command logs
outside these four roots. Referenced receipt existence, bytes, and original run
times were not revalidated. Reported historical measurements below are what the
source records state, not newly executed results. This bounded audit is one
input to the broader repository operations work, not an assertion that these
four roots contain every agent activity.

## Findings and design consequences

### 1. Canonical authority must outrank discovered historical prose

The original factory gap audit contains both a current buildout disposition and
a clearly superseded critique. Treating its old estimated completion table as
current would reverse the document's meaning. Development-loop review also
found a generated D4 declaration coexisting with a shadow D1 declaration.

Sources: `docs/briefs/008-learning-factory-buildout-gap-audit.md:13-20,45-65`;
`docs/reviewer-messages/030-autonomous-dev-loop-d1-d3-checkpoint-stop.md:19-24`;
`docs/reviewer-messages/031-autonomous-dev-loop-d1-d3-second-stop.md:12-18`.

Proposed operation: ingest history as evidence; obtain live admission only from
the current agent check/context. Show source time, snapshot, supersession, and
authority owner on every result. A context packet should be a concise projection
with drilldown, not concatenated historical goals. Curated lesson: `OPS-L001`.

### 2. Digests establish identity; semantic checks establish eligibility

The first checkpoint accepted stale reviews, a STOP disposition, and an
unverified audit as merge-ready. A second review still found canonically
re-digested fabricated checks and an invalid milestone/remote. Passing ordinary
tests did not expose these attacks. Repair required an exact check set,
status consistency, allowed milestones, remote identity, and linked current
test/review evidence.

Sources: `docs/reviewer-messages/030-autonomous-dev-loop-d1-d3-checkpoint-stop.md:11-18,26-35`;
`docs/reviewer-messages/031-autonomous-dev-loop-d1-d3-second-stop.md:7-18`;
`docs/reviewer-messages/032-autonomous-dev-loop-d1-d3-checkpoint-pass.md:12-26`.

Proposed operation: separate source-integrity status from semantic-admission
status; keep advisory lesson retrieval unable to manufacture a passing gate.
Curated lesson: `OPS-L002`.

### 3. Review should cover one exact candidate and explain the repair loop

Two checkpoint STOP reviews preceded acceptance. A later adapter review found
that output could be written before budget/separation checks. Its final review
covered 46 tests; a subsequent schema repair produced 47 tests and explicitly
required the final review to cover that newer identity.

Sources: `docs/reviewer-messages/030-autonomous-dev-loop-d1-d3-checkpoint-stop.md:22-24`;
`docs/reviewer-messages/033-autonomous-dev-loop-d4-d5-pass.md:12-24,26-38`.

Proposed operation: display candidate → findings → repair → verification →
independent disposition, with stale review links visibly invalidated after
changes. The number of reviewer files is not the number of reviews: later
executor logs also carry review dispositions. Curated lesson: `OPS-L003`.

### 4. Verification reuse and dependency invalidation belong together

Accepted checkpoint verification reused a 30-test receipt without launching
tests again. Earlier factory reuse omitted downstream implementation,
dependency, and binary identities. Later broad suites rediscovered stale
project-state and dataset-lineage bindings; recorded complete suites took
1,266.71 and 1,280.60 seconds. These are evidence for precise dependency checks,
not permission to skip required final gates.

Sources: `docs/reviewer-messages/032-autonomous-dev-loop-d1-d3-checkpoint-pass.md:12-18`;
`docs/briefs/008-learning-factory-buildout-gap-audit.md:118-141`;
`docs/session-logs/022-executor-sail-policy-flywheel.md:17-25`;
`docs/session-logs/024-executor-sail-publication-freeze.md:23-30`.

Proposed operation: expose existing exact-identity receipt reuse; preflight
dependency/source drift before expensive validation. Report reused proof,
focused proof, incomplete broad run, and broad pass separately. Curated lessons:
`OPS-L004`, `OPS-L006`.

### 5. Process ownership needs crash-resistant child identity

A runner initially leased the parent rather than the actual test child and did
not bind repository cwd. Repair added a pre-execution handshake and bound PID,
start token, command, and repository ownership; a crashed parent could no longer
cause duplicate work while its child remained alive.

Sources: `docs/reviewer-messages/030-autonomous-dev-loop-d1-d3-checkpoint-stop.md:16-18`;
`docs/session-logs/027-executor-dev-loop-control-plane-repair.md:15-25`.

Proposed operation: make process/lease status inspectable and associate progress
with the actual worker. Cleanup must verify ownership; elapsed lease time alone
must not authorize signaling an arbitrary process. Curated lesson: `OPS-L005`.

### 6. Feasibility, dependency access, and capability probes save wasted runs

GR00T reached model construction but stopped before optimizer step zero because
a dependency required gated access; the retained instruction was to pass local
access checks before provisioning again. A frozen route evaluator was
mathematically impossible: its maximum source clearance was 62.861793 mm while
requiring 88.9 mm. A renderer contract expected 19 unique assets, while the
manifest had 18 unique filenames/36 definitions and the implementation read all
36. These are different preflight failure classes.

Sources: `docs/session-logs/002-executor-groot-n17-brev-auth-gate.md:17-21,30-46`;
`docs/session-logs/051-executor-q05-preregistered-feasibility-audit.md:8-23`;
`docs/session-logs/148-executor-observable-registration-or76.md:11-21`.

Proposed operation: a preflight plan should derive counts from immutable inputs,
prove contract feasibility where cheap, validate dependency access, and only
then admit expensive work. A paid lease includes a bounded purpose, cutoff, and
verified teardown. Curated lessons: `OPS-L007`, `OPS-L009`.

### 7. Native crashes and environment failures are first-class verification results

The ObservableEpisode focused tests passed while a broad run reported 16
failures/6 errors and a separate unexcluded run hit a native segmentation fault.
Renderer probes also distinguished a unavailable GUI service from Chrome
SIGABRT and an exact cached WebKit abort. None produced renderer capability
evidence.

Sources: `docs/session-logs/060-executor-observable-episode-v2-min.md:13-29`;
`docs/session-logs/132-executor-observable-registration-or60.md:5-19`;
`docs/session-logs/133-executor-observable-registration-or61.md:5-20`;
`docs/session-logs/134-executor-observable-registration-or62.md:5-18`.

Proposed operation: classify assertion failure, identity drift, unavailable
tool, native crash, interrupted run, skip, and passed scope independently. Probe
native capabilities in bounded subprocesses and reuse a failure only for an
unchanged environment identity. Curated lesson: `OPS-L008`.

### 8. Instrumentation needs its own reproducibility gate before costly evidence work

A missing serializer left V2 with no receipt; the outputs stayed uninspected
and quarantined. OR133B later processed 222 baseline frames before discovering
that per-robot mask distance did not reproduce the union-mask statistic. A new
identity restored the exact classifier and retained separate masks only for
descriptive output.

Sources: `docs/reviewer-messages/058-proxy-collision-v2-quarantine-v3-freeze.md:3-8`;
`docs/session-logs/211-executor-observable-registration-or133b.md:3-23`;
`docs/session-logs/212-executor-observable-registration-or133c.md:3-16`.

Proposed operation: validate receipt serialization, predecessor identity, and
discriminating instrumentation cases using permitted fixtures before consuming
an official run budget. Preserve failed attempts; fixes create successor
identities. Curated lesson: `OPS-L010`.

### 9. Action lineage and clock meaning must be inspectable row by row

ObservableEpisode preserves requested, mapped, sent, and applied command rows,
not just hashes. The Pi stream audit showed that later-run video could not be
merged into the successful source and host-start-plus-PTS was not exposure
synchronization. OR156 then independently derived the clock association from
raw rows, narrowing one timing explanation while leaving application/exposure
timing unobserved.

Sources: `docs/session-logs/060-executor-observable-episode-v2-min.md:6-11`;
`docs/manager-log/007-pi-stream-intake-contact-causality-transition.md:14-23,31-47`;
`docs/reviewer-messages/228-observable-registration-or156-source-clock-provenance-audit.md:17-31`.

Proposed operation: expose source/run identity, units, clocks, uncertainty, row
ownership, and absent channels together. Exact action identity must remain
fixed when isolating simulator discrepancies. Curated lesson: `OPS-L011`.

### 10. Event and neighborhood diagnostics explain endpoint successes

OR50's reproduced endpoint success occupied one candidate where three
contiguous successful candidates were required. A 0.01 mm coordinate step
could change planar error by 194.082 mm; the selected trace lacked bilateral
named contact. Auditing 53 retained candidates revealed that none satisfied
four or five preterminal gates. This was obtained without rerunning dynamics.

Sources: `docs/session-logs/123-executor-observable-registration-or51.md:5-25`;
`docs/session-logs/125-executor-observable-registration-or53.md:5-28`.

Proposed operation: provide event tables, first divergence, gate-vector
intersections, robustness neighborhoods, and retained-family coverage beside
terminal scores. Show the exact sampled domain; do not claim the unsampled
continuum is exhausted. Curated lessons: `OPS-L012`, `OPS-L014`.

### 11. A missing discriminating observation is a useful terminal result

The SAIL operator integration replaced a manual 32-complete/514-replay/0-pass
baseline with a decision plane that selected unavailable force/deformation
measurement and stopped at zero interventions. OR23 likewise abstained when
four mechanisms lacked metric contact, relative velocity, support state, or a
named collision witness. OR156 closes only one row-clock explanation and
admits no successor.

Sources: `docs/manager-log/002-sail-live-operator.md:7-38`;
`docs/session-logs/095-executor-observable-registration-or23.md:9-40`;
`docs/reviewer-messages/228-observable-registration-or156-source-clock-provenance-audit.md:26-37`.

Proposed operation: make the blocker a typed prerequisite with evidence,
ownership, acceptable new input, and explicitly closed descendants. A new
search suggestion must explain what new information distinguishes it from the
closed family. Curated lessons: `OPS-L013`, `OPS-L014`.

### 12. Human review should expose semantic limits beside numeric passes

OR91 passed all frozen numeric visual gates, but six inspected frame pairs
showed missing/misaligned robot structure. The result retained its numerical
pass while rejecting a broader same-video claim. Existing Studio proof work
already demonstrates useful interaction: select a joint, scrub to source row
388, and synchronize video, pawn displacement, and playhead while keeping the
0/1 task result and missing channels visible.

Sources: `docs/session-logs/163-executor-observable-registration-or91.md:3-9`;
`docs/session-logs/086-executor-realized-action-c8-studio-proof.md:9-22,38-51`;
`docs/manager-log/008-visible-divergence-video-transition.md:7-27`.

Proposed operation: the CLI should drive an inspectable event/evidence model
that both terminal and future UI use. Preserve successful limited results and
show their exact scope, semantic review, and unresolved components. Curated
lesson: `OPS-L015`.

### 13. Optimize a measured implementation seam without changing its result

OR79 replaced the Python raster loop with dependency-free C11 while preserving
the exact triangle/color stream, all pixels, encoded image SHA, and
depth/occlusion counts. The record reports 22.0645 s versus 0.0356 s, a 620.1x
improvement for the raster stage in that bounded comparison. This does not
measure end-to-end speedup or all renderer workloads.

Source: `docs/session-logs/151-executor-observable-registration-or79.md:4-10`.

Proposed operation: make measured cost centers and reference/candidate
equivalence visible in optimization proposals. Retain an exact reference case
and a representative held-out performance workload before generalizing.
Curated lesson: `OPS-L016`.

### 14. Stable evidence IDs cannot come from filename order or task labels

The inventory contains 17 reused numeric session-log prefixes and one reused
brief prefix. OR125 has two distinct logs: `200` records a non-run caused by
identity drift; `202` records a later executed result. A second successful
recording's directory said `b5-to-a5` while its source receipt said brown pawn
`b2` to `b1`. These records must coexist without overwriting or relabeling.

Sources: `docs/session-logs/200-executor-observable-registration-or125.md:3-7`;
`docs/session-logs/202-executor-observable-registration-or125.md:3-10`;
`docs/session-logs/126-executor-observable-registration-or54.md:5-21`.

Proposed operation: key records by repository/path/content identity with
explicit attempt/card/source links. Keep raw title, semantic task identity,
run, and lifecycle event distinct. Curated lesson: `OPS-L017`.

### 15. Collective learning needs outcome evaluation, not favorable activity counts

The development-loop benchmark explicitly measures configured seeded-control
coverage, not general agent coding/research skill. The publication result
reports that a deterministic-plus-agent fixture added no recovery and doubled
evaluations. A well-functioning infrastructure can therefore be useful without
having demonstrated an improvement in agent effectiveness.

Sources: `docs/session-logs/027-executor-dev-loop-control-plane-repair.md:51-56`;
`docs/session-logs/024-executor-sail-publication-freeze.md:13-21`;
`docs/reviewer-messages/004-corrective-loop-closeout.md:17-31`.

Proposed operation: treat extracted lessons as proposed, source-bound advice.
Evaluate whether retrieval reduces repeated defects, time to locate authority,
review rounds, and verified task cost on a separately frozen task cohort.
Record failed and unchanged attempts as well as wins. Curated lesson:
`OPS-L018`.

## Prioritized operations structure

These are proposed capabilities, not claims that every feature is absent or
implemented. Existing `agent-context`, `dev-loop-*`, factory receipts, and Studio
should be mapped and reused before adding another owner.

| Priority | Capability | Human-visible result | Acceptance evidence |
| --- | --- | --- | --- |
| P0 | Source registry and coverage | Exact indexed roots, exclusions, identity, line-level evidence | Reindex is deterministic; changed/deleted source is detected; duplicate titles coexist |
| P0 | Current status and bounded context | One current admission view, active software task, blockers, next allowed command | Historical PASS/active text cannot override current closed state |
| P0 | Search and source-bound proposed lessons | Find failure/repair pairs and inspect original passages | Every lesson reference verifies; unsupported or stale advice is visibly unavailable |
| P0 | Separate lifecycle/proof dimensions | A STOP can coexist with a successful diagnostic closure | OR156 and OR50 fixtures retain their different disposition/result/claim boundaries |
| P1 | Dependency graph and verification planner | Explain affected checks, receipt reuse, invalidation, unresolved native failures | Exact matching proof reused; changed runtime/input/command invalidates reuse |
| P1 | Bounded task and process events | Actual worker, elapsed work, latest receipt, review needs, interruption state | Parent crash cannot duplicate work; cleanup cannot signal mismatched process |
| P1 | Failure-family and prerequisite registry | Closed family coverage and exact independent evidence needed | Same closed mechanism with unchanged inputs cannot be suggested as fresh evidence |
| P1 | Review transaction and human steering | Concrete candidate, review findings, proposed repair, accepted/rejected change | Steering records preserve source identity and cannot silently change campaign authority |
| P2 | Event-level analysis adapters | First divergence and action/clock/gate-vector inspection | Reads retained artifacts only; no hidden replay or absent-channel imputation |
| P2 | Performance and learning evaluation | Measured stage cost, avoided duplication, quality/cost tradeoff | Frozen reference/candidate cases; no speedup claim from log word counts |

The machine-readable proposal set is `configs/operations/lessons.v1.json`.
All lessons start as `proposed`; each separates the observed history from the
new operation and names a concrete validation. Their hashes bind cited source
files, not the truth of uninspected original receipts. Independent review can
accept, narrow, or reject these proposals without modifying the historical
records or the simulation campaign.
