# Physical Teleoperation Episode Intake

Date: 2026-07-18 America/Chicago

Machine-readable ledger:
`configs/data/physical_teleop_episode_intake_20260718.json`

Raw owner-local storage: `datasets/act_source_recordings/`. This directory is
ignored by Git; the tracked ledger contains relative pointers and hashes, not
the joint rows or C922 videos.

## What was found

Five physical-follower recordings were saved successfully. Together they hold
2,186 synchronized samples over 159.97 seconds of teleoperation and 203.2
seconds of finalized overhead video. All five sample, video, and video-metadata
hashes match their source receipts. Every row retains follower commands and
actual state, and all five traces report zero stalls, zero bus-read retries,
and zero stale-current samples.

The review generated a joint-response-only MuJoCo replay receipt and trace next
to each ignored source recording. Aggregate body-joint RMSE ranges from 2.83 to
3.45 degrees; maximum single body-joint error ranges from 6.84 to 10.22
degrees. These numbers compare command response only. They do not validate
piece motion, contact dynamics, task success, or simulator accuracy for chess.

## Episode disposition

| Recording | Receipt move | Operator text | Review | Route |
| --- | --- | --- | --- | --- |
| `20260718T224507Z-cb15a243` | D1→D2 | Push forward; successful | Video shows a pawn relocation, but this is explicitly push-only and the label is `vv` | Hold for a separately versioned pawn-push task; exclude from current pick/lift/place ACT and GR00T v1 |
| `20260718T225126Z-a19918d7` | D1→D2 | Label says B1→B2 and passed | Video shows a pawn relocation; coordinate metadata conflicts | Quarantine until the move and skill semantics are reconciled |
| `20260718T225419Z-bdd95fdf` | E2→E1 | Label says E2→E1 pass | Only coordinate-consistent nominal candidate; video shows a pawn relocation | Candidate ACT physical anchor after formal outcome, pose annotation, segmentation, and evaluator gates |
| `20260718T225715Z-e68b4076` | E2→E1 | Label says D1→D2; note reports a laggy start and technical pass | Useful hesitation/recovery hypothesis, but coordinate metadata conflicts | Hold for ACT-6/recovery analysis after exact segment and intervention lineage are established |
| `20260718T230416Z-573f2320` | E2→E1 | Label says F2→F1; note says pass with flying colors | Video shows a pawn relocation; coordinate metadata conflicts | Quarantine, then consider as a nominal ACT anchor only after reconciliation |

All source receipts still say `outcome_label: unreviewed`. A success phrase in
a free-text label or note is not a physical consequence verdict. Contact-sheet
review established visible board-state changes, not exact square identities or
strict task success.

## Pipeline decision

The state/action structure aligns more directly with the goal-conditioned ACT
lane than with the current GR00T lane, but none of these episodes is a training
row yet. The traces do not contain authoritative piece/target poses, the
physical evaluator has not run, skill boundaries have not been segmented, and
three coordinate labels conflict with recorder metadata.

The frozen GR00T v1 dataset remains simulation-only. These overhead videos are
not automatically compatible with its RGB/language LeRobot v2.1 contract. A
future versioned physical-RGB or recovery-v2 dataset may cite this cohort after
metadata repair, synchronized modality export, zero-row held-outs, and the
separately owned consequence evaluator; GR00T v1 must not be mutated.

Recommended order:

1. Reconcile the three conflicting moves against operator memory and original
   videos; record corrections in a new ledger version, never by rewriting raw
   receipts.
2. Set formal outcomes and annotate contact-sensitive segments. Treat the
   laggy-start episode as a recovery hypothesis, not a nominal success.
3. Add authoritative piece/target pose annotations or a reviewed video-based
   annotation contract, then replay and apply the frozen admission evaluator.
4. Keep the E2→E1 consistent episode as the first nominal ACT anchor candidate;
   keep the D1→D2 push in a separate skill/task family.
5. Admit only derived, lineage-complete rows into a versioned ACT or future
   GR00T dataset. The current admitted count remains zero.

## Failed-attempt boundary

There are 23 archived physical failed attempts under
`runs/teleop_recordings/failed_attempts/`. Six happened around this saved
cohort: four pose-pair mismatches, one leader-moved-during-sync refusal, and one
missing Feetech status packet during setup. All six contain zero action samples,
so they are useful gateway diagnostics but are not correction-training rows.

No policy was trained, checkpoint selected, physical authority opened, or paid
Brev resource started during this intake.
