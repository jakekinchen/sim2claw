# Board Robotward 72 mm Registration

Request: update every simulation and visualization surface after the owner
moved the physical chessboard 72 mm toward the robots.

Repo/path: `/Users/jakekinchen/Developer/sim2claw`

Date: 2026-07-18 America/Chicago

## Registration decision

Both SO-101 mounts have table-frame `y = 0.365 m`. Therefore "toward the
robots" is table-frame `+y`. The measured displacement changes the board center
from the historical overhead-photo pose `(0.040, -0.165) m` to the current pose
`(0.040, -0.093) m`; board size and yaw are unchanged.

| Field | Current value |
| --- | --- |
| Pose identity | `board_robotward_72mm_20260718_v2` |
| Board center | `(0.040, -0.093) m` in table frame |
| Previous center | `(0.040, -0.165) m` in table frame |
| Displacement | `0.072 m` along table-frame `+y` |
| Board rear clearance | `0.0997 m` |
| Center-arm nearest board-edge distance | `0.2548 m` |
| Side-arm nearest board-edge distance | `0.4433 m` |

The previous pose remains in the capture config as provenance and in the
2026-07-17 alignment log as historical evidence. The Polycam scan pose is also
left unchanged.

Frozen tasks that declare `photo_aligned_chess_workcell_v1` resolve the named
historical center `(0.040, -0.165) m`. Current Studio and recorder surfaces use
`operator_updated_chess_workcell_v2`. This prevents the workcell update from
silently changing held-out scenes or making an old checkpoint appear evaluated
against geometry it never owned.

## Propagation contract

The capture config is the single geometry source for the board collision slab,
pawn bodies, board squares, structured goals, generated MuJoCo manifests,
browser Three.js geometry, live simulation-follower view, and current-scene
posters. Recorder receipts now copy the pose identity and center so a newly
captured physical or simulated episode retains the workcell registration used
at collection time.

The Studio catalog derives its visible board label from the displacement and
its asset revision from all poster source hashes, including the capture config.
This makes a config-only workcell change visible to collaborators after they
pull the tracked generated assets.

## Verification

| Check | Result |
| --- | --- |
| Current Studio catalog | `operator_updated_chess_workcell_v2`; center `[0.04, -0.093]`; label `72 mm robotward`; asset revision `797152c9` |
| Live MuJoCo scene | Board world position `[-0.0950498637, 0.464815956, 0.783883941] m` |
| Frozen v1 registration | Resolves independently to table-frame center `[0.04, -0.165] m` |
| Current scripted grasp probe | PASS; tan pawn C8 rise `0.093782 m`; lift contact fraction `1.0` |
| Python suite | PASS; 67 tests and 10 subtests |
| JavaScript syntax and diff whitespace | PASS |
| Browser inspection | Robots card shows `72 mm robotward`; interactive 304-state replay loads; no browser logs |

The repo-wide Ruff run retains one unrelated pre-existing unused `Path` import
in `tests/test_act_pick_place.py`; all files changed for this registration pass
Ruff.

## Proof boundary

This is an operator-measured workcell update, not a new calibrated-camera or
hand-eye estimate. It does not rewrite prior episodes, traces, overlays, or
receipts. Any old replay whose manifest revision does not match the current
scene remains historical evidence rather than being silently re-registered.
No camera, serial bus, servo, or physical-motion path is opened by this update.
