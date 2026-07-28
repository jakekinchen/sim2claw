# AVFoundation C922 Callback Delivery v4 — Terminal Verified

Date: `2026-07-24`

Preregistration commit: `3cd554c`

Exact evaluator/execution commit:
`d49f2ef25ee6eee4b2cef603c7ab4059c8c2a986`

Proof class: `camera_source_callback_delivery`

## Result

V4 reused the byte-identical reviewed v3 Swift observer and its proven
lock-through-start behavior. One eleven-second C922-only session delivered
`334` samples, all exactly `640×480 420v`, with zero Apple drop callbacks.

The evaluator retained the first source-PTS second as a separately reported
warm-up: `27` samples and `26` intervals, including the visible
`0.06700000003911555 s` startup gap. The transition interval was
`0.03400000010151416 s`.

The scored window contained `307` samples and `306` intervals spanning
`10.199999999953434 s`. Mean interval was `0.033333333333181156 s`; median was
`0.03300000005401671 s`; maximum was `0.03400000010151416 s`, below the frozen
`0.049999950000049996 s` gate. The evaluator returned
`steady_callback_delivery_verified` with no failed gates.

This closes the C922 source-format and steady-cadence prerequisite for a
recorder that performs the proven lock-through-start sequence and one-second
pre-roll. The startup gap remains part of the evidence and was not deleted or
reclassified.

## Content-addressed evidence

- contract SHA-256:
  `6caa3affe419a74ff94582f9341387a614adb0648757811847722acf551801e9`
- reused Swift observer SHA-256:
  `79da2c743ac5e16ef90fb56dfd77802e015e8e4fd7d9763ac23e5410ea29bb53`
- evaluator SHA-256:
  `3201b8653aeb75f60ffa9ced94543ce58e9f415642be75c351c204b4c78b6a2e`
- compiled binary SHA-256:
  `26d76d43b9806262be768b7fd56e7b5c50594f279b9796415167b9ed94034bcb`
- prelaunch SHA-256:
  `896ef1a52c26447ef9cd48547db9ba6e972802a4f3012650e5ddc58faed8a57c`
- attempt SHA-256:
  `6b917acb107cf637dbf53be7b6d4bfa6aa00e093d7bc808de4451652df368bae`
- raw observation SHA-256:
  `6fb1301cea2b1d4c6da56c5902730c7359237855da1be91a96e7f9ceb0a98e3d`
- evaluation SHA-256:
  `0d18cfb7e614061a513135079a125789a317d0b1fd937612b47d5ee486bd6ebb`
- receipt SHA-256 / embedded digest:
  `7354ce1d33847c15fd4dfcddf0eba35a435788d8fd144bf6b2d842e11c0f1740` /
  `0933f548774b10e6fea4be3320b632931588824e04a6b6d1f00418d006bcb6c8`

## Authority and accounting

Exactly one observation and one eleven-second session were used, with no
retry. D405 lifecycle operations, robot motions, simulator replays, provider
calls, training, promotion, task-score changes, and physical-task authority
remained zero/closed. S2, HIL, inventory, and callback v1-v3 evidence remained
byte-identical.

This does not prove physical exposure continuity, container timing,
cross-camera synchronization, metric calibration, simulator fidelity, task
success, or physical transfer.
