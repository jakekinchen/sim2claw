# C2→C1 prospective exact REAL→SIM terminal negative

Date: 2026-07-27

## Result

The C2→C1 campaign completed one physical task attempt and one exact-action
physics leg. Both task outcomes failed. This is useful first-divergence
evidence, not task replay or transfer.

| Gate | Result |
| --- | --- |
| Counted canonical float64 action | 701 × 6, hash `0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da` |
| Physical action identity | Passed for all persisted counted rows |
| Clamp / rate / bus retry | 0 / 0 / 0 |
| Physical terminal tracking | Failed |
| Physical C1 upright occupancy | Failed |
| Physics selected-pawn contact | Failed |
| Physics lift | `0.0 m`, failed |
| Physics final C1 center error | `0.044450008 m`, failed |
| Strict evaluator promotion | Not admitted; execution-contract mismatch and consequence failure |
| SIM→REAL | Forbidden |

## Evidence

- Physical receipt:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/stage-1/execution_receipt.json`
- Physical outcome receipt:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/physical_outcome_adjudication_receipt.json`
- Physics receipt:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/physics/exact_action_replay_receipt.json`
- Browser comparison:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/artifact/c2_c1_exact_real_vs_sim_terminal_negative.mp4`
- Comparison poster:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/artifact/c2_c1_exact_real_vs_sim_terminal_negative_poster.png`
- Artifact receipt:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/artifact/artifact_receipt.json`

The comparison appends a clearly labeled setup-only C922 reveal after the
synchronized task interval. That reveal is not part of the frozen task bytes.

## Current boundary

The C pawn is now displaced/toppled, and its metric pose is unavailable.
Starting another exact case would create an unmatched workcell initial state;
attempting an unmeasured robot reset would create an unsafe assisted pawn
action. All other retained adjacent-square demonstrations enter elbow geometry
already rejected by repeated mechanism-specific tracking evidence.

The next safe slice therefore requires the exact human scene reset and
follower elbow inspection in reviewer message 038. Until that intervention,
the benchmark has zero complete bidirectional cases and no valid empirical
transfer-rate claim.

Headline remains `TWIN FIDELITY 0/6` and `TASK SCORE 0/11`.
