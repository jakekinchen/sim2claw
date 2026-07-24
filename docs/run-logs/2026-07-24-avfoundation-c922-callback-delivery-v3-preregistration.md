# AVFoundation C922 Callback Delivery v3 — Preregistration

Date: `2026-07-24`

Baseline: reviewed clean `main@56fc242dc0b28af853663cb8b1b7228181db441c`

V2 is terminal degraded and exhausted. It proved that exact format identity
survives association and commit but is replaced at `startRunning()` while the
session remains `AVCaptureSessionPresetHigh`.

V3 changes one mechanism only: the associated device configuration lock remains
held through commit, start return, and immediate post-start verification. The
observer then unlocks before the callback window. All candidate, output,
cadence, budget, and authority gates remain unchanged. One session is
available; no retry is permitted.
