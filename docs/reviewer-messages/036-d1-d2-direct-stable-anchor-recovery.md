# Reviewer message 036 — D1→D2 recovery v2 terminal safe stop

Decision: `STOP_SLICE_A_RECOVERY_TRACKING_NOT_QUALIFIED`

Evidence anchor: `100`

The packet was separately frozen and reviewed, CPU/fp64 preview passed, all
three RGB cameras enclosed the motion, all persisted requested/mapped/sent
arrays remained identical, and the executor stopped at the gateway's elbow
no-progress boundary. Torque-off, camera cleanup, unchanged board occupancy,
and no pawn/board/table contact are verified.

The fresh torque-off elbow is now inside its calibrated interval at
`101.670330°`, with `0.439560°` upper-limit margin and no clipping required.
However, the recovery completed only `263 / 481` rows and stopped after the
observed elbow remained `3.252747°` above its request for the one-second
warning interval. Exact recovery tracking therefore did not pass.

Do not retry or mutate this campaign. Do not freeze or execute the D1→D2 task
action from this partially recovered state under the current predecessor
contract. Slice B and Slice C are not admitted.

Accepted proof class:
`physical_recovery_terminal_safe_stop_in_range_anchor_elbow_stall_no_task_or_transfer_authority`.
