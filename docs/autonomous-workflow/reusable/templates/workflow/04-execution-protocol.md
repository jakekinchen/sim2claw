# Execution Protocol

## Slice Rule

The Executor does one smallest useful reviewable slice. A slice should usually fit in one commit and one session log.

Good slice examples:

- Add safe parsing with focused tests.
- Normalize one data model and expose indexes.
- Implement one detector or feature path with a fixture.
- Wire one generated artifact into the product path.

Bad slice examples:

- "Build the app."
- "Implement all features."
- "Polish everything."

## Startup Checklist

Before editing, Executor runs:

```bash
git status --short --branch
find . -maxdepth 3 -type f -print | sort
```

Then read:

1. `GOAL.md` if present.
2. The active `docs/briefs/NNN-*.md`.
3. Relevant product/spec sections.
4. Current git status.

## TDD Posture

Deterministic code should be test-first when practical.

Non-deterministic or presentation-heavy work should still have proof:

- Snapshot fixtures.
- Smoke checks.
- Browser or screenshot verification.
- Golden output.
- Manual visual evidence recorded in session logs.

## Codex Slice Lifecycle

1. Restate the slice in the session log.
2. Identify production files, tests, fixtures, and docs.
3. Write failing test or fixture first. If no deterministic test fits, explain the proof path before implementation.
4. Pause before green when the brief marks `requires_pre_green_review: true`.
5. Implement minimum code. No opportunistic refactors.
6. Run focused validation.
7. Run broad validation.
8. Prove reachability from a real product path.
9. Record evidence in `docs/session-logs/NNN-executor-*.md`.
10. Commit scoped files with explicit `git add <path>`.

## Pre-Green Review Use

Use a required pre-green pause for security-sensitive handling, public data contract changes, irreversible file operations, paid external calls, or any brief marked `requires_pre_green_review`.

## Reachability Rule

Tests passing is not enough. The Executor must show how the new behavior is reachable from a real product path.

If a feature exists but is not wired into the product flow, it is not done.

## Commit Rules

- Use Conventional Commits.
- Commit one slice at a time.
- Use explicit `git add <path>` only.
- Do not use `git add -A`.
- Do not push unless the user explicitly asks.
- Do not include unrelated files in the slice commit.
- If the worktree has unrelated changes, leave them alone and mention them in the session log.

## Done Means

A slice is done only when:

- The requested behavior exists.
- Focused validation ran.
- Broader validation ran or the reason it could not run is recorded.
- Reachability is proven or a wiring task is raised.
- Evidence is in a session log.
- Reviewer can audit it from repo state without relying on chat.
