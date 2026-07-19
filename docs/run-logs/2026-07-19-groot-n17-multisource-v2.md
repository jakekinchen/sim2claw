# GR00T N1.7 Multisource 100 mm Campaign

Date: 2026-07-19 UTC (2026-07-18 America/Chicago)

## Outcome

The bounded GR00T N1.7 multisource fine-tune completed 1,000 optimizer steps,
but its single predeclared current-geometry development rollout was a strict
terminal negative. The C8 pawn was not lifted or moved toward A6. This run
therefore grants no pawn, held-out, multi-piece, physical, or sim-to-real
authority.

The pre-run configuration's `current_pawn_authority_scope` identifies only the
narrow provenance of the admitted C8-to-A6 source episode. It is not a learned
model capability claim. The unchanged CPU/fp32 consequence evaluator owns that
decision, and it rejected the trained checkpoint.

## Admitted mixture

- 73 unique simulation source episodes and 28,162 unique source frames;
- 96 derived/weighted dataset episodes and 41,088 synchronized RGB, state,
  language, and action frames;
- 24 historical nominal rook/king episodes plus 48 evaluator-passing recovery
  episodes, retained as old-geometry skill priors;
- one evaluator-admitted current 100 mm C8-to-A6 pawn episode repeated 24 times
  as sampling weight, not as 24 independent pieces of evidence;
- 39,648 unpadded H16 starts, 634,368 action targets, and 3,806,208 action
  scalars.

The four current-geometry failed episodes contributed zero behavior-cloning
rows. Five 72 mm physical recordings, including 2,186 samples and five videos,
remained quarantined because their outcomes, labels, and geometry were not
reconciled. Every held-out split remained sealed and contributed zero rows.

Frozen dataset identities:

- contract SHA-256:
  `a5679e4efcba5c53bb6007b655aa595901f3d23e190c855f7970e37356a8a3da`;
- dataset receipt SHA-256:
  `990c520edbf8492eb77a38586772af1b383ef65f5a1d2efbfb37dbf9820452d7`;
- payload manifest SHA-256:
  `ea193e2e35e71fef64e40646e0a9d5db04286c8fe6255b97e149180e22604d12`;
- pinned NVIDIA loader receipt SHA-256:
  `a564208809e0ec783f0b161027c03393996232a1626008201ab6347fe6df65db`.

## Training

The one-challenger run started from the clean pinned
`nvidia/GR00T-N1.7-3B` base rather than a prior chess checkpoint. It finished
1,000 optimizer steps in 351.323 seconds with final reported training loss
`0.5443627974390983`. Checkpoint manifests were recorded at steps 250, 500,
750, and 1,000. The checkpoint-1,000 manifest SHA-256 is
`0e2f8376f7d8f2853dd06ef4f807a5c0e7801746548b224ec69ec4f1ce69c2fd`,
and the top-level training receipt SHA-256 is
`93c4d2fa3b66d841df0354b1bc7ea0753fec0ff9cc275d1b7780c351851cef1e`.

An earlier offline model-path launch failed before its first optimizer step
and is recorded separately. It is not training evidence. Two later evaluator
startup misses made zero policy queries and are likewise separate
infrastructure receipts, not rollouts.

## Frozen development result

Only checkpoint 1,000 and the predeclared C8-to-A6 development case were run.
The rollout used 71 policy queries and 562 model-owned actions with zero
assistance or reward guidance. Exact sample-hold replay passed for all 562
actions, but only 13 of 15 consequence gates passed:

- maximum pawn rise: `0.0 m`, below the required `0.04 m`;
- final XY error: `0.12572358052399646 m`, above the allowed `0.015 m`;
- target displacement: approximately `5.217e-8 m`.

The development receipt SHA-256 is
`6864aa325210e8e199a6a3bd12da0c556e92acc880d8f63061edfd1aa0685c4d`,
with canonical payload
`d402c82c9438a025b5a084d18499b756a1e5fc3657740bdfca8008186709e60c`.
The trajectory and video SHA-256 values are respectively
`1753877eac345cfdecebc80e4e4be6217e264e39f86fd92a2f69a35438751118`
and
`252a9ad7ee726e29aa43c568f81c62459bc46056769ad6e7c774ab52f8f8e882`.

This result must not be conflated with the older `development-v1` attempt,
which recorded 25.20 mm rise and 139.07 mm final XY error. No held-out episode
was opened after the current development gate failed.

## Evidence retention and teardown

The immutable external archive ID is
`groot-n17-multisource-v2-20260719T060030Z`. Its compact evidence tarball,
`groot-n17-multisource-20260719-evidence.tgz`, is 367,711 bytes with SHA-256
`0cc871b19ea009c4aae43abd1d2d408096fe27637b820190b4d0b8f818adf0f7`.
The archive's `MANIFEST.json` SHA-256 is
`dae1c400eb61a86b8dbdc60ed2c747a3f60b907cfb0c76b67a483927050d40b1`.

Full checkpoint weights were intentionally not retained after the terminal
negative. Their approximately 12.6 GB transfer projected about 45 additional
minutes on a non-stoppable paid worker. The incomplete local transfer was
removed; the four checkpoint manifests remain evidence identities, not
recoverable model artifacts.

The policy server was stopped, the GPU process inventory reached zero, and
Brev worker `908o7pu3f` was deleted. Final authenticated `brev ls --json`
returned `{"workspaces": null}`. No paid worker remains.

## Repository containment

Only source, tests, frozen JSON contracts, and launch/evaluation scripts are
tracked here. The scripts' `/home/shadeform/...` defaults are deliberate paths
for the recorded Brev runtime, not local checkout or artifact paths. No token
value, generated dataset, video, trajectory, archive, or checkpoint is part of
this change set.
