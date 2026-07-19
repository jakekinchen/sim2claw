# Browser Visualization Studio

Status: implemented for local replay, multi-feed evidence, interactive 3DGS visual calibration, on-demand live inspection, process observation, and gated ACT source recording

Date: 2026-07-18 America/Chicago

## Product boundary

The studio is the browser-first visual cousin of a process dashboard. Its job
is to make repo-native simulation evidence legible:

- tasks group their replayable episodes;
- episodes play as interactive 3D MuJoCo state traces, video, or frame
  sequences and expose a scrubber, phase rail, timecode, proof class,
  evaluator result, and selected metrics;
- physical release episodes keep the source recording and overhead, side, and
  wrist command-replay feeds selectable on the same bounded episode timeline;
- Calibration renders the exact, checksummed Robo Scanner Gaussian PLY with
  orbit and relative translate/rotate/scale controls; reviewed MuJoCo geometry
  is an optional comparison layer hidden by default;
- the live rail observes training, evaluation, dataset export, and simulation
  processes;
- the arm-status control opens a leased physical-joint mirror or three
  on-demand workcell camera previews;
- the robot bench shows which embodiments are present in the MuJoCo scene;
- all views preserve the difference between a convincing replay and authority.

## Display-only LLM scene proposal

Calibration exposes the tracked
`configs/scenes/robo_scanner_llm_workcell_v1.json` contract. It records the
checksummed source video and Gaussian Splat, LLM visual observations, the
semantic scene hierarchy, reproducible prompt/output hashes, review state, and
explicit authority limits. The browser renders the hierarchy as read-only text.
Separately, it can render the accepted MuJoCo manifest as an opt-in translucent
Three.js layer while the 3DGS remains movable with relative translation,
rotation, and scale controls. The default view has no generic floor or grid
overlay because an unregistered grid would imply a spatial relationship that
the visual inputs do not prove.

This is a comparison surface, not an implemented promotion path. LLM analysis
may propose objects, relationships, and approximate geometry. The current code
does not consume hierarchy body-name mappings, compile the JSON, promote it, or
use it to drive MuJoCo or Three.js. It cannot establish metric scale, collision
geometry, task coordinates, evaluator proof, or physical-control authority.

Replay, Library, Calibration, Robots, and process observation remain read-only. The Record
view adds one narrow exception: when the server binds to loopback, it may open
the identified physical leader with torque disabled and use its joint targets
to control the MuJoCo follower. It has no command-launch, network gateway, or
checkpoint-promotion endpoint. Physical follower mode uses
one reviewed local gateway with explicit operator acknowledgement, bounded
paired-pose synchronization, a torque-held countdown, relative-zero registration,
excursion limits, and fail-closed shutdown. Start keeps the same gateway session
open from Sync through recording instead of releasing torque between phases.
Physical task
proof remains deferred until
pose sensing and consequence evaluation are present.
The studio always reports `physical_authority: false` because the surface does
not promote or independently authorize a physical task.

## Run it

From the repository root:

```bash
uv run sim2claw studio
```

The command binds `127.0.0.1:4173` and opens the default browser. For a server
without automatic browser launch:

```bash
uv run sim2claw studio --no-open
```

Use `--port 0` to ask the operating system for an unused port. Binding to a
non-loopback host exposes generated visual artifacts without authentication;
do that only inside a separately protected network boundary. Recorder POST
endpoints are disabled on non-loopback binds.

### Verified private release intake

Studio does not treat another machine's directory layout as proof of parity.
It consumes source-free release assets only after their sizes and SHA-256
digests match the tracked manifests:

- `docs/reference/IPHONE_VIDEO_3DGS_RELEASE_20260719.json` indexes the exact
  334,537-splat PLY, preview, orbit, and original-video identity;
- `docs/reference/PHYSICAL_REPLAY_RELEASE_20260719.json` indexes the source
  overhead MP4, three replay MKVs, and receipts;
- downloaded assets live below ignored
  `artifacts/private/releases/<release>/` paths, never in Git;
- `scripts/prepare_studio_private_releases.py` verifies each original replay
  feed before losslessly remuxing its H.264 stream from MKV to browser-seekable
  MP4 and writing an ignored integration receipt.

The catalog admits only exact manifest-listed private media whose resolved
path, size, and SHA-256 all verify; derived browser MP4s must additionally bind
to a verified source asset in the ignored integration receipt. Traversal,
absolute names, separators, symlinks, unlisted files, and hash drift are
rejected. The 3DGS is
relative monocular visual context only: it cannot establish metric scale,
measured geometry, RGB-D, collision geometry, task coordinates, evaluator
success, learned-policy evidence, gateway authority, or robot motion.

The Record metadata surface uses the current 100 mm workcell and explicit
B1↔B2 contract. Simulator-follower mode defaults to B1→B2 on the canonical
brown-pawn pattern A2, B1, C2, D1, E2, F1, G2, and H1, with tan pawns mirrored
on A8, B7, C8, D7, E8, F7, G8, and H7. Physical-follower mode defaults to the
reverse B2→B1 labeling on the lower-side physical pattern A1, B2, C1, D2, E1,
F2, G1, and H2; selectable squares remain explicitly validated by the recorder.
A generated full-board preview marks the selected pawn, destination, all
remaining pawns, and move arrow. New recording, physical-command replay, and
Studio inspection scenes use the sparse 16-pawn layout; the standard 32-piece
scene remains available only for prior frozen proof paths. The prior 72 mm
C8→C6 default is historical and is not the current Studio UI or contract.
Current pawn geometry follows the owner-supplied physical-set silhouette with a
stepped foot, rounded/flared base, narrow waist, collar, and spherical head.
The photo is a shape reference, not a metric scan, so board-relative scale and
MuJoCo physics remain the reviewed scene values.
When Simulator follower is selected, the Record console also opens the current
sparse-pawn workcell as an interactive live 3D view. During recording, a
loopback-only lightweight endpoint publishes the latest `MjData.xpos` and
`MjData.xquat` body state at the recorder rate; the browser samples that feed at
up to 20 Hz and only mirrors those MuJoCo-owned transforms. The live frame is
kept out of the ACT sample rows because the separately written state trace is
the episode artifact. Physical follower mode hides this simulator feed.
Start begins C922 capture, then owns bounded Sync, a torque-held countdown, and
relative-zero registration in one continuous gateway session; the separate Sync
and Check buttons are optional torque-off controls. Failed attempts move to
ignored diagnostic storage and the recorder becomes ready again without a
native browser dialog or reset step.

## Live workspace contract

The masthead arm control is separate from the process heartbeat. While closed,
Studio checks only the existing device/calibration preflight and camera
inventory: it does not hold a motor bus or camera stream. `Arm ready` therefore
means the expected leader and follower paths and their calibration identities
are present, not that a joint sample or motion capability has been established.

Opening Live creates a five-second renewable loopback lease. The service opens
the reviewed SO-101 gateway with configuration rewriting disabled and follower
torque disabled, verifies torque remains off, and reads both calibrated joint
vectors. The browser projects the observed follower vector through the current
sparse-pawn MuJoCo model with `mj_forward`; it does not step dynamics, infer
contact, or send a physical command. If the physical recorder already owns the
gateway, the mirror may consume its last observed follower state without
opening a second bus owner. Closing the drawer, starting a recorder gateway
operation, losing the browser heartbeat, or shutting down Studio releases the
telemetry gateway and all preview processes.

The Live Feed tab enumerates the current AVFoundation indexes by exact camera
identity immediately before use and opens independent 640x480 inputs capped at
a 10 fps MJPEG browser preview:

| Stable Studio role | Current device identity | Display treatment |
| --- | --- | --- |
| D405 wrist | `Intel(R) RealSense(TM) Depth Camera 405  Depth` | Raw AVFoundation diagnostic display; no metric-depth claim |
| Logitech overhead | `C922 Pro Stream Webcam` | Operator-requested orientation; no additional ffmpeg flip |
| Logitech workspace | `USB Camera VID:1133 PID:2075` | Wide workcell context |

No camera process starts in the Simulator tab. Switching away from Live Feed
removes all three image sources, causing their server-side ffmpeg processes to
terminate. The lease reaper is a second fail-safe for a closed or abandoned
browser. The recorder remains the exclusive owner of the C922 when diagnostic
episode capture is active.

The D405 endpoint is intentionally labeled as visible diagnostic video only.
This path does not expose librealsense metric depth, intrinsics, a calibrated
camera-to-gripper transform, AprilTag family/ID observations, or hand-eye
residuals. Those calibration artifacts must be frozen and evaluated separately
before camera pixels can be used to claim robot/board coordinate registration.

Every admitted recording starts the exact-name `C922 Pro Stream Webcam` in a
separate ffmpeg process before the selected follower opens. The camera uses the
stable AVFoundation NV12 mode at 640x480 and a requested 30 fps; the observed
frame rate and frame count are probed into the receipt rather than assumed.
The mounted image is rotated 180 degrees in the capture process. Arm samples
carry `overhead_video_time_seconds`, and the video metadata records pre-start
sequence and teleoperation offsets against the camera clock. Sync/countdown
failures also retain one second of post-roll. Arm control and torque close first;
the camera retains at least one second of post-roll, then shuts down gracefully
so the MP4 remains seekable. A missing or prematurely stopped camera fails the
attempt closed and retains the partial diagnostic bundle.

Before recording, inspect the same preflight used by the UI:

```bash
uv run sim2claw teleop-preflight
```

The default recording path is
`datasets/manipulation_source_recordings/<label>__<recording-id>/`. Each directory has a
JSONL sample stream, checksummed receipt, `overhead_c922.mp4`, camera timing
metadata, and an ffmpeg log. Failed attempts retain the same available camera
evidence under `runs/teleop_recordings/failed_attempts/`. These generated
artifacts are ignored by Git. The overhead video is diagnostic-only, and the
raw episode remains non-training data until M7 deterministic replay and the
separately owned evaluator admit derived rows.

## Current adapters

The catalog is rebuilt from current local truth every two seconds:

| Surface | Source | Interpretation |
| --- | --- | --- |
| Task shelf | `configs/tasks/*.json` | Frozen task identity and proof class |
| GR00T episode contact sheet | `datasets/*/meta/*.json*`, videos, and `dataset_receipt.json` | Synthetic simulation demonstrations and evaluator verdicts |
| ACT replay | `outputs/**/evaluation_receipt.json`, MP4, or rendered frames | Separately evaluated learned-policy simulation episode |
| Robo Scanner calibration | Tracked 3DGS release manifest plus hash-verified private PLY, preview, and orbit | Interactive relative visual placement only; MuJoCo remains physics/collision authority |
| Physical release feeds | Tracked physical-release manifest plus hash-verified source and browser-remuxed overhead, side, and wrist videos | Recorded source and guarded command-replay views; no task-success or training-admission claim |
| Scripted probe | `outputs/**/grasp_probe_receipt.json`, `state_trace.json`, and phase frames | Scripted simulation probe, not learned-policy evidence |
| MuJoCo scene manifest | `/api/scene?layout=standard` or the sparse task layout, plus allowlisted SO-101 STL assets | Browser geometry and initial pose contract; MuJoCo owns physics |
| Episode state trace | `state_trace.json` from grasp, ACT evaluation, GR00T export, or simulated teleoperation | World body poses and contacts sampled from `MjData`; browser interpolation is visual only |
| Live process rail | `runs/studio/processes/*.json` plus a bounded local `ps` scan | Observability only; it never controls the process |
| Live physical mirror | Leased torque-off gateway observation projected through current MuJoCo forward kinematics | Joint-pose inspection only; no contact, task, or motion authority |
| Live camera previews | Exact-identity D405, C922, and second Logitech AVFoundation inputs | On-demand display only; no evaluator, depth, or calibration claim |
| Robot bench | Versioned `studio_*` MuJoCo cameras plus the current scene contract | Simulated embodiment presence and alignment, not connected hardware |
| ACT source recorder | Expected SO-101 leader bus, frozen ACT state/goal contract, MuJoCo follower | Raw simulated teleoperation source; never learned-policy or physical-task proof |
| Physical gateway | Expected leader/follower buses and calibration hashes | Operator-gated raw physical trace; unavailable pose fields keep it out of ACT training |
| Overhead diagnostic video | Exact-name Logitech C922 via isolated AVFoundation/ffmpeg process | Time-correlated visual diagnosis with one-second post-roll; never evaluator or training admission |
| Simulator trace replay | Saved physical follower commands and actual state | Joint-response comparison only; not learned-policy or object/contact validation |

Generated artifacts stay ignored by Git. The server only serves approved image,
video, state-trace JSON, and Gaussian PLY types below `outputs/`, `datasets/`,
and `runs/`. Files below the ignored private-release root require exact
manifest/hash admission rather than root-level trust; encoded media paths
cannot escape those roots. MP4 and PLY byte ranges are supported so browser
scrubbing and splat loading remain bounded.

## Live heartbeat contract

Long-running repo-native functions can use `StudioActivity` from
`sim2claw.studio_events`. The ACT trainer and held-out ACT evaluator publish
structured progress now. A heartbeat record contains:

- a process ID, task ID, title, kind, and start/update timestamps;
- `status`, `phase`, `current`, `total`, and normalized `progress`;
- optional metrics and a replayable `episode_id` after completion;
- an explicit false physical-authority field.

The writer uses atomic JSON replacement. If a process ends without a final
heartbeat, the catalog displays it as interrupted instead of continuing to
claim that it is live. GR00T dataset-export progress is inferred from completed
episode videos and the frozen episode count. Other commands not yet
instrumented are detected as running with indeterminate progress when their
command line matches a reviewed `sim2claw` training, evaluation, export, or
probe command.

## Visual direction

The interface is an evidence and collection workbench, not an admin dashboard.
Replay, Library, Calibration, Robots, and Record are distinct views; tasks are
filters within Replay and Library. Calibration deliberately uses one dark datum
stage and a narrow evidence console so its visual-placement role cannot be
mistaken for episode replay or robot control.
The selected episode, semantic filmstrip, and evaluator metrics fit in one
desktop viewport. An idle process rail consumes no layout space. The compact
arm-status control opens a separate observational drawer with Simulator and
Live Feed tabs.

The palette is disciplined around ceramic `#ecefed`, chalk `#f8f9f6`, carbon
`#151816`, graphite `#6b716d`, and motion orange `#ff5a1f`. Orange is reserved
for playback and live work. Evaluator green and failure red only communicate
verdicts. Barlow Semi Condensed carries episode and task identity; IBM Plex
Mono carries time, phases, metrics, and proof metadata at an 11px minimum.

Actual recorded media is used for episode thumbnails. When media has not loaded
or is unavailable, a deterministic phase portrait derived from episode identity
and real phase durations provides visual indexing. It is not presented as a
measured end-effector trajectory.

Thumbnail selection prefers the middle of grasp, lift, or transfer phases rather
than an arbitrary early frame. The replay stage identifies either the recorded
source camera or `MUJOCO / FREE ORBIT`. Episodes with a state trace open in 3D
by default and retain a Recorded toggle when source video or frames exist.
Multi-feed releases add an independent camera selector; changing the feed does
not change the simulator state trace or evaluator verdict. Drag
or touch to orbit, pan with the secondary pointer gesture, scroll to zoom, click
geometry to identify its body, and use Reset view to return to the versioned
overview camera.

The semantic filmstrip is the signature interaction: visible phase names,
ticks, preview, and a synchronized orange playhead turn the episode's real
temporal structure into the primary navigation model. Keyboard replay supports
Space, arrows, and frame stepping; visible focus and reduced-motion behavior
remain intact. Mobile keeps replay and verdict first, with episode browsing and
evidence details behind explicit disclosures and all five views in a bottom tab
bar.

## Workcell poster contract

The Robots view no longer reads an arbitrary historical PNG from `outputs/`.
Four committed inspection assets are regenerated from the current scene:

- `studio_overview` shows the board-reaching arm on the board centerline;
- `studio_left` shows the board-reaching arm and board relationship;
- `studio_right` isolates the folded edge arm;
- `studio_mug` provides a close inspection of the Antler mug and procedural
  wordmark on the left window sill.

Run `uv run sim2claw studio-assets` after changing the scene, capture config, or
SO-101 model. `assets/workcell/receipt.json` hashes the scene sources and each
PNG; the test suite rejects a stale poster generation. The poster renderer uses
a higher-contrast inspection palette and hides the photo-reference tripod group.
Neither choice changes the frozen `workcell` task camera, physics, evaluator, or
recorded training observations.

The current workspace registration is
`workspace_board_fiducial_robotward_100mm_20260718_v3`. Its board pose is
`board_robotward_100mm_20260718_v3` at `(0.040, -0.065) m`, 100 mm total along
`+y` from the overhead-photo pose and 28 mm beyond the historical 72 mm pose.
Its fiducial pose is `fiducial_robotward_100mm_20260718_v2` at
`(0.020, 0.180) m`; because the simulated sheet never received the earlier
board-only update, it moves the full 100 mm now. The Robots card surfaces the
board as `100 mm robotward`, while the scene manifest, live simulator, replay
geometry, pawn coordinates, and freshly generated posters consume the same
capture-config workspace. Recording receipts preserve both board and fiducial
pose identities so episodes are not later interpreted against a different
workcell layout.

## Dependency record

The Studio server itself still uses Python 3.12 standard-library HTTP, JSON,
subprocess, and browser-launch modules. The recorder adds the reviewed public
`lerobot[feetech]==0.6.0` dependency for SO-101 bus/calibration access and pins
NumPy to `2.2.6` for its declared compatibility range. The client uses native
HTML, CSS, JavaScript, `<video>`, and range requests. Three.js is vendored as
browser modules, so no Node, Electron, Tauri, CDN, or runtime package install is
added.

The 3D adapter uses `three@0.185.1` under MIT for WebGL rendering,
`OrbitControls`, `STLLoader`, and the `Pass` base required by Spark. Exact
source, adopted files, local import
specifier patch, license, and reason are recorded in
`studio_web/vendor/three/SOURCE.md`. The adapter loads the already-reviewed
MuJoCo Menagerie SO-101 STL assets; it does not introduce a second robot model.

The Calibration view uses `@sparkjsdev/spark@2.1.0` under its upstream MIT
license to render the verified Gaussian PLY. Its pinned tarball, upstream and
locally patched module hashes, adopted-file rationale, and World Labs license
notice are recorded in `studio_web/vendor/spark/SOURCE.md` and `LICENSE`.

Overhead diagnostics adopt the installed upstream FFmpeg 7.1.1 command-line
runtime. AVFoundation opens the C922 by exact device name, and
`h264_videotoolbox` keeps encoding outside the serial control thread and on the
Mac video encoder. `ffprobe` records actual dimensions, frame rate, frame count,
duration, and size after graceful finalization. This dependency is used only
for ignored diagnostic artifacts and creates no camera or motion authority.

Two open-source webfont assets are vendored for deterministic local typography:

| Package | Version | License | Reason |
| --- | --- | --- | --- |
| `@fontsource/barlow-semi-condensed` | `5.2.7` | SIL OFL 1.1 | Display and navigation identity |
| `@fontsource/ibm-plex-mono` | `5.2.7` | SIL OFL 1.1 | Legible metrics, timecode, and proof metadata |

Only the Latin 400/600 WOFF2 files are shipped. Their license texts live beside
the assets under `studio_web/assets/fonts/licenses/`.

## 3D replay contract and boundary

`sim2claw.mujoco_scene_manifest.v1` maps visible MuJoCo geoms (groups 0 and 2),
body identities, materials, primitive dimensions, compile-time STL transforms,
and a suggested inspection camera. `sim2claw.mujoco_body_state_trace.v1`
records body `xpos`/`xquat`, phase, and bounded contact markers at episode
cadence. The viewer interpolates adjacent recorded poses for smooth display and
never steps dynamics, computes contacts, evaluates success, or sends commands.

The scripted grasp probe and ACT evaluator write one trace beside their
receipts. GR00T export writes one trace per dataset episode under
`state_traces/`. The simulated teleoperation follower writes one beside its raw
source samples. Older artifacts without traces continue to replay as video or
frames.

MuJoCo remains the simulation and collision source of truth. Three.js is an
inspection renderer only; its visuals and interpolated frames cannot promote a
dataset, prove a learned policy, establish physical readiness, or authorize
robot motion.
