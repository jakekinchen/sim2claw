# Executor session 195: OR122

- Verified the OR122 receipt's canonical artifact digest.
- Found that both frozen code identities drifted before closeout: final
  implementation and test hashes do not equal the receipt-bound hashes.
- Reran the focused suite against the final worktree; it fails closed at
  `1 passed, 2 failed` because the source rejects the stale identities.
- Quarantined artifact `4c30dd9347783a04f01b825d8e43d80e41b7fdae7d620b208412365c8dfe9d33`.
  Its development metrics are advisory only and validation stayed unopened.
- Authorized only a fresh identity-bound reproduction. No retry overwrites,
  hardware action, simulator replay, threshold change, transfer claim, or
  promotion are permitted.
