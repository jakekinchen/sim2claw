# Renderer-native held-out visual and physics successor goal loop

## Mission

Build the legitimate successor to OR67: a shared, renderer-native 3D simulator
whose videos predict retained physical footage across distinct action-frozen
episodes. Improve camera, scene, articulation, contact, and object mechanisms
only through declared simulator parameters. Evaluated physical pixels may judge
a frozen candidate; they may never be used to construct its geometry, materials,
background, per-frame state, or post-render image.

This is retrospective cross-episode evidence because no fresh hardware is
available. It can establish retained-corpus generalization, not prospective
physical transfer.

## Source of truth

Read in this order:

1. The owner's latest instruction and `AGENTS.md`.
2. `configs/sail/observable_registration_current_graph_v1.json` and its one
   active card.
3. This goal loop and the observable-registration successor queue.
4. Frozen contracts, source hashes, evaluator receipts, and reviewer closeouts.
5. Historical results as evidence only. OR67 is a quarantined proxy pass, not
   a renderer, physics, or generalization result.

## Non-gameable candidate boundary

A candidate is admissible only when every output pixel is produced by a
declared 3D renderer from a shared scene/model, camera, lights, materials, and
an action-identical simulator state trace or replay. One parameter vector must
apply to every episode in every partition.

The candidate path may not read evaluator footage, OR63/OR66 screen-space
primitives, OR67 materials or video, physical masks, physical edges, physical
colors, physical homographies, background plates, image-derived textures, or
per-episode/per-frame corrections. No compositing, pixel-space overlay, optical
flow warp, target-derived crop, missing-frame substitution, or evaluator change
is admissible. Physical video access must be logged by partition and purpose.

## Frozen corpus and split

Use all 11 recording IDs in the immutable
`frozen_v3_timestep045_all.json` cohort. Sort them by
`SHA256(recording_id)` ascending, then assign positions 1-4 to development,
5-7 to validation, and 8-11 to evaluator-heldout. This rule is frozen before
any successor footage is decoded and is independent of the historical ranked
gallery outcome ordering.

- Development footage may be decoded for parameter fitting and mechanism
  diagnosis.
- Validation footage is evaluator-only and may reject or compare a frozen
  candidate, but it cannot select or modify one.
- Evaluator-heldout footage may be byte-hashed during admission but must not be
  decoded until the shared candidate configuration, code, and inputs are frozen
  and hash-bound. It is opened once for the terminal evaluation.
- Prior historical access means evaluator-heldout is not claimed to be pristine
  prospective data.

## Evaluation ladder

Advance in order; no later score substitutes for an earlier gate:

1. Provenance: exact recording/action identity, deterministic split, shared
   renderer inputs, and anti-leakage audit.
2. Renderer readiness: every episode has an action-identical 3D state trace or
   replay recipe; every frame is produced without physical-image input.
3. Kinematics: shared camera and robot geometry improve development and do not
   regress validation keypoint/trajectory errors.
4. Events: contact, object-motion, lift/support, and terminal event ordering are
   evaluated separately from appearance; missing physical observability abstains.
5. Video: after a single frozen temporal association, each validation and
   evaluator-heldout episode must pass mean full-frame linear pixel similarity
   `>=0.80`, p10 `>=0.75`, motion-union mean `>=0.75`, every declared phase mean
   `>=0.78`, and tolerant-edge F1 `>=0.40`.

Pixel similarity alone cannot close the physics or operational delta. Completion
requires every mandatory provenance, renderer, kinematic, observable event, and
video gate on the evaluator-heldout partition with no per-episode refit.

## Evidence and decision rules

Each card freezes one smallest mechanism family before execution, runs a bounded
candidate set, and records source hashes, decoded partitions, shared parameters,
actions, timestamps, renderer provenance, per-episode metrics, failures, proof
limits, and a reviewer decision. A candidate may advance only on development;
validation and evaluator-heldout can reject but never tune it. Training code,
candidate code, and a visually plausible video cannot promote themselves.

If the local renderer is unavailable, first finish all metadata-only admission,
trace, evaluator, and anti-leakage work. Escalate to GPT Pro research only when
local evidence cannot choose among technically admissible renderer or evaluation
routes; independently verify any adopted advice.

## Progress ledger

```text
Current state: successor requested; OR68 cross-episode admission proposed
Completed: OR67 preserved as an episode-specific screen-space proxy pass
Evidence: 11 physical/action-frozen recordings exist; 7 have published shared-scene state traces; 4 require renderer-native trace regeneration
Remaining: freeze split and provenance, regenerate missing traces, establish renderer runtime, freeze evaluator, tune development only, validate once, evaluate heldout once
Blockers: no fresh hardware; current retained holdout is retrospective; local renderer availability must be re-established
Next step: execute OR68 metadata-only cross-episode admission without decoding physical footage
```
