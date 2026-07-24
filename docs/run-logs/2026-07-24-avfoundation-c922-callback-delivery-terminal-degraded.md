# AVFoundation C922 Callback Delivery v1 — Terminal Degraded

Date: `2026-07-24`

Preregistration commit: `0c30321`

macOS preset-contract correction commit: `7becd95`

Exact implementation/execution commit:
`f00f4f11ad19e9b413482705df66e0a04e364099`

Proof class: `camera_source_callback_delivery`

## Result

The sole authorized ten-second C922-only observation completed with return code
zero. The observer matched the exact C922 name, unique ID, and model ID, and
applied sealed format index `16` / range index `0` as `640×480`, `420v`,
`30.00003000003 fps`, frame duration `0.03333330000003333 s`.

The source callback output did not preserve those dimensions. All `243`
output callbacks were `1920×1080`, `420v`; zero dropped callbacks were
reported. Across `242` PTS intervals, the mean interval was
`0.04200826446267907 s` and the maximum was
`0.08303333341609687 s`, above the frozen
`0.049999950000049996 s` gate. The independent evaluator therefore returned
`callback_delivery_degraded` with failed gates `exact_dimensions` and
`bounded_pts_interval`.

This is identifying evidence for AVFoundation session negotiation/configuration
order, not permission to reinterpret the sealed D405/container negative. The
implementation set `activeFormat` before the input was associated with the
session and did not re-verify it after session configuration/start. A future
version must preregister post-input-association format configuration plus
active/delivered-format verification before any new session. V1 used its only
attempt and cannot be retried.

## Content-addressed evidence

- contract SHA-256:
  `154854b53f2d18ddb4885b4f733e4ec4ef15f92f844f92e69cea0b2d5caf87ec`
- Swift observer SHA-256:
  `331928acb8753918fb8d2bb4ace174a1b28a2db09bfc101838658e978e5dbbdb`
- evaluator SHA-256:
  `727b3c9096f809800777fdb2aeac655ca6a69fb8cd9ac3927b6dc1aa717dfb42`
- compiled binary SHA-256:
  `88fc6dd4aa36efebf2a06a3239affbdbf957ac755a778a117577ddb2fd978cab`
- prelaunch SHA-256:
  `ef31e9ede87397c0ca2c538fc897d40429f53f156b0f08076abf556c8c6c980b`
- attempt SHA-256:
  `744abba7ca941919225410b03c40ac72f64297cecab97e5cafa9e1c546ad3bd5`
- raw observation SHA-256:
  `9e3e2d574a7fa7db4a91b5d2f5e653bbc47fa88c82ee812e334993ea3a3fc671`
- evaluation SHA-256:
  `25827c4d318e593df3042d19ae12fa7ba9041de864600b9d991c31845e8988af`
- receipt SHA-256 / embedded digest:
  `2096d836469662362e466f630fa1ede8b370412bf2e7a33592435e3c4436317b` /
  `558aae78b9721dd92a4718ff9d88a9572d84d8f5fa4607c0825edf75edb21b16`

Repeated evaluation materialization was byte-identical.

## Authority and accounting

Exactly one observation and one ten-second capture session were used. D405
lifecycle operations, robot motions, simulator replays, provider calls,
training, promotion, task-score changes, and retries were all zero. The eleven
S2 artifacts and both HIL campaign states remained byte-identical.

This result does not prove container timing, physical-exposure continuity,
cross-camera synchronization, metric calibration, simulator fidelity, task
success, or physical-transfer authority.
