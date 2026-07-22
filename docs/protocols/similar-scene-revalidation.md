# Similar-Scene Revalidation Protocol

The same SO-101 hardware is useful, but it does not make a recreated chess
scene the retired workcell. Unless the robot, servo calibration, gripper tips,
board identity, board-to-base transform, cameras, mounts, table/fixtures, and
control runtime are all independently matched, register the setup as a new
related workcell and preserve the old/new domains separately.

The machine-readable authority and collection checklist is
`configs/hardware/similar_scene_revalidation_v1.json`.

## Highest-signal first experiment

After a separate physical-motion authorization, collect five synchronized
empty-gripper open/close cycles before any task attempt. Record command-write,
bus-ack, joint-observation, current-read, and camera-capture timestamps. This
single control distinguishes the gripper's mechanical hard-stop/controller
signature from the loaded-closure proxy inferred retrospectively in the old
data.

Then collect three independently split task scenarios: interior vertical,
edge vertical, and horizontal. Measure new scene coordinates; do not reuse old
square coordinates as if the environment were identical. Include both success
and failure attempts, and freeze evaluator behavior before fitting.

## Evidence boundary

New measurements may validate whether the old event heuristic generalizes and
may support a new-workcell simulator/transfer claim. They do not retroactively
turn the retired recordings into instrumented contact data, nor can new-scene
success be relabeled as validation in the old physical environment.
