# Brief 012: Retrospective publication gate

Decision: `COMPLETE_WITH_TERMINAL_NEGATIVE_CALIBRATION_RESULT`

## Outcome

The retired cloud workspace does not erase the retained local evidence. The
current checkout contains 18 immutable physical teleoperation directories,
7,741 strict samples, and 54 catalog-bound sample/receipt/video assets. All 54
hashes match. The 36 extracted endpoint frames and all 26 owner-accepted visual
markers also remain hash-bound.

This supports a publication-grade retrospective source package, not a
publication-grade sim-to-real result. Each physical episode now has a replay
anchor that binds its raw assets, strict sample sequence, timing, and exact
recorded command/actual trace digest. Zero anchors are labeled simulator-replay
eligible.

## Posterior that is actually supported

The gate fits a Normal-Inverse-Gamma model to the per-episode mean physical
tracking residual for each of six source joints. Whole episodes, not 7,741
temporally correlated rows, are the independent units. It also fits the mean
sample interval across episodes and publishes pooled residual quantiles as
descriptive trace statistics.

This is a real-data posterior over observed command tracking and timing. It is
not a posterior over command latency, actuator gain, damping, friction, mass,
contact, endpoint pose, or other simulator parameters. It is not admitted to
domain randomization until a physical-to-simulator transform is independently
approved.

The same hash-bound source rows now also produce deterministic per-episode and
corpus-level requested/commanded/measured trace comparisons. These include
measured velocity, cached raw motor-current proxy, control/sample timing, video
timeline alignment, endpoint frame bindings, and receipt outcome context. Raw
current was nominally read at 5 Hz and cached into intervening rows; fresh-read
row identity was not recorded. It is not calibrated effort, video alignment is
not capture latency, and the comparison is physical command tracking—not
real-versus-simulator replay.

The 26 owner-reviewed markers additionally yield a qualitative image-offset
fit. The millimeter projection is retained only as sensitivity analysis under
the explicitly unreviewed homography. It is never fed to the metric evaluator.

## Terminal-negative identification result

The existing strict evaluator still reports:

- 18/18 source traces have valid sample semantics and provenance;
- 0/18 pass exact simulator joint-range validation;
- 0/18 are eligible for exact simulator replay;
- the physical joint transform is provisional and unapproved;
- end-effector pose, pawn pose, contact state, and contact force are unavailable;
- geometry, timing/control, contact/object, and overall calibration are not
  ready.

This is the correct stopping result. Clipping the trajectories, accepting the
homography retrospectively, or fitting physics to operator success labels would
manufacture identifiability.

## Frozen low-cost systems pilot

The active publication gate now freezes three systems at one attempt on three
nonredundant cases: native Codex CLI with GPT-5.6 Sol at high reasoning through
the operator's ChatGPT subscription, native Claude Code with Claude Fable 5 at
high effort through the authenticated Claude subscription, and open-weight
`openai/gpt-oss-120b` at high
reasoning through Groq. The selected cases isolate single-axis lateral,
coupled-XY, and vertical correction. The second single-axis lateral case is
excluded as redundant under this budget.

This is a nine-attempt one-shot pilot, not the earlier 240-attempt API
factorial and not a broad provider leaderboard. Inspect's model proxy does not
reuse interactive ChatGPT or Claude subscription sessions, so the subscription
systems use their native CLIs. They are therefore reported as complete system
configurations rather than bare-model comparisons. Provider effort labels are
also not treated as equivalent.

Every system receives the same static public packet and must commit one typed
hypothesis and bounded translation before seeing any score. The host refuses to
score until all nine outputs exist and validate. It then applies the same
deterministic evaluator and produces matched unchanged, seeded-random,
public-evidence heuristic, and oracle controls. There is no model judge.
Codex's shell and web search are disabled; Claude runs in safe mode with an
empty tool set; the open-weight request declares no tools.

The six subscription attempts have zero incremental dollar price but consume
subscription quota. The three open-weight API attempts have no retries, a
conservative computed maximum below the frozen USD 1 hard cap, and must stop
before a request that could exceed it. Execution remains disabled: access,
subscription use, provider calls, and spend have not been authorized, and no
model call was made while producing this brief. The larger Inspect factorial
remains an archival, unexecuted design rather than the active gate.

## Publication claim

Safe claim:

> We release a hash-bound retrospective physical source corpus with strict
> replay anchors, an episode-balanced diagnostic posterior over observed robot
> tracking and timing, qualitative endpoint evidence, and a fail-closed audit
> that localizes why simulator calibration and physical-transfer claims remain
> unidentifiable.

Unsafe claims include “calibrated simulator,” “real-to-sim posterior,”
“validated domain randomization,” “policy improvement,” and “sim-to-real
transfer.” The synthetic corrective benchmark can later measure agent reasoning
quality, but it cannot change those physical evidence boundaries.
