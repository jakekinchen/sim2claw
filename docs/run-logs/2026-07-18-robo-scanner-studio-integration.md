# Robo Scanner and private Studio release integration — 2026-07-18

## Outcome

The current Mac Studio now consumes the same immutable release identities used
for the Silicon-produced Robo Scanner and physical replay evidence:

- the exact 334,537-splat, spherical-harmonics-degree-3 Gaussian PLY is
  available in Studio Calibration with preview and orbit evidence;
- the physical source episode is available in Replay with source overhead,
  replay overhead, replay side, and replay wrist feed selectors;
- episodes with `state_trace.json` retain the independent **3D inspect** MuJoCo
  surface; changing a recorded feed does not change simulator state, evaluator
  verdict, or proof class;
- presentation text and the three submission posters now describe Robo Scanner
  and the visual-only 3DGS/MuJoCo authority split rather than the historical
  capture path.

This is a release-hash parity result, not a byte-for-byte audit of every file on
the remote Silicon filesystem.

## Transfer and source audit

`tailscale status` showed both hosts active and direct:

- current host: `kellys-mac-studio` / `100.115.44.101`;
- producer host: `silicon` / `100.90.246.116`.

The Taildrop queue was checked with the authenticated Tailscale app CLI and was
empty (`0` files moved). Direct remote filesystem inspection was attempted, but
SSH authentication was unavailable (`Permission denied
(publickey,password,keyboard-interactive)`). No remote parity claim is based on
that blocked SSH lane.

The authenticated private GitHub Releases were used as the durable transfer
surface instead:

- `iphone-video-3dgs-img5349-20260719`;
- `physical-replay-evidence-20260719`.

Assets were downloaded below ignored
`artifacts/private/releases/<release>/` directories. Nothing generated, private,
or source-video-sized was added to Git.

## Verified Robo Scanner release

Tracked authority: `docs/reference/IPHONE_VIDEO_3DGS_RELEASE_20260719.json` and
its `.sha256` companion.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `IMG_5349-primary-real-splat.ply` | 78,952,283 | `f8f3bfe0a0f1fa13d54e47602dbf43f8e0448178c0e85f0f22a5f2115530443b` |
| `IMG_5349-preview.png` | 1,151,448 | `555bb81cfdbbcb896e672cfeaafbf41d618877fa92c9c3a882d58ebc5bc42703` |
| `IMG_5349-orbit.mp4` | 8,441,321 | `b8bf14d03795d9c5fee8b11b4bd605ac977629153f5eb696f8119bb5202ce769` |
| source identity `IMG_5349.MOV` | 335,783,020 | `0079c19d5a321dd3613924f4a7e0838a4f99943b0833a0b8bed81a12d303dfa8` |

All downloaded release assets passed `shasum -a 256 -c`. The same PLY, preview,
orbit, and source-video identities also matched the Robo Scanner producer
package under `/Users/kelly/Developer/robo-scan/artifacts/incoming/IMG_5349/`.

Studio uses the public MIT-licensed `@sparkjsdev/spark` 2.1.0 renderer, pinned
and locally served. The tracked Studio view records the producer's exact-camera
center, rotation, vertical field of view, and preferred relative target, with
the source viewer-config hash preserved. That viewer-config file exists only in
the producer workspace and is not tracked or independently hash-verifiable in
this repository; the tracked release index marks that limitation explicitly.
The browser recenters the indexed target for interaction without inventing
metric scale; placement controls remain relative.
The splat grants no metric
scale, measured geometry, RGB-D, collision geometry, complete unseen geometry,
task-coordinate, evaluator, learned-policy, gateway, or robot authority.

## Verified physical replay release

Tracked authority: `docs/reference/PHYSICAL_REPLAY_RELEASE_20260719.json`.
Every original MP4, MKV, and JSON receipt passed its tracked size and SHA-256
check before catalog admission.

Because the three replay videos were MKV containers, the integration script
copied their existing H.264 video streams into browser-seekable MP4 containers
without re-encoding:

```bash
uv run python scripts/prepare_studio_private_releases.py \
  --ffmpeg /opt/homebrew/bin/ffmpeg
```

The ignored integration receipt records source hashes, derived hashes, the
ffmpeg executable hash, and the operation
`container_remux_h264_copy_to_mp4`.

| Studio feed | Bounded source window (seconds) |
| --- | ---: |
| Source overhead | 7.734–32.013 |
| Replay overhead | 40.640–69.553 |
| Replay side | 45.640–74.553 |
| Replay wrist | 33.640–62.553 |

The structured metadata says `E2 → E1`; the display label says `F2 → F1`.
Studio preserves and calls out that disagreement. The operator note is retained
as annotation, not promoted to task success. The release proves a recorded
physical source and a completed guarded command replay, including torque-off
shutdown; it does not prove autonomous ACT execution, learned-policy success,
object contact, board outcome, or training admission.

## Studio integration contract

The catalog now:

1. resolves allowlisted media below generated-data roots, while private media
   requires exact manifest/path/hash admission rather than root-level trust;
2. rejects private traversal, absolute/separator names, symlinks, unlisted
   files, and hash drift before exposing an asset;
3. omits a private episode or calibration model when verification fails;
4. exposes simulator-state replay and recorded feed replay as separate modes;
5. exposes the 3DGS only in the read-only Calibration view;
6. retains `physical_authority: false` and all evaluator-owned verdicts.

At integration time, the local catalog reported 18 tasks, 31 episodes, 30
evaluator passes, two simulated robots, and one ready calibration asset. Counts
are runtime inventory, not a new proof milestone.

## Display-only LLM scene proposal

The versioned `configs/scenes/robo_scanner_llm_workcell_v1.json` contract now
records model/tool identity, the exact prompt and its SHA-256, a canonical
analysis/hierarchy output SHA-256, source-video and 3DGS identities, visual
observations, semantic hierarchy, review state, and authority limits. The
contact sheet is explicitly marked producer-only and not locally verifiable;
the exact-camera preview is indexed by the tracked private-release manifest.

Studio renders that hierarchy as read-only text beside the capture. Separately,
it builds a translucent Three.js projection from the accepted MuJoCo manifest
and attaches it to the fixed calibration datum. The current code does not
consume hierarchy body names, compile or promote the JSON, or use it to drive
either geometry layer. The splat remains movable for relative inspection. LLM
analysis cannot establish metric scale, collision geometry, task coordinates,
evaluator proof, or physical authority.

## Remaining external limitation

Direct SSH access to `silicon` still needs a user-approved credential or key if
a full remote directory comparison is required. Release hashes already provide
the stable parity needed by Studio, so this blocker does not weaken the assets
admitted here; it only prevents claiming that every unrelated remote file has
been inventoried.
