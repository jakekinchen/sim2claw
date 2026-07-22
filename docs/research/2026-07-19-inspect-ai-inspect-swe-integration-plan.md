# Inspect AI and Inspect SWE Integration Plan

**Status:** proposed integration; documentation and import smoke only

**Date:** 2026-07-19 America/Chicago

**Authority:** no model/API campaign, simulator mutation, dependency change,
physical motion, held-out access, paid compute, or policy promotion is
authorized by this plan

## Decision

Use **Inspect AI** as the experiment, sandbox, transcript, budget, and scoring
harness, and use **Inspect SWE** as the adapter that runs the real Codex CLI and
Claude Code agent loops inside each benchmark sandbox.

Do not replace the Sim2Claw Learning Factory with Inspect. The Learning Factory
remains the domain workflow and evidence authority. Inspect runs controlled
agent attempts against exported reality-gap cases and records how well each
agent performs. A separately owned Sim2Claw evaluator still decides whether a
candidate improved fidelity or policy consequences.

The first integration should use Inspect SWE's built-in skill injection and
host-tool-to-MCP bridge. A standalone public Sim2Claw MCP server is not required
for the first benchmark slice. Once the six-tool contract described below is
stable, the same functions can be exposed as a normal MCP server for
interactive Codex and Claude Code use outside Inspect.

## Verified fit

The following was verified against current documentation and a clean temporary
Python 3.12 environment on 2026-07-19:

- `inspect-ai==0.3.248` and `inspect-swe==0.2.66` install and import together
  under Python 3.12;
- both packages declare Python `>=3.10` and are MIT-licensed;
- `inspect_swe.codex_cli()` and `inspect_swe.claude_code()` instantiate the
  real coding-agent harnesses inside an Inspect sandbox;
- both accept shared skill paths, MCP server configurations, host-side bridged
  tools, a system-prompt addition, a model selection, working directory,
  environment, sandbox identity, attempt count, and pinned agent version;
- Codex additionally exposes web-search mode, goal-tool enablement, an isolated
  home directory, and Codex config overrides;
- Claude Code additionally exposes native tool disallowing and separate model
  aliases for its model roles;
- Inspect captures bridged model traffic and agent transcripts and applies
  message, turn, token, wall-time, working-time, and cost limits;
- Inspect supports per-sample Docker/Compose sandboxes, sample files and setup,
  cleanup callbacks, retry/resume eval sets, deterministic custom scorers, and
  custom tool approvers; and
- the local machine currently has functioning Docker client/server access,
  Codex CLI `0.144.6`, Claude Code `2.1.199`, and `uv 0.9.29`.

The Inspect packages are not currently dependencies of Sim2Claw. The clean
smoke used an ephemeral `/tmp` environment and removed it afterward.

## What Inspect does and does not provide

| Need | Inspect/Inspect SWE support | Sim2Claw work still required |
| --- | --- | --- |
| Run real Codex CLI and Claude Code | Native `codex_cli()` and `claude_code()` agents | Pin versions and freeze per-harness configuration |
| Use shared skills | `skills=[Path(...)]` | Author vendor-neutral reality-gap skills and hash them |
| Give both agents the same tools | MCP configs and `bridged_tools` | Implement narrow typed Sim2Claw tools |
| Isolate cases | Per-sample Docker/Compose sandboxes | Build a public case image without hidden data or credentials |
| Enforce budgets | Message, turn, token, time, working-time, and cost limits | Freeze benchmark budgets and price active probes separately |
| Record trajectories | Inspect transcripts, logs, traces, and dataframes | Add Sim2Claw artifact and receipt identities to log metadata |
| Score outcomes | Multiple custom scorers and metrics | Implement deterministic fidelity, predictivity, safety, and discipline scorers |
| Retry/resume campaigns | `eval_set`, checkpointing, retry and resumption | Keep retries from becoming extra scientific attempts |
| Human-agent comparison | Centaur mode | Define a separate human-assisted track; do not mix with autonomous scores |
| Protect sealed held-outs | Sandbox isolation helps | Keep the evaluator and hidden case bytes outside the agent sandbox |
| Enforce robot authority | Not provided by default | Do not mount credentials/devices; use a separate operator-gated service |
| Promote a simulator or policy | Not an Inspect responsibility | Preserve Learning Factory evaluator and promotion ownership |

## Architectural placement

```text
Sim2Claw LF-05 / LF-07 / LF-12 evidence
              |
              v
      public GapBench case builder
              |
              v
   Inspect Sample + Docker sandbox
      |                       |
      |                       +-- shared reality-gap skills
      |
      +-- Codex CLI or Claude Code via Inspect SWE
              |
              +-- local shell in disposable public sandbox
              +-- six bridged Sim2Claw tools over MCP
              |
              v
      candidate + hypothesis + probe ledger
              |
              v
  host-side sealed Sim2Claw evaluator service
              |
              v
 deterministic scores + immutable attempt receipt
              |
              v
 optional LF-06 repair proposal or LF-12 counterexample
```

Inspect is outside the Learning Factory proof graph. An Inspect result may
produce a candidate proposal, diagnosis, or benchmark score. It may not mark
LF-05, LF-06, LF-07, LF-09, LF-11, or LF-13 as passed.

## Proposed repository slice

Keep the integration isolated from the robot/runtime dependencies:

```text
evals/inspect_gapbench/
  README.md
  task.py
  dataset.py
  agents.py
  case_schema.py
  tools.py
  approvers.py
  scorers.py
  metrics.py
  Dockerfile
  compose.yaml
  skills/
    freeze-case/SKILL.md
    localize-gap/SKILL.md
    design-probe/SKILL.md
    implement-repair/SKILL.md
    submit-evidence/SKILL.md
  fixtures/
    public/
  tests/
    test_case_schema.py
    test_tools.py
    test_scorers.py
    test_sandbox_boundary.py

configs/evaluations/
  sim2claw_gapbench_v1.json

docs/run-logs/
  <campaign receipts only; raw Inspect logs remain ignored>
```

Add Inspect packages to a dedicated `inspect` dependency group in the existing
`uv.lock`, not to runtime dependencies. Run them with an explicit group, for
example:

```text
uv run --group inspect inspect eval evals/inspect_gapbench/task.py@sim2claw_gapbench
```

Pin both Inspect packages and both agent binaries. Do not use Inspect SWE's
`auto`, `stable`, or `latest` agent-download behavior in paper runs. Build the
exact Linux agent binaries into the benchmark image and use
`version="sandbox"`.

## Case contract

One `GapCase.v1` should bind:

- case ID, track, proof class, and public/hidden role;
- source dataset or trace digest;
- policy/checkpoint/processor identity;
- baseline simulator, scene, reset, control, and preprocessing identities;
- public evidence manifest and editable candidate surface;
- allowed fault families and parameter envelopes;
- permitted tool tier and active-probe menu;
- prompt and skill bundle digests;
- public evaluator identity;
- sealed evaluator service identity, never its hidden bytes;
- token, cost, time, rollout, and probe budgets;
- allowed output paths;
- explicit forbidden inputs/actions; and
- terminal submission schema.

The sample copied into the agent sandbox contains only public case bytes. The
hidden fault values, hidden seeds, reference trajectories, physical verdicts,
and promotion thresholds remain outside the sandbox.

## Six-tool MCP surface

Implement these first as host-side Inspect tools and expose them to both
harnesses with `BridgedToolsSpec`:

1. `case_status(case_id)`
   - Return the frozen case identity, remaining budgets, available evidence,
     current submissions, and allowed next actions.
2. `read_evidence(case_id, artifact_id, slice)`
   - Return a bounded trace/frame/receipt slice from the public manifest.
3. `submit_hypotheses(case_id, hypotheses)`
   - Validate a ranked typed ledger containing mechanism, evidence,
     discriminating prediction, uncertainty, and abstention.
4. `request_probe(case_id, probe_spec)`
   - Execute only a predeclared simulated or read-only probe, charge its budget,
     and return an immutable probe receipt.
5. `run_public_evaluation(case_id, candidate_ref)`
   - Run visible development checks against a digest-bound candidate without
     exposing sealed outcomes.
6. `submit_candidate(case_id, candidate_ref, prediction, claim_boundary)`
   - Freeze the final candidate and prediction, invoke the sealed evaluator
     once, and return only its signed/digested score receipt.

Do not bridge arbitrary `factory-run`, unrestricted shell-on-host, evaluator
configuration, hidden-file reads, promotion, robot motion, or paid-resource
provisioning.

The standalone MCP server, when later extracted, should wrap these exact six
functions rather than invent a second contract.

## Agent configuration

Use one shared semantic configuration and minimal harness-specific adapters.

### Shared conditions

- identical case packet and workspace layout;
- identical skill contents and skill digest;
- identical six bridged tools and schemas;
- web search disabled;
- no network except the Inspect model bridge and allowed MCP bridge;
- one writable candidate workspace;
- no Docker socket, robot devices, camera devices, credentials, home-directory
  mounts, Brev credentials, or hidden evaluator mount;
- identical public simulator/runtime image;
- identical message, token, time, rollout, and probe budgets; and
- one scored final submission unless the experiment explicitly studies
  multiple attempts.

### Codex adapter

- `codex_cli(version="sandbox", web_search="disabled", goals=False)`;
- isolated `home_dir` inside the sandbox;
- explicit `model_config` matching the served model where supported;
- project-local AGENTS guidance generated from the case contract; and
- no global Codex state copied from the operator machine.

### Claude Code adapter

- `claude_code(version="sandbox")`;
- disallow WebSearch and any other unnecessary native tools;
- isolated Claude home/config inside the sandbox;
- project-local CLAUDE guidance generated from the same case contract; and
- no global Claude state copied from the operator machine.

Inspect SWE proxies model calls through Inspect rather than consuming the
operator's existing interactive Codex or Claude subscription session. A live
campaign therefore requires explicit Inspect model-provider configuration and
provider credentials. This is desirable for reproducible evaluation, but it is
different from manually opening the already-authenticated desktop/CLI tools.

## Shared skills

The benchmark should start with five skills rather than a large library:

1. **Freeze case** — verify identities, support, authority, and budgets before
   proposing work.
2. **Localize gap** — align real/sim phases, locate first divergence, maintain
   competing hypotheses, and state identifiability limits.
3. **Design probe** — choose a predeclared probe using predicted information
   gain, cost, risk, and the hypotheses it discriminates.
4. **Implement repair** — change one mechanism per candidate, preserve the
   baseline, add a regression, and bind the patch to its hypothesis.
5. **Submit evidence** — predict hidden consequences, declare uncertainty and
   claim boundaries, and freeze the terminal candidate.

Pass these paths through Inspect SWE's `skills` argument. Use the same source
files for the later Codex and Claude plugins so the benchmark does not test two
different scientific procedures accidentally.

## Sandbox and authority design

Inspect tool approval is useful for bridged tools, but it is not the sole
security boundary for the native coding agent's internal shell. Enforce the
benchmark boundary structurally:

- build a disposable per-sample container from a pinned image;
- copy public files into the sample rather than mounting the live checkout;
- run as a non-root user where practical;
- mount no host directories containing hidden data;
- mount no credentials or device nodes;
- prohibit the Docker socket and external network;
- send high-trust actions through typed bridged tools only;
- keep the sealed evaluator in the host process or a separate service identity;
- return aggregate evaluator receipts rather than hidden traces; and
- use task cleanup to terminate child processes and verify no paid worker was
  created or left running.

For `request_probe`, use a custom Inspect approver:

- auto-approve declared simulated probes within remaining budget;
- reject undeclared or over-budget probes;
- reject all physical probes in v0.1;
- optionally escalate a separately declared physical-probe track to a human;
  and
- terminate the sample on attempted hidden-evaluator, credential, or robot
  bypass.

## Scoring

Primary scoring must be deterministic. Do not use an LLM judge for task
success.

Implement separate custom scorers for:

- `localization_top1` and `localization_top3` on seeded cases;
- `heldout_residual_gain` against the sealed baseline/candidate comparison;
- `policy_consequence_agreement` where paired policy outcomes exist;
- `repair_non_regression` on already-passing public and hidden cases;
- `probe_efficiency` per charged probe, rollout, token, dollar, and minute;
- `evidence_discipline` for correct identities, abstention, and claim scope;
- `forbidden_action_rate` from tool, sandbox, and transcript events;
- `receipt_completeness` and deterministic rerun status; and
- a frozen aggregate score that retains all component values in metadata.

For real-anchor cases without a known true parameter, omit parameter-recovery
accuracy. Score predictive residual/consequence improvement and calibrated
abstention instead.

Model grading may be used only for a secondary prose-quality analysis. It may
not change admission, fidelity, safety, or promotion scores.

## Experimental matrix

Separate model, harness, skill, and tool effects instead of comparing product
bundles only.

### A. Infrastructure smoke

- one public synthetic case;
- one Codex CLI attempt and one Claude Code attempt;
- one inexpensive configured model or mock provider;
- one shared skill bundle;
- no sealed real data and no paid training;
- objective: prove sandbox, skill, MCP, receipt, cleanup, and scorer behavior.

### B. Harness-controlled comparison

Run the same served model through both `codex_cli()` and `claude_code()` with
the same case, tools, skills, and limits. This estimates harness effects.

### C. Model-controlled comparison

Hold the harness fixed and vary the served model and reasoning configuration.
This estimates model effects without changing the tool loop.

### D. Native product comparison

Run the preferred OpenAI model through Codex CLI and the preferred Anthropic
model through Claude Code. Report this separately as an end-user product
comparison, not as a pure model comparison.

### E. Skill and tool ablations

- no shared skills versus shared reality-gap skills;
- text/code tools versus trace/visual tools;
- passive evidence versus priced simulated probes; and
- one attempt versus a predeclared multi-attempt condition.

Do not start with the full factorial. Begin with one case, two harnesses, and
one shared model; then expand to six public development cases only after the
receipts and scores reproduce.

## First benchmark cases

Use six synthetic development cases with one primary fault each:

1. reset state outside policy support;
2. board/robot frame sign or near-180-degree orientation mismatch;
3. camera crop/resize or preprocessing mismatch;
4. observation/control latency mismatch;
5. joint zero or ordering mismatch; and
6. contact prior mismatch with an intentionally non-identifiable alternative.

Then add twelve separately generated sealed cases. The current 0/12 GR00T pawn
episode tuple becomes a real-anchor case only after its public evidence packet,
allowed candidate surface, and sealed outcome contract are frozen. It must not
be used as a hidden seeded-fault ground-truth case because its causal mechanism
is not yet known.

## Learning Factory integration

Map Inspect artifacts into existing stages without changing verdict ownership:

- LF-05 exports replay/support evidence into a case packet;
- LF-06 accepts an agent-authored calibration experiment or repair candidate;
- LF-07 remains the owner of before/after fidelity and policy-probe comparison;
- LF-12 receives typed failed attempts, counterexamples, and repair routes;
- LF-13 may publish the benchmark receipt but cannot promote from an Inspect
  aggregate score alone; and
- LF-10/LF-11 training/evaluation are outside v0.1.

Add two new non-authoritative receipt types:

- `sim2claw.gapbench_agent_attempt.v1`; and
- `sim2claw.gapbench_campaign_summary.v1`.

Each attempt receipt should bind:

- case, sandbox image, repo snapshot, policy, simulator, and evaluator digests;
- agent harness and binary version;
- served model/provider and generation/reasoning configuration;
- prompt, AGENTS/CLAUDE guidance, and skill digests;
- MCP/bridged tool schema digest;
- budgets and actual usage;
- tool calls, probes, candidate patches, hypotheses, and predictions;
- scorer values and aggregate; and
- completion, limit, error, forbidden-action, and cleanup outcomes.

## Dependency and release strategy

1. Add a locked optional `inspect` development group only after the task API
   and Docker smoke are reviewed.
2. Keep raw `.eval` logs, transcripts, candidate workspaces, caches, and agent
   binaries ignored; publish redacted summaries and selected trajectories.
3. Build the benchmark image from reviewed public dependencies and pin its
   digest in every case.
4. Treat Inspect and Inspect SWE as adopted public dependencies and record the
   exact reason for each in the dependency ledger.
5. Keep private physical media and provider credentials outside sample files,
   images, logs, and source control.
6. Extract an open-source package only after the Sim2Claw reference cases and
   tool schemas stabilize.

## Phased implementation

### Phase 0 — package and contract preflight

- add optional locked dependencies;
- freeze `GapCase.v1` and the six tool schemas;
- add the Docker image and one public fixture;
- add negative tests proving hidden paths and credentials are absent; and
- instantiate both Inspect SWE agents without a live model call.

**Exit:** clean clone can build the image, load the task, enumerate both
agents/skills/tools/scorers, and prove the sandbox boundary.

### Phase 1 — end-to-end synthetic smoke

- run one case through both harnesses;
- use identical model, skills, and budgets;
- exercise hypothesis submission, one probe, public evaluation, final
  submission, sealed scoring, cleanup, and resume; and
- verify stable scientific receipt fields across reruns.

**Exit:** both harnesses produce independently scored attempt receipts; no
hidden bytes enter either transcript or candidate workspace.

### Phase 2 — six-case development benchmark

- add the six public fault families;
- freeze deterministic scorers and aggregate weights;
- run skill/tool ablations;
- add Inspect dataframe/report export; and
- expose attempt replay in Studio or a linked Rerun recording.

**Exit:** scores reproduce and the largest failures are attributable to model,
harness, skill, or tool treatment rather than environment drift.

### Phase 3 — sealed benchmark and model study

- generate twelve hidden cases from a separately owned builder;
- freeze them before model selection;
- run the predeclared model/harness matrix;
- report all failed, limited, refused, and environment-error attempts; and
- release public task code plus hidden-evaluator methodology.

**Exit:** reviewer-reproducible leaderboard table with full configuration and
separate synthetic versus real-anchor results.

### Phase 4 — real-anchor case

- freeze a public packet for the current pawn failure;
- expose only admitted traces and derived evidence;
- score predictive improvement and abstention, not hidden parameter recovery;
- require an independently measured real anchor before any physical-transfer
  statement; and
- keep physical probes disabled unless a later operator-owned contract enables
  one exact action.

**Exit:** one causal or truthfully inconclusive Sim2Claw case study attached to
the general agent benchmark.

## Acceptance gates

The integration is not ready for a paper campaign until all are true:

- clean-clone task/image build passes from the locked environment;
- both pinned agent binaries run inside the same image;
- shared skill and tool digests match across harnesses;
- public and hidden case inventories are disjoint and hash-bound;
- hidden bytes are absent from sandbox layers, sample files, prompts, logs, and
  published artifacts;
- public evaluation cannot mutate the sealed evaluator;
- deterministic scorers reproduce from saved terminal artifacts;
- limit and cleanup behavior is verified under interruption;
- all costs, retries, refusals, crashes, and forbidden attempts are recorded;
- no trainer, model, harness, or Inspect scorer can promote itself; and
- real-anchor claims remain separate from seeded-fault benchmark scores.

## Immediate next implementation slice

Implement Phase 0 only:

1. add the optional locked dependency group;
2. create `evals/inspect_gapbench/` with one reset-support fixture;
3. define `GapCase.v1`, the six bridged tool schemas, and deterministic dummy
   scorers;
4. build one pinned Docker image containing both agent binaries;
5. instantiate the Codex and Claude solvers with the same skills and disabled
   web access;
6. test that neither sandbox can see the live repo, hidden evaluator, user home,
   credentials, devices, or Docker socket; and
7. stop before any provider-backed model call until the run matrix, model IDs,
   budgets, credentials, and publication authority are explicitly frozen.

## Sources checked

- Inspect AI tutorial and coding-agent integration:
  <https://inspect.aisi.org.uk/tutorial.html#coding-agents>
- Inspect AI Agent Bridge and bridged MCP tools:
  <https://inspect.aisi.org.uk/agent-bridge.html>
- Inspect AI sandboxing, task limits, approvals, and scoring:
  <https://inspect.aisi.org.uk/sandboxing.html>
  <https://inspect.aisi.org.uk/tasks.html>
  <https://inspect.aisi.org.uk/approval.html>
  <https://inspect.aisi.org.uk/scoring.html>
- Inspect SWE overview and agent-specific options:
  <https://meridianlabs-ai.github.io/inspect_swe/>
  <https://meridianlabs-ai.github.io/inspect_swe/codex_cli.html>
  <https://meridianlabs-ai.github.io/inspect_swe/claude_code.html>
- Current Codex customization/manual surface:
  <https://developers.openai.com/codex/codex-manual.md>
- Current Claude Code extension and plugin surfaces:
  <https://code.claude.com/docs/en/features-overview>
  <https://code.claude.com/docs/en/plugins>
