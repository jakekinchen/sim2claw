# Upstream source record

- Repository: `https://github.com/google-deepmind/mujoco_menagerie.git`
- Commit: `71f066ad0be9cd271f7ed58c030243ef157af9f4`
- Upstream path: `robotstudio_so101/`
- License: Apache-2.0 (preserved in `LICENSE`)
- Retrieved: 2026-07-17 by a fresh sparse checkout
- Reason adopted: reviewed public MuJoCo model for the two SO-101-style arms visible in the owner-provided scene photo.

The upstream model files are vendored without edits. `sim2claw` changes material
colors, mount transforms, and joint poses only in memory while assembling the
photo-reference scene. Those transforms are visual estimates, not hardware
calibration or physical authority.
