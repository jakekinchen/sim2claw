# Training dojo metadata adapter verification

Scope: the owner-requested software integration between Sim2Claw's operations
atlas and MicroDuck's Duck Lab. The native adapters were authored separately;
only the versioned schema and data-only fixtures are shared. Active training,
frozen policy/evaluator bindings, robot gateways and runtime environments were
not changed by this Sim2Claw task.

## Reproduced checks

```bash
uv run --locked pytest -q tests/test_workspace_adapter.py tests/test_ops.py tests/test_ops_cli.py tests/test_agent_context.py tests/test_dev_loop_state.py tests/test_dev_loop_lifecycle.py tests/test_dev_loop_runner.py tests/test_dev_loop_bench.py
```

Result: **257 passed in 21.44 seconds**, including 117 adapter tests.
Output: `outputs/operations/adapter-tests.txt`. This is focused/adjacent
validation, not a claim that the entire repository suite is green.

The adapter tests independently cover all 30 shared fixtures, native declaration
and authority-path rebinding, source/HEAD drift, dirty snapshots, native gate
refusal, duplicate JSON keys, numeric overflow, nonfinite and recursive values,
timezone-qualified timestamps without optional jsonschema format extras,
traversal/symlinks, bounded FIFO rejection, inert hostile entrypoints, false
execution/portability flags and CLI failure exit codes. Fresh-process import
checks keep simulator/provider runtimes out of the adapter path.

The shared schema SHA-256 is
`7f6115335dac03c0493940ed9f63d1aba0c741ba55defd434b5208acedf52bf0`.
The shared fixture SHA-256 is
`7ea788e0ddce6ce77a99ae18fb1c87589ec5437806ed68ed6d2b8efde0f6eaa4`.
Both are byte-identical in the peer repository. Each native conformance command
accepts three valid synthetic envelopes and rejects 27 invalid ones.

## Bilateral source-bound evidence

`outputs/operations/adapter-bilateral-receipt.json` retains both real exports'
paths, SHA-256 and Git identities; exact reader hashes; all four producer/reader
checks; both native conformance results; and the native ABI comparison. Each
inspection uses an explicit producer root. Both readers accept both exports.
The native Sim2Claw command compares the four declared SO-101 profiles with
MicroDuck's fourteen-action profile and reports their differences explicitly.

The retained copies are `outputs/operations/sim2claw-workspace-exchange.json`
and `outputs/operations/microduck-workspace-exchange.json`. Regenerate exports
after any referenced source or Git HEAD changes. Receipts describe exact
observations at their recorded time, not perpetual checkout agreement.
Generated packets and receipts remain ignored; no run artifacts are imported.

The peer independently retains its check under
`docs/workspace/exchange/receipts/20260905/interop.json`, with its own
`docs/workspace/exchange/CONFORMANCE.md`. The adapter owners coordinated through
the active tasks recorded in `DOJO_ADAPTER.md`, and their guides require both
readers, mirrored schema/fixtures and migration guidance for future changes.

## Review and claim boundary

See `adapter-review.md` for the independent native ABI and input review.
Review found and fixed stale hardcoded authority paths/replay constants,
JSON nesting and blocking non-regular-file reads. The parser tests also caught
overflow-number acceptance and optional timestamp-validator behavior.

`agent-goal --check` still passes with 49 lines. The campaign compiler correctly
refuses the operations feature branch because the campaign requires `main`.
No authority file was rewritten to alter that result. Metadata conformance
does not establish robot/policy portability, causal physics diagnosis, task
success, current process liveness, training readiness or physical authority.
No training, paid compute, robot access, external publication or merge occurred.

The existing interactive atlas report is regenerated from the expanded map;
its previously unavailable real-browser visual QA remains explicitly open.
Use the verified terminal commands for current adapter inspection.
