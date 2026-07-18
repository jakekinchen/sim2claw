# Browser Visualization Studio

Status: implemented for local replay, process observation, and gated ACT source recording

Date: 2026-07-18 America/Chicago

## Product boundary

The studio is the browser-first visual cousin of a process dashboard. Its job
is to make repo-native simulation evidence legible:

- tasks group their replayable episodes;
- episodes play as interactive 3D MuJoCo state traces, video, or frame
  sequences and expose a scrubber, phase rail, timecode, proof class,
  evaluator result, and selected metrics;
- the live rail observes training, evaluation, dataset export, and simulation
  processes;
- the robot bench shows which embodiments are present in the MuJoCo scene;
- all views preserve the difference between a convincing replay and authority.

Replay, Library, Robots, and process observation remain read-only. The Record
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

The Record metadata surface mirrors the current physical test layout: brown
pawns begin at A2, B1, C2, D1, E2, F1, G2, and H1; destinations are unoccupied
squares in rows 1–4. Tan pawns mirror them at A8, B7, C8, D7, E8, F7, G8, and
H7. A generated full-board preview marks the selected pawn, destination, all
remaining pawns, and move arrow. New recording, physical-command replay, and
Studio inspection scenes use this 16-pawn layout; the standard 32-piece scene
remains available only for prior frozen proof paths. B1→B2 at 30 Hz is the
initial metadata default, and later choices persist in browser-local settings.
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
`datasets/act_source_recordings/<label>__<recording-id>/`. Each directory has a
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
| Scripted probe | `outputs/**/grasp_probe_receipt.json`, `state_trace.json`, and phase frames | Scripted simulation probe, not learned-policy evidence |
| MuJoCo scene manifest | `/api/scene?layout=standard` or the sparse task layout, plus allowlisted SO-101 STL assets | Browser geometry and initial pose contract; MuJoCo owns physics |
| Episode state trace | `state_trace.json` from grasp, ACT evaluation, GR00T export, or simulated teleoperation | World body poses and contacts sampled from `MjData`; browser interpolation is visual only |
| Live process rail | `runs/studio/processes/*.json` plus a bounded local `ps` scan | Observability only; it never controls the process |
| Robot bench | Versioned `studio_*` MuJoCo cameras plus the current scene contract | Simulated embodiment presence and alignment, not connected hardware |
| ACT source recorder | Expected SO-101 leader bus, frozen ACT state/goal contract, MuJoCo follower | Raw simulated teleoperation source; never learned-policy or physical-task proof |
| Physical gateway | Expected leader/follower buses and calibration hashes | Operator-gated raw physical trace; unavailable pose fields keep it out of ACT training |
| Overhead diagnostic video | Exact-name Logitech C922 via isolated AVFoundation/ffmpeg process | Time-correlated visual diagnosis with one-second post-roll; never evaluator or training admission |
| Simulator trace replay | Saved physical follower commands and actual state | Joint-response comparison only; not learned-policy or object/contact validation |

Generated artifacts stay ignored by Git. The server only serves approved image,
video, and state-trace JSON types below `outputs/`, `datasets/`, and `runs/`; encoded media paths
cannot escape those roots. MP4 byte ranges are supported so native browser
scrubbing does not require loading a whole video first.

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
Replay, Library, Robots, and Record are distinct views; tasks are filters within
Replay and Library.
The selected episode, semantic filmstrip, and evaluator metrics fit in one
desktop viewport. An idle live rail consumes no layout space; active work opens
from a compact status control into an observational drawer.

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
by default and retain a Recorded toggle when source video or frames exist. Drag
or touch to orbit, pan with the secondary pointer gesture, scroll to zoom, click
geometry to identify its body, and use Reset view to return to the versioned
overview camera.

The semantic filmstrip is the signature interaction: visible phase names,
ticks, preview, and a synchronized orange playhead turn the episode's real
temporal structure into the primary navigation model. Keyboard replay supports
Space, arrows, and frame stepping; visible focus and reduced-motion behavior
remain intact. Mobile keeps replay and verdict first, with episode browsing and
evidence details behind explicit disclosures and all four views in a bottom tab
bar.

## Workcell poster contract

The Robots view no longer reads an arbitrary historical PNG from `outputs/`.
Three committed inspection assets are regenerated from the current scene:

- `studio_overview` shows the board-reaching arm on the board centerline;
- `studio_left` shows the board-reaching arm and board relationship;
- `studio_right` isolates the folded edge arm.

Run `uv run sim2claw studio-assets` after changing the scene, capture config, or
SO-101 model. `assets/workcell/receipt.json` hashes those three sources and each
PNG; the test suite rejects a stale poster generation. The poster renderer uses
a higher-contrast inspection palette and hides the photo-reference tripod group.
Neither choice changes the frozen `workcell` task camera, physics, evaluator, or
recorded training observations.

The current board registration is
`board_robotward_72mm_20260718_v2`: center `(0.040, -0.093) m` in the table
frame, 72 mm along `+y` from the earlier overhead-photo pose. The Robots card
surfaces this as `72 mm robotward`, while the scene manifest, live simulator,
replay geometry, pawn coordinates, and freshly generated posters all consume
the same capture-config center. Recording receipts preserve this pose identity
so episodes are not later interpreted against a different workcell layout.

## Dependency record

The Studio server itself still uses Python 3.12 standard-library HTTP, JSON,
subprocess, and browser-launch modules. The recorder adds the reviewed public
`lerobot[feetech]==0.6.0` dependency for SO-101 bus/calibration access and pins
NumPy to `2.2.6` for its declared compatibility range. The client uses native
HTML, CSS, JavaScript, `<video>`, and range requests. Three.js is vendored as
browser modules, so no Node, Electron, Tauri, CDN, or runtime package install is
added.

The 3D adapter uses `three@0.185.1` under MIT for WebGL rendering,
`OrbitControls`, and `STLLoader`. Exact source, adopted files, local import
specifier patch, license, and reason are recorded in
`studio_web/vendor/three/SOURCE.md`. The adapter loads the already-reviewed
MuJoCo Menagerie SO-101 STL assets; it does not introduce a second robot model.

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
