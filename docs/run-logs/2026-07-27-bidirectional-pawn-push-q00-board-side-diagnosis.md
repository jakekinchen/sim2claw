# Q00 immutable C2 board-side diagnosis

Date: 2026-07-27

Proof class: `read_only_action_frozen_perfect_tracking_fk_diagnostic`

Physical authority: false

Robot motion: none

## Decision

The categorical board-side diagnosis is confirmed, but the advisory numbers
mixed two different geometric observables.

Using the advisory's `left_gripperframe` site-to-square-base definition
reproduces `265.275519 mm` to C2. The same definition gives `80.897091 mm` to
C8 and `100.783880 mm` to C7.

Using the repository's task-relevant calibrated pad-gap pinch point and a
28 mm pawn-neck target gives:

| Target | Minimum 3D approach | Canonical row |
| --- | ---: | ---: |
| C2 neck | `257.506340 mm` | `435` |
| C8 neck | `64.673854 mm` | `242` |
| C7 neck | `85.525518 mm` | `270` |

The second definition reproduces the reported approximately `64.5/86 mm`
C8/C7 values. It does not reproduce `265.3 mm` for C2 because `265.3 mm`
belongs to the first definition. Both complete metric triples are recorded
above rather than presenting the mixed advisory triple as one measurement.

The current C2 and C8 square centers are exactly `266.700000 mm` apart:
`6 * 44.45 mm`. The immutable C2 trajectory passes far closer to the
simulator's rank-7/rank-8 side than to simulated C2. Therefore the compiled
scene's categorical rank/side convention is a necessary explanation for
physical contact with no simulated C2 contact.

It is not a sufficient complete correction. Even the corrected-side C8
pad-gap/neck residual is `64.673854 mm`, above the queue's `25 mm` gate, and
the trajectory's closest neck target over the full board is D8 at
`52.228 mm`. Q01-Q03 must therefore freeze and validate the registration
dataset before choosing the exact categorical orientation and bounded XY/yaw
refinement. No joint-zero change is justified by Q00 alone.

## Immutable inputs

| Input | SHA-256 / identity |
| --- | --- |
| Canonical C2 action NPY | `0af43f1709e8e7294c21e0876992dfbc21e6902165d4c24a50af9ed4ced47196` |
| Canonical raw little-endian float64 C-order bytes | `0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da` |
| Shape / rate | `701 x 6` / `40 Hz` |
| Candidate manifest | `f4110c4be9712aa14df9682ce0e28f4d7f0d6d00bc8bc2561290cc49de18f170` |
| Candidate digest | `2da7425cbf0fd10e27822a415890ca180dde7a4f1b042bf3ed49030bcad018af` |
| Canonical candidate config | `fbf451821e96c9f236b89feb076b964fd81f52416028f93e627118e296697368` |
| Joint transform | `72812016bfa9dba2ba97fe448724394ad290a2b22458177bcbdec95aae0689e6` |
| Scene ID | `operator_updated_chess_workcell_v3` |
| Capture/scene config | `0dbe0c95fe50f84a8ff8e60f9727f7123c15c921ace55a0460b49ffa4c34dc05` |
| Physics terminal-negative receipt | `c2b67d6e30fbc9893e21482ede7cdb6767a9f8acb7edd21c58551ac72ea77733` |
| Physical execution receipt | `48a5642c131a3958f371dd3c6d81526b90f435b0d13d7283e196720d0f4cf14b` |
| C922 outcome receipt | `8e963ac252df7908ec616833bbe7a0bbd595aeca03207415dc787a1064828bce` |

The candidate transform is still
`calibration_approved:false` /
`review_status:provisional_range_audit_blocked`. Q00 does not promote it.

## Exact source of the categorical placement

- `src/sim2claw/recorded_replay.py::_compile_model` compiles
  `model.kind == "current_chess_scene"` through
  `build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT)`.
- `src/sim2claw/scene.py::board_square_center` maps file and rank directly as
  zero-based indices and rotates them by the configured board yaw.
- `src/sim2claw/scene.py::_piece_bodies` uses the same direct rank mapping for
  `sparse_two_sided_pawns`.
- `configs/polycam/8873B66C-774C-48B1-B51D-338645867009.json` supplies board
  center `[0.04, -0.065] m`, side `0.3556 m`, and relative yaw `1.55 deg`.
- The candidate manifest binds `left_gripperframe` as the end-effector site
  and the provisional physical-to-simulator transform above.

Source hashes at evaluation time:

- `src/sim2claw/scene.py`:
  `b346222a4e601f22e199e59eb9f46a08cc086b6fa9fe3492a68000ece9061daf`
- `src/sim2claw/recorded_replay.py`:
  `5d27449e16629550d5559d602c50313e4e91cb8e039c3537fe9fd006837ffdae`
- `src/sim2claw/wrist_view_reposition.py`:
  `317e674abbe2804c16800cfe308b135cb50af7e2fa896a1b4fc46bc259c4550c`
- `src/sim2claw/grasp.py`:
  `c4c0d4382c8319e0dec25d0e1d740fd92fdd7fdd6e8717e99a4aaa6c37e2e313`

## Reproduction command

Run from `/Users/kelly/Developer/sim2claw`:

```bash
uv run python - <<'PY'
import json
from pathlib import Path
import mujoco
import numpy as np
from sim2claw.recorded_replay import _compile_model
from sim2claw.wrist_view_reposition import _physical_to_model_position
from sim2claw.grasp import _pinch_offset, _pinch_point
from sim2claw.scene import board_square_center

action = np.load(
    "runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/"
    "compiled/counted_task_action.npy",
    allow_pickle=False,
)
manifest = json.loads(
    Path(
        "runs/physical_excitation/20260725-follower-only-v1/"
        "simulation-canary-v1/candidate_manifest.json"
    ).read_text()
)
config = manifest["candidate_config"]
model, _ = _compile_model(config, base_directory=None)
data = mujoco.MjData(model)
joint_ids = [
    mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
    for name in config["bindings"]["joint_names"]
]
qpos = np.array([model.jnt_qposadr[joint_id] for joint_id in joint_ids])
mapped = _physical_to_model_position(action, config)
data.qpos[qpos] = mapped[0]
mujoco.mj_forward(model, data)
pinch_local = _pinch_offset(model, data, "left")
site_id = mujoco.mj_name2id(
    model, mujoco.mjtObj.mjOBJ_SITE, "left_gripperframe"
)
sites = []
pinches = []
for row in mapped:
    data.qpos[qpos] = row
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)
    sites.append(data.site_xpos[site_id].copy())
    pinches.append(_pinch_point(model, data, "left", pinch_local).copy())
for label, points, dz in (
    ("site_base", np.array(sites), 0.0),
    ("pinch_neck28", np.array(pinches), 0.028),
):
    print(label)
    for square in ("c2", "c8", "c7"):
        target = np.array(board_square_center(square)) + [0, 0, dz]
        distance = np.linalg.norm(points - target, axis=1)
        print(square, distance.min() * 1000, int(distance.argmin()))
PY
```

Observed output:

```text
site_base
c2 265.27551856666787 434
c8 80.89709137643065 242
c7 100.78387965814872 270
pinch_neck28
c2 257.50633957866 435
c8 64.67385431538496 242
c7 85.52551774909892 270
```

## Claim boundary

This is a deterministic, read-only, action-frozen FK diagnosis. It confirms a
categorical scene-registration defect and rejects controller tuning as a
solution to the historical simulator miss. It is not a calibrated scene,
held-out validation, task success, transfer proof, or authority for physical
motion.
