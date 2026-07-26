# Slice Brief 043 — Pi Proximal-Tag Constraint

## Required outcome

Add an independently observed proximal-link constraint to the existing fixed
IMX708/tag-2 bundle before fitting any additional joint, camera, or simulator
parameter.

## Frozen pose roles

The pose targets and roles are frozen before the first new physical capture:

| Pose | Role | Target body joints (degrees) |
|---|---|---|
| G | training candidate | `8, -90, 76, -95, -90` |
| H | second heldout | `10, -60, 90, -95, -30` |
| I | training candidate | `30, -70, 82, -95, 50` |
| J | training candidate | `-5, -58, 68, -95, -50` |

The gripper target remains the existing empty-gripper value
`3.0878859857482186%`. Pose D remains the first heldout and is never used for
fitting. Pose H is captured with the other observations but remains sealed
until the candidate family is frozen from training poses A/B/C/E/F/G/I/J.

## Capture and admission

- Every motion uses the reviewed follower-only gateway with exact float64
  actions consumed byte-identically by the CPU preview and hardware path.
- A fresh torque-off preflight must pass before compilation and execution.
- A separately reviewed setup-recovery anchor may clip only the known
  gravity-sagged start back into calibrated limits, with at most `10 degrees`
  per body joint.
- C922, D405, and one IMX708 still are captured during the torque-on final
  hold. Shutdown must leave follower torque off.
- A training candidate is admitted only when OpenCV tag36h11 detection returns
  exactly one full-corner ID 1 observation and exactly one full-corner ID 2
  observation. Failed or ambiguous detections remain rejected diagnostics.

## Frozen model-selection gate

Fit one joint model with tag 1 bound to the CAD-keyed proximal body and tag 2
bound to the already used distal body. Screen the proximal body identity from
training observations only. Do not add distortion or unconstrained camera
terms in response to heldout error.

Promotion requires both pose D and pose H to pass the same frozen per-pose
corner-error gate of at most `8 px RMSE` and `15 px maximum`, without any joint
offset reaching its `±8 degree` bound. Pose D is scored on its automatically
decoded distal tag; pose H is scored on every uniquely decoded follower tag.
Otherwise publish a rejected diagnostic and promote nothing.

## Evidence and stop boundary

This slice is physical static calibration data, not task or transfer proof. It
does not authorize policy, teleoperation, geometric task commands, training,
or simulator-parameter promotion by the acquisition code. Stop before any
policy/task motion even if calibration readiness improves.
