# SO-101 Arm Calibration (reference)

LeRobot calibration captured on Kelly's Mac (2026-07-03) for the SO-101
follower (robot) and leader (teleoperator) arms. Reference/provenance
artifact only — it is data, not physical-transfer authority.

## Physical mass profile

`follower_mass_profile_v1.json` maps the owner's June 28 scale measurements
and inline photos to the MuJoCo rigid bodies. It uses the Feetech C001
manufacturer value of `55 +/- 1 g` per STS3215, not the unverified `28 g`
heading in the note. It also records a bounded estimate for the exact custom
library-printed D405 support, the official `60 g` D405 mass, arm hardware, and
the routed camera cable.

The default chess scene applies the profile in memory. The vendored Menagerie
XML remains unchanged. The resulting nominal masses are `907 g` without the
D405 payload and `1,006 g` for the left board-reaching arm with that payload;
the component-bounded total is `977--1,035 g`. The reported conservative range
is `965--1,047 g` after an additional `12 g` margin for rounded or nominal
source values that do not carry a stated tolerance.

The already-frozen ACT and GR00T contracts continue to instantiate
`ChessRookLiftEnv` with its legacy default (`mass_profile_path=None`) so their
receipts remain reproducible. New requalification runs can opt into this model
with `mass_profile_path=DEFAULT_SO101_MASS_PROFILE`; their results must receive
new receipts and cannot inherit promotion from the legacy dynamics.

Only mass is measurement-led at this boundary. Existing CAD centers of mass
are retained and inertia tensors are scaled linearly per rigid body; the D405
uses an explicit `42 x 42 x 23 mm` box at the vendored camera pose. This is a
better dynamics prior, not an identified inertia model. Gravity-hold fitting is
still required before claiming calibrated centers of mass or inertias.

## What these files encode

Per motor: `homing_offset` (the raw encoder tick LeRobot treats as zero) and
`range_min` / `range_max` (the reachable sweep in raw ticks, 0–4095), plus
`drive_mode` and the bus `id`. **These numbers describe one specific physical
arm** — they are fixed by how each servo horn was seated on its spline and how
the motors were mounted. They are independent of the host computer or OS.

## When you may reuse this file

- **Same physical arm** → valid. Any machine driving *this* arm can use these
  files instead of re-calibrating. Calibration follows the arm, not the host.
- **A different SO-101 arm** → do NOT use these to drive it. Homing offsets and
  ranges differ per unit; wrong values map commands to wrong physical angles
  and can drive into joint limits. Calibrate that arm on its own hardware.

## Do you even need this on the policy-server box?

In the gateway architecture the **policy server runs inference over the
network and does not touch the serial arm** — the machine physically wired to
the arm (its USB robot client) is the one that needs calibration. If the
NVIDIA box is inference-only, it does not need a calibration file at all. It
only needs one if the arm is plugged directly into it.

## Installing on another machine (same-arm case)

LeRobot reads calibration from its cache by robot **type** and **id**. Copy to
the matching paths (the type/id folders must match your LeRobot robot config):

```bash
# follower (robot)
mkdir -p ~/.cache/huggingface/lerobot/calibration/robots/so_follower
cp calibration/so101/follower_arm.json \
  ~/.cache/huggingface/lerobot/calibration/robots/so_follower/follower_arm.json

# leader (teleoperator) — only if teleoperating
mkdir -p ~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader
cp calibration/so101/leader_arm.json \
  ~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/leader_arm.json
```

If your LeRobot robot `id`/type differs (e.g. not `so_follower` /
`follower_arm`), rename the folder/file to match, or point
`HF_LEROBOT_CALIBRATION` at a directory you control. LeRobot skips its
interactive calibration step when a matching file already exists.

## Deployment-consistency note

For a trained policy to act correctly on hardware, the calibration at
deployment must match the calibration used when the training action space was
defined. Treat this file as the canonical reference for that arm and keep all
machines pointed at the same values.
