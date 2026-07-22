# SAIL Structural-Discrimination Acquisition Run Log

Date: 2026-07-22

Milestone: P1-09

Proof class: deterministic predictive acquisition and unexecuted intervention plans

## Frozen identities

- Configuration: `02bc19d8d8851fdc0199f8cb70025fea589260a36aac6cf480625b1f592e3411`
- Ranking: `a59b2a9b242c35425515973edee9807a0dfdd7c8bd4daa385b12b1cf71e7fb56`
- Ranking digest: `cc244a4ca23c5de57a84ffcffe1d530f3e6e57a9598ded4df6415afbfcc8665c`
- Intervention plans: `53ce9fbeffdf8adeabd62e6c1ead685173a78a460566e76de2018a4f3130257f`
- Receipt: `9203137c954da58e1e0bbd3eaaf6674e0bb263af717abf86efe48e91fa322db6`
- Receipt digest: `2bccb25a967bbd2c0ed778bc50565cb1a4d6a154882c96234977064f116dce0e`
- Deterministic tree digest: `d5a6b54872f8f9db72f10a9fa023ed93938137fe2067313aedcb6454bdd21367`

## Result

- `sim_load_frequency_discriminator` wins the structural ranking at 0.8625;
  common-mode RMS scores 0.37375 despite larger predicted debt reduction.
- `sim_parameter_refine_load` separately wins parameter refinement at 0.8745.
- Random, coordinate, residual-magnitude, and uncertainty baseline regrets are
  0.29969, 0.48875, 0.48875, and 0.59125.
- Six sealed Intervention.v1 plans compile; two hardware plans are unavailable
  with zero trials/wall/provider/cost budgets. No probe executed.
- GOLD-12, 22 focused tests, 101 SAIL tests, and the full 708-test plus 328-
  subtest suite pass; three expected skips remain. Full duration: 1,236.23 s.
- Repeated output trees are byte-identical.

## Claim boundary

All scores are predicted acquisition values, not observed causal evidence. No
simulator, hardware, provider, training, or policy action executed or promoted;
source actions remain unchanged and Brev was not used.
