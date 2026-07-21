# Simulator and policy-training progression ledger

Date: 2026-07-19 America/Chicago

Machine-readable snapshot:
`docs/run-logs/2026-07-19-simulator-progression-ledger.json`.

![Sequential simulator spatial-error progression](2026-07-19-simulator-accuracy-progression.svg)

## Metric boundary

This ledger deliberately separates four metric families:

1. spatial event-fit error in meters;
2. command-driven replay consequences such as contact, lift, and task success;
3. actuator joint-tracking RMS in degrees;
4. learned-policy optimization loss and open-loop action error.

Values from different families are not interchangeable. Training loss is a
diagnostic of optimizer fit, not simulator fidelity or task success. A new
simulator or training revision should append a row with its Git commit,
contract/receipt identity, data split, proof state, and all available
consequence counts. Rejected and terminal-negative rows remain in the ledger.

## B-G spatial and replay progression

The chart treats each row as the next simulator optimization action on one
continuum. Its y-axis is training-side event RMS error in millimeters, so lower
is better. The first two points are committed evidence; the remaining points
are explicitly marked as working receipts from the active Claude worktree.

| Revision | Proof state | Split | Event RMS | Contact | Lift | Full success |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Provisional identity | committed terminal negative | train | 309.55 mm | 0/11 | 0/11 | 0/11 |
| Free-sign source adapter | committed rejected candidate | train | 118.42 mm | 0/11 | 0/11 | 0/11 |
| 180 degree board relabel | uncommitted working receipt | train | 106.71 mm | not replayed separately | not replayed separately | not replayed separately |
| Planar board fit | uncommitted working receipt | train | 89.41 mm | not replayed separately | not replayed separately | not replayed separately |
| Small joint offsets | uncommitted working receipt | train | 39.70 mm | 0/11 | 0/11 | 0/11 |
| Height and timing nuisance | uncommitted working receipt | train | 26.14 mm | 0/11 | 0/11 | 0/11 |
| Lift-dominant offset | uncommitted working receipt | train | 17.41 mm | 9/11 | 1/11 | 0/11 |
| Frozen lift-dominant candidate | uncommitted kinematic-only admission | held out | 23.55 mm | 2/2 | 0/2 | 0/2 |

The simulator became much closer in the event-fit metric, and the latest
working candidate finally produced contact. It has not produced a complete
pawn move. Its held-out admission is kinematic-only and does not grant policy,
training, physical-calibration, or physical-motion authority.

## 2026-07-20 dynamics continuation (metric family 3: joint-tracking degrees)

Appended per the required-fields rule; details and receipts in
`docs/run-logs/2026-07-20-pawn-bg-dynamics-grasp-observability.md`.

| Revision | Proof state | Split | Joint-tracking RMS | Stall reproduction (lift/elbow) | Contact | Full success |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Frozen candidate, nominal dynamics | working receipt | train | 2.041 deg | 3% / 1% | 9/11 | 0/11 |
| Global scale fit (gain/damping/force) | working receipt, near-null | train | 2.032 deg | unchanged | not rerun | 0/11 |
| Per-joint bounded fit (latency identified, 50.6 ms) | working receipt | train | 1.622 deg | 9% / 6% | 9/11 | 0/11 |
| Per-joint bounded fit | working receipt, held-out reuse labeled (already opened) | held out | 1.640 deg (from 2.132) | 27% / 3% | 2/2 | 0/2 |

The identified latency is the only dynamics parameter the recorded episodes
support; the hold-sag that gates grasp retention needs either a
deadband-capable actuator model or measured object trajectories before it can
be fitted honestly.

## Policy-loss evidence

Full per-step GR00T histories exist for the nominal 5,000-step chess run, the
1,000-step phase-progress challenger, the 1,000-step current-geometry pawn run,
and the 1,000-step multisource run. ACT retained only aggregate final and
last-100 loss values for its three recipes.

The ACT receipts demonstrate why loss must not select a model: recipe 1 has
the lowest final loss (`0.01674`) but failed its closed-loop episode, while
recipe 3 has higher final loss (`0.03175`) and passed only the narrow rook-lift
v1 evaluator. GR00T likewise reduced optimization loss substantially while
the separately owned task evaluators remained terminal-negative.

## Required fields for future rows

- timestamp and Git commit or explicit `uncommitted` state;
- simulator/configuration change;
- dataset and train/held-out split identity;
- receipt path plus SHA-256 when frozen;
- event-fit RMS when available;
- clipping, contact, lift, and strict-success counts;
- final target error and collateral/safety gates;
- optimizer loss and open-loop error only when a policy was actually trained;
- explicit proof class and promotion authority.
