# Goal Loop — Current 100 mm C922 Frame Lineage v1

## Mission

Convert the already-observed byte-identical relationship between the frozen
C922 video and `overhead_start.png` into one deterministic, evaluator-owned
frame-extraction receipt without opening a camera or changing either source.

## Ordered Source of Truth

1. The current 100 mm metric-registration readiness terminal packet.
2. Exact clean baseline
   `083b5f138e2055d1d22dc1fce7a4afd92a621f7b`.
3. The hash-bound C922 capture receipt, video, and existing source frame.
4. `configs/evaluations/current_100mm_frame_lineage_v1.json`.
5. Exact committed runner/evaluator identities.
6. GOAL, project state, orchestration ledger, and terminal run log.

## Intended Outcome

One bounded offline derivation either verifies that C922 video frame index `29`
at PTS `1.000000 s` is byte-identical to the existing source PNG, or seals a
lineage mismatch. A pass closes only deterministic frame-extraction lineage;
it does not provide metric scale, intrinsics, distortion, extrinsics, object
pose, simulator calibration, or task evidence.

## Acceptance Criteria

1. Preserve frozen S2, HIL, camera, and metric-readiness evidence
   byte-identically.
2. Commit this goal and contract before implementing or running the proof.
3. Bind the source capture receipt, video, existing frame, FFmpeg, and FFprobe
   by exact SHA-256.
4. Independently verify video stream identity, `640 × 480` dimensions,
   `1049` frames, frame index `29`, and PTS `1.000000 s`.
5. Decode exactly one derived PNG with the frozen command and require both its
   file SHA-256 and decoded RGB24 SHA-256 to match the existing frame.
6. Preserve the capture-time `hflip,vflip` orientation as already encoded in
   the source video; apply no new geometric transform during extraction.
7. Write only inside the ignored canonical output root. Never overwrite the
   existing video or frame.
8. One derivation and one metadata probe maximum; no retry or alternate
   timestamp/index/decoder/command.
9. Add adversarial tests for source, decoder, timestamp, frame-index,
   orientation, output-root, dimensions, PTS, file-byte, and decoded-pixel
   substitution.
10. Seal exact hashes, budgets, verdict, and closed authority. A future metric
    manifest may consume the receipt, but v1 metric-readiness evidence remains
    unchanged.

## Evidence Standard

Report exact commits/trees; contract, source, decoder/probe, derived frame,
evaluation, and receipt hashes; frame index/PTS; file and decoded-pixel
equality; budgets; focused tests; frozen evidence; and authority limits.

## Decision Status

### Confirmed

- Read-only audit found the existing frame byte-identical to both an exact
  index-29 decode and an exact `1.000000 s` seek under FFmpeg `8.0.1`.
- This audit is design input, not the formal one-shot receipt.
- The reviewed formal derivation passed: frame index `29` / PTS `1.000000 s`
  is byte-identical and decoded-RGB-identical to the existing frame.

### Assumptions

- None. The formal evaluator must rederive the relationship under the frozen
  identities.

### Recommended Default

- Run the single deterministic extraction after exact-byte review. Stop on any
  mismatch; do not search adjacent frames or timestamps.

### Open Questions

- None for the bounded lineage proof. Metric calibration inputs remain
  separate.

## Execution Rhythm

1. Commit preregistration.
2. Implement/test the one-shot derivation and independent evaluator.
3. Commit exact bytes and obtain pre-execution review.
4. Execute once, seal, update durable state, and stop.

## Progress Ledger

```text
Current state: Terminal verified; one probe/derivation budget exhausted with no retry.
Completed: Preregistration 4692bea; reviewed implementation cc30304; 1/1 probe and derivation; tracked exhaustion control.
Evidence: Video 1643520f; frame/file 2543230b; RGB24 7046a08b; evaluation 4788a827; receipt file 3b44795c / digest 15d90882.
Remaining: Consume this pass in a new metric-readiness version; do not edit v1.
Blockers: None for offline lineage.
Next step: Acquire direct scale/intrinsics/correspondence/object/extrinsic measurements under a new transaction.
```
