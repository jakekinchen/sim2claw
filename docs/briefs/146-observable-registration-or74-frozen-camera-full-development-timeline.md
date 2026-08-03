# OR74 frozen camera full development timeline

OR74 carries the exact OR73 camera into all four development timelines without
refit. It uses the same complete-duration `5 Hz` sampling as OR72, the known
C922 `hflip,vflip` evaluator orientation, identity declared RGBA, zero time
offset, and the unchanged OR55-style full-frame, motion-union, phase, and edge
gates.

The card emits four analytic candidate videos and evaluator rows. Candidate
pixels remain exclusively projected from the frozen 3D scene and replay state;
physical frames are targets only. No camera, appearance, timing, state, or
physics parameter changes. Validation and evaluator-heldout data remain
unopened. A pass would only clear the development video metric; it would not
establish validation, heldout generalization, event parity, physics fidelity,
promotion, or transfer.
