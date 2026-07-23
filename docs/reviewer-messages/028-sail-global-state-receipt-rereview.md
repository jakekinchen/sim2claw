# Reviewer disposition 028: SAIL state and receipt corrective handoff

Status: `READY FOR INDEPENDENT REREVIEW; NO MERGE AUTHORITY`

The terminal retained-C2 result remains
`abstain_measurement_acquisition_required`. No new simulator evaluation,
measurement trial, training admission, physical capture, or robot motion was
opened.

Generic simulator evidence admission is now disabled. A receipt, result, raw
bundle, hashes, and copied evaluator identity can be mutually consistent while
remaining agent-authored; without a trusted deterministic adapter that
recomputes concrete mutations and consequence, that bundle fails closed. The
packet-bound synthetic measurement lane remains admissible because its
features, classification, likelihoods, and consequence are recomputed locally
from the raw fixture under the frozen contract.

Persistent state now has one canonical ignored path under
`outputs/sail/live-campaign-state-v1`, keyed by campaign ID and canonical config
digest and independent of `--output`. Alternate and escaping roots fail.
Admissions are prepared in memory; selected intervention, affected-factor
scope, likelihoods, consequence, closure, every output artifact, and the final
receipt validate before the append-only state transition is the final write. A
poisoned unaffected-factor update leaves state bytes and budgets unchanged.

The exported `verify_live_operator_receipt` rechecks the canonical receipt
digest; config, source, compiler and output hashes; action/evaluator/
intervention identities; the current state hash, digest, chain and budget; and
all-false promotion, training, and physical authority. Artifact tamper,
resealed authority tamper, and receipts stale against a later state head fail.

The exact comparison remains: 514 historical evaluations informed the frozen
retrospective decision; SAIL used zero additional evaluations after the pause.
This is improved control-plane integrity, not demonstrated twin-error
reduction. PR creation and merge to main remain owner decisions.
