# Live simulation-follower Record view

Date: 2026-07-18 America/Chicago

## Goal

Show the current MuJoCo follower and sparse-pawn workcell live on the Record
page while the physical leader drives a simulation-follower recording.

## Implementation

- `SimulationFollowerBackend` reuses the authoritative body state already
  sampled by `EpisodeStateTraceRecorder` after each MuJoCo step.
- A separate loopback-only endpoint exposes only the latest body positions,
  quaternions, contacts, scene identity, and recording identity. It does not
  read either arm bus and does not add browser-delivery fields to ACT sample
  rows.
- The Record page loads the current scene while idle, samples the lightweight
  live-state endpoint at up to 20 Hz during simulator recording, and applies
  those MuJoCo-owned transforms in the existing Three.js inspection adapter.
- The panel is visible only when Simulator follower is selected. It is hidden
  for Physical follower mode and never claims physical authority.

## Verification

- The current sparse scene contains 43 bodies; one live JSON payload is about
  5.3 KB.
- The isolated rendered Record page loaded the interactive scene, showed the
  ready state, exposed orbit/reset controls, hid the panel for Physical
  follower, restored it for Simulator follower, and emitted no browser warnings
  or errors.
- `uv run pytest -q`: 67 tests and 10 subtests passed.
- Targeted Ruff and JavaScript syntax checks passed for all changed feature
  files. Two unrelated pre-existing unused imports remain in the wider dirty
  worktree and were not changed.

The production Studio process was not restarted during verification because an
operator-owned physical-follower recording was active with torque enabled.
