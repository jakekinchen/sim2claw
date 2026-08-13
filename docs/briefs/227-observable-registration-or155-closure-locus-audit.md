# OR155 closure-locus and contact-provenance audit

OR155 is a read-only, zero-dynamics reproduction of an already observed
discrepancy. The user reports that the simulated gripper closes before its
center reaches the first square, while the retained physical wrist footage
appears to close around the centered pawn. GPT Pro and Fable 5 Extra were
consulted independently against exact pushed commit
`d4f477bac60058b224ca4173c37078b31a7a44d0`; both reject another task replay
and admit only a diagnostic audit.

The audit keeps the exact OR154 scene, raw measured rows, exact-D1 pawn state,
and immutable OR154 trace. It may call `mj_forward` to report the named jaw-tip
midpoint relative to D1 during physical enclosure and command closure, compare
requested/sent/measured gripper rows, and reconstruct collision distances at
OR154's first broad body-level contact sample. It also binds OR149's nominal,
unsynchronized presentation boundary and the existing fit/validation exposure
ledger.

No dynamics step, replay, fit, search, render, task evaluation, action change,
timestamp rebinding, camera change, collision change, hardware action, or paid
compute is allowed. The diagnostic was explored locally before this contract
was frozen, so its result is outcome-known and permanently cannot select a
simulator correction. Its value is a durable, independently reviewable answer
to the discrepancy—not a new success claim.
