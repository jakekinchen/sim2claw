# Brief 033: SAIL project application and grasp retention

## Outcome

Use the completed Phase 1 system as an executable diagnostic loop over the
project's retained physical-action simulations. The immediate anchor is the
best C2-to-C1 replay, where the pawn reaches the destination region but slips
from an apparently closed grasp before intended release and happens to land
upright.

## Current reproduced fact

Under the accepted V3 parameters and the original action SHA-256
`402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`,
the moving-jaw contact disappears 78 source frames before the declared release
onset while both the gripper command and simulated gripper position remain
closed. Before loss, total simulated normal force, opposing-normal score, and
contact span collapse as the mean contact point migrates upward on the pawn.
These MuJoCo constraint forces are diagnostic only, not physical force
measurements.

The existing sliding-friction-2.0 result is not a fix: it improves average
retention and final target distance but changes neither lift nor transport
counts and violates the full-set end-effector guardrail. The next experiment
therefore discriminates solver creep, friction-constraint formulation,
compliance/load distribution, and contact-surface migration before considering
another bounded geometry family.

## Work products

1. An identity-rich trace naming each jaw geom, pawn collision surface, contact
   position and normal, constraint force, and deterministic load-bearing pair.
2. A project-wide SAIL inventory that distinguishes grasp loss, wrong-piece
   contact, collateral displacement, target containment, upright/release, and
   trace inconsistency.
3. Bounded action-frozen contact-model candidates on three declared sentinels.
4. A frozen-family evaluation over eight previously opened episodes, run once.
5. Evaluator receipts, Studio evidence, tests, and a final proof-boundary
   verdict.

## Acceptance and authority

The exact acceptance lanes, budgets, hashes, and stop conditions are frozen in
[`configs/sail/project_application_v1.json`](../../configs/sail/project_application_v1.json).
No outcome opens policy training, simulator promotion, physical calibration,
or robot authority unless a separate existing gate is satisfied.
