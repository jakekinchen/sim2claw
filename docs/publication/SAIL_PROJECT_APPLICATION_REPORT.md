# SAIL project application: retained pawn transport and grasp retention

Date: 2026-07-22
Proof class: `retrospective_action_frozen_simulator_mechanism_diagnostic`

## Verdict

The completed Phase 1 SAIL/ClawLoop system was applied to all 31 items in the
retained evidence compilation and, in the executable pawn lane, to all 11
action-frozen simulator episodes. The bounded contact-model campaign is a
terminal negative for grasp repair and simulator promotion, with real
observability and diagnostic metric gains.

No tested composite improves the frozen task counts beyond 4/11 lifts, 1/11
lift-and-transport outcomes, and 0 strict successes while also satisfying the
trace and collateral gates. Training, simulator promotion, physical contact
calibration, and robot authority remain closed.

## What caused the visible C2-to-C1 drop in this simulator

The action array is byte-identical at SHA-256
`402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
The gripper command remains closed and the simulated gripper joint does not
open. Bilateral contact is lost at source frame 323, 78 frames before intended
release.

The load-bearing witness resolves the apparent contradiction:

- the moving side contacts through the modeled rubber sleeve;
- the fixed side contacts through rigid `left_fixed_jaw_box6`, not its rubber
  sleeve;
- at lift onset the fixed side is on the pawn head sphere while the moving side
  is on the upper-collar ellipsoid;
- both sides migrate onto the head sphere as the opposing-normal score falls
  from about 0.96 to 0.29 and the load-bearing pair's minimum simulated normal
  force falls from about 12.6 N to 0.28 N;
- these forces are MuJoCo constraint diagnostics, not calibrated physical
  measurements.

The fixed rubber sleeve is centered too far distally to enter this replay's
contact witness. Moving it across three bounded placements makes the simulated
rubber representation more symmetric but regresses the sentinel consequence
vector. The evidence therefore localizes a simulator geometry inconsistency
and surface-migration failure; it does not identify the physical rubber shape,
friction, or compliance.

## Contact-model campaign

The three declared sentinels screened 12 total composites, including baseline:

- Newton baseline;
- no-slip iterations 1, 5, and 10;
- pyramidal versus elliptic friction cones;
- rubber contact dimensions 3, 4, and 6;
- CG and PGS solvers;
- three fixed-sleeve placements spanning the relevant distal rigid
  primitives.

Higher scalar sliding friction had already been falsified as a single fix. The
new no-slip, alternate solver, cone, and corrected-sleeve probes either regress
lift/transport, violate the trace guards, or become numerically unstable.

`rubber_contact_condim=4` was frozen before the eight previously opened
evaluation episodes were run once. Across all 11 episodes it adds one qualified
bilateral episode and one whole-base destination ending, improves mean final
target distance by 15.5%, and reduces mean post-grasp slip by 6.5%. It is still
rejected because:

- lift-and-transport remains 1/11 rather than the diagnostic minimum 2/11;
- strict successes remain 0/11;
- full-set EE RMS is 11.647 mm, above the 11.457 mm guard;
- C2 contact loss moves nine source frames earlier; and
- C2 slip reduction is 7.7%, below the 10% mechanism threshold.

These are sensitivity gains, not an admitted task or grasp advancement.

## Project-wide failure inventory

The accepted V3 baseline has 10 explicit failure classes:

| Failure | Episodes |
| --- | ---: |
| terminal destination containment | 11 |
| wrong-piece robot contact | 8 |
| no 40 mm lift | 7 |
| terminal upright | 6 |
| collateral displacement | 5 |
| terminal settle | 3 |
| no transport while above lift gate | 3 |
| no bilateral contact | 2 |
| no qualified pinch | 2 |
| destination entry hidden below instantaneous lift gate | 2 |

This inventory shows why contact tuning alone cannot produce strict success.
The best C2 replay also touches the wrong D1 pawn and displaces collateral by
254 mm. Those path/scene failures occur independently of the selected pawn's
eventual grasp retention.

## Task-metric gain

The frozen evaluator and original `maximum_transport_progress_after_lift`
metric update only while the pawn is currently at least 40 mm above its start.
The new secondary `post_first_lift_task_diagnostic` observes the remainder of
the episode after first reaching 40 mm without changing any pass/fail gate.

It reveals that C2, D2, and F2 all enter the whole-base center-distance region
after first lift while still bilaterally grasped. D2 and F2 enter after
descending below 40 mm, so the old instantaneous-gate metric hid those
task-oriented consequences. Their maximum targetward progress after first lift
is 94.6% and 88.0%, respectively, versus 41.9% and 10.1% under the old metric.

This is an admitted observability improvement only. It does not revise the
frozen evaluator or create additional task successes.

## Evidence and reproduction

- Campaign contract: `configs/sail/project_application_v1.json`
  (`1142884783ee198c0facb350cce0f65dca06df5d95de9330a5b13eafa9216013`)
- Candidate freeze: `configs/sail/project_application_candidate_freeze_v1.json`
  (`e1b96609770d9760952be084dc34800f0a4c7892384a8ac78d20d61e4338a834`)
- Application receipt: `outputs/sail/project-application-v1/receipt.json`
  (`a2345ac50c8de15905a0ef1ecc03bf7b8803cb49fca27ada5874ce6037fdedf8`)
- Failure inventory: `outputs/sail/project-application-v1/failure_inventory.json`
  (`cd36e705d887a3a6173c59cc0406c14bd665bb68930f005609d5e7b7f499a2aa`)
- Evaluator verdict: `outputs/sail/project-application-v1/verdict.json`
  (`9048da843ae28e7cd1a69d6e6651e73275076357585296ab43b07d14f02b7f20`)
- Read-only Studio surface: `/project-application.html`, with a tracked static
  manifest and publication receipt. The original Phase 1 SAIL page and server
  remain byte-identical to their frozen receipt.

Recompile the inventory and verdict without rerunning simulation:

```bash
uv run python scripts/compile_sail_project_application.py
```

The ignored simulator evidence must already be present and match all bound
SHA-256 values. The compiler fails closed on source, action, candidate,
evaluation, or artifact drift.

## Minimum evidence to reopen contact identification

Reopening requires measured metric vertical registration, per-episode pawn
centers, exact pawn dimensions and mass, the two-sided rubber collision profile
and jaw registration, and a new independently sealed physical replay set. A
new physical campaign still requires separately granted capture and motion
authority.
