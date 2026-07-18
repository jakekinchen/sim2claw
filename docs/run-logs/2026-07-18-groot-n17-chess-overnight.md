# GR00T N1.7 Dynamic Chess Overnight Campaign

Date: 2026-07-18 America/Chicago

## Frozen campaign

- User ceiling: `$50.00`.
- Worker count: exactly one.
- Selected type: `massedcompute_A100_sxm4_80G_DGX`, quoted `$1.656/hour`.
- Time cutoff: 08:30 CDT or budget ceiling, whichever occurs first.
- Projected 00:32--08:30 compute: `$13.248`.
- NVIDIA source: `n1.7-release` / `23ace64f17aa5015259b8609d371eb61a357c776`.
- Base model: `nvidia/GR00T-N1.7-3B`.

## Local foundation

The first full-board expert carried the a8 rook to b6 within 8.6 mm but the
arm displaced the black queen by 0.888 m. That trajectory is a counterexample,
not training data. The frozen first curriculum therefore keeps the rook and
king visible and parks all other pieces during reset.

The accepted split contains 24 training demonstrations for rook a8 to b6,
king e8 to d6, and king e8 to c6. Four held-out demonstrations cover unseen
rook a8 to c6 and king e8 to e6 cases with zero training rows. All 28 scripted
consequences passed lift, placement, upright, settled, clearance, distractor,
contact, ownership, and assistance gates. `uv run pytest -q` passed 15 tests.

## Evidence boundary

These are synthetic scripted demonstrations, not learned-policy results. The
dense reward is diagnostic and cannot promote. NVIDIA loader/server,
post-training, and closed-loop learned-policy results remain pending.

## Spend ledger

| Event | Local time | State | Accrued/projected spend |
| --- | --- | --- | --- |
| Initial inventory | 00:30 CDT | `workspaces: null` | `$0.00` |
| Campaign frozen | 00:32 CDT | no worker provisioned | `$0.00` |

Final provision, training, preservation, deletion, and empty-inventory rows are
appended only after observed events.
