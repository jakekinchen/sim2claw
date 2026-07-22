# SAIL Golden Evidence Rules

The 25 SAIL golden cases freeze failure, abstention, authority, and structural
recovery behavior before prospective experiments. A changed implementation may
not rewrite a golden expected result. Any semantic change requires a new schema,
contract, or benchmark version and reviewer rationale.

Rules:

- Missing observations are represented by availability masks and
  `not_evaluable`; they are never imputed as zero or pass.
- Action identity includes shape, dtype, ordering, bytes, SHA-256, and
  application times. Numerically similar actions are not identical evidence.
- Retrospective, prospective simulator, synthetic, learned-policy, physical
  read-only, and physical-task claims remain separate.
- Agents, trainers, and diagnostic rewards cannot promote artifacts.
- Sealed bytes are evaluator-owned and unavailable to agent tools.
- Failed prefixes, failed suffixes, rejected candidates, and held-out hardware
  trials contribute zero training rows.
- A certificate with changed bytes grants no downstream capability.
- TwinWorthiness never grants camera, serial, servo, gateway, or motion
  authority.

Tracked fixtures are small and freshly authored. Retained evidence is bound by
digest and regenerated into ignored directories; it is never copied from the
archive or committed as a generated campaign.
