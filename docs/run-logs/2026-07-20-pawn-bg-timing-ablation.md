# 2026-07-20 B--G timestamp/application ablation

Command:

```text
uv run --offline python scripts/run_pawn_bg_timing_ablation.py
```

The audit found that legacy replay applied an action, integrated one sample
interval, and then recorded the simulator state against the row timestamp. The
timestamp-aligned variant records state at the row timestamp and applies the
unchanged action over the following zero-order-hold interval.

On 11 product training episodes, the legacy joint/EE RMS is 2.563 degrees and
20.843 mm. Timestamp alignment with zero delay reaches 2.033 degrees and
18.769 mm. A 0--150 ms grouped-episode CV grid selects 110 ms on all-train;
folds select 100--110 ms. The selected result reaches 1.461 degrees and
16.417 mm, a 43.0% joint and 21.2% EE reduction from legacy.

Every source action array remains contiguous float64 and byte-identical across
variants, with no clipping, offsets, IK, suffix, or assistance. Consequence
remains 9/11 contact, 0/11 lift, and 0/11 strict success, so this is an accepted
timing diagnostic, not a composite simulator or physical latency calibration.

Receipt: `outputs/pawn_bg_timing_ablation_v1/timing_ablation_receipt.json`.
