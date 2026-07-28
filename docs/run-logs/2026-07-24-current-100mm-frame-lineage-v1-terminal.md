# Current 100 mm C922 Frame Lineage v1 — Verified

Date: `2026-07-24`

Proof class: `deterministic_physical_video_frame_lineage`

Preregistration `4692bea` preceded implementation. Initial exact-byte review
blocked execution on missing `-show_frames`, receipt-consumer incompatibility,
and fail-open receipt semantics. Commit `cc30304` closed those issues; final
review passed `13/13` focused tests before the one formal derivation.

The sole FFprobe metadata operation verified the frozen H.264 `640 × 480`
stream and frame index `29` at PTS `1.000000 s`. The sole tracked-wrapper
decode produced PNG SHA-256
`2543230b795c8a61ab6f7ddb1e9c672588ea88958cddbbb84397d689034b5dfc`
and RGB24 SHA-256
`7046a08b731c736471c73abba80bbcc366b650569bee5bbf6d4db97366cecaa8`,
both exactly matching the existing `overhead_start.png`. No geometric filter
was applied during extraction; the capture-time `hflip,vflip` is already
encoded in the source video.

- Evaluation SHA-256: `4788a827c10514164e4ca457a57e322285e12e0df2d282e09b27769fc8f4b496`
- Evaluation digest: `a2cf32e045c5234ecec940b1d2bea507771dfe6c6e57992fee65de25e89b5b4e`
- Receipt file SHA-256: `3b44795c161c9f19025a64b244aadea9d03c93ca2635449d90781f6a1a957ed7`
- Receipt digest: `15d90882157bf6ad91e497a33a15e2ade3098876d8ad09029b692db85c28f246`

Budget use was one probe, one derivation, and zero retries, camera sessions,
new camera frames, robot motions, simulator replays, or provider calls. This
closes deterministic frame lineage for a future metric-readiness version. It
does not modify the terminal v1 readiness packet or close metric scale,
intrinsics, distortion, correspondences, object pose, extrinsics, Twin
fidelity, or task authority.

At exact closeout head `968566f7fc5c92b4e53bd038e3b8fa416124984b`,
the focused lineage/control, metric-readiness/control, and exact project-state
pin bracket passed `48 / 48` in `0.94 s`. Frozen S2 evidence remained
`11 / 11` byte-identical at one event, four anchor replays, and zero
measurement trials.
