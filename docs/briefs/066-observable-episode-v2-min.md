# Brief 066 — ObservableEpisode.v2-min

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Implement the smallest strict causal episode needed by the canonical
bidirectional transfer campaign. Preserve requested, mapped, sent, and applied
commands separately; retain timestamps and missingness; bind joints, link
poses, board-plane pawn SE(2), covariance, contact, first motion, and final
outcome.

## Acceptance

The simulator and physical-source adapters serialize deterministic synthetic
fixtures. The validator rejects changed action hashes, nonmonotonic timing,
fabricated unavailable contact probability, invalid covariance, and partial
action channels. First-divergence extraction reports action application before
downstream joint, link, contact, object, or outcome differences.

## Stop

This slice opens neither MuJoCo task replay nor hardware. It authorizes a
separately frozen CC02 replay that emits the accepted episode schema.
