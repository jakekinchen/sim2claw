# Studio live workspace audit

Date: 2026-07-18 America/Chicago

Repo/path: `/Users/jakekinchen/Developer/sim2claw`

## Scope

Implement and verify an on-demand Studio surface for the connected SO-101 and
three local cameras. Keep physical motion, camera calibration, simulation
contact, learned-policy evaluation, and task success as separate proof classes.

## Implemented contract

- The masthead indicator now reports the physical-arm preflight state instead
  of the process heartbeat count.
- Opening Live creates a short renewable loopback lease, opens the reviewed
  physical gateway with configuration rewriting disabled and torque off, and
  mirrors the observed follower joints through current-scene MuJoCo forward
  kinematics.
- Live Feed starts camera processes only while that tab is selected. Switching
  to Simulator, closing the drawer, starting a recorder gateway action, losing
  the lease, or shutting down the server releases all preview processes.
- The three feeds occupy equal cells in a 2x2 grid; the fourth cell remains an
  intentional open camera slot. The overhead preview is rotated 180 degrees
  from the first live implementation per operator request.
- The physical mirror publishes no contact markers and has no motion or task
  authority. The D405 preview explicitly carries no metric-depth, intrinsics,
  AprilTag-pose, or hand-eye-calibration claim.

## Connected-device evidence

| Studio role | Verified identity | Verified preview |
| --- | --- | --- |
| D405 wrist | Intel RealSense D405, USB `8086:0b5b` | 640x360 browser image from a 640x480 AVFoundation request |
| Logitech overhead | C922, USB `046d:085c`, serial `F5AA89BF` | 640x480; chessboard and AprilTags visible |
| Logitech workspace | Logitech `046d:081b`, serial `967FA250` | 640x480; arm and wider workcell visible |

All three inputs produced simultaneous multipart MJPEG data at the conservative
640x480 input baseline. The bounded command-line probe retained 20 D405, 27
overhead, and 16 workspace JPEG parts before its clients closed. The server
terminated all three ffmpeg workers afterward.

The D405 stream is operational, but at the observed torque-off follower pose it
looks upward toward the ceiling and light rather than at the board. Correcting
that field of view requires a physical wrist pose or mount/extrinsic decision;
rotating browser pixels cannot change its optical axis.

## Physical-arm observation

The loopback service opened the expected leader and follower buses and returned
a fresh follower vector of approximately:

```text
[42.02, -106.64, 98.86, -101.58, -133.14, 1.78]
```

The receipt reported follower torque disabled and no physical motion command.
The browser rendered this vector in the current sparse-pawn workcell. A separate
paired-pose preflight found the two physical arms outside the registration guard,
so no synchronization or physical trial was attempted.

## Rendered-surface verification

Chromium loaded both live modes with no console or page errors:

- Simulator: `Arm live`, six observed joint values, and a continuously updated
  MuJoCo body-state mirror.
- Live Feed: all three cards reached `Live`; natural image sizes were 640x360,
  640x480, and 640x480.
- Compact grid: all three cards and the open slot were wholly inside the drawer.
  At 1440x900, the drawer height and content height were both 878 pixels and
  each feed card was 576x303. At 1280x800, both drawer measurements were 778
  pixels and each card was 576x253. Neither MacBook-sized viewport required
  vertical scrolling.
- Demand boundary: after selecting Simulator, every camera image `src` was
  removed and the API reported zero streams. After closing Live, the API
  reported no active lease; `lsof` and the process table showed no serial or
  preview-process owners.

## Simulator/task comparison

Two clean temporary scripted probes exercised the latest sparse scene without
changing the committed proof artifacts:

| Left-arm target | Mount distance | Rise | Lift/hold contact | Result |
| --- | ---: | ---: | ---: | --- |
| `tan_pawn_c8` | 0.3044 m | 0.093782 m | 1.0 | pass |
| `brown_pawn_e2` | 0.5781 m | effectively 0 m | 0.0 | fail |

The brown E2 attempt had 47.75 mm stand-off, 106.10 mm advance, and 121.17 mm
lift residuals with no jaw/pawn contact. This is consistent with a board/task
axis or ownership mismatch: the current left arm reaches the tan near side but
not the brown far side. It is not evidence that a learned policy failed.

No learned-policy checkpoint is present in this checkout. The five existing
physical-command replay receipts report only joint-response comparison (roughly
2.83 to 3.45 degrees aggregate body-joint RMSE), explicitly leave learned-policy,
object/contact, and task-success verification false, and retain an older scene
label. The receipt writer now records the current scene ID, board-pose ID, and
manifest revision for future replays without rewriting those historical files.

## Remaining calibration gate

Before claiming camera/robot/board registration, freeze and separately evaluate:

- explicit A1 origin, file direction, and rank direction;
- D405/Logitech intrinsics and exact device identities;
- camera-to-robot and board-to-camera transforms with residuals;
- AprilTag family, IDs, detections, and pose-estimation convention;
- a new versioned scene/transform rather than mutating frozen v1/v2 evidence.

The Kelly-side calibration lane was found active on its own dirty branch and
was not modified or duplicated. A single coordination message was attempted
through the Codex thread route, but the host had no registered AppServerManager,
so delivery did not occur. No SSH resume, remote worktree edit, commit, merge,
or push was used as a fallback.
