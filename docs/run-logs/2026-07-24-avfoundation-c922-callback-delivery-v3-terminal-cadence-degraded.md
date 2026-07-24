# AVFoundation C922 Callback Delivery v3 — Format Verified, Cadence Degraded

Date: `2026-07-24`

Preregistration commit: `d6c1a08`

Exact implementation/execution commit:
`a779dc5ff351b61334ddcaf3e5462a624b949708`

Proof class: `camera_source_callback_delivery`

## Result

The single changed mechanism worked: retaining the associated C922 device
configuration lock through session commit, `startRunning()`, and immediate
post-start verification prevented AVFoundation's v2 start-time format override.
Before commit, after commit, and after start, active format remained exactly
`640×480 420v` with minimum and maximum duration
`0.03333330000003333 s`. The session preset getter remained
`AVCaptureSessionPresetHigh`; no preset was assigned.

The callback delegate was attached only after post-start verification and
device unlock. All `305` output samples were `640×480 420v`, and Apple reported
zero drop callbacks. Across `304` PTS intervals, mean was
`0.034180811403769586 s`, median `0.03300000005401671 s`, and maximum
`0.0659999999916181 s`. The maximum exceeded the frozen
`0.049999950000049996 s` gate, so the evaluator correctly returned
`callback_delivery_degraded` with only `bounded_pts_interval` failed.

The over-limit interval was index `0`, the first measured interval. The
remaining `303 / 303` intervals were within the unchanged gate. This is
identifying evidence for a bounded warm-up before a scored/recorded callback
window, not permission to remove the maximum-gap requirement post hoc. V3 used
its only session and cannot be retried.

## Content-addressed evidence

- contract SHA-256:
  `bfd1d6435b436f8dea09fd8357bd300d85333dab4d7ccfacdc748ea9d3344adf`
- Swift observer SHA-256:
  `79da2c743ac5e16ef90fb56dfd77802e015e8e4fd7d9763ac23e5410ea29bb53`
- evaluator SHA-256:
  `a2ffdce45eb6ceafafd034fee76ab5423a8b2a7f539db687b67ef31c1155a23f`
- compiled binary SHA-256:
  `e31f594bce795c43299eef7ceeafd3560f2e739678f4da1d3c51c16fcf532191`
- prelaunch SHA-256:
  `0dbed725ca69e7bec859d51e9114692c2b881a94d9fcc3059a9cdcb26f0e9253`
- attempt SHA-256:
  `da4f2b92931ec4fb87fb8e1f33ba5ddffa0caad6a9c252a562129571487130ae`
- raw observation SHA-256:
  `df6aac8d735dc1f157bbd5c76b5a333eb4abd9bca64f7997a253e06db16f3ae9`
- evaluation SHA-256:
  `b4cc00376001cdfc531bdc22d6adc6bf9846fd7e2171d0d8ead222e2a6445fa2`
- receipt SHA-256 / embedded digest:
  `276611fd190c31ec9c7d76fa1b9c1154982974d1055b152f35d3d9ed0ff1eabe` /
  `7c5965661c987807c899c7b1a4ca019bb8f1fed1b47cb9b3898d17abf81000c6`

## Authority and accounting

Exactly one observation and one ten-second C922 session were used. There was
no retry. D405 lifecycle operations, robot motions, simulator replays,
provider calls, training, promotion, task-score changes, and physical-task
authority remained zero/closed. S2, HIL, format-inventory, callback v1, and
callback v2 evidence remained byte-identical.

This verifies the lock-through-start format mechanism, not stable source
cadence, container timing, physical-exposure continuity, synchronization,
metric calibration, simulator fidelity, task success, or transfer.
