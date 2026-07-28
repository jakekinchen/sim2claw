# AVFoundation C922 Callback Delivery v2 — Terminal Degraded

Date: `2026-07-24`

Preregistration commit: `e90ef28`

Exact implementation/execution commit:
`c8d2f50100f5899d821ef5ed85750b207d97d21c`

Proof class: `camera_source_callback_delivery`

## Result

The sole authorized C922-only observation completed with return code zero. The
exact input and `420v` output were associated with the session before the
observer set format index `16`, range index `0`. The active device format was
exactly `640×480 420v` with minimum and maximum duration
`0.03333330000003333 s` both after input association and after configuration
commit. At both stages, the session preset raw value remained
`AVCaptureSessionPresetHigh`.

`startRunning()` then changed the active device format to
`1920×1080 420v` with minimum and maximum duration
`0.0416666006945489 s`. The observer stopped fail closed after the first
delivered `1920×1080 420v` sample. There were zero Apple drop callbacks. The
evaluator returned `callback_delivery_degraded` and failed
`exact_format_after_start`, `minimum_output_callbacks`, `exact_dimensions`,
`strictly_increasing_pts`, and `bounded_pts_interval`.

This identifies start-time session-preset negotiation as the remaining C922
callback prerequisite. V2 used its sole session and cannot be retried. A future
version must separately preregister a post-commit format or input-priority
binding mechanism before session start.

## Content-addressed evidence

- contract SHA-256:
  `6ccfcf08452e5cbd22444368579ef4a7202cc0e6d17dcb0c4d2030c7ffd774df`
- Swift observer SHA-256:
  `bb8120df1e43aa1f5f106f07fd9bd438ed21a9546cf743fc0552e2e64c673daf`
- evaluator SHA-256:
  `0afeee34d99efa82f4bbc59d9c40df3815a3ac941811ae0ac57c988662d29a18`
- compiled binary SHA-256:
  `f8902434ca48b56240db7050640a16d41c68a5665d1d9442046870305ee27e66`
- prelaunch SHA-256:
  `3d30cbf7487baff206ca94a998d942ba0fc8ba70857fd383092f43964cd0883b`
- attempt SHA-256:
  `2a9194b9ba660b43bc34aabe506c18c2eb9fb119d471683ec5a4f65767725430`
- raw observation SHA-256:
  `593c3d3e62bb49e4a08713bab63e6e699584a2ad1da91341452318362b2d4314`
- evaluation SHA-256:
  `a889450f94187906f745779620ed769e7e642def45e9d458a390c3064fce1935`
- receipt SHA-256 / embedded digest:
  `5dd301ab462395706f6b4d505d7f41a829871542682967da795b5dab17950c2f` /
  `ae6dd332ba20710bd06dff2bf3bba49d3662d2fd727eac05243a6d6bae84c4fd`

## Authority and accounting

Exactly one observation and one capture session were used; the intended
ten-second callback window ended early because the start-stage format gate
failed. D405 lifecycle operations, robot motions, simulator replays, provider
calls, training, promotion, task-score changes, and retries were zero. The
eleven S2 artifacts, both HIL campaign states, and callback v1 evidence remained
byte-identical.

This does not prove container timing, physical-exposure continuity,
cross-camera synchronization, metric calibration, simulator fidelity, task
success, or physical-transfer authority.
