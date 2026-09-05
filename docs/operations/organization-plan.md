# Repository organization and shared workcell plan

Owner authorization, 2026-09-05: organize both Sim2Claw and MicroDuck RL Genesis,
retain meaningful Git history, and grow toward a common simulated environment
in which an arm can eventually service the duck's battery. Local Mac GPU
compute is the default; bounded NVIDIA/Brev inference or validation is a last
resort when a named gate cannot be resolved locally.

This plan governs the new software organization/interoperability work only.
It does not reopen Sim2Claw's OR156 campaign, replace MicroDuck's ordered training
queue, alter frozen evaluator bindings, or activate robot hardware.

| Gate | Required outcome | State |
| --- | --- | --- |
| O1 Ownership and history | Workspace changes have scoped commits; unfinished staged training work has an explicitly incomplete recovery snapshot; native ownership remains intact | complete |
| O2 Repository navigation | Current entry points are distinguished from historical evidence; generated artifacts and protected source bindings have explicit homes | complete |
| O3 Shared workcell direction | Both repos retain the same staged actor/frame/clock/contact/compute plan with mechanical unknowns explicit | complete for declaration layer |
| O4 Verification and handoff | Scoped tests, metadata conformance, Git status and exact commits are recorded in both owners' handoffs | complete for software scope |

The coordination task owns Sim2Claw changes. The MicroDuck workspace and training
tasks own their respective commits and shared-document changes. Staging, moving
or deleting another task's active files is not a cleanup technique. Existing
receipt paths and immutable model/evaluator bindings are preserved.

Delivered: `ops git-health`, `ops workcell`, an artifact ownership map, current
versus historical navigation, a lightweight operations CI definition and
accepted-v1 digest tests. The map has 30 components and 48 relationships.
The owner selected existing battery hardware; the shared plan rejects an
assumed redesign, bypassed mechanical prerequisites and unbounded remote use.

Validation: 297 tests pass in an isolated Python 3.12 environment containing
only 12 lock-pinned inspection dependencies. The live workcell inspection
verifies ten direct source hashes; only its declaration gate passes. Seven
physics/mechanical/training gates remain unmet. See
`organization-verification.md` and `SHARED_WORKCELL.md`.

MicroDuck workspace commit: `a3b13cdb502d03d2d48253afa40adf4d7241bbab`.
Its shared-workcell mirror commit: `82d6d961fe829694db97d0b5bc9200c6fb030784`.
The training owner's staged changes were preserved during both scoped commits.
A staged-only recovery snapshot exists at
`codex/laser-dynamic-staged-snapshot-20260905`, commit
`dab881760269798e1324f324ba9bffbb23a5bf17`. It is incomplete work in progress,
not an accepted release; it excludes unstaged/untracked changes. Creating it
preserved the active main HEAD and real index bytes exactly. The active task
continues to own its release and later gait work.
