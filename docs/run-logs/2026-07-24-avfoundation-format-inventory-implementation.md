# AVFoundation format-inventory implementation checkpoint

Date: 2026-07-24

Preregistration commit: `8a29d3f`.

## Implemented surface

- `tools/macos/AVFoundationFormatInventory.swift`
  (`289c3fc2ca3f66ff9da18d783c70936bbb8c4c3d823c5e522ec6c26ff8e09750`)
  enumerates the exact-name device and all native formats/ranges. It writes
  explicit `capture_session_created: false`,
  `capture_session_started: false`, and `source_sample_count: 0`.
- `src/sim2claw/avfoundation_format_inventory.py`
  (`3ec4e50acf2ae052dab70616efe2b2ed561a4763d3460cbddb3298e0cc7d54aa`)
  owns compilation/runtime identity, one-observation accounting, strict raw
  validation, the frozen candidate ranking, verdict, and receipt.
- `tests/test_avfoundation_format_inventory.py` covers contract/threshold
  mutation, observer surface, fractional-rate admission, out-of-tolerance
  rejection, subtype tie-break, prerequisite abstention, source/evaluator/
  binary/raw/budget/authority/camera substitution, duplicate format indices,
  and byte-identical materialization.

The observer source contains none of the forbidden capture APIs declared by
the contract. This is reviewed source-level isolation for the committed
non-hostile observer, not cryptographic sandboxing.

## Verification and authority

- Swift typecheck: PASS.
- Direct inventory tests: `15 passed`.
- Combined camera, HIL, and Studio tests: `96 passed`.
- Inventory observations used: `0 / 1`.
- Capture sessions, source samples, D405 lifecycle operations, robot motions,
  simulator replays, provider calls, and task-score changes: `0`.

The implementation must be committed before the single live device
enumeration. Prior S2/HIL/D405/source-localization evidence remains immutable.
