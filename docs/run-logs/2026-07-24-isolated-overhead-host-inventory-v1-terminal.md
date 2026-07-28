# Isolated Overhead Host Inventory v1 — Attachment Required

Date: 2026-07-24

## Result

The sole preregistered zero-session metadata inventory reached
`silicon.local`, independently evaluated its camera and USB metadata, and
returned `isolated_overhead_host_requires_c922_attachment`.

Silicon reports macOS `26.3.1`. It has zero exact C922 camera matches, zero
C922 USB `1133:2140` matches, zero D405 camera matches, and zero D405 USB
`32902:2907` matches. The host is therefore available and cleanly isolated,
but the fixed overhead C922 is not physically attached.

## Exact evidence

- Preregistration commit: `76beee9`
- Reviewed execution commit: `7810c659faa268d68e09d6ce8d9fe246db29708e`
- Contract: `10f4d01df62fc1f59b8efd46b61f4d19116966f17a18296c0e3ad5bb41623a7a`
- Runner/evaluator: `1ceb83a8e2699853ee0aa3f68bcf0685db2e9662e752b90a639a2fc37bd63fc6`
- Reviewed SSH executable: `aa3ba829a6283f29ffb81e0e3c57ff43d0cee132fea789072a0a2a2688af3afc`
- Prelaunch: `5feff32164c565a64c920ff04c8e5db26ef4adb0b66f52aff0396ca7e1f58ffb`
- Attempt: `ebd916b89e79484e668b272fbd6876ebabd53b0d4d3688c23668e27492ce0a29`
- Captured stdout: `254cf819b55a3aca6db3687ef09aa3b2a5b2607e07c5ef74b4b7c2e45a8487e4`
- Empty stderr: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Raw observation: `f3cf7ed87308bc4d9d489d9604980ac365a7a251a716417c9858adba8ac53a48`
- Evaluation file/digest: `fdcd13599306560a4b47a5a29424cbee607bfabb7b9720a9348fad26fe37e588`
- Receipt file: `109532c8e6547d679dcd3ffa451c7f717f0a13d7605ee9c73efdcd49932b51e7`
- Receipt digest: `44ad7049ab30177539805f1a1462cdfe7b77a3456f3311b6bf83560d20dd8d56`

## Budget and authority

- remote inventories: `1 / 1`
- strict metadata connections: `1 / 1`
- retries: `0`
- capture sessions: `0`
- camera frames: `0`
- remote files written: `0`
- robot motions: `0`
- simulator replays: `0`
- provider calls: `0`

The family is exhausted. Its tracked guard and separate control refuse before
any new process delegation. This result proves host/device inventory only.

## Next prerequisite

Physically move the fixed overhead C922 USB attachment from `kelly-claude` to
the Silicon Mac while leaving the motion-coupled D405 on the robot-side host.
After that physical change, open a new preregistered exact-device confirmation
and capture-transport transaction. Do not retry this inventory or substitute
another camera.
