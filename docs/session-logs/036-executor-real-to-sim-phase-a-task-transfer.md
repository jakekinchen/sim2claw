# Session 036 — Phase A real-to-sim task transfer

Date: 2026-07-27
Branch: `codex/geometric-microtransfer-20260727`

## Work completed

- Inspected the real C922 and D405 footage plus samples and receipts for both
  fresh operator recordings.
- Selected D1→D2 because the physical start and upright terminal square were
  clearest, the dual-camera lineage was complete, and the nominal scene already
  contains `brown_pawn_d1`.
- Added a receipt-bound comparison to the existing Studio episode flow:
  original C922, observed-joint MuJoCo visual reconstruction, and a visible
  action-frozen-physics blocker.
- Preserved the source receipt's stale B2→B1 instruction and square fields as a
  conflict; raw evidence was not rewritten.
- Kept the pawn at its reviewed source endpoint until grasp, hid it during the
  unmeasured carry, and displayed its reviewed D2 endpoint after release.
- Did not open a robot bus, enable torque, or move hardware.

## Result

Phase A visual artifact passed. Exact action replay is ineligible: no row is a
precompiled exact action; 151/531 rows were rate limited and safety clamped;
284/531 requested rows differ from gateway-sent rows; actuator
application/ack timestamps are absent; the receipt requires float32 replay;
direct targets exceed present MuJoCo controls; and fixed-step replay would
require forbidden retiming.

The browser-loaded artifact reports `REAL → SIM Partial` and
`Physics gate Blocked`. Phase B was not started in this session.
