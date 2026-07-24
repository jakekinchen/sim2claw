# D405 AVFoundation Format Inventory v1 Preregistration

Date: 2026-07-24

Baseline: `3fafda3b7429f6c727afaacade86346791e72b52`

The independently reviewed nested dual-camera lifecycle family is terminal at
one attempt with verdict `reject_stationary_nested_dual_camera_lifecycle`.
It may not be retried. This new transaction freezes one read-only D405
AVFoundation format inventory as the minimum prerequisite for designing a
native two-input common session.

The observer may enumerate the exact D405 device and its format/rate metadata.
Its budget is one observation, zero capture sessions, zero frames, zero D405 or
C922 lifecycle operations, zero robot motions, zero simulator replays, and zero
provider calls. Candidate selection is exact 424×240 near 5 fps within 0.01
fps using the preregistered subtype and tie-break order.

No evaluator implementation exists for this v1 transaction and no device
observation has occurred. A selected candidate, if any, is inventory evidence
only and grants no stream, synchronization, metric-depth, simulator, task, or
physical-task authority.

## Terminal result

Preregistration commit `359506e` preceded the exact final implementation and
observation commit `2e3a94f3f716a8bb098e752e74c762f34e8d3727`.
The single observer returned zero and materialized:

- 1 exact D405 device match;
- 12 formats and 56 frame-rate ranges;
- 10 exact-dimension candidate rows and 2 eligible rows;
- selected format index 0, range 4, 424×240, `2vuy`, exact 5 fps;
- 1/1 inventory observation;
- 0 capture sessions, frames, C922/D405 lifecycle operations, robot motions,
  simulator replays, or provider calls.

Content identities:

- observer source: `73f0e6b7675cb20be8fc7fccdd5b1c6dd1c369ee75443627ec2c43ba9e612aab`
- evaluator: `f5ad88887b8822765532d60c66d52969ad7a8cc0004e8116f629d14dad11684c`
- binary: `b75847230e2904c0c6f69cdbdf7a973a493e611ca15501aefe1ffb933286a359`
- prelaunch: `b85122b465bed7309a1fe82a8dd15e3b1453854b012d979e54293e5c990ff258`
- attempt: `ccded9ed94d0407238b852a1a7e3d5586a1fe97dfb1436a1ff8ea4d5477b617e`
- raw inventory: `ca2bef8b552fee3c55ae9cffd6bd2da0f5286449dd7c76f5922ef65dadd7917a`
- evaluation file/digest: `68ad34b9e004b5781f73a38e2c7df88536f0e5291b3845d90856a0e69d9edb8b`
- receipt file: `fb4e76d990b44bd5633fa3ec955c1480c044430bd8e32427b9386269f4553ed3`
- receipt digest: `674d5825732ad72f0ea2513519307098f3c7dc27e7a26926fe5fcceadeee22b8`

The verdict is `supported_d405_common_session_candidate`. This closes only
native format selection. Capture-session admission, callback delivery,
cross-camera timing, motion reliability, metric depth, simulator calibration,
and task authority remain unproved.

Post-terminal control uses tracked exhaustion guard
`b8194ddc4e9ee11b53f5f950243c7be7bdb8418ca01e58d3c656cd3c5232c531`
and separate control module
`78027bd591e379550cc43deefcee2ed9a5060d5913aedb0843396c13ad9f67b2`.
The control checks the committed one-of-one accounting and refuses before any
runner or device delegation, even if ignored generated outputs are moved.
