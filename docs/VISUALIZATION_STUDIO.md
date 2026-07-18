# Browser Visualization Studio

Status: implemented for local read-only replay and process observation

Date: 2026-07-18 America/Chicago

## Product boundary

The studio is the browser-first visual cousin of a process dashboard. Its job
is to make repo-native simulation evidence legible:

- tasks group their replayable episodes;
- episodes play as video or frame sequences and expose a scrubber, phase rail,
  timecode, proof class, evaluator result, and selected metrics;
- the live rail observes training, evaluation, dataset export, and simulation
  processes;
- the robot bench shows which embodiments are present in the MuJoCo scene;
- all views preserve the difference between a convincing replay and authority.

The server is read-only. It has no command-launch, camera, network gateway,
serial, servo, checkpoint-promotion, or physical-motion endpoint. The studio
always reports `physical_authority: false`.

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
do that only inside a separately protected network boundary.

## Current adapters

The catalog is rebuilt from current local truth every two seconds:

| Surface | Source | Interpretation |
| --- | --- | --- |
| Task shelf | `configs/tasks/*.json` | Frozen task identity and proof class |
| GR00T episode contact sheet | `datasets/*/meta/*.json*`, videos, and `dataset_receipt.json` | Synthetic simulation demonstrations and evaluator verdicts |
| ACT replay | `outputs/**/evaluation_receipt.json`, MP4, or rendered frames | Separately evaluated learned-policy simulation episode |
| Scripted probe | `outputs/**/grasp_probe_receipt.json` and phase frames | Scripted simulation probe, not learned-policy evidence |
| Live process rail | `runs/studio/processes/*.json` plus a bounded local `ps` scan | Observability only; it never controls the process |
| Robot bench | Versioned `studio_*` MuJoCo cameras plus the current scene contract | Simulated embodiment presence and alignment, not connected hardware |

Generated artifacts stay ignored by Git. The server only serves approved image
and video types below `outputs/`, `datasets/`, and `runs/`; encoded media paths
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

The interface is a replay workbench, not an admin dashboard. Replay, Library,
and Robots are distinct views; tasks are filters within Replay and Library.
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
than an arbitrary early frame. The replay stage identifies the recorded source
camera so task evidence cannot be confused with the inspection-only poster
cameras.

The semantic filmstrip is the signature interaction: visible phase names,
ticks, preview, and a synchronized orange playhead turn the episode's real
temporal structure into the primary navigation model. Keyboard replay supports
Space, arrows, and frame stepping; visible focus and reduced-motion behavior
remain intact. Mobile keeps replay and verdict first, with episode browsing and
evidence details behind explicit disclosures and Replay, Library, and Robots in
a bottom tab bar.

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

## Dependency record

No runtime dependency was added. The server uses Python 3.12 standard-library
HTTP, JSON, subprocess, and browser-launch modules. The client uses native
HTML, CSS, JavaScript, `<video>`, and range requests. This keeps the studio
inside the existing explicit Python runtime and avoids a second Node, Electron,
or Tauri build chain at this boundary.

Two open-source webfont assets are vendored for deterministic local typography:

| Package | Version | License | Reason |
| --- | --- | --- | --- |
| `@fontsource/barlow-semi-condensed` | `5.2.7` | SIL OFL 1.1 | Display and navigation identity |
| `@fontsource/ibm-plex-mono` | `5.2.7` | SIL OFL 1.1 | Legible metrics, timecode, and proof metadata |

Only the Latin 400/600 WOFF2 files are shipped. Their license texts live beside
the assets under `studio_web/assets/fonts/licenses/`.

## Known boundary

The studio replays rendered camera evidence; it is not a second physics engine
and does not reconstruct authoritative 3D state in the browser. MuJoCo remains
the simulation source of truth. A future state-stream adapter can add a
Three.js inspection camera without changing evaluator ownership or treating
browser rendering as collision evidence.
