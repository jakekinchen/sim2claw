# AVFoundation C922 Callback Delivery v4 — Preregistration

Date: `2026-07-24`

Baseline: independently reviewed `main@1ff887e`

V3 repaired start-time format negotiation but failed one strict cadence gate:
interval index zero was 66 ms, while the remaining 303 intervals passed.

V4 reuses the exact v3 Swift observer bytes. Before observation it freezes a
one-second source-PTS warm-up followed by a ten-second target measurement
window. Warm-up cadence is reported but not scored; exact format, numeric and
strict PTS, and zero reported drops remain full-session gates. One eleven-second
session is available with no retry.
