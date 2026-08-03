# Executor session 165: OR93

- Started from admitted active card `OR93`; agent profile and executor context passed after repairing the queue binding changed by the card transition.
- Evaluated `195` fixed-seed analytic candidates for one shared robot-only SE(2), then rendered six baseline and six selected exact full-source-mesh frames.
- The low-resolution proxy selected `[73.658239, 0.231256, 0.010777]`, but exact outside-board edge F1 regressed from `0.302649` to `0.231925`; zero of six samples improved by at least `0.02`.
- Board-plus-margin F1 remained stable (`0.552385` to `0.564357`), isolating the failure to the shared robot registration assumption rather than board destruction.
- Reviewer decision: reject a single shared robot-base transform and freeze an independent left/right renderer-native diagnostic. This remains post-final retrospective evidence with no same-video, physics, transfer, or promotion claim.
