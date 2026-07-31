# Executor session 112 — OR40 retained-video jaw-surface mapping

Date: 2026-07-31
Card: `OR40`
Result: `DIRECTIONAL_PLAY_UNIDENTIFIABLE_NO_REPLAY`

## Scope

The executor used only the retained D1-to-D2 D405 RGB stream, its frozen
sample/frame schedule, and the immutable 531-row follower measured-state
trace. No camera, robot, gateway, paid compute, heldout set, training surface,
or physical task authority was opened.

An owner-requested ChatGPT Pro research pass inspected repository commit
`43d2a513ba5c1255cf6eedda288bc0f449891192` through the GitHub connector. It
was advisory. Its useful evidence-safe correction was to reject metric
aperture and camera-calibration claims from the RGB-only moving wrist view and
instead test one scale-free directional play estimand, with a frozen no-refit
validation split and zero replay on an identifiability failure.

## Frozen evaluation

- Mapping samples: `110–224`.
- Contact holdout: `228–260`.
- Terminal seal: `261–530`.
- Deterministic extraction: two largest qualifying red HSV components,
  ordered left-to-right, reporting moving-minus-fixed centroid X in pixels.
- Fit frames: `floor(frame_index / 2) mod 2 == 0`.
- Validation frames: the complementary two-frame blocks.
- Candidate: one causal rate-independent play half-width in raw gripper
  degrees, with camera lag jointly profiled over `[-0.11, +0.11] s`.
- Dynamic replay budget: at most one, and only after every mapping gate passes.

The content-addressed candidate manifest was written before validation was
evaluated.

## Immutable result

- Accepted preterminal frames: `25`.
- Abstained frames: `60, 61, 62, 63, 89`.
- Selected play half-width: `0.0°`.
- Selected camera lag: `-0.065 s`.
- Fit RMS: `1.7252985014 px`.
- Validation RMS: `2.2809216600 px`.
- Zero-play validation RMS: `2.2809216600 px`.
- Validation improvement over zero play: `0.0`.
- Fit opening/closing frame counts: `4 / 4`.
- Validation opening/closing frame counts: `5 / 0`.
- Near-optimum play/lag correlation: `0.9861502215`.
- Dynamic replays executed: `0`.

The retained video proves image-space jaw-surface observability but does not
identify directional encoder-to-surface play. The best candidate is the null
model, the frozen split lacks a closing validation branch, validation exceeds
the `2 px` gate, and play remains confounded with lag. No alternate split,
convenient lag, metric scaling, contact geometry, compliance, or terminal
outcome may be substituted.

## Verification

`uv run --locked pytest -q
tests/test_observable_registration_retained_video_jaw_surface_mapping.py`
passed `4` tests. The repository-wide agent and goal checks are recorded at
the transition commit.
