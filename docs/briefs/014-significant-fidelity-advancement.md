# Brief 014: Significant action-frozen fidelity advancement

Decision: `ACCEPT RMS LANE; STOP AND CLOSE OUT`

Evidence anchor: `100` — the publication receipt binds the current baseline at
1.2956 degrees joint RMS, 12.936 mm EE RMS, 11/11 contact, 2/11 lift, and 0/11
strict success under byte-identical actions.

## Required outcome

Verify one significant advancement without changing policy action values:

1. RMS lane: at least 5% pooled whole-episode CV improvement from 1.2956
   degrees, with EE RMS no worse than 12.936 mm and no action-invariance breach;
   or
2. consequence lane: at least 6/11 lift-and-transport outcomes or at least one
   strict evaluator success, with unchanged actions and no newly regressed
   observable vector component.

## First slice

Diagnose the selected timing-plus-deadband residual by joint, stationary/moving
phase, direction, command gap, and pose. The elbow residual is currently the
largest per-joint component. Test only identifiable simulator response classes
before any broader contact sweep:

- independent lift/elbow deadband widths;
- bounded residual holding gain inside each deadband;
- joint-specific application delay only if residual timing evidence warrants
  it; and
- a gripper response model only if the recorded command/measured aperture trace
  identifies it.

Use four existing whole-episode folds. Freeze grids and selection constraints
before the formal campaign. The already-opened two-episode confirmation split
is regression-only.

## Stop and redirect conditions

- Reject candidates that require changed action bytes, post-policy target
  offsets, IK, clipping, assistance, or evaluator changes.
- Do not expand the frozen rubber-tip prior merely because the current evaluator
  fails.
- If RMS advances but consequence does not, report a trace-fidelity advancement
  only.
- If neither lane crosses its threshold, retain the terminal-negative contact
  identifiability verdict and name the next missing measurement.

## Executed result

The RMS lane crossed its frozen threshold. Fold-selected pooled joint RMS is
1.2118497 degrees, 6.461% below the 1.2955577-degree baseline, and EE RMS is
11.3437 mm, 12.312% lower. Every validation fold improves and action hashes are
unchanged. A 10,000-replicate paired whole-episode bootstrap gives a
4.398--8.540% 95% interval for relative joint-RMS improvement.
That interval is conditional on the 11 retained episodes from one acquisition
session and does not establish independent-session generalization.

The accepted model class adds a bounded elbow load response only inside the
servo deadband. Its -1.5 coefficient is exactly the frozen lower search bound,
so the magnitude is not identified and will not be chased by a post-hoc grid
expansion.

The consequence lane does not pass: contact is 11/11, lift is 1/11 versus the
2/11 baseline, destination-inside endings are 2/11 versus 0/11, and strict
success stays 0/11. Accept trace-fidelity advancement only; keep grasp,
composite, training, policy, and transfer promotion closed.
