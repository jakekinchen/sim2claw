# NVIDIA baseline evidence — physical replay, 2026-07-19

**Status: drafted locally, not yet committed or pushed.** This file is not
part of any commit; it summarizes an already-published GitHub Release for
presentation purposes and adds no new claims beyond what that release states.

## Source of truth

- Private GitHub Release: [`physical-replay-evidence-20260719`](https://github.com/jakekinchen/sim2claw/releases/tag/physical-replay-evidence-20260719)
- Published: 2026-07-19T01:17:25Z by `jakekinchen`
- Built from branch `agent/studio-live-evidence` (commit `8c769df`, "Add guarded
  physical episode replay"), not yet merged to `main`.
- Machine-readable manifest committed in that branch at
  `docs/reference/PHYSICAL_REPLAY_RELEASE_20260719.json`
  (`schema_version: sim2claw.github_release_evidence_manifest.v1`), with a
  matching `.sha256` file. Every asset below is checksum-verifiable against
  that manifest.

## What this evidence is

A recorded physical-teleoperation source episode (brown pawn `e2` → `e1`,
recording id `20260718T230416Z-573f2320`) had its saved command trace replayed
through the guarded physical gateway, and the replay was captured from three
independent cameras simultaneously:

| Camera | Role | Notes |
|---|---|---|
| C922 | Overhead board | Full board view |
| Logitech | Side arm | Arm motion view |
| D405 | Wrist / gripper-upward | Ordinary visible video only — no metric depth, intrinsics, or hand-eye calibration established |

Replay run `20260719T010448Z-20260718T230416Z-573f2320-8e655391`: **243
samples completed**, 233 exact-command samples, 51 samples reported as
safety-clamped. Follower torque was off after shutdown. Camera-to-replay
alignment uses file creation time with an estimated uncertainty of 1.0 second.

All 12 release assets (3 videos, 6 receipts, README, manifest, SHA256SUMS) are
individually checksummed in the manifest.

## What this evidence explicitly does NOT establish

Carried over verbatim from the release's own proof boundary — this is the
part that matters most for an external audience:

- `learned_act_checkpoint_executed: false`
- `physical_chess_task_success_verified: false`
- `object_or_contact_dynamics_verified: false`
- `metric_depth_verified: false`
- `training_admission_granted: false`

Proof class: `physical_teleoperation_source_unqualified`. The operator's
recorded note ("Pass with flying colors") belongs to the original source
recording and is **not** an evaluator result — no separate evaluator scored
this episode's outcome.

## Why this is still a legitimate baseline exhibit

Despite the narrow proof boundary, this is genuinely differentiated evidence
for an NVIDIA-facing audience because it is:

- **Real physical hardware**, not simulation-only.
- **Multi-camera verified** — the manifest records `decoded_replay_frame_verified: true`
  for each replay video, i.e. someone checked that real frames decode from the
  replay window, not just that a file exists.
- **Checksummed and reproducible** — every asset ties to a SHA-256 in a
  committed manifest, so a reviewer can verify integrity independently of any
  claim in this document.
- **Honestly scoped** — the same release that provides the evidence also
  states, in machine-readable form, exactly what it does not prove. That
  scoping discipline is itself a point worth making to NVIDIA: results are
  receipted, not narrated.

The correct framing for a live presentation: *"This is our raw hardware
replay-fidelity evidence — a command trace generated from a human demonstration,
replayed on the physical arm, and camera-verified frame-by-frame. It is not a
task-success claim. Task-success evaluation is a separate, frozen gate our
pipeline requires before any result is promoted."* That sentence should
appear verbatim or near-verbatim wherever this evidence is shown.

## How this becomes the orchestration-benchmark baseline

Per the earlier Nemotron/NeMo orchestration-bench plan, this release now
serves as **Baseline A** in place of the not-yet-available ACT
`chess_rook_lift_v1` held-out receipt:

1. **Baseline A (this release):** replay-fidelity evidence for a
   manually-demonstrated episode — proves the recorded trace reproduces
   physically, not that the task succeeded.
2. **Nemotron orchestration bench:** vanilla-then-fine-tuned Nemotron
   orchestrator run against task instances from the same episode family,
   scored by whatever evaluator gate applies once one exists for this task —
   currently none does, which is the next real gap to close, not this one.
3. **Delta report:** any `sim2claw.orchestrator_before_after.v1` comparison
   built on top of this baseline must inherit its proof-class boundary
   (`_unqualified`) until a dedicated evaluator for this task exists. Do not
   let a later comparison silently upgrade this baseline's evidentiary
   weight.

## Open item

No task-success evaluator exists yet for this specific episode/task family
(pawn `e2`→`e1`), unlike `chess_rook_lift_v1` which has one. If a "before vs
after" success-rate number is needed for NVIDIA rather than a fidelity-only
number, that evaluator is the actual prerequisite — worth flagging to Jake
given he already built the replay path.
