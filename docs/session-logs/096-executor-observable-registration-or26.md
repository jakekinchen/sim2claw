# Executor session 096 — OR26 synchronized visible divergence

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

The immutable OR21 exact-action physics trace and the retained native C922
recording now play on one `531`-sample, `20 Hz` timeline. The simulator view
uses the retained OR10 camera family scaled to the measured `324 mm` playing
surface and one explicitly display-only board homography. No action, physics
state, contact parameter, or source timestamp was changed.

The registered planar pawn path is already close:

- initial simulator root to physical annotated pawn base: `10.774 px`;
- terminal simulator root to physical annotated pawn base: `12.584 px`;
- post-warp board-corner RMS: `0.000008 px` (display registration only).

The material divergence is therefore contact consequence, not failure to
approach D2. Simulator unilateral contact begins at sample `231`; pawn tilt
exceeds `5°` at `248`; bilateral contact begins at `255`; sustained board
support loss begins at `260`. The retained physical source carries the pawn
upright through the corresponding interval. Because the physical pawn axis is
occluded, the receipt bounds the first visible causal split to samples
`248–260`, or `12.402–13.002 s`, rather than claiming a falsely exact physical
orientation timestamp.

The generated browser-playable artifacts remain ignored evidence under
`outputs/observable_registration_visible_divergence_video_v1/`:

- `comparison.mp4`: synchronized 1280×540 side by side;
- `physical.mp4` and `simulator.mp4`: separately controllable 640×480 lanes;
- `poster_sample_248.png`: threshold frame;
- `motion_curves.json`: timestamped display and motion diagnostics.

## Verification

```text
uv run --locked pytest -q tests/test_observable_registration_visible_divergence_video.py
2 passed

artifact_sha256
47e7822a48731364aaf2e1cd8b0c697e20b55064db731587e51f7f63c83afe36
```

No camera, serial bus, gateway, hardware motion, paid compute, parameter fit,
simulator promotion, task-success claim, or transfer claim was opened.
