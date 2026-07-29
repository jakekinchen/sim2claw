# Executor log 061 — canonical seeded temporal V2 freeze

CC02 implementation now emits separate requested, mapped, sent, and applied
traces plus one ObservableEpisode.v2-min per action, plant path, and fixed reset
variant. Each episode includes simulator joint/link state, canonical board SE(2)
pawn state, contact, first motion, and outcome. Direct-versus-ZOH first
divergence is extracted with applied action ahead of downstream channels.

The implementation also checks whole-trajectory camera margin, maximum
excluded-pawn displacement over time, no-lift, contact/collision gates, and
the unmodified applied action's gateway rate compatibility. It never clips,
smooths, retimes, offsets, repairs, or rate-limits the evidence action.

The unintended full V1 test replay is quarantined by decision
`1693f5c6...`; its temporary outputs are not evidence. The V2 successor
inherits every outcome-relevant V1 field and is frozen at `ae31376f...`.

Validation before official execution:

- Temporal and observable focused tests: `14 passed`.
- Python compilation: pass.
- `git diff --check`: pass.

No camera, gateway, serial, torque, physical motion, or task attempt occurred.
The official V2 immutable output remains absent.
