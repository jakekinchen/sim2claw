# Phase A REAL → SIM partial — D1→D2

Release:
`https://github.com/jakekinchen/sim2claw/releases/tag/phase-a-real-to-sim-d1-d2-20260727`

This is the smallest public application artifact for the current Phase A
result. It shows a visibly verified physical D1→D2 pawn move beside a
MuJoCo/CAD reconstruction driven by the observed physical joint states. The
third lane stays visibly blocked because the source action was not eligible
for exact physics replay.

## What passed

- C922 review shows an upright brown pawn on D1 at the start and upright on D2
  at the end.
- The 531-row observed-joint trace is hash-bound to the visual/kinematic twin.
- The composite MP4 is browser-playable H.264 at 640×1080, 20 fps, 531 frames,
  and 26.55 seconds.
- Studio admits the exact hash-bound asset and labels it `REAL → SIM Partial`
  with `Physics gate Blocked`.
- The physics lane fails closed instead of clipping, retiming, repairing, or
  inventing object motion.

## What did not pass

- No action-frozen physics replay was executed.
- No simulator task success, SIM→REAL task transfer, bidirectional transfer,
  training admission, physical-control authority, or six-domain Twin fidelity
  is claimed.
- The current project headline remains `TWIN FIDELITY 0/6` and
  `TASK SCORE 0/11`.

The historical source is ineligible for exact replay: 0/531 rows were marked
precompiled exact, 151/531 rows were gateway rate-limited and safety-clamped,
284/531 requested rows differ from gateway-sent rows, actuator application
acknowledgements are absent, the source contract requires float32 replay rather
than frozen float64, direct targets exceed current MuJoCo controls, and host
timing is irregular. Those facts are preserved rather than repaired or
relabeled.

## Public assets

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `phase_a_comparison.mp4` | 2,035,913 | `fa265434d04ac25ed99264e866eb8b7563142d5580a135bcec78bfd4742c327d` |
| `phase_a_comparison_poster.png` | 875,143 | `ef5fd26cd3815227ebb5dc8cff4725f6724a702cad2eff5f0933623fdb1a7e3a` |

`PUBLIC_RECEIPT.json` is the redacted machine-readable claim and asset
contract. The private source recordings, full dataset, kinematic trace,
credentials, local paths, and device or network identifiers are not included.

## Proof class

`physical_source_to_visual_kinematic_simulator_partial`

The physical endpoint result is square-level camera evidence. The visual twin
reconstructs robot motion from observed joints and has no object-contact or
physics authority. The missing physics lane is explicit evidence of an
eligibility failure, not a successful replay.
