# Workspace adapter software review

Review time: 2026-09-05T10:16:01Z. Reviewer: `infra_audit`, independent of the
adapter implementation owner. Repository HEAD:
`ee9e532825fe72a0eca4f34443e138a28fdb344d`; branch:
`codex/operations-atlas`. The checkout contained uncommitted integration work.

Decision: no remaining blocking code-review findings in the bounded metadata
adapter at the hashes below. This decision covers software inspection and
metadata validation only. It does not accept a robot task, policy, simulation,
training result, physical transfer, or campaign milestone.

## Exact review scope

Reviewed the native exporter/validator/comparator, shared schema and synthetic
fixture runner, additive CLI adapter commands, and the design document snapshot.
The source hashes identify the reviewed bytes; the HEAD alone does not identify
these uncommitted changes.

| Path | SHA-256 at review time |
| --- | --- |
| `src/sim2claw/ops/adapter.py` | `2f96b8edb30f75d9a28525c77aa8e43676173e32ef94d2f94c9f0128946d0a5f` |
| `src/sim2claw/ops/cli.py` | `7f8fc19bc24bb202b142ad0061761c596bb27efb86a60af2f0eab3f9eff6935a` |
| `configs/operations/workspace_adapter.v1.schema.json` | `7f6115335dac03c0493940ed9f63d1aba0c741ba55defd434b5208acedf52bf0` |
| `configs/operations/workspace_adapter.v1.fixtures.json` | `7ea788e0ddce6ce77a99ae18fb1c87589ec5437806ed68ed6d2b8efde0f6eaa4` |
| `docs/operations/DOJO_ADAPTER.md` | `4817c56e796ec75ddb79e9568862abfa6f0022bc1e2cd9b9eba48a04eacb1482` |

Later documentation, roadmap, tests, exports, or receipt updates are outside this
snapshot review. Changes to the reviewed implementation or shared schema require
review of those changed bytes. Bilateral peer checks and the final test run are
separately owned evidence; this review does not independently attest to the
partner repository or to a later retained receipt.

## Boundaries checked

- **Native authority remains native.** `adapter.py:185` reads the current-state
  manifest, then takes campaign, project-state and goal paths from it and the
  queue path from the declared graph. `adapter.py:256` invokes the native manager
  context compiler and records its result. The observed refusal was
  `repository branch drift: expected main, got codex/operations-atlas`. This is
  the legitimate campaign boundary on the authorized software feature branch,
  not an admission error to bypass. The adapter does not reactivate closed OR156.
- **Metadata never grants execution.** `adapter.py:27` fixes execution, source
  mutation, training, hardware, promotion and paid-compute permissions to false.
  `adapter.py:120` rejects altered permissions. Capability entrypoints remain
  strings; export/check/compare/conformance do not evaluate them, load policies,
  import peer packages, or call a simulator. Validation and comparison preserve
  `execution_authorized=false` and `policy_portable=false`.
- **Identity has a narrow meaning.** `adapter.py:116` requires the supported
  envelope version and exact shared-schema digest. `adapter.py:125` checks unique
  IDs, source references, action dimensions/order and per-axis units.
  `adapter.py:147` checks producer-relative paths and, only with an explicit
  producer root, file hashes and Git HEAD. `adapter.py:171` labels this metadata
  and optional source-byte verification; it does not establish evaluator
  acceptance, native semantic correctness, or a clean committed checkout.
- **Human output remains inert.** `cli.py:62` exposes only the four adapter
  inspection commands. `cli.py:91` reports metadata compatibility and its proof
  boundary; `cli.py:223` dispatches those commands without executing declared
  entrypoints. The existing terminal-output boundary escapes control sequences,
  while JSON output retains machine-readable values. Rejected checks return a
  nonzero status.

## Robot-specific ABI review

The four profiles preserve separate native interfaces (`adapter.py:233`):

| Profile | Reviewed native meaning |
| --- | --- |
| Source episode v4 | One selected SO-101 arm, six ordered absolute joint targets in radians, float32 identity, 20 Hz hold and 0.005-second physics steps. The scene contains two six-actuator arms; its total actuator count is not the per-arm policy dimension. |
| Historical ACT state v1 | Distinct left-arm task, six named radian targets and 61 frozen observation features. Native clipping is explicitly described. A shared observation dimension with MicroDuck does not establish feature compatibility. |
| Physical gateway v2 | First five targets use degrees; the gripper uses its calibrated 0–100 interface. Physical-to-simulation mapping and gripper clipping remain a separate conversion boundary. No global control rate or exposure/application clock is inferred. |
| Exact replay v1 | One timestamped six-axis tensor, native radian units, little-endian float64 C-order hash encoding, identity transforms and artifact-specific timestamps. Its schema, encoding and units are read from native declarations. |

The native anchors checked were `scene.py:25` and `scene.py:929`,
`configs/tasks/chess_pick_place_source_episode_v4.json:40`,
`configs/tasks/chess_pick_place_source_episode_v4.json:60`,
`configs/tasks/chess_pick_place_act_state_v1.json:14`,
`configs/tasks/chess_pick_place_act_state_v1.json:41`,
`physical_gateway.py:100`, `physical_gateway.py:363`,
`physical_sim_replay.py:49`, and `replay_eligibility.py:15`.
Python-module anchors in this paragraph are under `src/sim2claw/`.

## Review findings resolved

1. The exporter previously named fixed authority files. It now follows the
   current manifest and graph (`adapter.py:185`).
2. Exact-replay schema, units and hash encoding were duplicated as adapter
   literals. They now come from AST-read native declarations (`adapter.py:249`),
   including the native report schema (`adapter.py:278`).
3. Deep JSON could leak a `RecursionError` through the CLI. `adapter.py:48`
   normalizes decoder recursion to a `ValueError`, and `adapter.py:97` returns
   an invalid result for cyclic or overly nested programmatic payloads.
4. A FIFO could block before the byte limit applied. `adapter.py:55` requires a
   regular file, opens with `O_NONBLOCK | O_NOFOLLOW`, and checks the opened
   descriptor again before the bounded read. This closes the reviewed FIFO and
   final-component symlink cases without waiting for an external writer.

## Reviewer-observed checks

A bounded `uv run --locked python -c ...` inspection imported only the metadata
adapter and exercised its validation functions:

- A roughly 40 KB document with 20,000 nested arrays raised `ValueError` with
  `JSON nesting exceeds the inspection limit`.
- A cyclic programmatic payload returned `valid=false`, source verification
  `unchecked`, and false execution and policy-portability flags.
- A native export and explicit-root validation returned `valid=true` and
  `hash_verified` for all 18 declared source files, while preserving the exact
  campaign branch refusal above.
- The shared synthetic conformance runner passed all 30 cases with the schema
  and fixture digests recorded in the table.

The `run_audit` agent owns the automated regression suite, including bounded
FIFO/depth checks and CLI failure behavior. Its final test result must be retained
separately. No simulation, training, hardware, paid compute, partner-repository
mutation, staging, or commit was performed for this review.
