# Maintenance review — 2026-09-06

Candidate: `deb3bd4` (native RGBD preparation), plus reviewed integration commits
`d7380ec`, `ebe3c66` and PR merge `034e589`.

Decision: **STOP** at the physical-input boundary. Evidence anchor: **100**.
Software maintenance is accepted; physical calibration and simulator fidelity
are not advanced. This is a separate review pass by the implementing agent,
not an independent scientific evaluator verdict.

## Reviewed boundaries and evidence

- The new native recorder is separate from frozen OR44. Required capture flag,
  explicit identifiers, bounded frame count and new output directory are checked
  before SDK context construction. No serial/servo/gateway path is imported.
  The six executed binary checks all return before hardware access.
- Color/depth retain separate device clocks and frame counters. SDK frameset
  association is disclosed without an exposure-synchronization claim. Partial
  files cannot acquire a completion manifest before stream closure.
- The offline validator checks both stream calibrations, rigid extrinsics,
  byte ranges and sizes, row order, frame uniqueness, clock monotonicity, serial/
  experiment identity and explicit optional-metadata missingness. Rehashed
  metadata must match parsed bytes even when file size/time are restored.
- Passing synthetic or unreviewed files cannot grant physical capture,
  synchronization, jaw geometry, fitting or calibration authority. The result
  remains `STRUCTURALLY_VALID_UNREVIEWED` and lists missing independent inputs.
- 380 required software tests and 21 adjacent tests pass. The native source
  compiles with six pre-camera smoke checks. Neither constitutes device-stream
  execution, physical observation quality or predictive simulation proof.
- Original actions, timestamps, frozen scene/gateway/evaluator/authority files
  and scientific receipts are preserved. The caller supplement fixes current
  inventory coverage without retroactively changing the frozen migration.
- Unique stale experiments, alternate-root architecture and recovery snapshots
  remain preserved with dispositions; they are not bulk-merged into live code.

## Remaining constraints

Actual native RGBD capture and producer-to-validator operation with real frames
remain unverified. Marker extraction, physical marker-to-jaw transforms and
gateway clock association cannot be certified from software fixtures. OR48's
independent metric and untouched-validation gates still own that next step.
The acquisition guide makes these prerequisites concrete; no repeated fit or
new physical operation is admitted by this review.
