# Executor Session Log 010 - SAIL Phase-Aligned Residual Field

**Date:** 2026-07-22

## Slice

P1-03 — build the phase-aligned residual field.

## Implemented

- Observable five-phase segmentation and six event landmarks from the bound
  mapped-measured gripper channel.
- Strict time-base validation, finite differences, and mask-safe linear
  resampling that neither extrapolates nor fills unavailable gaps.
- Complete physical command/measured, real/sim joint and velocity, EE,
  aperture, and event-timing residual curves with units, frames, masks, and
  evidence provenance.
- Explicit abstentions for retained EE-source, EE-target, pawn-target,
  physical-contact, contact-force, and consequence channels.
- Episode/phase/global robust summaries and deterministic whole-episode
  bootstrap intervals.
- Receipt-bound JSON/SVG heatmap and episode drilldowns.
- CLI compilation, compiler/config drift checks, action identity checks, and
  GOLD-03/GOLD-04 coverage.

## Validation

- Focused tier: 30 passed.
- Broad tier: 650 passed, three skipped, all 328 subtests passed.
- Two compilation runs and the complete output tree matched byte-for-byte.
- Python compilation and `git diff --check`: pass.

## Known limitations

The retained sources do not include metric source/target/pawn trajectories,
physical contact force/state, or formal physical consequences. These channels
abstain. Phase boundaries are observable gripper/event landmarks rather than
physical contact claims. Bootstrap intervals describe the 11 retained episodes
from one acquisition context and are not population or transfer evidence.
