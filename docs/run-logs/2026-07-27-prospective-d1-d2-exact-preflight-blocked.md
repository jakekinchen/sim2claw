# Prospective exact D1→D2 REAL→SIM preflight — blocked

Date: 2026-07-27

Verdict: `blocked_required_d405_unavailable`

Proof class: `prospective_task_preflight_terminal_blocker`

No task motion was attempted.

## Phase A secured first

The reviewer-shareable Phase A artifact was published and anonymously
re-downloaded before this campaign began:

`https://github.com/jakekinchen/sim2claw/releases/tag/phase-a-real-to-sim-d1-d2-20260727`

The release remains exactly four public assets: composite MP4, poster,
claim/metrics document, and redacted public receipt.

## Decisive pre-torque gate

One motion-free static tricam transaction was invoked under the existing
single-attempt/no-retry contract. C922 completed 67 retained frames with zero
dropped callbacks. D405 startup then failed before `rs-record` began.

The direct librealsense diagnostic reported:

- failed to claim USB interface 0;
- `RS2_USB_STATUS_ACCESS`;
- failed to set the D405 power state;
- no librealsense device available to record.

macOS still exposed the D405 UVC camera entry, so this is not evidence that the
cable is absent. It is evidence that the required librealsense recording owner
could not acquire the device for this transaction. The Pi IMX708 stage was not
reached after the required D405 gate failed.

The stopped transaction left no `rs-record`, Pi camera, libcamera, FFmpeg, or
static-capture process running.

## Scene, action, and review consequences

The final C922 frame was visually inspected, but C922 alone cannot admit the
required tricam scene/start gate. Therefore the following were not established:

- upright pawn at D1 and empty D2 under all required views;
- robot identity plus a safe exact task start;
- C922, D405, and Pi enclosure of the complete prospective action.

The old 531-row observed-joint trace remained provenance only. Its direct
float64 bytes hash to
`ec75ad25adf9957311e837744af7340e27b602cfec5a2985db7841b5c3558312`.
At a newly imposed 20 Hz clock its per-joint maximum rates would be
`[45.7143, 58.0220, 49.2308, 47.4725, 59.7802, 61.7577]` physical units per
second, so it was not silently relabeled as an accepted exact gateway action.

Because the camera gate failed first:

- no prospective canonical action was compiled or frozen;
- no new action hash was accepted;
- no simulator safety preview was promoted to transfer evidence;
- no independent motion review receipt was issued;
- no gateway clamp, rate limit, repair, offset, IK correction, or suffix was
  used;
- no physical REAL→SIM task attempt occurred.

## Torque-off closeout

The task gateway was never opened. A follower-only configuration-free
preflight then opened the expected follower bus torque-off, required torque to
already be off, and closed it again with:

- `physical_follower_torque_enabled: false`;
- `device_configuration_rewritten: false`;
- `real_leader_opened: false`.

The local ignored blocker receipt is:

`runs/prospective-real-to-sim/20260727-d1-d2-exact-v1/preflight_blocker_receipt.json`

SHA-256:
`8d096ae63666a5e58be6f53f35d53e47599ae7b60b3cfce8f522569f4834e149`

## Stop decision

The required D405/Pi/C922 gate was not established, so the campaign stopped
before task motion exactly as preregistered. Phase 1 did not pass; therefore
Phase 2 SIM→REAL pawn motion is forbidden and was not attempted.

The project headline remains `TWIN FIDELITY 0/6` and `TASK SCORE 0/11`.
