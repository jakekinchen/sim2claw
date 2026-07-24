# Four-hour HIL identifiability and sim-to-real closure

Date: 2026-07-24

Status: physical, simulator, offline-analysis, and Studio evidence are frozen.
The minimum wall-clock window and exact-head verification still own terminal
closeout.

## Proof result

This transaction produced four one-attempt
`physical_hil_unloaded_joint_observation` packets, one independently evaluated
`action_frozen_hil_simulator_comparison`, and two deterministic offline trace
diagnostics. It did not produce a pawn-task success, calibrated-force result,
canonical simulator improvement, training row, policy result, or
physical-transfer result. The strict physical task score remains `0/11`.

The owner authorized the four bounded tests and guaranteed that no person or
object would enter the chessboard workcell. Every packet still passed through
the identified follower/calibration, torque-off, camera, action-envelope,
telemetry, return/hold, and evaluator gates. There were no retries.

## Physical packet results

| Packet | Requested / actual span | Best sample alignment / RMSE | Raw current p95 / max | Camera evidence | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| `HIL-GRIPPER-05` | 20.000° / 19.596° | 0.150 s / 0.624° | 2 / 3 | C922 555 frames; D405 93 | admitted unloaded measurement |
| `HIL-SHOULDER-LIFT-22` | 22.000° / 21.626° | 0.150 s / 0.636° | 2 / 3 | C922 372; D405 62 | admitted unloaded measurement |
| `HIL-ELBOW-FLEX-22` | 22.000° / 18.374° | 0.200 s / 1.822° | 17 / 21 | C922 378; D405 64 | rejected: 11 rate-limited and 6 stall-warning samples |
| `HIL-WRIST-FLEX-30` | 30.000° / 28.747° | 0.150 s / 0.463° | 3.5 / 5 | C922 373; D405 failed finalization | rejected: wrist coverage |

All four actions returned to the recorded source start within the frozen
packet evaluator gate. Maximum bus retries were zero and follower torque was
off after every attempt. The sample alignment values above are 50 ms
sample-quantized command-to-position alignments, not actuator-application
latency. Raw current is an uncalibrated motor register, not torque or force.

Campaign state:

- path: `runs/current-100mm-hil-identifiability-20260724/campaign_state.json`
- SHA-256:
  `b364aae639bb753b58216177386aa6ae93d43dad5462c8dd1a3d33dd44330858`
- accounting: `4 / 4` attempts, `2` admitted, `2` rejected, `0` retries,
  `0` evaluator/provider calls

Per-packet action SHA-256:

- gripper:
  `30e7addea882fe94523e88d2c9135f182afe023f4621672650f0f4f72a9d747c`
- shoulder lift:
  `a61706c3bb36bb10c1ebcb758a9343a99d5dd69193c8e26a757b409137dad1b8`
- elbow flex:
  `efd0cfb10f8e57d117d1ea6fd6c6ada85411703d9a87959314e5a1fa74e70230`
- wrist flex:
  `58894fd504feaad80ee625f0a9612641b2ceb28a5ca71f0ac32f2e6d52c4b2b6`

## Frozen simulator comparison

The sole simulator follow-up used the admitted 201-by-6 shoulder action twice,
byte-identically. Its candidate value came from the pre-existing follower
endpoint calibration; it was not fitted from these HIL results.

- shoulder RMSE: `4.289228° → 1.280866°` (`70.14%` reduction)
- elbow RMSE: `5.223° → 5.734°` (`+0.510566°`)
- frozen maximum per-joint regression: `0.25°`
- strict task/EE consequence: unavailable
- result:
  `diagnostic_shoulder_range_external_tie_or_loss_no_promotion`
- simulator budget: `2 / 2` replays, `0` retries, `0` provider calls
- raw comparison SHA-256:
  `c0b9d1da684353ccffe3caceac04a1c6a14904a414d4379626a08acac4e0ef7b`
- evaluation SHA-256:
  `bfd126fde51cf3d3a858a47689a9754aa986bb64268871646c47347f13a6e2ec`
- receipt SHA-256:
  `f98137e9f83d0001cc312a10994fa60928a1e51f71b38c620d6b5fa765b7a5ad`
- embedded receipt digest:
  `38e0598a642ed19480d1caf01ca4661e85a85e6f936ac8d3958dd20e5e42d8ec`

The target-channel reduction is a rejected diagnostic sensitivity. The
non-target regression and absent strict consequence close parameter,
posterior, calibration, and score changes.

## Offline trace decomposition

The v1 report measured directional residuals, plateau sufficiency,
single-packet return residual, and fresh-current association. No packet passed
the frozen scale/offset gate. The elbow raw-current p95 of 17 and six stall
warnings were distinct from the other packets, but remain diagnostic.

The separately versioned v2 report disclosed that v1 results and an
owner-requested GPT-5.6 advisory were visible before its methods were frozen.
The advisory is not evaluator evidence. It then separated requested from
applied action tensors, emitted all lag candidates at the native 50 ms
resolution, partitioned residuals, and built a six-joint excitation and
identifiability matrix for every packet.

The elbow chronology is:

1. gateway rate limit at sample `59`;
2. first peak fresh raw current at sample `68`;
3. velocity collapse under greater-than-3° tracking error at sample `83`;
4. stall warning at sample `99`.

Its pre-rate-limit window selected a `0.35 s` sample alignment with `0.123°`
RMSE; the full fault-contaminated trace selected `0.20 s` with `1.822°` RMSE.
This is index-aligned correlation that separates controller intervention from
the full observed response; it is not causal load, force, or latency proof.

Requested-versus-applied byte identity:

- shoulder lift: identical;
- gripper: non-identical in 13 samples with no gateway rate-limit flag;
- elbow flex: 11 non-identical, 11 rate-limited samples;
- wrist flex: 6 non-identical, 4 rate-limited samples.

Consequently, the physical packet action hash is explicitly the requested
action identity. Applied actions have separate content hashes. The
action-identical simulator comparison remains a different proof lane.

Offline artifacts:

- v1 report SHA-256:
  `a62481c1dac5930306e26efd847c39e87873c37eeabb96e8cef98194c6c2e698`
- v1 receipt SHA-256:
  `fc588df9e94c8a7bbdfb4c61cbbf959e07c1048d6dc0d56da13c03ac3e68e10c`
- v1 embedded receipt digest:
  `311d0c023d73b4b60a6186353ea375d04634f46cc2d14e2143694c57c7c35e36`
- v2 report SHA-256:
  `e4fbc956153f0bd1c68981adfc87cfd90984402f5bcdba0e48ce12f47d19e7e5`
- v2 receipt SHA-256:
  `523c5a52648682a674c086e1326412bef0317cd881ce8cba10cc0d56311aeb5f`
- v2 embedded receipt digest:
  `ccf87f0c960000ba5912f75d56ea0d17c2dbc7dab99fac5b7656a6d52f951af8`

Both reports rederive byte-identically. They used zero additional physical
attempts, simulator replays, or evaluator/provider calls. The single external
browser advisory was owner requested, method-design only, and is accounted
separately.

## Studio and future observability

The four receipt-verified packets appear in Replay with the available C922 and
D405 streams. Twin fidelity requires the selected requested-action hash to
match the publication; no episode-ID fallback is allowed. Its gap map exposes:

- observed, missing, and failed geometry, kinematics, action/timing,
  contact/compliance, actuator/load-path, and task/EE consequence states;
- requested-versus-applied action counts and the elbow fault chronology;
- sample alignment without relabelling it actuator latency;
- directional and return residuals without relabelling them backlash or reset
  drift;
- raw current without relabelling it force;
- the rejected shoulder sensitivity and elbow regression;
- exact next timing, camera, current-calibration, excitation, reset, and
  consequence prerequisites.

The reviewed physical gateway now records ordered same-process host timestamps
around leader read, command call, follower-position read, and refreshed current
read for future packets. It explicitly records that actuator
application/acknowledgement and synchronized device clocks remain unavailable.
This does not retroactively add fields to the four frozen packets.

Desktop and phone-width Studio checks verify the read-only drawer, responsive
layout, keyboard close/focus return, stream switching, video seeking, 180°
C922 presentation rotation, and no console errors. Generated exact-head
receipts, rather than a post-verification tracked edit, own the terminal test
observations and counts.

## Remaining prerequisites and authority

Still missing:

- actuator application or acknowledgement timestamps;
- device-synchronized position/current timestamps;
- camera PTS, exposure, drop, and duplicate counters;
- calibrated current zero/scale and torque provenance;
- at least three distributed levels, multiple speeds, and repeated clean
  traversals per direction;
- repeated reference reset trials;
- known load/contact state and calibrated force;
- strict pawn-task and end-effector consequence.

Training, promotion, another parameter family, another replay, task-score
change, physical-transfer authority, paid compute, Brev, provider-backed
evaluation, public push, VideoSim work, and unbounded robot motion remain
closed.

## Verification

The tracked closeout freeze is prepared before the terminal proof sequence:

- focused HIL/gateway/publication/Studio tests;
- SAIL automatic fast-contract, synthetic-golden, and integration tiers;
- one full repository suite;
- unchanged S2 eleven-file hash set and
  `1 event / 4 replays / 0 measurement trials` before and after every tier.

The generated exact-head verifier receipts own the final commands, counts,
commit/tree identities, and outcomes. This tracked log is not edited after the
terminal full-suite proof begins.
