# Brief 034: physical-trace-anchored grasp-retention resolution

## Required outcome

Resolve why the retained physical C2 grasp holds the pawn through transport
while the byte-identical simulator replay closes fully, migrates onto the pawn
head, and loses bilateral contact before release.

## Confirmed evidence

- Physical video SHA-256: `e5cf0b1ab23174e908d509791653d2289a85770476381931384ea2f7308a867b`.
- Physical samples SHA-256: `b93fed706dd205197e9e068aec62d8fe552b822be150218dff5601a1a5eec183`.
- During source indices 246 through 401, the recorder's normalized command and
  measured medians are about 1.07% and 4.39%. The corresponding mapped joint
  medians are -0.15401 and -0.09017 radians. Velocity is flat for 91.6% of rows,
  and closed-minus-open raw current has median 7.
- The video visibly retains the pawn through transport until intended release.
- The simulator is about 3.12 degrees more closed, loses bilateral contact at
  source index 323, uses moving rubber but fixed rigid box6 as its load pair,
  and its fixed rubber sleeve is displaced away from that load surface.

## Execution

1. Freeze and verify the contract and physical/simulator source hashes.
2. Screen each source-bound candidate family on C2 with retention traces.
3. Advance at most four candidates to the three sentinels only after an anchor
   pass, using the frozen tie-break.
4. Freeze at most one composite before running all eleven episodes.
5. Publish the evaluator decision and exact residual. No campaign may expand
   its own grid after results are visible.

## Acceptance

The exact family and gates are in
[`configs/sail/grasp_retention_resolution_v1.json`](../../configs/sail/grasp_retention_resolution_v1.json).
Matching loaded aperture without preserving squeeze, C2 transport, and contact
through release is explicitly not a repair.

Final result: eight frozen families produced 98 byte-identical C2 replays and
zero anchor passes. Sentinel and all-eleven promotion evaluation therefore
remained closed. See
[`2026-07-22-c2-grasp-retention-resolution.md`](../research/2026-07-22-c2-grasp-retention-resolution.md).
