# Reviewer decision 045: Q06 fresh RGB scene gate

Date: 2026-07-27

Decision: `ESCALATE`

Evidence anchor: `100`

## Acceptance audit

- Fresh C922 scene captured without motion: pass.
- C922, D405 color, and Pi IMX708 RGB availability: pass.
- Metric depth dependency absent: pass.
- Reset sparse layout and upright/empty-destination state observed: pass,
  RGB-only claim.
- All ten preregistered cases evaluated under the frozen gate: pass.
- Required route clearance `88.9 mm`: bound to Q05.
- Best clearance for every frozen case `44.45 mm`: fail.
- Action compilation and gateway construction suppressed: pass.
- Counted motion and physical attempts: zero.
- Case expansion, scene manipulation, and post-observation gate weakening:
  not authorized.
- Safe task-local alternatives: exhausted.

## Finding

Q06 cannot admit a safe case. Every frozen route begins or ends one square
from an excluded reset-layout pawn. The geometric contradiction is
deterministic and is corroborated by the fresh C922 layout frame. An action
cannot lawfully be compiled under Q07.

This is a queue-authorized human-only scene-reconfiguration/safety boundary,
not the F3 repeated-mechanism boundary. There were no physical attempts and no
physical or bidirectional task result.

## Routing

Q07-Q12 are not authorized. Route directly to Q13 to package the terminal
boundary, then perform Q14 closeout and Q15 advisory review. Preserve exact
`0/0` per-direction denominators and `0/10` total attempts.
