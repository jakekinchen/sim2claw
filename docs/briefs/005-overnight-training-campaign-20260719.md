# Slice Brief 005 - Overnight Training Campaign Assessment

**Date:** 2026-07-19 America/Chicago
**Status:** historical pre-run assessment, superseded by the bounded 1,000-step
campaign and its terminal-negative closeout; this brief never granted compute
authority

## Supersession note

The owner subsequently authorized a narrower paid lane than the 5,000-step,
eight-hour proposal below: one A100 worker, 1,000 steps, a three-hour ceiling,
and a $4.968 spend cap. That run completed and its sole frozen C8→A6
development rollout was terminal negative: 0 mm pawn rise and 125.724 mm final
XY error. Held-outs remained sealed, the compact evidence archive was retained,
checkpoint weights were intentionally not retained, and the worker was deleted.

The actual closeout is
`docs/run-logs/2026-07-19-groot-n17-multisource-v2.md`. The text below is
preserved as the proposal assessed before launch; its logged-out inventory,
5,000-step recipe, proposed $20 cap, and future-tense instructions are not
current state or authority.

## Decision

The only policy training lane that is close enough to run overnight is one
bounded GR00T N1.7 multisource challenger. It should start from the pinned base
model, not from either terminal-negative pawn or rook/king checkpoint, and use
only the already evaluator-admitted simulation datasets.

Do not start goal-conditioned ACT training yet. M7 still lacks the segmented,
retargeted, replayed, strict-success 500--2,000 episode dataset required by the
governing ACT roadmap. Do not put any current physical recording, raw learned
failure, held-out row, or iPhone/3DGS frame into behavior cloning.

The proposed GR00T run is a skill-prior and simulator-learning experiment. It
does not directly train the owner-selected rank-1/rank-2 pawn product task and
cannot claim pawn generalization or physical authority.

## Live evidence assessed

The current main checkout is clean at `13a6dfd`. The candidate dataset work is
still uncommitted in the separately owned worktree
`/Users/kelly/Developer/sim2claw-groot-multisource-0719` on
`codex/groot-multisource-100mm-v2`; do not race or overwrite that writer.

The draft builder was exercised end to end against the three hash-bound source
datasets. Its focused contract tests passed `3/3`. A scratch export and full
preflight produced:

- 73 unique evaluator-admitted source episodes;
- 96 derived training episodes;
- 41,088 aligned video/action/state frames at 20 Hz;
- 39,648 valid H16 starts and 3,806,208 scalar action targets;
- zero held-out, failed-action, or physical-training rows;
- 96 aligned parquet files and 96 aligned videos;
- dataset receipt SHA-256
  `83f99abf7f49727f4a62d3b9d377b9a17dcc6572e3719a17abfdef3c2b981025`;
  and
- payload-manifest SHA-256
  `14222b7ba947c38ab4962cffb61bb548c9bf7655f288be25d7d71e679e4c0373`.

These hashes describe the assessed uncommitted draft and must be regenerated
after the dataset worktree is finalized. They are not frozen campaign
identities yet.

The Brev CLI session is currently logged out, so a current paid-resource
inventory could not be proven. The previous pawn closeout reports deletion,
but that historical receipt is not a substitute for a fresh authenticated
`brev ls --json` before launch.

## Data disposition

| Cohort | Available evidence | Overnight disposition |
| --- | ---: | --- |
| Historical nominal rook/king simulation | 24 episodes, 8,712 frames, all expert episodes passed | Include once, as a historical manipulation prior |
| Historical recovery rook/king simulation | 48 episodes, 18,888 frames, all expert episodes passed | Include once, as contact/recovery and distractor prior |
| Current 100 mm pawn simulation anchor | 1 episode, 562 frames, strict evaluator pass | Include at 24x sampling weight; this remains one unique source |
| New current physical catalog | 18 episodes, 7,741 samples; 7 metadata-consistent and 11 conflicting | Exclude from imitation; use all traces only for joint-response/latency diagnostics after raw-hash staging |
| Older 72 mm physical cohort | 5 episodes, 2,186 samples | Exclude; historical geometry and no strict outcome admission |
| Current 100 mm failed simulation probes | 4 complete counterexamples plus incomplete scratch probes | Exclude actions; retain for failure classification and future validated corrective suffixes |
| Nominal/recovery/product held-outs | 4 nominal, 24 recovery, 48 rank-1/rank-2 product realizations | Keep sealed and at zero training rows |
| iPhone-video 3DGS release | visual reconstruction evidence without action synchronization | Viewer/background diagnostic only; no behavior-cloning or geometry authority |

The derived frame mixture is approximately 21.2% historical nominal, 46.0%
historical recovery, and 32.8% repeated current-pawn anchor. The pawn replica
count is a sampling weight, not 24 independent demonstrations.

## Required work before a GPU exists

1. Let the multisource worktree owner finish its code, tests, contract, intake,
   builder, and CLI changes. Review and commit that slice without folding in
   unrelated worktree state.
2. Re-export the immutable dataset from the three source receipts and rerun the
   local full preflight. Record the final contract, receipt, payload-manifest,
   source-cohort, and builder hashes.
3. Add a pinned NVIDIA-loader preflight for all 96 episodes. It must prove the
   six expected columns, 256x256 decoded RGB, absolute six-joint actions, H16
   extraction, exact start denominator, no padding, and no dataset mutation.
4. Freeze the training, checkpoint selector, training-only development, sealed
   held-out, spend, archive, and teardown contracts before optimizer step zero.
5. Reauthenticate Brev, require an empty or explicitly owned inventory, refresh
   the A100-80GB type and hourly quote, and authorize one worker plus a current
   hard dollar cap. Prior campaign budget authority does not carry forward.
6. Verify the exact GR00T source commit, base revision, Cosmos processor
   snapshot, offline processor construction, checkpoint inventory, CUDA/EGL or
   OSMesa diagnostic runtime, and absence of credentials from Git and receipts.

Any failure above is a no-launch result, not a reason to weaken the contract.

## Proposed bounded GR00T run

Use one A100-80GB worker, one run, and no automatic retry instance. Start from
`nvidia/GR00T-N1.7-3B` revision
`2fc962b973bccdd5d8ce4f67cc63b264d6886495`; retain the old pawn
`checkpoint-1000` and rook/king checkpoints only as declared negative
baselines.

Recommended first recipe:

- 5,000 optimizer steps, which is about two global-batch passes over 39,648
  effective H16 starts at global batch 16;
- checkpoints at 500, 1,000, 2,000, 3,000, 4,000, and 5,000;
- learning rate `5e-5`, state dropout `0.0`, global batch `16`;
- absolute six-joint targets, action horizon `16`, pinned data seed `42`;
- the frozen visual encoder and existing color-jitter contract; prior evidence
  does not justify visual unfreezing; and
- an eight-hour wall-clock ceiling, whichever hard dollar cap is reached first,
  and immediate artifact preservation plus worker deletion when the campaign
  reaches a terminal result.

At the previous quoted `$1.656/hour`, eight raw compute hours would be
`$13.248`, but that quote is stale until refreshed. A proposed `$20` campaign
ceiling is reasonable only after the user explicitly authorizes it.

## Checkpoint selection and evaluation

Training loss and open-loop MSE may diagnose the run but cannot select a
promotable checkpoint. Evaluate every saved checkpoint on a frozen
training-only development matrix with model-derived actions, zero assistance,
the same K=5 median/noise-0.5/H16/H8 temporal executor, and independent CPU/fp32
consequence evaluation.

The development matrix should contain at least:

- the exact current 100 mm C8-to-A6 pawn source task at two fixed inference
  seeds;
- one historical nominal training case at two fixed inference seeds; and
- one historical recovery/distractor training case at two fixed inference
  seeds.

Rank checkpoints lexicographically by full task-consequence passes, worst
cohort, board safety, placement, lift, and only then open-loop error. Require at
least one full pass in every development cohort and repeatability across the two
fixed inference seeds before opening any held-out set.

If that gate passes, run the complete four nominal and 24 recovery held-out
episodes under their frozen seeds. Do not open the 48-case rank-1/rank-2 product
benchmark: no rank-1/rank-2 training dataset or implemented benchmark evaluator
has yet earned that comparison.

If no checkpoint passes the training-only development gate, close the campaign
as a terminal negative. Do not extend optimizer steps or unfreeze the visual
encoder during the same run.

## Parallel non-policy data work

The 18 new physical traces can support a separate CPU/local calibration job
after their owner-local raw payloads are staged and hash-verified. Fit and
report per-joint command-response lag, tracking error, rate-limit frequency,
and velocity envelopes. Move-label conflicts do not invalidate those dynamics
measurements, but they do invalidate task-conditioned imitation.

For later physical imitation admission, create an append-only corrected ledger;
establish the actual source/destination and skill family; add authoritative
pose and segment annotations; replay the exact commanded trace; and obtain a
separately owned physical consequence verdict. An LLM/VLM review may propose
labels or failure classes but cannot admit a row.

## ACT work, not ACT training

The highest-value ACT overnight work is finishing M7, not running an optimizer:

1. generalize the fixed source expert/reset/evaluator beyond C8-to-A6;
2. implement contact-segment extraction and object/target-relative transforms;
3. retarget across frozen source/target cells, plan connecting free-space
   motion, solve IK, and replay exact float32 actions;
4. retain strict evaluator successes with complete lineage and a rejection
   histogram; and
5. reach 10--20 diverse source episodes and 500--2,000 accepted pawn-family
   episodes with G2/H1 and all held-out pose cells at zero training rows.

Only then freeze and train ACT-1 variable-pose grasp/lift, followed by ACT-2
placement. The current zero-row M7 state is a hard no-go for ACT fine-tuning.

## Morning decision tree

- **No launch:** any local/remote hash, loader, auth, inventory, budget, or
  runtime preflight fails. Preserve the failure receipt and do not create a
  worker.
- **Development terminal negative:** preserve every checkpoint and consequence
  matrix, delete the worker, and move next effort to current-geometry near-rank
  data plus evaluator-passing corrective suffixes.
- **Development pass, held-out negative:** keep the checkpoint as partial
  evidence, preserve per-failure consequences, delete the worker, and generate
  new training data from failure classes without admitting held-out traces.
- **Held-out pass:** preserve the candidate and receipts, delete the worker,
  then design a new current-geometry rank-1/rank-2 training and evaluation lane.
  No physical trial or product claim follows automatically.

## Required closeout artifacts

Preserve the final dataset and source identities, remote loader receipt,
training command/config, per-checkpoint manifests, optimizer/runtime receipts,
training-only selector matrix, held-out receipts when opened, videos and action
traces, process/GPU teardown proof, spend ledger, transferred archive manifest,
and an authenticated post-deletion `brev ls --json` inventory.
