# AVFoundation format-inventory v2 preregistration

Date: 2026-07-24

Baseline: `4e1807f0c32185846d69e0a0cc706abb0920d3da`.

V1 is terminal and immutable: binary `aa432262...`, stderr `e8404380...`,
evaluation `c4677bb5...`, receipt `eb95e1eb...` / `0157d4b1...`, one
observation used, zero usable inventory.

## V2 change

V2 uses new source/evaluator paths. The raw payload must be concrete Swift
`Codable` structs encoded by `Foundation.JSONEncoder`; heterogeneous
`[String: Any]`, `JSONSerialization`, and implicit `__SwiftValue` bridges are
forbidden. AVFoundation enums and numeric values must be converted to explicit
`Int`/`Double`, while unavailable macOS fields are typed optionals/null.

The runner must write exact contract/source/evaluator/compiler/binary identity
and budget to an attempt manifest before launching the observer, then finalize
the manifest after any return or signal. Missing raw output remains an
abstention.

## Frozen decision and authority

The scientific decision rule is unchanged: exact 640×480 dimensions, nearest
supported rate to 30.0, maximum deviation 0.05 fps, and the same subtype and
tie-break order. Budget is one v2 inventory observation and zero capture
sessions, frames, D405 operations, robot motions, simulator replays, providers,
training, promotion, or task-score changes.

Contract SHA-256:
`ec25b9443f024972a8f4f6f9d7c1b600ad1893b4e7cb3e379f5be3db4c841dcd`.
Goal SHA-256:
`e85ec4fb52210eaa1808919b086f686f88c201a3c6fab3cf6301f162d094bb1e`.

No v2 implementation or observation exists at this checkpoint.
