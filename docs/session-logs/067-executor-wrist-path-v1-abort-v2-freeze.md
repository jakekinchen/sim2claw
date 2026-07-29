# Executor log 067 — wrist/path V1 abort and V2 freeze

V1 referenced `current_task_scene`, which does not exist; the canonical helper
lives in `current_workcell`. The import failed before contract read, output
creation, model loading, or cell evaluation.

V2 resolves the helper from `current_workcell` and otherwise inherits V1.
Focused tests: `2 passed`; compilation and `git diff --check` passed. V2 output
is absent and physical authority is false.
