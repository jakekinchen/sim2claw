# Inspect physical telemetry trace build

Request: Integrate physical telemetry evidence tools into Inspect and produce
trace comparisons from every property supported by the retained dataset.

Repo/path: `/Users/kelly/Developer/sim2claw`

Started: 2026-07-20

Completed: 2026-07-20

Owner constraints: retired workcell; no new physical test; no provider call;
never infer unrecorded object, contact, grasp, or latency measurements.

## Acceptance Criteria

- [x] Requested, commanded, and measured positions are exposed as bounded,
  synchronized trace rows.
- [x] Measured velocity and raw present-current proxy are included with their
  actual units and calibration limitations.
- [x] Monotonic, control, video, and endpoint-frame evidence is hash-bound.
- [x] Endpoint frames are returned as image content through an Inspect tool.
- [x] Object, contact, grasp, actuation-latency, camera-latency, and simulator
  traces fail closed as unavailable.
- [x] Human receipt outcomes remain distinct from policy or grasp results.
- [x] All 18 episodes produce deterministic command-versus-measured JSON and
  visual comparisons.
- [x] Focused and full repository verification are recorded.

## Model And Tool Roles

| Role | Model/Tool | Purpose | Inputs | Outputs |
| --- | --- | --- | --- | --- |
| Contract implementation | Codex | Create schemas, extractor, Inspect bridge, and tests | Existing repo contracts and retained physical corpus | Tracked source and documentation |
| Deterministic extraction | Python, NumPy, Pillow | Validate hashes and produce comparisons | 18 recordings, 7,741 samples, 36 frames | JSON, CSV, 18 PNG plots |
| Inspect orchestration | Inspect AI and Inspect SWE | Present bounded host tools to Codex CLI or Claude Code | Materialized host receipts | 18 read-only audit samples |
| Verification | Pytest and Inspect task loader | Exercise boundaries without a provider call | Source contracts and local ignored data | Test results and task enumeration |

## Generated Assets

| Asset | Source | Prompt or Script | Output Path | License/Notes |
| --- | --- | --- | --- | --- |
| Corpus comparison | Retained physical source recordings | `scripts/materialize_physical_telemetry_trace.py` | `runs/physical-telemetry-trace-v1/physical_telemetry_corpus_comparison.json` | Ignored, hash-bound physical observation |
| Aggregate joint table | Same | Same script | `runs/physical-telemetry-trace-v1/aggregate_joint_comparison.csv` | Descriptive only |
| Episode trace plots | Same | Same script | `runs/physical-telemetry-trace-v1/episodes/*/command_vs_measured.png` | 18 generated plots; commanded versus measured only |

## Verification

| Proof Surface | Command/URL | Result | Artifact |
| --- | --- | --- | --- |
| Core and Inspect focused tests | `uv run pytest -q tests/test_physical_telemetry.py tests/test_inspect_physical_telemetry.py` | `5 passed` in 7.51 seconds | Test log |
| Frozen-campaign regression | Focused tests plus `tests/test_retrospective_publication.py::test_provider_campaign_is_frozen_dry_run_without_secret_values` | `6 passed` in 7.83 seconds; telemetry adapter isolated from frozen corrective adapter | Test log |
| Full repository suite | `uv run pytest -q` | `549 passed, 328 subtests passed` in 244.95 seconds | Test log |
| Inspect task enumeration | `uv run --group inspect inspect list tasks evals/inspect_gapbench/telemetry_task.py` | One task found; provider calls 0 | `sim2claw_physical_telemetry_audit` |
| Current dataset materialization | `uv run python scripts/materialize_physical_telemetry_trace.py` | 18 episodes, 7,741 samples, 36 frames, physical actions 0 | Ignored run artifacts |
| Deterministic rerun | Materializer executed twice consecutively | Corpus JSON, aggregate CSV, and representative plot remained byte-identical | File SHA-256: `596126712ebe829f2eeb4e99b9cfa638b8e74a24d6f1b23eb05dca45df8c98f2`, `818a4a49c542876bf6fbfa587fecde61e6c24ddab11365b228e7199978c2f0ae`, `a220b1e9628279f5ff69888f866e66b42a50013cffcdb3acb853d2c4653b4519` |

## Descriptive Results

- Command-to-measured position RMSE is 1.406, 2.968, 2.948, 2.194, and
  2.019 degrees for shoulder pan through wrist roll, and 2.662 percentage
  points for the gripper.
- Pooled successive-sample timing is 50.010 ms mean, 61.743 ms p95, and
  170.160 ms maximum. Recorded control interval is 49.876 ms mean and
  61.651 ms p95.
- There are 7,736 non-stale cached-current rows and five stale-current rows;
  freshness of the nominal 5 Hz bus read is not identifiable per row.
- Requested-to-commanded differences include 2,660 rate-limited and safety-
  clamped rows, so their maxima are not treated as simulator-transform error.
- Corpus logical comparison digest:
  `29f2dc81f4d92baa8caaeeb8c64dc56df545d5287c9bfa69ea50c20e06026ee0`.

## Known Gaps

- Zero episodes are exact simulator-replay eligible, so no real-versus-sim
  trace comparison is produced.
- Metric object and target pose fields are null for all 7,741 samples.
- No contact state, contact force, or instrumented grasp outcome was recorded.
- Present current is a 5 Hz raw device proxy cached into intervening rows, not
  calibrated joint effort; fresh-read row identity is not recorded.
- Timing supports interval and video-timeline diagnostics, not separately
  identifiable actuation or camera latency.
- All 18 receipt outcomes say success and belong to human teleoperation; this
  is not a balanced success/failure policy corpus.

## Follow-Up Queue

- Add real-versus-sim comparison only after an approved joint transform makes
  exact unclipped replay eligible.
- For future collection, record command-write, bus-ack, observation-read, and
  camera-capture timestamps plus calibrated object/contact observables.
