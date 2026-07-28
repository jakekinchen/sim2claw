# AVFoundation format-inventory v1 terminal abstention

Date: 2026-07-24

Proof class: `camera_device_format_inventory`. This is a prerequisite
abstention, not a native-format observation, source-delivery result, stream
qualification, simulator result, or task result.

## Execution

Preregistration `8a29d3f` and implementation `c868038` preceded the only
authorized observation. The observer source remained
`289c3fc2ca3f66ff9da18d783c70936bbb8c4c3d823c5e522ec6c26ff8e09750`
and evaluator remained
`3ec4e50acf2ae052dab70616efe2b2ed561a4763d3460cbddb3298e0cc7d54aa`.

The compiled binary
`aa432262d039b3c275831966685292fd11a6047a21647eeb0451f6710e2c09da`
terminated while serializing its payload:

`Invalid type in JSON write (__SwiftValue)`

The stderr artifact is
`e8404380ca2940ce707c90df1daa87a0e8f23d0394e820654b7cef22bc473c25`.
No raw inventory or observation manifest was written. No format count, rate
range, exact-device match, or candidate can therefore be claimed.

## Sealed result

Fail-closed sealer commit `9b3a5bf` refuses any raw inventory and binds the
executed source/evaluator, compiler, binary, and stderr.

- Evaluation SHA-256:
  `c4677bb56893ac1c45494503c33143f9b021a3fe3afc2720d62c3497efa507e4`.
- Receipt file SHA-256:
  `eb95e1eb8e20cb3c0753a8e385c735cc003416d282a44a4f1a2aa1e52b2533f4`.
- Embedded receipt digest:
  `0157d4b166436623a8b3c22ef8941c845bd7996cc78991be523fe39d0026ef57`.
- Verdict: `prerequisite_abstention`.

Budget: one of one inventory observations used; zero usable inventories,
capture sessions, source samples, D405 lifecycle operations, robot motions,
simulator replays, provider calls, or task-score changes.

V1 is exhausted and will not be rerun. The next software prerequisite is a
separately versioned observer that explicitly converts every emitted value to
JSON-compatible `String`, `Int`, `Double`, `Bool`, array, dictionary, or
`NSNull`, with its own committed source and one-observation authority.
