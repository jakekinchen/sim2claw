# Development and software checks

Use `scripts/check_operations.py` for changes to operations history retrieval,
metadata exchange, Git inspection, and workcell declarations. It shares the
same explicit test groups and lock-derived dependencies with
`.github/workflows/operations.yml`. It runs software tests and never grants
campaign, simulation, training, hardware, or paid-compute admission.

The [reviewed improvement ledger](refactor-opportunities.md) records this pass's
evidence, accepted changes, and deferred limits. The
[operations guide](operations/README.md) explains the tools themselves.

## Choose the environment for the work

| Work | Environment | First verification |
| --- | --- | --- |
| Operations CLI, evidence index, metadata adapters, Git/workcell declarations | Isolated inspection environment below | `python scripts/check_operations.py check` |
| MuJoCo scenes, renderers, learning or scientific analysis | Existing project runtime from `scripts/bootstrap_runtime.sh` | Targeted component tests plus the applicable evaluator/readiness checks |
| Admitted autonomous campaign | Native manifest, exact role packet, and existing dev-loop runner | `check --profile agent` followed by `agent-context --role <role>` |

The inspection environment is a small test environment derived from the existing
lock, not another dependency manifest or robot runtime. Keep active training
environments and evaluator-bound source files intact.

## Set up the inspection environment

Prerequisites are Python **3.12**, Git, and SQLite with FTS5 in that Python build.
The check command diagnoses missing or mismatched packages and FTS5 before
running tests. It performs no automatic installation. The following explicit
installation needs network access or a populated package cache:

```bash
cd /path/to/sim2claw
python3.12 -m venv outputs/operations-dev/venv
python3.12 scripts/check_operations.py requirements > outputs/operations-dev/requirements.txt
outputs/operations-dev/venv/bin/python -m pip install \
  --no-deps --require-hashes --only-binary=:all: \
  -r outputs/operations-dev/requirements.txt
outputs/operations-dev/venv/bin/python scripts/check_operations.py check
```

If Python 3.12 is managed by `uv`, `uv python find 3.12` identifies its executable;
use that path in place of `python3.12`. The package versions and artifact hashes
come from `uv.lock` each time. The dependency closure includes platform-conditional
inspection dependencies conservatively; ambiguous versions require an explicit
maintenance change instead of a guess. If no wheel matches the current host,
installation fails visibly instead of compiling an unreviewed source package.

The generated `outputs/operations-dev/venv/` and `requirements.txt` can be rebuilt
after checking that no active process owns them. Preserve any other receipts or
unrecognized files placed there. This location is separate from the durable
feedback journal at `outputs/operations/journal.sqlite`; do not delete the whole
`outputs/` tree.

An already synced project environment can use the same check without installing
anything else:

```bash
.venv/bin/python scripts/check_operations.py check
# Or let uv validate the existing project lock first:
uv run --locked python scripts/check_operations.py check
```

## Discover and select checks

```bash
python3.12 scripts/check_operations.py list
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite operations
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite adapter
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite workcell
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite git
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite contracts
outputs/operations-dev/venv/bin/python scripts/check_operations.py check --suite runner
```

Omit `--suite` to run every named group. `list` prints the exact files and locked
dependency versions without collecting tests. The script resolves the checkout
from its own path, so invoking `/path/to/worktree/scripts/check_operations.py`
from another directory still checks that worktree. It sets source import paths
for the selected checkout and does not depend on an editable install elsewhere.
Each checkout/worktree should use its own ignored inspection environment.

The final `OPERATIONS_CHECK_RESULT` JSON line records the selected files,
interpreter, lock hash, collected/passed/failed/skipped counts, duration, and
exit codes. Pytest prints failure and skip reasons immediately above it.

| Exit | Meaning |
| --- | --- |
| `0` | Every collected test in the named group passed; at least one test ran |
| `1` | Tests failed or required coverage was incomplete, including skips/xfails/deselection |
| `2` | Setup or collection failed, or execution was interrupted |
| Other nonzero | Pytest's native failure code is preserved, including `5` for zero tests |

There is no blanket skip allowance. A skipped platform check is visible and
makes the named required suite incomplete. Windows support is not established
by the current Unix-oriented fixtures. The runner clears inherited
`PYTEST_ADDOPTS`/`PYTEST_PLUGINS`, disables automatic plugin loading, and ignores
configured `addopts`; those must not silently select fewer tests or load unrelated
project plugins. It has no generic pytest-argument passthrough.

For a change outside these groups, discover the nearest existing tests and run
them directly in the full project runtime:

```bash
rg --files tests | rg 'test_.*component'
uv run --locked pytest --collect-only -q tests/test_component.py
uv run --locked pytest -q -ra tests/test_component.py
```

Replace the illustrative filename with an existing test file. Inspect collection,
failures, and skips before reporting a result. A broad `pytest -q` run has
additional runtime, fixture, and platform requirements; it is not the default
operations check. Simulator tests and renders do not establish physical success.

## Checkout authority and diagnostics

Autonomous workflow work still begins with the existing commands:

```bash
uv run --locked sim2claw check --profile agent
uv run --locked sim2claw agent-context --role executor
```

Use the role appropriate to the work. On the separate `codex/operations-atlas`
maintenance branch, the native campaign correctly refuses because its manifest
expects `main`. Read that refusal; do not rewrite the manifest, switch branches
over dirty work, or edit frozen contracts to make it green. Owner-authorized
software maintenance is checked with `scripts/check_operations.py check`
independently of native campaign admission. `GOAL.md` and historical filenames
do not override it.

For admitted campaign jobs, reuse the existing
[`dev_loop/runner.py`](../src/sim2claw/dev_loop/runner.py) and native context packet
for command identity, process leases, logs, and receipts. The operations check
script is only the small local/CI test entry point; it does not replace that
runner or dispatch historical commands.

Use `ops git-health` before committing staged payloads and `ops status` to inspect
authority/coverage. In the isolated environment the lightweight CLI is available
without installing the project:

```bash
PYTHONPATH=src outputs/operations-dev/venv/bin/python -m sim2claw.ops --json status
PYTHONPATH=src outputs/operations-dev/venv/bin/python -m sim2claw.ops git-health --check
```

CI installs only the inspection closure and runs the same default suite. A local
pass is local evidence; only an observed remote workflow result proves CI ran.
