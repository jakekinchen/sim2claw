# Sim2Claw GapBench on Inspect

This package runs six hardware-free seeded reality-gap cases through either
Inspect SWE's Codex CLI or Claude Code adapter. Both harnesses receive the same
opaque public packets, five skills, six bridged host tools, Docker sandbox,
budgets, and deterministic sealed scorer.

## What this proves

The local fixture proves contracts, access separation, tool accounting, and
scorer determinism. It does not benchmark a language model and does not prove
physical transfer, robot task success, or simulator admission.

The sealed case set is deliberately absent from Git, wheels, and sandbox
files. The trusted host must provide its digest-bound path through
`SIM2CLAW_GAPBENCH_SEALED_SOURCE`; the public campaign contract contains only
the expected SHA-256, schema, and case count. Missing or changed sealed bytes
fail closed before a task or fixture is built.

Run the no-provider proof:

```bash
SIM2CLAW_GAPBENCH_SEALED_SOURCE=/private/path/gapbench-sealed-v1.json \
  uv run python scripts/run_gapbench_fixture.py
```

Load and inspect both tasks without invoking a model:

```bash
SIM2CLAW_GAPBENCH_SEALED_SOURCE=/private/path/gapbench-sealed-v1.json \
  uv run --group inspect inspect list tasks evals/inspect_gapbench/task.py
SIM2CLAW_GAPBENCH_SEALED_SOURCE=/private/path/gapbench-sealed-v1.json \
  uv run --group inspect python -c \
  'from evals.inspect_gapbench.task import sim2claw_gapbench; print(len(sim2claw_gapbench().dataset))'
```

Build and verify the shared sandbox:

```bash
docker build -t sim2claw-gapbench:0.1.0 evals/inspect_gapbench
docker compose -f evals/inspect_gapbench/compose.yaml run --rm default \
  sh -lc 'su agent -s /bin/sh -c "codex --version && claude --version"'
```

## Retrospective physical-telemetry task

The physical telemetry lane exposes nine read-only bridged tools over all 18
retained human-teleoperation episodes. It provides bounded synchronized slices
of requested, commanded, and measured joint positions; measured velocity;
cached raw motor-current proxy; monotonic/control/video timing; qualitative initial/final
frames; receipt outcome; and deterministic trace-comparison summaries.

Current is nominally polled at 5 Hz and cached into intervening rows; the
dataset does not identify which rows performed a fresh current read. The tools
explicitly return unavailable receipts for metric object trajectory,
physical contact state/force, instrumented grasp outcome, command-to-actuation
latency, camera capture latency, and exact simulator trace. They never infer
those quantities from video or operator success labels.

Generate the current-dataset JSON, CSV, and 18 comparison plots without a model
or physical action:

```bash
uv run python scripts/materialize_physical_telemetry_trace.py
```

Enumerate the Inspect task without invoking a model:

```bash
uv run --group inspect inspect list tasks \
  evals/inspect_gapbench/telemetry_task.py
```

The task returns endpoint frames as actual image tool content while retaining
all source recordings and evaluator state on the host side. Its terminal audit
only proves that the agent preserved the exact available/unavailable inventory
and comparison digest. It is not a learned-policy, calibrated-simulator,
domain-randomization, or transfer result.

## Fixed-data interaction-event task

The interaction-event lane turns the immutable trace into deterministic
gripper-phase candidates, row-level event-conditioned metrics, and nine-frame
full-resolution visual strips. Closure, loaded closure, transport, and release
are explicitly candidates or proxies: the retained data does not contain
instrumented contact, calibrated force, metric object trajectories, or true
command-to-actuation latency.

Materialize all 15 development episodes without a model call:

```bash
uv run python scripts/materialize_interaction_event_pipeline.py
```

Held-out materialization is a separate evaluator-owned operation:

```bash
uv run python scripts/materialize_interaction_event_pipeline.py \
  --partition held_out --evaluator-owned \
  --output-root runs/fixed-data-event-pipeline-v1/held-out-evaluator
```

Enumerate the matched Codex/Claude task without invoking either provider:

```bash
uv run --group inspect inspect list tasks \
  evals/inspect_gapbench/event_task.py
```

Each task session can read one synchronized strip, bounded event/metric data,
submit one finite-enum visual annotation, and submit one terminal evidence
audit. The receipt outcome is omitted from the annotator prompt. Signed raw
annotations can be compiled into deterministic agreement/disagreement output;
there is no model judge and annotations carry no promotion authority.

The same corpus also emits a deterministic phase-weighted sampling manifest.
It changes sampling probability only: the inventory remains 18 episodes and
7,741 unique rows, and the manifest grants neither training admission nor new
independent evidence. Real-versus-simulator phase comparison fails closed until
an approved, unclipped, unrepaired, row-aligned exact replay trace exists.

## Provider-backed campaign gate

Do not run a live campaign until model IDs, reasoning settings, harness order,
case split, attempt counts, token/time/cost limits, credentials, and publication
authority are frozen. Inspect SWE proxies the agent's model requests through
Inspect; it does not reuse an operator's interactive CLI subscription session.

After that separate gate, run one harness at a time with an explicit provider
model, preserving every failure and environment error:

```bash
uv run --group inspect inspect eval \
  evals/inspect_gapbench/task.py@sim2claw_gapbench \
  -T harness=codex_cli \
  -T sealed_source=/private/path/gapbench-sealed-v1.json \
  --model provider/model-id
```

Raw `.eval` logs, generated packets, state, and candidate workspaces are ignored.
Publish only redacted campaign summaries with configuration, image and skill
digests, all attempts, costs, and the synthetic-only claim boundary.

## Corrective-repair task

The companion task measures whether an agent can turn repeated
transfer-observable pregrasp residuals into the repository's existing typed,
bounded task-space proposal. It has four public/sealed synthetic cases, a
repair-specific five-skill bundle, six bridged tools, eight public candidate
evaluations (136 simulator calls), two probes, and one terminal submission.
The deterministic scorer has no model judge.

Run all non-model controls:

```bash
task_root=$(mktemp -d)
uv run python scripts/run_corrective_repair_controls.py --work-root "$task_root"
```

Enumerate the Inspect task without a model call:

```bash
uv run --group inspect inspect list tasks \
  evals/inspect_gapbench/corrective_task.py
```

After separately freezing and authorizing a provider campaign, use the same
task for either harness:

```bash
uv run --group inspect inspect eval \
  evals/inspect_gapbench/corrective_task.py@sim2claw_corrective_repair \
  -T harness=codex_cli --model provider/model-id
```

Validate the active low-cost pilot without making a provider call:

```bash
uv run python scripts/freeze_corrective_subscription_pilot.py
```

The active frozen contract is
`configs/evaluations/sim2claw_corrective_subscription_pilot_v1.json`. It uses
native Codex and Claude CLIs for subscription access plus a USD 1-capped
open-weight Groq lane. Inspect cannot reuse those interactive subscription
sessions, so this is a one-shot systems pilot rather than the canonical
interactive Inspect task. Its nine-job manifest is deliberately unauthorized
and contains environment-variable names only, never credential values.

After all nine normalized JSON outputs have been committed, score the complete
campaign and matched controls in one evaluator-owned phase:

```bash
uv run python scripts/score_corrective_subscription_pilot.py
```

The host refuses to reveal any scores while an output is missing or invalid.
The earlier
`configs/evaluations/sim2claw_corrective_provider_campaign_v1.json` remains the
archival 240-attempt Inspect/API factorial and has not been executed.

For a publishable comparison, keep case order, attempts, tool and simulator
budgets, skills, sandbox image, task limits, model snapshot, reasoning setting,
temperature, and retry policy fixed. Report unchanged, seeded-random, bounded
search, and oracle controls beside every model. The oracle is an instrumentation
ceiling; the synthetic cases do not establish a calibrated real posterior,
learned-policy improvement, or sim-to-real transfer.
