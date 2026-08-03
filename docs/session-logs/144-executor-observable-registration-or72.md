# OR72 executor session

Date: 2026-08-03

OR72 rendered and compared the untouched analytic scene over all four frozen
development episodes. It used the shared manifest camera, declared RGBA, zero
time offset, and complete trace duration sampled at `5 Hz`. It produced `423`
analytic frames and four candidate videos, and compared exactly `423`
development physical frames after full-frame area resize.

The pooled full-frame mean is `0.584921`, p10 is `0.573482`, motion-union mean
is `0.632754`, and tolerant-edge F1 is `0.109442`. Episode means lie in a narrow
`0.583080–0.585844` range. All six gates fail. Visual inspection confirms the
scene-native studio camera is a frontal view while the C922 footage is an
overhead oblique view stored under the known `hflip,vflip` orientation.

This is a useful terminal baseline negative, not a renderer failure. The
cross-episode consistency supports fitting one bounded shared 3D camera on
development only. The card performed zero fits, validation/heldout reads,
simulator replays, state or physics changes, hardware actions, or paid compute.
Physical frames were evaluator targets only and were never candidate inputs.

Focused verification: `2 passed`.
