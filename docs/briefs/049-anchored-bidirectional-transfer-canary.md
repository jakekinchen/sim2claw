# Brief 049: anchored bidirectional transfer canary

Status: complete; sign-reversed follow-on is ready but not execution-admitted
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
The final five 20 Hz encoder samples must each remain within the reviewed
gateway return tolerance on every joint; a single final sample is insufficient.

This result never promotes the provisional joint transform, camera
registration, evaluator, policy, task success, or physical task capability.

## Stop conditions

Stop without motion if any hash, hardware identity, calibrated range, current
pose tolerance, camera owner, prebound simulation trace, review field, or
contact classification differs. Stop safely with torque off if any camera
stalls, the gateway modifies an action, a rate/clamp/stall flag appears, or the
arm fails to return within the reviewed tolerance. Do not escalate to a pawn
  move or broader trajectory in this campaign.

## Follow-on calibration queue

The v2 diagnostic passed its broad safety envelope, but it is not a parity
pass. Simulation produced `2.0301017 deg` shoulder-pan peak-to-peak versus
`1.0549451 deg` physically. The `0.9751567 deg` disagreement consumed all but
`0.0248433 deg` of the frozen `1 deg` bound and overpredicted measured
excursion by `92.4%`. Prebound and postexecution metrics are two evaluations of
the same physical trace, not independent transfer trials.

Do not reopen the non-unique latency/gain/damping sweep. Its admitted latency
is `0.082581 s`, while near-equivalent prior fits spanned latency
`0.0541–0.0826 s`, gain `0.5–1.5`, and damping `0.5–1.775`.

The next sole writer has this bounded queue:

1. Add one shoulder-pan-only stateful play/deadband parameter in the simulator
   actuator, never in the action path:
   `z_i = max(u_i - b, min(u_i + b, z_(i-1)))`.
2. Freeze the one-parameter family before fitting. Keep the admitted latency,
   gain, damping, geometry, transforms, contact, action bytes, and evaluator
   ownership unchanged.
3. Fit only `b` on historical execution-v4. Current-pose v1 is excluded from
   formal fitting because its terminal return failure intentionally produced
   no execution receipt. A read-only proxy that included v1 selected
   `b=0.4301 deg`; this number remains a post-hoc starting point, not an
   admitted parameter.
4. Use v2 only as retrospective validation because it motivated the family.
   Require at least `50%` pan-RMSE reduction, pan maximum absolute error at
   most `0.40 deg`, peak-to-peak disagreement at most `0.25 deg`, identical
   source and mapped action hashes, no clipping/contact/limit change, and no
   other body-joint RMSE worsening above `0.02 deg`.
5. If the retrospective gate passes, freeze and independently review a
   current-anchor, sign-reversed `+-1 deg` triangle with the same one-second
   hold as a genuinely prospective held-out packet.
6. Stop once that packet and its baseline/candidate predictions are physically
   ready. Do not execute it in this campaign.

## Follow-on closeout

The preregistered one-parameter diagnostic selected `b=0.40 deg` using only
historical execution-v4. On v2 retrospective validation it reduced pan RMSE
from `0.3354721 deg` to `0.1359543 deg`, reduced maximum pan error from
`0.7142274 deg` to `0.3147316 deg`, and reduced peak-to-peak disagreement to
`0.1752865 deg`. All tighter gates passed, but this remains self-scored
retrospective evidence with no parameter promotion.

The held-out negative-first packet is frozen at
`runs/anchored-transfer-canary/fresh-current-pose-v3-sign-reversed/physical-canary-packet.json`.
Its exact 57-row action SHA is
`f4692749e5108e1b213ae0bbd536cf393193faecd86051a350c6e09d18bb294b`.
The baseline and fitted prediction SHAs are respectively
`bcc1976ed69b1f5ea6503fd3f35b397e3666392982f551c76fe65bdcf6b270b0`
and
`2a51d3f7ce8c0866f46882f4343c04971e13b1fc4b01d14b3ee9bc96e7382b97`.

Independent decision
`safe-canary-audit-20260727-heldout-sign-reversed-readiness-v1` approved
readiness only. No execution artifact exists, `physical_packet_execution_admitted`
remains `false`, and no physical command was issued during this follow-on.
