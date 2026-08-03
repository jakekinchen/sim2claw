# Physical-to-simulator temporal pixel-similarity goal loop

Start: `2026-08-03T01:01:16Z` (`2026-08-02T20:01:16-05:00`)

Deadline: `2026-08-03T09:01:16Z` (`2026-08-03T04:01:16-05:00`)

## Mission

Iteratively improve an action-identical, camera-registered simulator rendering
of the retained successful D1-to-D2 physical episode until an evaluator-owned
temporal pixel metric reaches the `0.80–0.90` target band, or until the absolute
eight-hour deadline. This is episode-specific visual replay work. It does not
by itself establish calibrated physics, physical transfer, or task success.

## Source of truth

Read in this order:

1. The owner's latest instruction and the absolute deadline above.
2. `AGENTS.md`, especially proof-class separation and exact-action invariance.
3. `configs/sail/observable_registration_current_graph_v1.json` and its single
   active card.
4. This goal loop and
   `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
5. Frozen evaluator contracts and independently generated receipts.
6. Historical receipts, videos, and prior cards as evidence, never authority.

## Intended outcome

Produce synchronized 640x480 physical and simulator videos over the same 531
source samples, with policy actions and timestamps unchanged, and pass a frozen
evaluator with:

- mean full-frame linear pixel similarity of at least `0.80`;
- 10th-percentile frame similarity of at least `0.75`;
- mean motion-union pixel similarity of at least `0.75`;
- every declared task phase averaging at least `0.78`;
- tolerant edge F1 of at least `0.40`;
- no per-frame geometric warp, per-frame color correction, physical-frame
  compositing, missing-frame substitution, or physical pixels used as simulator
  texture.

Scores above `0.90` remain valid and are reported as exceeding the requested
band. The primary metric is `1 - mean(abs(physical-simulator))/255`, computed
over source-available frames after the single frozen board display homography.
Temporal-difference similarity and SSIM are diagnostics, not substitutes for
the primary gates.

## Decision status

Confirmed:

- Hardware is unavailable; only retained footage and simulator execution are
  in scope.
- The D1-to-D2 source, 531-sample action timeline, and OR26 synchronized video
  lineage are the primary episode.
- The user authorizes iterative local simulator and evaluator work for eight
  hours, but not commit, push, paid compute, or physical authority.
- GPT Pro research is an advisory escalation if local evidence reaches a
  genuine mechanism-selection blocker.

Assumptions and defaults:

- `0.80` is the pass threshold for the requested `80–90%` band.
- Rendering, camera, material, illumination, distortion, and scene-background
  parameters may be tested only under versioned cards with bounded families.
- Policy actions remain byte-identical. Outcome-informed candidates remain
  permanently episode-specific and cannot self-promote.

## Execution rhythm

1. Check the wall clock, goal projection, graph, queue, and dirty worktree.
2. Keep exactly one active card with a frozen contract and smallest useful
   mechanism family.
3. Run the baseline or candidate once, emit per-frame metrics and hashes, and
   preserve generated media under ignored `outputs/`.
4. Review the residual by phase and channel; choose `CONTINUE`, `NUDGE`,
   `REDIRECT`, `STOP`, or `ESCALATE` with evidence.
5. Never improve the score by changing actions, timestamps, physical frames,
   or evaluator behavior after seeing a candidate.
6. Continue until every acceptance gate passes or the absolute deadline is
   reached. At the deadline, close the active card and report the best verified
   score and remaining residual without inflating the claim.

Use GPT Pro research only after local code, receipts, and bounded candidate
families fail to nominate a defensible next mechanism. Send a non-sensitive
summary, treat its answer as third-party advice, and independently verify any
adopted method.

## Evidence standard

Every closed slice records changed files, source hashes, exact parameters,
per-frame and per-phase metrics, generated video hashes, focused tests, proof
limits, the best-so-far candidate, elapsed time, and the next card or stop
reason. A recap or visually plausible video never substitutes for evaluator
output.

## Progress ledger

```text
Current state: OR55 temporal pixel evaluator baseline freeze active
Completed: OR26 synchronized physical/simulator video; OR51-OR54 robustness and footage constraints
Evidence: OR26 has 516 available physical frames on a 531-sample action-identical timeline; exploratory unpromoted full-frame pixel similarity is approximately 0.704
Best verified primary score: none under the new frozen evaluator
Remaining: freeze evaluator, establish baseline, isolate appearance/camera/geometry/event residuals, validate best candidate
Blockers: no hardware; no metric depth/force; commit and push unauthorized
Next step: execute OR55 once against the immutable OR26 physical and simulator videos
```
