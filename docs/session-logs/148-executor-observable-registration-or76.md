# OR76 executor session

Date: 2026-08-03

OR76 built and ran one software depth-buffer capability frame under the frozen
OR73 camera. It hash-verified every manifest mesh definition, reversed the
declared compiler transforms, rasterized `18,432` selected mesh triangles plus
analytic primitive triangles, and recorded `17,557` occluded fragments. It read
zero physical pixels and fit no parameter.

The card is rejected. Its contract expected `19` unique mesh assets, but the
scene manifest references `18` unique filenames across `36` mesh definitions.
The implementation also loaded each definition independently, causing `36`
asset reads against a frozen budget of `19`. Eleven of twelve image/scene gates
pass, but neither a mistaken expectation nor an unguarded resource overrun may
be edited after the run to manufacture a pass.

The successor must derive the unique asset count from the already hash-bound
manifest, cache exactly `18` unique asset reads for all `36` definitions, and
use all source mesh triangles for the capability frame. OR76 remains a terminal
contract/resource-boundary negative, not visual-fidelity evidence.

Focused verification: `2 passed`.
