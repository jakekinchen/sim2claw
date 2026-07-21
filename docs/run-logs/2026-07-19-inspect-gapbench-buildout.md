# Inspect GapBench Buildout Run Log

## Run identity

- Date: 2026-07-19
- Repository: `/Users/kelly/Developer/sim2claw`
- Proof class: synthetic benchmark infrastructure
- Goal: `docs/autonomous-workflow/goal-loop-inspect-gapbench.md`
- Status: complete

## Safety and authority boundary

- Existing dirty and untracked user work is preserved.
- No robot, camera, serial device, provider API, credential, or Brev resource is
  required or authorized.
- Learning Factory evaluator ownership remains unchanged.
- Raw attempts will be written only to ignored or temporary run directories.

## Build stages

| Stage | Status | Evidence |
|---|---|---|
| Spec and goal loop | complete | Goal contract and integration plan |
| Core contracts | complete | `GapCase.v1`, `AgentAttempt.v1`, campaign and receipt schemas |
| Six synthetic cases | complete | Opaque public cases plus host-only seeded specifications |
| Tool and scorer boundary | complete | Six tools, nine component scores, single-use sealed gate |
| Inspect integrations | complete | Codex CLI and Claude Code adapters load and run through the bridge |
| Skills and sandbox | complete | Five validated skills; pinned isolated image |
| End-to-end proof | complete | Twelve deterministic fixture attempts plus one mock run per harness |
| Full verification | complete | 487 tests and 328 subtests pass |

## Command log

### Dependency and contract proof

- `uv lock`: PASS; 165 packages resolved. Optional group pins Inspect AI
  `0.3.248`, Inspect SWE `0.2.66`, OpenAI Python `2.46.0`, and Anthropic Python
  `0.117.0`.
- `uv lock --check`: PASS.
- `uv run --group inspect inspect list tasks evals/inspect_gapbench/task.py`:
  PASS; `sim2claw_gapbench` enumerated without a model call.
- Five `quick_validate.py` runs: PASS for all shared skills.

### Deterministic scientific proof

- `uv run python scripts/run_gapbench_fixture.py --output
  runs/gapbench/local-fixture-v1`: PASS.
- Six cases and twelve attempts completed; every oracle repair outscored its
  unchanged control.
- Campaign digest:
  `add6903639e105b01cacc91b3aab9aac4ca833d94874abcfafbc4d851e919801`.
- Repeated runs produced identical scientific attempt fields in the focused
  determinism test.

### Sandbox and harness proof

- Built `sim2claw-gapbench:0.1.0` as
  `sha256:d5c8ac00e039c9ea1fa99f817d8506417d64d70f29774cfc1c1334d05c81c821`.
- Image contains Codex CLI `0.144.6` and Claude Code `2.1.199`.
- Agent user is UID/GID `10001`; network mode is `none`; the live-repo mount,
  Docker socket, video device, serial device, credentials, and robot path are
  absent. Inspect's root control plane retains only `CHOWN`, `SETUID`, and
  `SETGID` so it can inject files and drop the actual agent to UID 10001.
- Mock Inspect run, Codex:
  `runs/gapbench/mock-inspect-codex/2026-07-20T03-14-10-00-00_sim2claw-gapbench_KUNS3JdhjpRPgjmn4By8DL.eval`.
- Mock Inspect run, Claude:
  `runs/gapbench/mock-inspect-claude/2026-07-20T03-14-45-00-00_sim2claw-gapbench_Fznof6yp5uHoewXSCimb7S.eval`.
- Both harnesses completed through the actual agent/model bridge and scored
  `0.0` because the deterministic mock returned prose and made no terminal
  scientific submission. This is infrastructure proof, not model performance.
- `docker compose ... ps --all`: no benchmark containers remain.

### Preserved failures and corrections

- First mock launch: sample setup failed because Docker Desktop applied
  `noexec` to `/tmp`. The final compose explicitly uses an executable tmpfs,
  which Inspect requires for its generated setup script.
- Next launch: Inspect rejected tool schemas without per-argument docstrings.
  All six schemas now include complete parameter descriptions.
- Capability hardening initially prevented Inspect from changing ownership and
  dropping to the agent user. The final supervisor capability set is the
  minimal observed set above; the actual coding agents remain non-root.
- The first full suite had one failure because the optional dependency group
  changed `uv.lock`. The physical replay audit was re-executed read-only; its
  output retained the exact historical digest
  `40dc058e817cdc652297b32d92c37dd7abd63edd74851204f5ebaadb8426cb49`.
  Only its current-lock binding and reproduction note were refreshed.

### Final verification

- Focused GapBench and refreshed replay-receipt tests: 8 PASS.
- `uv build`: source distribution and wheel PASS.
- Full `uv run --group inspect pytest -q`: 487 tests and 328 subtests PASS in
  147.90 seconds.
- `git diff --check`: PASS.
- No provider-backed model request, credential, physical action, paid compute,
  or Brev resource was used.

## Current conclusion

### Publication-boundary refresh on 2026-07-21

The command log above records the original local build. Before publication,
the production sealed case set was removed from the Git/package surface and
bound to `SIM2CLAW_GAPBENCH_SEALED_SOURCE` plus campaign-owned SHA-256, schema,
and case-count checks. There is no package-local fallback and callers cannot
override the expected digest. Public tests inject unrelated throwaway evaluator
bytes under `tmp_path`; they do not expose or substitute the campaign cases.

The retained private case file reproduced the six-case, twelve-attempt fixture
and the task constructed without a model call. Nine focused tests passed. A
fresh source distribution and wheel contained no sealed fixture or Codex
visualization artifact.

The hardware-free GapBench implementation is complete and runnable for both
Inspect SWE harnesses. The evidence proves contracts, isolation, bridge startup,
scoring, cleanup, and deterministic seeded-case behavior. It does not establish
language-model benchmark quality, physical transfer, current pawn success, or
promotion; those require a separately frozen provider/model campaign and real
anchor evidence.
