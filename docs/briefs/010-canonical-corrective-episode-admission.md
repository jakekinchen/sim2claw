# Brief 010: Canonical Corrective Episode and Admission

Decision: `COMPLETE`

Evidence anchor: `100` — branch execution and LF evidence exist, but the
compiled actions are not yet authenticated against canonical episode rows.

## Slice objective

Complete T07 with one hardware-free canonical corrective source candidate and
an unchanged independent evaluator admission that exports suffix rows only.

## Required implementation

1. Add a bounded corrective-action override hook to the existing repo-native
   pawn geometric source generator.
2. Require contiguous, finite, in-range float32 actions and immutable proposal,
   compiler, branch, parent, and intervention lineage.
3. Mark exactly those rows as interventions while retaining
   `geometric_expert` as action owner.
4. Record fresh RGB, observable state, contacts, and evaluator-only MuJoCo state
   for every corrected row; do not copy stale frames or states.
5. Harden LF-12 so a v1 LLM intervention is rejected unless its compiled action
   rows exactly equal the canonical corrective episode rows beginning at the
   declared branch.
6. Run the unchanged pawn evaluator over the entire episode before constructing
   a corrective-suffix verdict.
7. Prove the existing adapter returns zero failed-prefix rows and only the
   evaluator-approved suffix.

## Fixture boundary

The first successful fixture may attach an early, bounded pregrasp perturbation
to the existing off-product C8-to-A6 geometric episode. It proves the mechanism
only; it is not B--G, learned-policy, or sim-to-real evidence. Its parent
counterexample must remain explicitly synthetic unless a real evaluator-owned
failed trace is used.

## Rejections

- Non-contiguous override indices.
- Override action requiring clipping.
- Proposal/compiler/branch digest mismatch.
- Intervention row mismatch, wrong owner, or missing intervention bit.
- Branch state that differs from the canonical state before the suffix.
- Ordinary success relabeled as corrective admission without evidence bindings.

## Verification outcome

The canonical C8-to-A6 fixture preserves the nominal prefix, inserts five
compiler-authenticated corrective actions, records fresh rows, passes the
unchanged strict full-episode evaluator, and admits 561 suffix rows with zero
failed-prefix or held-out rows. The follow-on dataset fixture byte-binds those
rows and a two-update CPU ACT checkpoint; its independent finite-action runtime
smoke is explicitly non-behavioral. The proof remains synthetic/off-product.
