# Twin Fidelity Multilevel HIL — Terminal Partial

Date: `2026-07-24`

Baseline preregistration commit:
`6bc8745c079ef93197ccf038fa3f275e1569863f`

Proof classes:

- `preregistered_physical_hil_action_packet`
- `unloaded_physical_joint_response_measurement`
- `twin_fidelity_measurement_readiness`

This run is not task success, simulator promotion, contact calibration, or
physical-transfer proof.

## Frozen contract and live preflight

The six-packet contract
`configs/evaluations/current_100mm_hil_multilevel_v2.json` has SHA-256
`8dbe616efc5450e6a94115459b38d50f8aac959453a77db3a75d8baea80671bb`.
It froze one unloaded multilevel/multispeed packet per gateway joint, one
attempt per packet, exact start-relative envelopes, dual-camera admission,
controlled return, zero retries, and zero replacement packets.

Before the first attempt, the exact hardware and calibration identities
matched, follower torque was off, both cameras were discovered, all six
start-relative envelopes passed, and the campaign contained zero attempts. A
three-second dual-camera preflight and a 35-second camera-plus-serial no-motion
stress test both completed. These checks did not waive the per-packet camera
gates.

## Physical execution

Campaign state:
`runs/current-100mm-hil-multilevel-20260724/campaign_state.json`

Campaign state SHA-256:
`0e818d2228cf91dc4dd96dd44341795199b53eb1041245e869df7d327e2176b5`

Exactly six attempts ran. All six trajectories and controlled returns
completed, no gateway packet was retried, maximum bus retries were zero, and
follower torque was off after every attempt.

| Packet | Verdict | Action SHA-256 | Evaluation SHA-256 | Result |
| --- | --- | --- | --- | --- |
| Shoulder pan | admitted | `bd91045dd84ff25a8708a0e02be940a83f51e32d8a76df1da4af332796955a98` | `6cd8f38d7fecb77c6ebd1d9aa8534d0b2e101e59870ec5addfc429a4b796fea0` | 29.802° span; 0.527° max return error |
| Shoulder lift | rejected | `2f895cbfc7b89705acc2d492d54ca719b81fb7ffe49867d4b9d84b1f22bc9849` | `737cc66ff8eafeaba44a83af5d5e8520d90b89aecbf7f70a94061eb14892df2e` | robot/return complete; D405 completion and coverage failed |
| Elbow flex | admitted | `d2fdf8972bb1eb53046d5ecad4362feb806f35b40b8a84d4a4a331046938c77f` | `33cbf4c08cc202982944e24e807a1b341aca2e202422eddb66c0967ef04b474d` | 26.725° span; 0.176° max return error |
| Wrist flex | rejected | `a688cfc3b870386aed546735637b872a649b3396561b413f16e18cd7bfb50bde` | `7cd65d9a201bf3c1f8b978bef101bfff509312fc233bd7dc39343494888e24e4` | robot/return complete; D405 completion and coverage failed |
| Wrist roll | admitted | `143eb6311c0442363f937a4e4b6894d7827d418fa4cbb4f535eb8ec8104446c2` | `68b82eb6827a421907e7c28333e08c7a8d65fde16e90fb734f66eb644a2e2727` | 44.396° span; 0.440° max return error |
| Gripper | admitted | `5782669cd6b22be059992eb882090480a4efa2f59d23f837f06f50f828a658ee` | `321bb9b93a3a39d4779c3fcc23684f5af7cb9526ea978740bef92ec7a97ea4fb` | 44.299° span; 0.713° max return error |

The two rejected packets are preserved as diagnostic physical observations.
They are not admitted for fitting and were not retried. Raw current remains an
uncalibrated device register, not torque, load, contact, or force.

## Verified derived evidence

The versioned evidence compiler rederives the six results and preserves the
historical HIL v1 summary and receipt byte-identically.

- v2 summary SHA-256:
  `91130bcd94eb5b889da90ddbb3d46dc21088246daab966fa2d5d92787a184da1`
- v2 receipt file SHA-256:
  `e8ce53b1c4289624ef7ed2588452b222516670fc0c93af1b3ceb759223f4c179`
- embedded receipt digest:
  `d8f8a312ceff51b91f3e1d4bfcfe3d0e04d6d7d782152266a39a2687be7f22b3`
- accounting: `6` attempts, `6` completed trajectories, `4` admitted,
  `2` rejected, `0` retries, `0` provider calls

## Evaluator-owned closure

Closure v2 was bound after the results without changing the v1 completion
rules, weights, thresholds, or admission semantics. Rejected packets remain
unavailable rather than being admitted post hoc.

- closure contract SHA-256:
  `de72fce3fdec0a233a42548256eece37d4a7b953ffc04886636bc51ff134521e`
- report SHA-256:
  `8cad92323964e93f04032a3b729f0abd4782858824d00511c86a3cbd84e10b5d`
- receipt file SHA-256:
  `f248c813e0c056cece7ba977246e19907b65d6cf47af37cc34aafce143c20239`
- receipt digest:
  `2069d9fbfd9de80a19c2a30907cbfc31c0bc2d7ed8b69026a1202a8ac8c8ac06`

The verdict remains `0 / 6`, with no weighted percentage:

- geometry/scale: `missing`
- kinematics: `partial`
- action/timing: `partial`
- contact/compliance: `missing`
- actuator/load path: `partial`
- task/EE consequence: `failed`

Studio displays the same receipt-verified denominator and domain states. At
desktop and phone widths the Twin fidelity drawer remained read-only, showed
the terminal-negative simulator wording, opened with focus on Close, closed
with Escape, returned focus to its trigger, and produced no browser console
errors.

Precommit verification passed:

- static compilation and JSON validation
- focused HIL/closure/Studio/project-map tests: `38 passed`
- exact LF-00…LF-13 component gate: `1 passed`
- SAIL fast-contract tier: `36 passed`
- SAIL synthetic-golden tier: `58 passed`
- SAIL integration tier: `78 passed, 2 subtests passed`

The frozen-evidence guard digest was
`2545da5958b291389776d03ed93f8023ed964a95b8f66dd8365a15b9885d388d`
before and after every SAIL tier.

## Frozen evidence and authority

The historical four-packet HIL campaign remains SHA-256 `b364aae6...` with
four attempts and zero retries. All eleven frozen S2 files remain
byte-identical; campaign accounting remains one event, four action-identical
anchor replays, and zero measurement trials.

No simulator or adapter replay, threshold change, new parameter family,
posterior update, training, promotion, provider call, paid compute, task-score
change, or strict task claim occurred. This packet family is exhausted.

## External measurement prerequisite

The immediate acquisition blocker is intermittent D405 completion under
motion, despite the camera-only stress test passing. Future work also requires
metric board/object/camera registration, actuator/device-synchronized timing,
calibrated current-to-torque/force/contact evidence, known loaded/unloaded and
reset trials, and strict held-out physical task/end-effector consequence. A
new transaction must preregister those measurements; it may not silently retry
this family or substitute another simulator search.
