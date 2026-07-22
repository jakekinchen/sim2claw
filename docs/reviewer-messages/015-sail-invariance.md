# Reviewer Message 015 - SAIL Mechanism-Specific Invariance

Decision: `CONTINUE`

Evidence anchor: `100`

P1-08 meets its acceptance criteria. Invariance is plugin-declared and
whole-episode grouped; seeded stable behavior passes, context-specific behavior
fails universality, insufficient coverage abstains, and the retained inventory
issues zero unjustified passes.

## Acceptance review

- Plugin-specific invariant parameters and allowed covariates: pass.
- Eight-family context vocabulary: pass.
- Whole-episode grouping and no episode leakage: pass.
- Stable seeded control: pass.
- Context-specific seeded mechanism rejected as universal: pass.
- Single-context case returns `not_evaluable`: pass.
- Retained missing observables/posteriors/context remain `not_evaluable`: pass.
- Retained invariance pass count: zero, as required by available evidence.
- GOLD-11: pass.
- Complete SAIL tests: 93/93 pass.
- Complete regression gate: 700 tests and 328 subtests pass; three expected
  environment/optional skips remain.

## Verification verdict

The ignored output contains verified seeded invariance controls, a retained
coverage inventory, and config/compiler/source/output-bound receipt. No
retained physical mechanism is declared invariant or identified, and no
simulator, training, policy, capture, motion, or transfer authority is granted.
P1-09 may begin as the sole active milestone.
