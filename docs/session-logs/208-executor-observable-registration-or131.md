# OR131 executor session

- Card: `OR131_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_FULL_TIMELINE_PROPAGATION_V1`
- Candidate delta: exact OR130 complete and clipped fixture streams, 256 triangles total
- Budget: 11 physical decodes, 1,210 candidate renders, 11 videos, one receipt
- Closed: physical-pixel texture projection, screen-space overlay, fit, selection, threshold change, retry, replay, hardware, paid compute, promotion, physics, transfer
- Focused tests: `3 passed` before and after execution
- Receipt SHA-256: `d100315ca8c7a78c1b882a82c4527f01adf39ce86c93d57b5d6f047e2cebb33a`
- Artifact SHA-256: `ad7e3071670a8a8442ccdecd46c7cb640e27a06880be64031b77253a9de1dff2`
- Result: full `0.841731`, motion `0.792209`, whole edge `0.517387`; full-improvement passes, while board mean `0.570955` and outside mean/p10 `0.476838/0.448385` remain below the composite same-video gates
