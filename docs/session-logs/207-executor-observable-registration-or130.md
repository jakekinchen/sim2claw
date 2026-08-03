# OR130 executor session

- Card: `OR130_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_STATIC_COMPARISON_V1`
- Candidate delta: append the frozen OR126 and OR129 procedural fixture triangles before the existing OR119 finite object
- Development budget: 7 physical initial-frame decodes and 21 native static renders
- Conditional corroboration budget: 4 physical initial-frame decodes and 12 native static renders, no refit
- Closed: physical-pixel texture projection, screen-space candidate overlay, state/action/timing change, retry, replay, hardware, paid compute, promotion, physics, transfer
- Focused tests: `3 passed` before and after execution
- Receipt SHA-256: `75d090073ec2b7621614c235ac206e1401452d91baa809d09fa6aab5fc909836`
- Artifact SHA-256: `3e81607fac382818f1703f01c525f5f9546edb137c6a139c54382029329c8091`
- Result: full similarity `+0.004305`, outside edge F1 `+0.082385`, and clipped-fixture edge F1 `+0.476995` versus complete-only; no-refit corroboration and all integrity gates pass
