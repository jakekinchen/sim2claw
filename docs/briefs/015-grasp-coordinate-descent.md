# Brief 015: Action-frozen grasp coordinate descent

Decision: `CONTINUE`

Evidence anchor: `100` — the previous campaign verified a 6.461% pooled-CV
joint-RMS improvement with byte-identical actions, but lift regressed to 1/11
and strict success remained 0/11. Contact alone is saturated at 11/11 and is no
longer a useful selection metric.

## Required outcome

Verify one consequence-level simulator win under unchanged source actions:

- at least 6/11 episodes both lift and make at least 50% targetward planar
  progress after lift, including at least 4/8 campaign-held evaluation
  episodes; or
- at least one unchanged-evaluator strict task success.

Joint and EE RMS must remain within 1% of the accepted trace baseline. A paired
whole-episode bootstrap must support a positive lift-and-transport delta.

## First slice

Instrument bilateral jaw contact, contact span, opposing contact normals,
post-closure retention, pawn slip in the gripper frame, lift, targetward
transport, placement, release, and original strict gates. Then run a frozen
three-point-or-wider coordinate ladder over gripper force/response, rubber-tip
geometry, friction/softness, and pawn mass/friction.

Only three declared sentinels may steer adaptive selection. Freeze the final
parameter vector and its digest before opening the other eight episodes.

## Boundaries

- Never mutate, clip, offset, retarget, or append to source actions.
- Do not select on the two already-opened confirmation episodes.
- Parameter sweeps establish simulator sensitivity only.
- A task win does not establish physical calibration or transfer.
- If contact geometry improves touching but not retained lift, redirect toward
  gripper transmission/force and opposing-contact formation before more
  friction.
