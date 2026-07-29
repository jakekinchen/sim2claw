# Session 086 — Realized-Action C8 Studio Proof

Date: `2026-07-29`

Decision: `CLOSE_C8_PASS_ACTIVATE_C9`

## Result

Studio now has a dedicated `#/proof` surface for the complete C2--C7
realized-action chain. A deterministic, tamper-rejecting bundle presents all
`531` requested, gateway-sent, measured, and C4-applied rows beside the
physical C922 video and immutable simulator pawn path.

The page keeps the successful actuator result visible without promoting it:
validation joint RMS fell from `2.368` to `1.055 deg`, and provisional EE RMS
fell from `16.786` to `6.965 mm`. The action-to-task result remains the
immutable `0/1`. Sample `386` marks the first greater-than-1-mm simulated pawn
motion and sample `388` marks the catastrophic launch.

Contact state, global robot mapping, floor metric residual, physical metric
object path, and probabilistic uncertainty remain visibly missing or
unapproved.

## Evidence

- Generated bundle SHA-256:
  `ad4bf47e5cafe9231f87cbc5fe8cdca6f40204f6df6f286fb7e58058c5b859bd`.
- Generated bundle artifact:
  `34b8dc493aa9d365a2bb25d8c90773c565f4e7dd39e294a02dc45d0b1b772436`.
- Generated receipt SHA-256:
  `9d17e4137b79f746db533a2ff102e8b8e5fc83b6fb02330c34ebae49e251b3f0`.
- Generated receipt artifact:
  `bf295feefc506c4d3eaf1885154e9aa5bb6b152083df5d3bb812d1d27d5769c2`.
- Two builds were byte-identical.
- `36 passed, 2 subtests passed`; JavaScript syntax, Python compileall, and
  diff check passed.

## Visual acceptance

- Desktop `1280 x 720`: route, video, verdicts, and evidence lanes render.
- Phone `390 x 844`: no horizontal overflow; verdicts stack; the timeline
  readout is sticky.
- Selecting wrist roll and scrubbing to source index `388` updated the
  playhead, pawn displacement, and video time together.
- The browser reported no JavaScript errors.

## Boundary

The surface is GET-only and read-only. It cannot open a camera, gateway,
serial bus, simulator replay, physical motion, task attempt, or proof
promotion. C9 is active only to close the future physical work at the external
elbow-service boundary.
