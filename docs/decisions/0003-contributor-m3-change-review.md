# Decision 0003 — Contributor M3 change review

## Status

Accepted in part on 2026-07-18. The existing runtime proof and frozen
`chess_rook_lift_v1` task remain unchanged.

## Context

Contributor branch `jeff_differences_0` at commit
`beddd784f514155c87dd26612823642d52a0924d` proposed five changes under the
summary "added code to run on Jeff M3":

1. document a separately installed FFmpeg 8.1.2 executable in the generated
   Python requirements export;
2. infer whether to skip the bootstrap render probe from display-related
   environment variables;
3. replace the frozen task's configured state noise and state-feature dropout
   with hard-coded zeros during ACT training;
4. close the gripper immediately for a subset of expert demonstrations after
   advance-phase contact; and
5. close the scripted gripper farther and lift it higher.

The complete contributor branch passed the existing 12-test unit suite in an
isolated worktree. That establishes contract-test compatibility only; it does
not preserve the identity of the accepted ACT checkpoint, task contract, or
scripted-grasp behavior.

## Decision

### Adopt with modification: optional FFmpeg documentation

The evaluator already invokes the external `ffmpeg` CLI to encode H.264 video
and records its observed version in the evaluation receipt. FFmpeg is useful
for reviewable MP4 output, but it does not participate in policy inference or
success gating. The README now documents the executable, its purpose, its
macOS installation command, and the no-video behavior when it is absent.

The generated `requirements.txt` remains an unmodified export of `uv.lock`.
The PyPI package named `ffmpeg` is not adopted, and the system executable is
not pinned to the contributor host's observed 8.1.2 version.

Sources and reason:

- <https://ffmpeg.org/> — upstream project for the video-encoding executable;
- <https://formulae.brew.sh/formula/ffmpeg> — public macOS installation path;
- adopted only to encode evaluator PNG frames as an optional H.264/libx264
  review artifact.

### Do not adopt: automatic render-probe skipping

`DISPLAY`, `WAYLAND_DISPLAY`, and `TERM_PROGRAM` do not reliably determine
whether MuJoCo's platform-default offscreen renderer works on macOS. Skipping
the probe would allow bootstrap to report success without verifying the
compile/step/render path that defines the current Mac runtime proof. The
bootstrap therefore continues to run `doctor --render-probe` and fail visibly
when rendering is unavailable.

### Do not adopt: hidden ACT augmentation overrides

The task contract freezes `normalized_state_noise_std` at `0.25` and
`state_feature_dropout_probability` at `0.1`. Training must consume those
reviewed values rather than silently substitute zeros. A deterministic
zero-augmentation experiment requires a new recipe revision and task-contract
hash before training; it cannot reuse the accepted v1 proof identity.

### Hold for a separately versioned experiment: task-mechanics changes

The close-timing condition, jaw target change from `-0.10` to `-0.28` radians,
and lift-height change from `0.09` to `0.14` metres alter synthetic expert data
and scripted-grasp behavior. They may be useful experiments, but the current
branch provides no separately frozen task revision, before/after receipt, or
held-out evaluation demonstrating why they should replace the accepted
mechanics. They remain outside `main` until reviewed under a new recipe and
proof boundary.

## Consequences

- Apple Silicon setup retains a required compile/step/render bootstrap check.
- Optional MP4 production is documented without corrupting the generated
  Python dependency export.
- The accepted ACT run remains attributable to its existing task-contract and
  checkpoint hashes.
- The contributor commit remains available for future experimental work, but
  none of its proof-changing code is promoted by this decision.
