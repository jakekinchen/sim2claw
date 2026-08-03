# OR132 executor session

- Card: `OR132_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_RESIDUAL_RECONCILIATION_V1`
- Inputs: 11 already-open physical videos, 11 OR131 simulator videos, and 1,210 bound frame rows
- Method: exact OR120 persistent/dynamic outside-board occupancy factorization
- Closed: render, fit, selection, threshold change, retry, replay, hardware, paid compute, promotion, physics, transfer
- Focused tests: `3 passed` before and after execution
- Receipt SHA-256: `b3f9d1dd33bb92fe91f6c2d89943b3f4e990ef2d44f54e6143f9e6a22973d737`
- Artifact SHA-256: `386e958dc20f362e8e61b10495af5e489cc78819181c96e189b741357f77b692`
- Result: persistent occupancy F1 `0.480578`, dynamic occupancy F1 `0.572664`; persistent deficit dominates `8/11`, below the frozen `9/11` single-successor gate, so the residual is combined/unresolved
