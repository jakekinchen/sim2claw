# Brief 049: anchored bidirectional transfer canary

Status: implementation freeze before fresh physical evidence
Branch: `codex/anchored-transfer-20260727`
Proof target: one prospective, action-frozen, shoulder-pan-only diagnostic
whose dynamic simulation trace is sealed before motion and whose physical
execution returns to its starting anchor.

## Inputs

- Phone video `/Users/kelly/Downloads/IMG_5431.MOV`, SHA-256
  `9baa9f37edbd9bb695588976808f5067b827c64a3ed580c5242b4df904699fa9`.
- Existing simulation canary and candidate manifest under
  `runs/physical_excitation/20260725-follower-only-v1/simulation-canary-v1/`.
- Existing exact physical canary execution-v4, retained only as retrospective
  evidence.
- New teleoperation recordings B5→A5 and D1→D2 plus the full-range capture,
  retained as physical source diagnostics. Their rate-limited samples are not
  exact-replay inputs.

## Frozen experiment

1. Read the follower through the reviewed gateway with torque off.
2. If necessary, execute only the existing bounded inward normalization for
   shoulder-lift and wrist-flex.
3. Compile a fresh 57-sample, 20 Hz, ±1 degree shoulder-pan packet relative to
   that normalized pose, including a frozen one-second final anchor hold. No
   old absolute packet may be reused.
4. Before review or motion, bind into the packet:
   - exact mixed-unit physical action bytes and SHA;
   - candidate manifest/config and provisional joint-transform SHAs;
   - complete CPU MuJoCo joint prediction and SHA;
   - evaluator contract and implementation/runtime identities;
   - unchanged-contact kinematic preview;
   - follower calibration and calibrated ranges.
5. Independently review the sealed packet. All acknowledgement fields must be
   literal booleans and the review timestamp must be timezone-aware.
6. Reproduce every preexecution binding immediately before gateway
   construction.
7. Record C922, D405 RGB, and Pi IMX708 video while executing the exact packet.
   Poll both camera owners before every action. Always close the gateway and
   leave follower torque off.
8. Compare physical encoders to the prebound simulation trace for sim→real,
   then replay from the actual measured initial state for real→sim. Preserve
   the original physical bytes; do no fitting, assistance, clipping, suffix,
   IK, or offset repair.

## Diagnostic bounds

The packet must hash-bind
`configs/evaluations/physical_canary_roundtrip_bounds_v1.json` before motion.
Both directions must satisfy every bound for the result to be described as
`prospective_diagnostic_bounds_satisfied_no_promotion`.

This result never promotes the provisional joint transform, camera
registration, evaluator, policy, task success, or physical task capability.

## Stop conditions

Stop without motion if any hash, hardware identity, calibrated range, current
pose tolerance, camera owner, prebound simulation trace, review field, or
contact classification differs. Stop safely with torque off if any camera
stalls, the gateway modifies an action, a rate/clamp/stall flag appears, or the
arm fails to return within the reviewed tolerance. Do not escalate to a pawn
  move or broader trajectory in this campaign.
