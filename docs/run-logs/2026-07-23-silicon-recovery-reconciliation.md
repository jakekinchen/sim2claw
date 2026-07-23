# Silicon recovery reconciliation

Date: 2026-07-23

## Source inventory

The reachable checkout at `/Users/jakekinchen/Developer/sim2claw` on
`silicon.local` was on `main@090549ae7824b244c81a1af7d5e0484e8a747f41`,
102 commits behind the centralized baseline
`3a0e45864419a393ef902d255a48518b5d728f3b`. It had 20 modified tracked
files, 18 untracked source files, no stash, and no active Sim2Claw or demo
process.

All 38 source files were retrieved byte-identically. Their SHA-256 manifest is
`d05c7056b0081d6fbb423c7fb2c26712e6ae72c614f4e2463ff9072a419953df`.
The exact original tree is preserved on
`codex/silicon-recovery-20260723@f5e8e2995333f3abe169c7e37a0e273b7943e790`.
That branch is recovery provenance, not a current product or authority branch.

Generated Swift build products and application caches were excluded.

## Historical physical evidence

Raw generated evidence was copied into the repository's ignored `runs/`
locations and verified against the remote directory manifests:

| Root | Files | Receipts | Directory-manifest SHA-256 |
| --- | ---: | ---: | --- |
| `runs/task_orchestrator/owner_directed_base_loop/` | 71 | 34 | `b620eec32b3e4b07ed6d2dc87e99b9cae9c47f043af323a68b8a9f73b9d3d37e` |
| `runs/physical_replays/` | 239 | 128 | `6fd8534b8f1846cdd9599d3801bd22f85e8542c45d64d31cd0dc33dc74e65b79` |

The loop receipts contain 10 completed command cycles and 24 failures. The
physical replay receipts contain 105 completed command deliveries and 23
failures. Every receipt keeps `task_success_verified: false`; no learned-policy,
placement, transfer, or physical-task success is admitted. The proof class is
historical unqualified physical command replay.

## Reconciliation decisions

Retained on current code:

- bounded bus-read retry and torque-off behavior;
- source-bound reverse replay and guarded relative-origin handling;
- local overhead snapshot and workcell inventory projection;
- fixed owner-directed loop implementation and native macOS controller;
- read-only projection of the newest fully source/output-bound historical B2
  physical replay.

Changed before integration:

- ordinary Studio startup does not construct or advertise the physical demo
  controller;
- `--enable-physical-demo` is required and rejected for read-only or
  non-loopback servers;
- the native app additionally requires
  `SIM2CLAW_ENABLE_PHYSICAL_DEMO=1` and stops only the process it launched;
- historical replay projection validates exact source samples, replay samples,
  receipt schema, torque-off state, and negative task/policy labels;
- UI wording states the authority boundary.

Rejected as stale:

- the old physical episode catalog, because current Studio already owns the
  verified 18 recording / 18 visual-only / 7 physics / 11 unavailable truth;
- heuristic C922 rotation, because current media uses receipt-owned
  `display_rotation_degrees`;
- relaxed Three.js body-name compatibility, because exact scene-manifest
  revision binding remains required.

## Frozen evidence boundary

No SAIL simulator or adapter was executed. Before and after deterministic
publication refresh, these ignored roots were byte-identical:

- benchmark v2 root manifest:
  `45cc7dfa2cd8a8c2f158462a2fc30c071a685388fddfaae19a91fe710472d48b`;
- live operator C2 adapter root manifest:
  `ba0b69c80c52497bb1284a0129d8b19dddac55961f83d1ec9f34fa0e39bfb961`;
- live campaign-state root manifest:
  `aa18a614f23a90554f934fe805385d36871be266bd3e2ed635acd791b6804805`.

The retained C2 state remains one event, four anchor replays, zero measurement
trials, evaluator reject, and unchanged posterior. Physical authority remains
closed.

## Verification and closeout

The compatible recovery landed as
`77d5270398530706211ba88dfffd13cc4d3cd272`. The Studio observatory receipt was
then deterministically refreshed because that integration intentionally
changed the bound Studio server and UI sources. Its manifest remained
`127b2faa0fbfcff3b946184920b3c3d324d5bcc62ff6745940499be4f0bf0422`;
the refreshed receipt is
`453e9ccde854c4f5914eed239fb15d3d53ef58a7bc1bdb43d07390897db76176`.
The publication package remained
`98173b9d5dca97c75ce8aa579fd727b02a32ff96474e3025283d590ebdd8f833`;
its refreshed receipt is
`97b65f6413184b8b0f5547feb0dabeccf606a65ea57ddf5774a4467db85b449b`.
The one-line publication binding landed as
`df7dada1fc4b9a4dcc3844e1195b6fdff7ff5b2a`.

Focused Python/static verification passed with 143 tests, seven skips, and 24
subtests. The native Swift package passed two tests. The refreshed
Studio/publication slice passed 16 tests. The exact code/config commit
`df7dada1fc4b9a4dcc3844e1195b6fdff7ff5b2a` passed the full repository suite:
1002 tests passed, three skipped, and 328 subtests passed.

Two runs are excluded diagnostic history: a temporary Git worktree lacked the
owner-local ignored evidence required by content-addressed contracts, and the
first primary-checkout run correctly rejected the stale pre-refresh Studio
receipt. Neither is represented as proof, and neither executed the C2 adapter,
simulator, provider, capture, gateway, or robot-motion lanes.
