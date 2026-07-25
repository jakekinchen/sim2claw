# Current 100 mm Metric Registration Readiness v1 — Terminal Missing

Date: `2026-07-24`

Proof class: `physical_measurement_readiness_only`

This is a source-lineage and measurement-readiness result. It is not a camera
calibration, metric pose, geometry/scale closure, simulator improvement,
physical task result, training input, or promotion.

## Frozen transaction

- Baseline: `17d297b2a58dcceec9c9e9449da84746978167dd`
- Preregistration: `86e7c85`
- Reviewed execution implementation:
  `4bdba091d14ca7300e392b47514e06beb92ae001`
- Contract SHA-256:
  `dc8cbd7ee4363943512522774f2fb8e882f7bf88a192768ffdd9d210fd3c4910`
- Input manifest SHA-256:
  `05cb1ba4a9907dab168bf9f62abd08af7d9c388c977d079342dd7730e9bc61f7`
- Evaluator SHA-256:
  `40b1d75109708c9058240e12fd35dae39e7c728f07728a7a26cb255e75b2ea08`

Independent pre-execution review initially found five fail-open proof defects:
caller-declared quadrants, non-rigid transforms, self-attested fit-evaluator
ownership, malformed-data misclassification, and empty decoder identity. The
exact `4bdba09` implementation closes all five. The final narrow review passed
`22 / 22` focused tests and direct counterexample probes before execution.

## Verified existing source

The evaluator independently verified:

- capture receipt:
  `3fafb113a7b89e0b80640b9c7b4cc2016db16ecafcb9f46cba79a79a1330499f`
- C922 overhead video:
  `1643520f5e53ff4694df2cd3ffe102b9f947eb9742678a3e0f2d2f74ba0ececc`
- available source frame:
  `2543230b795c8a61ab6f7ddb1e9c672588ea88958cddbbb84397d689034b5dfc`
- exact `640 × 480` C922 overhead identity, `hflip,vflip` orientation,
  completed video coverage, diagnostic physical-observation proof class, and
  closed training/promotion authority.

The frame remains available pixels only because its deterministic extraction
receipt is missing.

## Terminal result

Verdict: `measurement_prerequisites_missing`

Missing prerequisites:

1. all-four-board-quadrant coverage;
2. direct board measurement;
3. exact-mode camera intrinsics;
4. frame-extraction lineage;
5. independent board-fit evaluation;
6. lens-distortion control;
7. metric object keypoints with uncertainty;
8. minimum independent board correspondences;
9. overhead-camera-to-workcell transform;
10. wrist-camera extrinsics.

There were zero invalid source inputs. The evaluator did not substitute the
historical `355.6 mm` nominal/visual value, a proposal homography, simulator
geometry, or self-scored measurements.

- Evaluation file SHA-256:
  `5900ff1297385d16ca7753aab5dfa89e828e60c49c5e0ee3a470bd704c3cdf7e`
- Evaluation digest:
  `bb7bd2f324710bb61132aec8be575d1a49791274a1dd46dc80fe6e47101e7f7d`
- Receipt file SHA-256:
  `12b1624d6fdb6f2114df274cab2cd80e0b1c97a2aed72e37e8061991371f2df4`
- Receipt digest:
  `18bcbb0297e8660fce22613e66685aba35f11f134f788feef62812a810707057`

## Accounting and authority

Exactly one offline readiness evaluation ran. Camera sessions, captured
frames, robot motions, simulator replays, provider calls, and training rows
were all zero. Twin fidelity remains `0 / 6`; geometry/scale remains
`missing`. The frozen S2 set remains byte-identical at one event, four replays,
and zero measurement trials.

The v1 family is exhausted. A tracked guard and separate control refuse a
second official evaluation before delegation. A later acquisition must use a
new preregistered contract and cannot edit or promote this terminal packet.
