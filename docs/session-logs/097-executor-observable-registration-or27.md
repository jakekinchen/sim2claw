# Executor session 097 — OR27 visible-divergence Studio

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

Studio now exposes `/visible-divergence.html`, a responsive read-only surface
for the hash-verified OR26 physical and simulator lanes. It has one shared
playhead, play/pause, one-frame stepping, `0.5×/1×/2×` playback, causal event
markers, and a direct jump to sample `248`.

The publication loader verifies the OR26 closeout, receipt, artifact identity,
and every media digest before returning a URL. A missing or changed artifact
fails closed. The UI keeps the native C922 pixels and MuJoCo rendering in
separate labeled panes and states that the board homography is display-only.

Browser review covered the desktop surface and a `390×844` phone viewport.
The physical and simulator first frames render independently, the panes remain
synchronized during playback, the jump control lands at `12.40 s / sample
248`, and the phone view stacks the evidence lanes under a sticky shared
transport.

An initial browser review caught that the combined comparison poster was being
assigned to both separate video elements. That duplicated both lanes inside
each pane. The poster assignment was removed and the two native first frames
were re-inspected before closeout.

## Verification

```text
uv run --locked pytest -q \
  tests/test_visible_divergence_studio.py \
  tests/test_observable_registration_visible_divergence_video.py \
  tests/test_studio.py

22 passed, 2 subtests passed
```

No camera, serial bus, gateway, hardware motion, paid compute, simulator
promotion, task-success claim, or transfer claim was opened.
