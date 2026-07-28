# Sign-reversed pan-play canary ready

Date: 2026-07-27
Branch: `codex/anchored-transfer-20260727`
Status: `approved_readiness_only`

The action-frozen shoulder-pan play diagnostic selected a `0.40 deg` radius on
historical execution-v4. Retrospective validation on v2 passed every frozen
tighter gate while leaving the source and mapped action hashes unchanged.
This is a self-scored actuator-model diagnostic, not a promoted calibration.

The held-out packet is
`runs/anchored-transfer-canary/fresh-current-pose-v3-sign-reversed/physical-canary-packet.json`.
It binds 57 exact float64 rows, negative-first order, a `[-1,+1] deg` pan
range, invariant non-pan channels, and a 20-row final anchor hold. Its action
SHA is
`f4692749e5108e1b213ae0bbd536cf393193faecd86051a350c6e09d18bb294b`.

The baseline prediction SHA is
`bcc1976ed69b1f5ea6503fd3f35b397e3666392982f551c76fe65bdcf6b270b0`.
The receipt-bound 0.40-degree prediction SHA is
`2a51d3f7ce8c0866f46882f4343c04971e13b1fc4b01d14b3ee9bc96e7382b97`.
Both predictions reproduced independently without clipping or source-action
rewriting.

Independent review decision
`safe-canary-audit-20260727-heldout-sign-reversed-readiness-v1` approved only
physical readiness. The packet file SHA is
`bd75069216b1ca9a018e3d170ab7276102e1664bc8c48697f3e5f60ccfabdbbb`.
The target directory had no execution receipt or execution directory at
review time. The packet retains `physical_packet_execution_admitted=false`;
no physical motion was commanded in this follow-on.

Proof caveats:

- The kinematic contact preview has no configured contact regression or
  external pair, but reports no metric minimum-distance value.
- The fitted radius is retrospective, self-scored, and non-promotional.
