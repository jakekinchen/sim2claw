# Four controls for project work

Use this contract at task startup and closeout. Scale it to the work: a routine
edit does not need an experiment protocol. Current campaign authority and the
user's separate software-maintenance scope remain distinct.

## 1. Retrieve before planning

Verify the checkout and current task. For autonomous workflow work, run the
existing agent check and exact role context. Then retrieve a bounded brief:

```bash
uv run --locked sim2claw ops brief --refresh "specific task and failure terms"
```

The CLI writes its local index/journal, including during a brief query. Use it
only when that task permits these cache writes. A read-only reviewer or a task
with narrower write scope reads a prebuilt brief and its original sources;
report missing/stale context rather than widening write authority.

`--refresh` rehashes admitted sources using the default 4 MiB per-file cap before
retrieval. For a deliberately larger corpus, use `ops index --max-bytes N`
followed by `ops brief` without refresh. Inspect coverage, omitted counts and
source freshness; a missing result is not proof no previous attempt exists.

Read the nearest relevant failure/repair or accepted result. State what changed
and what new information the next attempt can provide. Link history instead of
appending it to the working prompt. Reuse standing user authorization within its
scope; keep authorization, readiness and experimental validity distinct.

## 2. Check prerequisites before spending

Before costly work, check the prerequisites that could invalidate it: input and
runtime identity, actual hardware/model identity when relevant, dependency
access, feasible thresholds, required observations, and a discriminating
instrumentation/serialization fixture. Put cheap checks before full processing.
Use existing task-specific preflights and evaluators. If an indispensable
observation is missing, retain the blocker and the evidence needed to proceed;
do not substitute another parameter sweep.

## 3. Reuse or execute once

Look for an existing receipt or verified live worker at the same task, inputs,
code, runtime, evaluator and command identity. Use the existing receipt verifier
and owned-process checks; matching prose or hashes alone is insufficient. Reuse
eligible evidence or attach to the worker; otherwise launch one bounded attempt
under the applicable existing task contract. Dependency changes invalidate
reuse. Bind ownership to the actual worker and paid resources to the task and
cutoff; verify teardown when finished.

The historical `dev_loop` provides identity, lease and verification primitives;
its closed campaign is not reactivated by this contract. Run required checks
once at the final applicable identity. Optimize measured bottlenecks only under
output-equivalence checks.

## 4. Close with evidence and a reopening condition

Use the normal session/review record, with links instead of duplicate ledgers:

- intended outcome, previous attempt and changed variable;
- source/code/runtime/evaluator identities and reused receipt or worker;
- prerequisite result, measured result and verification scope;
- proof class, claim limits and exact review identity where required;
- closure reason, resource disposition and evidence that would justify reopening.

Keep result status, proof class and claim eligibility separate. Inspect event
behavior and representative visuals when endpoint scores cannot establish the
intended result. Retain failed and null attempts. Reopen for new evidence, a
materially changed identity or explicitly changed scope. `ops note` can point
to a closeout for later retrieval; it remains an annotation, not a review or
evaluator receipt.

## Limit the process itself

Reuse existing components. Add infrastructure only for a named, reproducible
failure blocking the next useful result, and make the repair as small as
possible. Retrieve detailed lessons on demand instead of turning each into a
mandatory skill, approval, document or test suite. The [18 source-linked
lessons](../../configs/operations/lessons.v1.json) support this consolidation;
their benefit on future work remains to be measured.
