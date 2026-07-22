# SAIL Deterministic Belief Graph Run Log

Date: 2026-07-22

Milestone: P1-04

Proof class: deterministic retrospective lineage compilation

## Commands

```bash
uv run sim2claw sail-compile-belief-graph --config configs/sail/belief_graph_retired_bg_v1.json --output outputs/sail/retired-bg-v1/belief-graph
uv run pytest -q tests/test_sail_contracts.py tests/test_sail_evidence.py tests/test_sail_residuals.py tests/test_sail_belief_graph.py
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Frozen identities

- Configuration: `40bc1a9ea31de767049904e3b229ef799ac5bf2e46392131ca0eb399c350f475`
- Graph: `a5cf6e19214fe4406f798189e30c9fb3f9dbbe1fb662130d3904b1e55486c4e0`
- Graph digest: `07c48a10a02387f3b3b5dc7ae025ee603ba98b2607bb8401cc10b37047a66e75`
- Receipt: `da1ad4de3f3b1139376bda47e45d0b14f4805d25035e7809d007a7ee6f2aee59`
- Receipt digest: `1005c5480d070ccf4b5b15a3bbd4b5ed71c576216e6158c43d15f35a045f5f0f`
- Deterministic tree digest: `1489197ef7c2144bc5c4365410320db66261f02fe59bd32e8b49cddec59ef08b`
- Before SVG: `d3bb8d0844cd3be41a50e622139fd43fcffdae795f43231d5a13e40fff113048`
- After SVG: `16f60ada65e94eda5fd7f94ed0d4d988a132ac9e25a5bacacda97d9c63ce7b21`
- Revision timeline: `170c2f2929937009080847c687e726ccfd4114db694b17c29d432db280a194b5`

## Compilation result

- 71 nodes across all 16 required node types and 191 canonical edges.
- All 11 required edge types are frozen in the vocabulary; no `admitted-to`
  edge exists while the TwinWorthiness certificate remains unissued.
- 13 chronological revisions, 12 declared-scope influence candidate sets, and
  20 queryable negative/counterexample verdict nodes.
- Geometry/scale, reset, timing, deadband, load response, contact ensemble,
  timestep, fixed pad, friction, and terminal outcomes remain source-bound.
- Directed traversal from the compiled action-frozen evidence node reaches the
  terminal publication verdict.

## Validation result

- Focused SAIL tier: 39 passed.
- Complete repository: 659 passed, three expected skips, 328 subtests passed in
  1,227.15 seconds.
- Reversed history input and repeated compilation preserve the same graph and
  output-tree digests.
- Duplicate IDs, dangling edges, closed-certificate admission, proof-class
  rewrite, evaluator rewrite, and receipt drift fail closed.

## Claim boundary

The graph is deterministic lineage and declared-scope bookkeeping. Its edges,
chronology, or visual proximity do not identify a cause or promote a candidate.
All training, selection, simulator-promotion, and physical authority stay
closed.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
