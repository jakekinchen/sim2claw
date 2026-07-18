# Archive Index — Where Predecessor Knowledge Lives

This repo is a clean-room restart. Byte copies of predecessor documents are
not kept here; when you need the old material, read it at one of two archive
locations and write anything you carry forward from scratch:

- **GitHub archive:** `jakekinchen/sim2claw-imported-archive` at commit
  `798491e` (`798491ecb1a88b64b96875634ad63397a55ab846`) — the frozen first
  sim2claw fork, 126 documents. Paths below are relative to that repo root.
- **Local read-only checkout:** `/Users/kelly/Developer/sim-link` (branch
  `codex/pi05-autolearn-loop`) — the original sim-link/SceneSmith repo with
  the far deeper history (roughly 335 session logs, 237 briefs, 330 reviewer
  messages, plus manager logs and evidence trees). Treat it as read-only.

Nothing in either archive carries forward as permission: any grant, permit,
one-use marker, or reviewer verdict you find there describes what happened
then, and authorizes nothing in this repository.

## Owner directions

Dated instructions the owner issued to the autonomous loop: the T20.41
capability-route decision that ended the optimizer-correction era and opened
the R0–R3 standard-recipe ladder, the overnight and final-hour task orderings
for 2026-07-16/17, the addendum resolving the interrupted T20.43c ACT run,
and the day-one closeout that sequenced work after the first Gate C pass.
These documents order tasks; they explicitly do not grant hardware, network,
or compute authority. Archive: `docs/autonomous-workflow/owner-route-decision-2026-07-16-t20-41.md`,
`owner-direction-2026-07-16-overnight-foundation.md`,
`owner-direction-2026-07-16-final-hour.md`,
`owner-addendum-2026-07-16-t20-43c-act-resolution.md`,
`owner-direction-2026-07-17-final-overnight.md`,
`owner-direction-2026-07-17-day-one-closeout.md`, plus the hash-guarded
snapshot `configurations/robot_lab/t20_41_owner_route_decision_e9d0507.snapshot.md`.
More owner directions, morning summaries, and goal-loop ledgers exist only in
sim-link under `docs/autonomous-workflow/`.

## Briefs

Scoped work orders for single slices, each with objective, invariants, and
verification gates. The archive holds the fork-native series 001–008 (the F0c
fork foundation and recovery chain, the cold-start state-RL vertical slice,
the Mac/NVIDIA hackathon bring-up) and the late sim-link series 226–233 (the
portable closeout refresh, the T20.43c zero-update ACT continuation, the
F0/F0a/F0b release-gap diagnostics, and the F3 capsule fold that birthed the
fork). Archive: `docs/briefs/`. The full 237-brief history is in sim-link at
`docs/briefs/`.

## Reviewer messages

Accept/reject decisions from the independent reviewer role, each restating
the evidence chain and the boundaries a result does not cross. The archive
carries fork decisions 001–021 (verifying the F0c chain through the Gate C
acceptance in `018-verify-f0c-attempt-3-gate-c-pass.md`, W3/W5 proofs, and
the state-RL slice) and late sim-link decisions 261, 289, 302, 313, 314, 318
(the R2 ACT terminal negative), 320, 321, and 325. Archive:
`docs/reviewer-messages/`. The full 330-message set is in sim-link at
`docs/reviewer-messages/`.

## Session logs

Terse per-session records of what actually executed, with exact receipt
identities. Fork logs 001–022 cover the fork's birth through the Gate C pass
(`020-f0c-attempt-3-gate-c-pass.md`), including the two preserved F0c
infrastructure failures (009, 014, 017) and the W5 localhost transport pass
(010). Sim-link logs 317–330 cover the final nights: the RGB camera census
failure (317), the T20.43c interruption (318), the T20.43c-R2 terminal
negative (323), and the F0/F0a/F0b release localization (325, 326, 330).
Archive: `docs/session-logs/`. The ~335-log history is in sim-link at
`docs/session-logs/`.

## Reconstruction kit documents

The distilled transfer package written so a successor repo could rebuild the
capability without the old codebase. Two generations exist: the earlier
`reconstruction-kit/` snapshot (adds `GATEWAY_SPEC.md`,
`NVIDIA_DAY1_CHECKLIST.md`, `DAY1_GATEWAY_INTEGRATION.md`,
`PINNED_LEROBOT_ASYNC_REHEARSAL.md`) and the updated `docs/reconstruction/`
fold, which is the more current truth. Key files there: `CURRENT_STATE.md`
and `CURRENT_STATE.json` (the exact proof/claim boundary, including the F1
result), `RESULTS_AND_LESSONS.md` (what worked, clean negatives, and the
infrastructure-failure taxonomy), `ARCHITECTURE.md`, `FORWARD_PLAN.md`,
`QUICKSTART.md`, `F0C_FIRST_TRAINING_TASK.md` (the frozen continuation spec),
`HARDWARE_READINESS_RGB_CAMERAS.md` (the K3 camera failure boundary), and the
machine manifests `SOURCE_MANIFEST.json`, `source-selection.json`, and
`R0_LOCAL_EPOCH_TEMPLATE.json`.

## Autonomous-workflow doctrine

How the solo autonomous loop was governed and what the fork kept: the
hackathon fork annex (`docs/autonomous-workflow/hackathon-fork-annex-2026-07-16.md`)
is the densest single document — the five assets worth copying, the three
permanent rules, the distributed-training plan, the compute doctrine, and the
scar-tissue warnings. Beside it sit the four-lane team runbook
(`docs/autonomous-workflow/handoff-runbook-2026-07-17.md`), the authoritative
machine state (`docs/autonomous-workflow/project_state.json`), the operating
rules (`AGENTS.md`), the mission (`GOAL.md`, `README.md`, `PROVENANCE.md`),
and the top-level guides `docs/README.md`, `docs/architecture.md`,
`docs/sim-link-mvp-execution-plan.md` (capability ladder A–F and the full
T20.x task table), `docs/SIM2CLAW_PLAN_PROCESS_AND_KEY_PARTS.md`,
`docs/START_TRAINING.md`, `docs/HACKATHON_INFRASTRUCTURE.md`,
`docs/PIPELINE_PHONE_TO_POLICY.md`, and `docs/SPINE_EXPORT.md`. The
`automation/macos/` pair documents the bounded launchd reply-watcher used for
a one-time collaborator handoff. Deeper process doctrine (role contracts,
planning system, manager interventions) exists only in sim-link under
`docs/manager-log/`.

## Third-party notes

Exact dependency pins, licenses, and redistribution boundaries:
`docs/reconstruction/THIRD_PARTY.md` (and the older
`reconstruction-kit/THIRD_PARTY.md`) records the pinned LeRobot commit plus
patch hash, SO-ARM100, leLab, MuJoCo Menagerie, and openpi pins with required
byte checks, and lists what was deliberately never redistributed (weights,
caches, generated outputs, private scans). The vendored robot description
reference lives at `third_party/mujoco_menagerie/robotstudio_so101/README.md`
and `LICENSE`. Live dependency checkouts were never part of the archive;
acquire and re-verify them from their owners.

## Identities worth knowing

- **Gate C pass (F0c attempt 3):** accepted checkpoint tree
  `8ecf7bb959c68ba34524aa503b2a0c548540e51a3c1261de143b7d5b57836830`; final
  terminal receipt
  `9e957708219a31d683643714c45bead0398447a984555da1961cb12e5e66352a`.
- **R2 ACT lineage:** R0 dataset → T20.43 (infra failure, receipt
  `b64ec6d0...`) → T20.43b (infra failure at zero updates, receipt
  `89b6dbff...`) → T20.43c (exact-continuation proof, interrupted at update
  728, terminal `d848a1a8...`) → T20.43c-R2 (full 10,000-update campaign,
  final receipt `be11a258...`, release-only failure). The R2 update-10000
  checkpoint tree `c77ee36250f921dbdfc7b19802ab8705c9795b298fa14d4a2b1825acf68451ab`
  is the parent the F0c continuation trained from, under frozen spec
  `6a178138f79236f27adc04b337e0142a5dfa851f1f67d32d55dcc8b41e4da5dd`.
- **Frozen consequence gate:** `463477dc...`, the consequence-calibrated
  Gate B amendment frozen before scoring (T20.36l); no threshold change
  without a fresh owner decision.
- **R0 dataset boundary:** 129 training episodes, 31,366 frames, 59,904
  windows; result `d238379bce62d884833da0a449535e3dc24f988b8da573513ae684bbb19a5969`,
  mixture `37b30d34...`, statistics `02ba0e70...`; 11 held-out cases frozen
  with zero training or statistics rows.
- **Other anchors:** SmolVLA terminal negative `9d916206...`; F1 pi0.5 run
  receipt `ca9a23b1...` with teardown `7343ad9f...`; W1 bootstrap
  `392fcc8b...`; W2 reconstruction `86739578...`; fork import tag
  `sim2claw-genesis`; sim-link freeze tag `freeze-2026-07-17-hackathon-fork`.
