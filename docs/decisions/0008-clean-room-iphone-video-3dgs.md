# Decision 0008: clean-room iPhone video to 3DGS pathway

## Decision

`sim2claw` owns a fresh, fail-closed `sim2claw iphone-3dgs` pathway. It uses
public command-line interfaces to extract frames, freeze a holdout before
fitting, recover a relative-scale camera model, and train a Gaussian splat.
Generated inputs and outputs must remain below `artifacts/private`.

The prior scanner checkout may be read only to recover requirements and proof
boundaries. Its source text, implementation, scripts, configuration, datasets,
models, caches, and receipts are not copied. The implementation in
`src/sim2claw/iphone_3dgs.py` was authored manually for this repository.

## Public dependencies and reasons

| Dependency | Source | Reason |
| --- | --- | --- |
| FFmpeg / ffprobe | https://ffmpeg.org/ | Decode the owner-provided MOV, strip non-video streams/metadata, and extract deterministic JPEG inputs. |
| COLMAP | https://github.com/colmap/colmap | Public SIFT, exhaustive matching, shared-camera bundle adjustment, and sparse relative-scale reconstruction. |
| Brush | https://github.com/ArthurBrussee/brush | Public Gaussian-splat optimizer and binary PLY export. The executable is owner-supplied and checksumable; it is not vendored. |

These are runtime executables rather than new Python package dependencies. The
CLI requires explicit executable paths so runs do not silently select another
installation.

## Frozen behavior

1. Verify and probe one MOV.
2. Extract a bounded frame set into a new ignored run directory.
3. Assign the deterministic holdout before feature fitting.
4. Stage training frames only.
5. Run CPU SIFT, exhaustive matching, and COLMAP mapping.
6. Run one bounded Brush candidate with explicit steps, resolution, splat cap,
   SH degree, and seed.
7. Reject a missing or non-Gaussian binary PLY and checksum the accepted output.
8. Emit an ignored receipt that keeps visual, metric, RGB-D, physical, and
   learned-policy proof classes separate.

V1 deliberately does not score held-out photometric quality or promote its own
candidate. A future evaluator must own that admission decision.

