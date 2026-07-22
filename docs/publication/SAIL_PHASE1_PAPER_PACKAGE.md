# SAIL/ClawLoop Phase 1 Paper Package

**Frozen:** 2026-07-22

**Campaign:** `sail-clawloop-phase1-publication-v1`

**Proof scope:** synthetic benchmark, retained retrospective evidence,
prospective simulator evidence, governed agent campaign, and learned-policy
simulation only. No new physical observations or transfer claim.

## Result in one paragraph

Phase 1 implements SAIL as a deterministic, receipt-gated structural
real-to-sim loop and closes the hardware-free methods result. On eight disjoint
seeded sealed fault families, deterministic SAIL reaches 0.75 mechanism-family
top-1 accuracy versus 0.00 for parameter-only calibration, 0.50 for sequential
no-revisit calibration, and 1.00 for the privileged full-batch oracle. Its
influence precision/recall are both 0.818, it reaches threshold in eight probes
and 16 simulator evaluations, and its sparse graph path recomputes 11 affected
decisions versus 64 for full-batch-style baselines. In the dedicated GOLD-10
case, sparse loop closure recomputes 2/8 decisions and matches full-batch score
within `5.29e-15`. Retained evidence remains a partial/terminal-negative case:
all ten mechanism-specific invariance checks are `not_evaluable`, the current
certificate stays at `TW-REPLAY`, data generation and policy selection remain
denied, the synthetic ACT candidate is terminal-negative, and GR00T is an
explicit compute-unavailable challenger. The governed provider comparison is
also not evaluable because Codex and Claude attempts were blocked before model
calls; the seeded deterministic-plus-agent fixture ties deterministic SAIL on
recovery while doubling simulator evaluations.

## Frozen research-question answers

| RQ | Phase 1 answer | Proof class |
|---|---|---|
| RQ1 structure recovery | Large descriptive seeded effect against parameter-only; directional against sequential. With only eight cases, the parameter-only paired risk difference is 0.75 (bootstrap 95% interval 0.50–1.00), raw sign-test `p=0.03125`, Holm-adjusted `p=0.34375`. | seeded sealed synthetic |
| RQ2 loop closure | Supported in GOLD-10: sparse 2/8 recomputation versus full 8/8 with effectively equal score. | seeded synthetic |
| RQ3 invariance | Partial seeded support: top-1 falls from 0.750 to 0.625 without invariance. Retained mechanisms remain not evaluable. | seeded plus retained abstention |
| RQ4 acquisition | Supported in the seeded fixture: 8 probes for deterministic SAIL versus 16 without structural acquisition. | seeded sealed synthetic |
| RQ5 agents | Terminal negative / not evaluable. The fixture adds no recovery and doubles evaluations; provider transports never made a model call and cannot be pooled. | governed agent plus seeded fixture |
| RQ6 TwinWorthiness | Kill-switch behavior is verified: diagnostics open, data generation/policy selection/physical canary/motion denied. Predictive validity for future physical harm remains not evaluable. | deterministic capability gate |

The small seeded case count is deliberate and visible. Confidence intervals and
effect sizes are primary reporting surfaces; no secondary comparison is called
significant after Holm correction.

## Required ablation inventory

| Ablation | Top-1 | Key consequence |
|---|---:|---|
| no residual phase alignment | 0.500 | loses timing/camera discrimination |
| no compensation debt | 0.500 | misses compensating two-fault cases |
| no mechanism plugins | 0.000 | collapses to parameter-only behavior |
| no influence discovery | 0.750 | recovery ties, influence F1 becomes 0 and recomputation rises to 64 |
| no invariance | 0.625 | loses context-specific discrimination |
| no loop closure | 0.500 | misses compensating histories |
| no structural acquisition | 0.625 | doubles probes/evaluations |
| no TwinWorthiness gate | 0.750 | recovery ties but false-promotion rate becomes 0.25 |
| deterministic only | 0.750 | 11 graph recomputations, 8 probes, 16 simulator evaluations |
| agent only vs deterministic-plus-agent | not evaluable / 0.750 | provider calls blocked; fixture adds no recovery and doubles evaluations |

These are seeded structural-fixture results, not physical mechanism or transfer
measurements. Missing provider outcomes are `not_evaluable`, not zero scores.

## Retained whole-episode statistics

The retained table uses 10,000 deterministic bootstrap resamples of the 11
whole episodes. Samples within an episode are never treated as independent.

| Channel | Mean RMSE | 95% whole-episode interval |
|---|---:|---:|
| shoulder-lift joint residual | 0.02320 rad | 0.02211–0.02430 |
| elbow-flex joint residual | 0.03811 rad | 0.03678–0.03954 |
| end-effector norm | 0.01147 m | 0.01108–0.01185 |
| aperture residual | 0.03941 rad | 0.03278–0.04638 |
| near-closed timing | 0.33160 s | 0.16779–0.57703 |
| release-onset timing | 0.35882 s | 0.12324–0.65917 |

These intervals describe one retired acquisition session and do not establish
independent-session or physical-population validity.

## Paper asset slots

The ignored, reproducible output at `outputs/sail/publication-v1/` contains:

1. architecture and authority boundary;
2. SAIL algorithm and belief-graph evolution;
3. benchmark recovery and probe efficiency;
4. compensation debt and sparse loop closure;
5. the same receipt-bound retained residual heatmap used by Studio;
6. TwinWorthiness ladder and current verdict;
7. governed agent cost/runtime terminal negative;
8. a table slot explicitly unavailable until the Phase 2 warm-start study; and
9. an optional downstream policy table carrying the ACT terminal negative,
   GR00T compute skip, and zero current-real comparisons.

Nine CSV tables, the claim ledger, proof-lane ledger, ablation matrix, retained
statistics, agent comparison, reproduction map, Phase 2 packet, and all seven
SVG figures are individually SHA-256-bound by the publication receipt.

## Claim boundary

The minimum publishable Phase 1 result is a methods contribution with a seeded
benchmark, governed agent terminal negative, retained case study, prospective
simulator predictions, and honest TwinWorthiness partial certificate. A policy
win is not required and is not claimed. Future related-workcell results must be
added as a separately frozen Phase 2 cohort; they cannot rewrite this package.
