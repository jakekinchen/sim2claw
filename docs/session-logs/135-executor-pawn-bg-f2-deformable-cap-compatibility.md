# OR135 executor log

OR135's single rigid compatibility run reproduced the historical dynamics and
compiled model, but its hash-bound independent compatibility evaluator used the
wrong sampling domain for one retained statistic. The compiled MJB SHA-256 was
exactly `9e93243ffa094853c37bfe8dfa4378df1b3eb42ff8885af2452dd359530f4ea3`.
The producer/source-boundary final target distance, maximum rise, lift,
qualified bilateral contact, and upright values all reproduced exactly.

The frozen independent verifier compared the retained source-boundary maximum
rise (`0.042395539952 m`) to the full-integration-step maximum rise
(`0.046678285044 m`). Reconstructing the historical 440 action boundaries plus
the terminal row from the complete OR135 trace returns exactly
`0.042395539952 m`. This establishes an evaluator-sampling mismatch, not a
dynamics mismatch.

OR135 cannot correct its verifier after reading the result. It therefore closes
as `TERMINAL_INDEPENDENT_COMPATIBILITY_SAMPLING_DOMAIN_MISMATCH_NO_FLEX_EXECUTED`.
Exactly one rigid run and zero flex runs executed. OR136 must freeze separate
source-boundary compatibility and full-step strict metrics, then execute a fresh
rigid replay before any flex candidate.
