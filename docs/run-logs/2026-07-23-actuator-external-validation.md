# Actuator-response external-validation terminal negative

Date: 2026-07-23

Proof class:
`historical_cross_session_action_frozen_simulator_trace_validation`.
This is conditional historical simulator-trace evidence only. It is not
current-workspace calibration, physical torque/contact identification, task
success, training, promotion, or transfer evidence.

## Frozen execution

Preregistration commit:
`fd5e8dafe23a6a73bc3c334c0eb72ce361e77856`.

The single authorized run evaluated two frozen variants on five separately
recovered historical acquisition sessions: ten simulator replays, zero
retries, zero provider calls, and 2,186 action rows. Every baseline/candidate
pair used one identical float64 `[N, 6]` action array with zero clipping,
resampling, offsets, IK, suffix, or assistance.

| Recording | Action SHA-256 | Baseline joint RMS (deg) | Candidate joint RMS (deg) | Relative change | Baseline EE RMS (m) | Candidate EE RMS (m) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `20260718T224507Z-cb15a243` | `2d0590af806830f16ad5620e0f80f5451af261bd28d4f825097485e2543da741` | 1.484535 | 1.366274 | +7.966% | 0.015916 | 0.013965 |
| `20260718T225126Z-a19918d7` | `47094ce6c2aefc63dbf360aec079321327e445b7f091c1aad119f0ff7bf72b26` | 1.493892 | 1.515424 | -1.441% | 0.013564 | 0.015157 |
| `20260718T225419Z-bdd95fdf` | `5035ff5678e01d34c4aad59eb790ca226d4dfab76b3c80b601d9e7643f1cdadb` | 1.295331 | 1.246818 | +3.745% | 0.011883 | 0.010874 |
| `20260718T225715Z-e68b4076` | `2f6d3fc524d51a0c9654720a7a7c71f32ad80621816b505837bc6a5a899c217f` | 1.264121 | 1.217975 | +3.650% | 0.012197 | 0.011600 |
| `20260718T230416Z-573f2320` | `28de7bce27dbe753be1cb85f3a740fdf964717fc129e44bf0b688b7c11d9e9a8` | 1.440750 | 1.381724 | +4.097% | 0.013171 | 0.012288 |

## Evaluator decision

Pooled joint RMS fell from `1.410977` to `1.360044` degrees, a `3.6098%`
improvement. Four of five sessions improved. Pooled EE RMS fell from
`0.0137558` to `0.0132328` m, a `3.8021%` improvement.

The preregistered pooled-effect, episode-count, EE-non-regression, and action
invariance gates passed. The bootstrap-direction gate failed: the deterministic
10,000-replicate, 95% whole-session interval for joint-RMS relative improvement
was `[-0.0006486, 0.0694745]`. The negative lower endpoint is small but must not
be rounded into a pass.

Verdict:
`external_trace_validation_reject_task_completion_unchanged`.

The existing independent simulator consequence receipt remains 0/11 strict
success before and after. No result value was used to expand the family, no
candidate was promoted, and no task-completion score changed.

## Content-addressed evidence

- Contract SHA-256:
  `3f8b83764741690fca8b73572840e2bc33a862a47fe49fbeb8aee4a4ed951c4c`.
- Implementation SHA-256:
  `a9be358cb5753ca2aec38d7de5f50012c4dcd0d1211fa5c249ad27de315fc778`.
- Raw execution SHA-256:
  `097baa940ed6951fad69519e10f8cdd8d2565f10d9c632b0da46f228ba5c963d`.
- Evaluation SHA-256:
  `1d8b91e423f10f9d3649608b70b87ffd532819fff2010db55a5e8afac67a2f19`.
- Receipt SHA-256 / digest:
  `6854ff26082d8491bf2e755c5e9e27f372846437e2355d359834f96981c345b2` /
  `21e1c55164e39d659824657c397c34e6e38945efa7435ef81f7a148418ab14d0`.

The generated evidence remains ignored under
`outputs/pawn_actuator_external_validation_v1/`.

## Scientific next step

The data support the direction of the shoulder/load-path correction but do not
provide stable enough cross-session evidence to recalibrate or raise the task
score. The next useful transaction is independently synchronized current-100
mm angle/current/load/contact measurement, with task consequences evaluated
separately. Another post-result parameter sweep is not admitted.
