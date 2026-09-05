# Repository organization and workcell declaration verification

Owner scope: organize both repositories, retain Git history and grow toward
cooperative arm/duck simulation, using existing battery hardware and local Mac
GPU compute first. This closeout accepts software organization and declaration
inspection. It does not accept a shared simulator, removable battery mechanism,
trained skill, physical task or remote-compute deployment.

## Implemented and checked

- Current navigation now starts at the native manifest and operations tools.
  The root pair-programming guide and old documentation index are explicitly
  historical. Their existing paths remain intact.
- `ops git-health` reports HEAD/index sizes, unique staged growth, largest new
  blobs, branch tracking and dirty-state counts. It preserves Git state,
  disables configured filters/filesystem monitors and provides an optional
  review exit code. Git may internally hash files for status; payload contents
  are never returned or evaluated. Reported blob bytes are not disk/upload size.
- `ops workcell` validates the existing-hardware plan, exact native action
  semantics, model joint/actuator types, gate dependencies and proposed timing.
  It creates no action values and loads no simulator.
- The artifact map distinguishes human journal data, derived index state,
  retained evidence and unclassified/active artifacts. No bulk movement,
  deletion, untracking, history rewrite or environment consolidation occurred.
- The accepted metadata v1 schema and fixture digests now have native freeze
  assertions; a new lightweight Sim2Claw CI definition exercises these tools
  without installing simulator packages. The peer also added digest assertions.

## Test and review evidence

The CI-equivalent local run passed **297 tests in 20.94 seconds**, including
74 workcell and 36 Git-health tests. It used Python 3.12.12 on macOS arm64 with
exactly 12 dependencies selected from `uv.lock` for pytest/jsonschema.
MuJoCo, NumPy, Torch and Genesis were not installed in that isolated test
environment. All 20 recorded source/test/config/workflow/lock hashes remained
stable during the run. GitHub's Ubuntu runner was not executed.

Receipt:
`outputs/operations-audit/organization-ci-20260905T105018.521452Z.json`.
SHA-256:
`1dc94d3335616f5ad97c60568a149c63a544b4499538af7aa35fa9074f649cf6`.
It retains the exact command, runtime, package versions, stdout and hashes.

Independent reviews found and fixed rehashed incompatible joint/actuator types,
deep AST parsing, and Git's ability to run configured clean filters during
status. Negative tests cover these cases. Review also confirmed exact remote
request constraints, the required gate dependency graph, malformed-input CLI
failure behavior and distinct 6/14-action planning buffers. No blocking finding
remained. Documentation review checked 48 local links/anchors and corrected
the backend-specific collision-filter and MJX-JAX claims using primary docs.

Live `ops workcell --peer-root ...` verified ten direct source hashes. Only
`declaration_check` passed; seven later gates stayed unmet. The shared plan
SHA-256 is
`0ec9b9e0bee51bd78680d132ba65b8cd1edc113cd21fa0d82c28a1f5865f9a31`.
The MicroDuck mirror checker accepts those exact bytes and the peer mirror;
tampered local data and a missing peer reject. That checker does not validate
the ten native sources; the separate Sim2Claw inspector does.

## Git history and active work preservation

MicroDuck workspace tools were committed by their owner as `a3b13cd`. The
shared plan, native digest checker and roadmap were then committed as
`82d6d96`, touching only `docs/workspace/coordination/`. The latter verified
all 1,144 foreign index entries were identical before/after the scoped commit.
Receipt: `outputs/operations/microduck-coordination-commit.json`.

The unfinished staged training release also has a recovery commit `dab8817`
on `codex/laser-dynamic-staged-snapshot-20260905`. A copied temporary index
produced the snapshot; the real index SHA-256 and active main HEAD were exactly
preserved. It does not include unstaged or untracked work and has no release or
training-acceptance meaning. Receipt:
`outputs/operations/microduck-staged-snapshot.json`.

The observed staged release added 148,895,429 unique uncompressed blob bytes,
so the new advisory budget correctly requested review. The data was retained
at its original paths. Exact duplicate receipt sources already share Git
objects; deleting their paths would weaken evidence with little storage gain.
The training task's ongoing changes remain its responsibility, including later
gait correction. This task did not commit that work onto main or interrupt it.

Sim2Claw's generated goal still passes `agent-goal --check` at 49 lines. Native
campaign, scene, gateway, model, replay and evaluator-bound source files remain
unchanged. The campaign's feature-branch refusal remains intact. No paid
compute or hardware was used. Commits and the recovery branch are local; no
remote publication or push was performed by this task.

Generated final inspection receipts and the refreshed report remain under
ignored `outputs/operations/`. The previous real-browser report QA limitation
still applies; the new terminal paths and local source-bound checks are verified.
