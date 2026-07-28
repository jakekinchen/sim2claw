# Executor Session 040 - C2→C1 exact REAL→SIM

**Date:** 2026-07-27

## Physical executor result

The one reviewed C2→C1 physical attempt consumed the exact full transaction
hash
`ecf950ea9252c3e6c1b7e4b5df333dfcb75eb2b5bff43ee5d4d1a7b6154828ed`.
Setup rows 0-359 remained outside the counted task boundary. Counted rows
360-1060 consumed the exact float64 hash
`0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da`.

All 701 counted rows were issued. Persisted requested and gateway-sent arrays
match, with zero safety clamps, zero rate-limited rows, zero bus retries, and
no IK, offsets, repair, assistance, or suffix. The executor stopped before the
terminal camera hold because the final lift residual was `4.803839°` and the
wrist-flex residual was `-3.397246°`, beyond the reviewed target tolerance.
Torque was disabled on close.

## Physical consequence

The task cameras enclosed the physical action with zero material drops, but
the stopped arm occluded the terminal task squares. A later independently
reviewed setup-only reveal preserved the task bytes and moved no pawn. Its
C922 frame shows C1 empty of an upright pawn and the selected C pawn
displaced/toppled near C2.

Physical verdict: `task_failure`.

## Exact physics leg

The exact counted float64 bytes were mapped once with transform hash
`72812016bfa9dba2ba97fe448724394ad290a2b22458177bcbdec95aae0689e6`.
Every mapped control was inside the model bounds. The simulator started from
the physical counted-task robot observation and an upright stationary C2 pawn,
then applied five `0.005 s` physics steps per 40 Hz action with no clipping,
retiming, latency, state forcing, or post-action settling suffix.

The simulated pawn had:

- maximum rise `0.0 m`;
- final C1 center error `0.044450008 m`;
- no selected-piece jaw contact;
- final upright cosine `0.999999999`;
- no physics task success.

First physics divergence: the mapped gripper trajectory never established
selected-pawn contact.

The frozen pawn evaluator v3 owns float32 actions at 20 Hz, ten physics steps
per action, and an evaluator-privileged state ledger. It cannot promote the
new float64/40 Hz contract. Applying its consequence gates as a
non-promotional negative check also fails minimum rise and final XY.

## Closeout

- REAL task success: false.
- Physics task success: false.
- Exact canonical action identity: true.
- Evaluator-owned REAL→SIM success: false.
- SIM→REAL authorization: false.
- Follower torque at final read: off.
- Repo-owned camera/gateway processes: none.

Accepted proof class:
`exact_action_real_and_physics_terminal_negative_no_transfer_authority`.
