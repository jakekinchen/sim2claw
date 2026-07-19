# iPhone video 3DGS private release — 2026-07-19 UTC

Private GitHub Release: `iphone-video-3dgs-img5349-20260719`

This release preserves the exact real Gaussian-splat artifact reconstructed from
owner-provided `IMG_5349.MOV`. The PLY is a generated private release asset and
is not stored in Git history. The tracked JSON index fixes its checksum, size,
proof class, and limitations.

## Result

- Artifact: `IMG_5349-primary-real-splat.ply`
- Representation: binary little-endian PLY, 334,537 Gaussian splats, spherical
  harmonics degree 3
- Size: 78,952,283 bytes
- SHA-256: `f8f3bfe0a0f1fa13d54e47602dbf43f8e0448178c0e85f0f22a5f2115530443b`
- Source MOV SHA-256:
  `0079c19d5a321dd3613924f4a7e0838a4f99943b0833a0b8bed81a12d303dfa8`
- Proof class: `monocular_video_relative_scale_3dgs`

The chessboard and pieces are visually coherent in the selected camera and
bounded orbit. The lower robot/workcell region is soft and ghosted.

## Proof boundary

This is a real monocular-video visual reconstruction. Its SfM coordinate system
has arbitrary global scale. It is not metric or measured geometry, RGB-D,
collision geometry, a complete unseen-surface model, training data, learned
policy evidence, or robot-control authority. The frozen ten-frame holdout was
excluded from fitting, but no accepted held-out dense-render score was produced.

## Local private copy

After downloading the release asset, place it below the ignored directory:

```text
artifacts/private/releases/img5349-3dgs-20260719/
```

Verify it against `IPHONE_VIDEO_3DGS_RELEASE_20260719.sha256` before use.

## Clean-room implementation boundary

The repo-native pathway is `sim2claw iphone-3dgs`. It was authored manually in
this repository from reviewed behavioral requirements and public dependency
interfaces. No implementation file, script, configuration, generated dataset,
checkpoint, or artifact was copied from the prior scanner repository into Git.

