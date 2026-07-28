# AVFoundation format-inventory v2 implementation checkpoint

Date: 2026-07-24

Preregistration commit: `622602c19f79f11ae9ee38a8c98f9b707220e766`

Implementation commit: `995e8bbfed956150f77bfa2bc7408be450339be7`

## Implemented surface

- `tools/macos/AVFoundationFormatInventoryV2.swift`
  (`73f0e6b7675cb20be8fc7fccdd5b1c6dd1c369ee75443627ec2c43ba9e612aab`)
  uses concrete `Codable` structs and `Foundation.JSONEncoder`. It enumerates
  the exact-name device and its native formats/ranges without constructing a
  capture session. Unsupported macOS format metadata is an explicit typed
  null, not a synthesized measurement.
- `src/sim2claw/avfoundation_format_inventory_v2.py`
  (`ab13da6a5c544e0a8991dd96491274ed0f2838b23e9d66b452c50619e60c25a3`)
  verifies contract/source/evaluator/compiler/binary identity, writes the
  attempt manifest before launch, finalizes it after any return, validates the
  primitive raw payload, and alone applies the unchanged candidate rule.
- `tests/test_avfoundation_format_inventory_v2.py`
  (`6d863a7d682678775b423a7e9c959fb076fc186d35c219a37913d485dd470880`)
  covers contract and threshold mutation, primitive source/typecheck,
  pre-launch persistence, signal/nonzero and missing-raw outcomes, runtime,
  raw, budget, camera substitution, macOS-null metadata, fractional-rate
  admission, and byte-identical evaluation.

## Verification and authority

- Swift typecheck: PASS.
- Direct v2 tests: `15 passed`.
- Combined inventory/camera/HIL/Studio tests: `138 passed, 2 subtests passed`.
- Inventory observations used: `0 / 1`.
- Capture sessions, source samples, D405 lifecycle operations, robot motions,
  simulator replays, provider calls, and task-score changes: `0`.

This is reviewed non-hostile source isolation, not a hostile-code sandbox. The
single device/format enumeration remains unconsumed and may run only after
this implementation and its project-state binding are committed.
