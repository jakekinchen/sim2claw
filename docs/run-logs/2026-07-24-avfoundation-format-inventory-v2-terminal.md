# AVFoundation format-inventory v2 terminal result

Date: 2026-07-24

Execution head: `79fdbe8467f0a79e5f1f33dd5401090d6dcd09b1`

Proof class: `camera_device_format_inventory`

Verdict: `supported_exact_or_fractional_rate_candidate`

## Frozen identities

- Contract: `ec25b9443f024972a8f4f6f9d7c1b600ad1893b4e7cb3e379f5be3db4c841dcd`
- Source: `73f0e6b7675cb20be8fc7fccdd5b1c6dd1c369ee75443627ec2c43ba9e612aab`
- Evaluator: `ab13da6a5c544e0a8991dd96491274ed0f2838b23e9d66b452c50619e60c25a3`
- Compiler: `3e7d30871a9740446f33a907b14d28f10ebe6d4e1c146a4c0788308f573a6609`
- Binary: `cb699b41378f12410fb03ecdb81b5a7752075f4b595acd4b0a78d183447695b1`
- Pre-launch manifest: `b65515a15ccce493532d4616e6a254aa3ac81dea097e5f5b2496d1e729b716bf`
- Attempt manifest: `d9844d4db585d0aa14830f326f1e841c3a0ed988dbdb81563091c30f71147f1e`
- Raw inventory: `3754a62fa643359fa1f13484bd4f86ba7c1ab13d234b2a3f7f5b5bcb60e830a2`
- Stderr: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Evaluation: `3c59915c81f9d8073f02acd4ca3eae8b9c715db9485e9e838ca4638427e05d7d`
- Receipt file: `14c8f82147611854ac4ecc317426f447ac4b3fbccef9cd133e1cd4026287e98f`
- Embedded receipt digest:
  `9c42f8a55357f2508897a8515d3b7d3dba98bbe7409ba246c1c8b14ccec932ac`

## Evaluator result

- Exact-name device matches: `1`
- Native formats: `33`
- Frame-rate ranges: `209`
- Exact-640×480 candidates: `14`
- Eligible candidates within `0.05 fps` of 30: `2`
- Selected format/range: `16 / 0`
- Selected subtype: `420v`
- Selected dimensions: `640 × 480`
- Supported rate: `30.00003000003 fps`
- Absolute deviation: `0.00003000003 fps`

The subtype preference and every threshold were frozen before observation.

## Budget and claim boundary

- Inventory observations: `1 / 1`
- Capture sessions: `0`
- Source samples/frames: `0`
- D405 lifecycle operations: `0`
- Robot motions: `0`
- Simulator replays: `0`
- Provider calls: `0`

The result proves a supported native format/rate request only. It does not
measure callback delivery, source continuity, container timing, exposure,
cross-camera synchronization, metric depth, simulator calibration, or task
success. It does not reopen either exhausted v1 campaign or authorize a new
stream campaign.
