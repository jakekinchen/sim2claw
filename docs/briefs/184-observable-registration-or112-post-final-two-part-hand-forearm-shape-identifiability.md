# OR112: two-part hand/forearm shape identifiability

OR111 shows that the 3D renderer preserves the single-capsule silhouette and
scene visibility; the frozen capsule itself lacks boundary detail. OR112 tests
the smallest extra degree of freedom without rendering:

- compute the full component PCA axis;
- orient it so the endpoint nearest any image border is proximal;
- split component pixels once at the median axial coordinate;
- fit the unchanged OR109 deterministic capsule to each half;
- compare their union with the OR109 single capsule on the reused development
  and validation cohorts.

The split is not searched or refit. Passing requires both shape overlap and
local physical-edge improvement. The result remains a 2D, post-final,
retained-footage-conditioned shape diagnostic.
