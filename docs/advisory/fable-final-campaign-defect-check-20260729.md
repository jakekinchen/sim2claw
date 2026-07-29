# Fable Final Campaign Defect Check

Status: `COMPLETE_NO_MATERIAL_IN_SCOPE_PROOF_DEFECT`

Date: `2026-07-29`

Reviewer: Claude Fable 5, effort `High`, existing project thread

Reviewed branch and commit:
`codex/bidirectional-transfer-goal-loop-20260728` at `6da1289`

Review mode: read-only repository inspection. Fable changed no files and
opened no camera, gateway, serial, hardware, or paid-compute authority.

## Packet reviewed

The final packet reported:

- REAL->SIM successes/attempts: `0/0`;
- SIM->REAL successes/attempts: `0/0`;
- physical pawn-task attempts: `0/10`;
- wrist held-out receipt SHA-256
  `16b7896c45904c7563d00f8b8386cddf3892de9deec70c77c0a2c9ff087294c6`;
- CC03E telemetry receipt SHA-256
  `876cc47862b21f719646b7797b3e67c5dc8ec7e654735e984f4ee09265da666b`;
- CC03K static receipt SHA-256
  `f8bb0e86f61fbdb380a337d2f565d163534e37ce16acb9157e45f931750bb094`;
- the exact claim that no task transfer, general sim-to-real bridge, broken
  component, or physical interpretation of simulator-only task outcomes was
  being asserted.

## Independent defect challenge

Fable independently reproduced the locked-elbow pose-space search at the fresh
post-CC03E anchor. It confirmed:

- the anchor legitimately has no baseline self-contact;
- there is no strict collision-free pose below `80 mm` site height in the pawn
  annulus;
- the two historical folded-arm overlap pairs do not make CC03K unwinnable by
  construction;
- tolerating only those two named historical pairs does not rescue any CC03K
  action, because every compiled action also introduces at least one genuinely
  new pair;
- the historically evidenced harmless overlap depth is at most about
  `3.24 mm`, while the reopened pose sliver requires about `3.33--10.94 mm`;
  the best sliver therefore has no safety margin before a full approach,
  contact, and `40 mm` consequence route is considered.

The suspected collision-gate implementation defect is rejected. A successor
that widens the artifact allowance or searches for a route through the
zero-margin sliver is classified as outcome-informed path hunting, not a
material in-scope correction.

## Telemetry review

Fable independently reconciled earlier recapture samples with CC03E:

- earlier elbow response was about `0.79--0.88 deg` against a `2.91 deg`
  request;
- CC03E response was `1.58--1.76 deg` against a `5 deg` request in both
  directions;
- current/load rose, status and temperature remained normal, the matched wrist
  tracked, and a torque cycle did not restore elbow response.

That proportional bidirectional shortfall supports the repository wording
`mechanical-resistance signature`. It does not prove a mechanically broken
part. A RAM P-gain increase remains rejected because it would drive more
torque into a resistance signature without an accepted safety basis.

## Recommendation disposition

| Item | Disposition | Evidence |
|---|---|---|
| CC03K strict terminal boundary | Already satisfied | Receipt `f8bb0e86...`, closeout `ca107505...`, and independent pose-space reproduction. |
| Artifact-pair allowance successor | Receipt-backed reject | No CC03K cell fails on only the two historical pairs; evidenced depth is exhausted at the best pose sliver. |
| CC03E mechanical-resistance classification | Already satisfied | Receipt `876cc478...`, closeout `f9c5d8fa...`, and earlier-sample corroboration. |
| RAM P-gain experiment | Receipt-backed reject | Symmetric proportional response with rising load; additional torque is not a safe diagnostic correction. |
| Elbow inspection or repair | Receipt-backed defer | Human/external hardware boundary. |
| Further locked-elbow task, tool, other-arm, or unbounded simulator screens | Receipt-backed reject | Physical envelope and collision geometry have been independently reproduced. |
| Gravity-direction wording and the vacuous empty-selection field | Packaging note | Clarify in the final evidence package; no implementation card is reopened. |

## Final verdict

Fable reported no material unresolved in-scope proof defect. The current
hardware state is honestly terminal for a safe pawn consequence. CC04--CC12
cannot open because there is no safe family from which to approve mapping,
freeze a counted evaluator, execute transfer, or collect the paired physical
sample required for policy ranking.

The highest-value application package is the existing wrist held-out
correspondence, the CC03E hardware telemetry truth, and the CC03K refusal to
weaken a safety gate. This is evidence of an autonomous engineering system
that finds and records both valid correspondences and hard boundaries. It is
not evidence of bidirectional task transfer.

## Exact claim boundary

Supported:

> An autonomous, receipt-gated engineering loop corrected a categorical board
> orientation error, validated one bounded wrist-channel real/sim trajectory
> correspondence on a frozen held-out, localized an elbow
> mechanical-resistance signature with exact telemetry, and independently
> proved that the remaining collision-safe pawn-consequence set is empty for
> the current hardware state.

Not supported:

- any REAL->SIM or SIM->REAL task transfer;
- a general sim-to-real bridging result;
- a mechanically diagnosed broken component;
- physical capability inferred from simulator-only task outcomes;
- predictive policy ranking from a physical sample of zero.
