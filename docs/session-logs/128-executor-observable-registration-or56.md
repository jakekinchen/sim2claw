# OR56 executor session

Date: 2026-08-02

OR56 fit twelve time-invariant camera-response/blur variants on `220`
development frames only. The selected diagonal BGR transform uses gain `0.5`
and bias `+64` on every channel with a `7 px` Gaussian kernel. Validation and
stress were not read for selection.

The selected response improves full-frame mean similarity by `0.087243` on
development, `0.089550` on the untouched `180`-frame validation partition,
and `0.088126` on the `116`-frame stress partition. The decoded emitted video
scores `0.793053` mean, `0.783518` p10, and `0.754035` motion-union mean under
the unchanged OR55 evaluator. Those p10, motion, and all-phase gates pass;
the mean remains `0.006947` below target.

Mean tolerant-edge F1 falls from the OR55 baseline `0.226697` to `0.133238`.
This confirms that global exposure/color/blur can recover most of the average
pixel loss but masks rather than repairs the geometry. The next card keeps the
global matrix frozen, reopens only the four preregistered blur choices, and
tests a small board-preserving camera-parallax family by development edge F1
before opening validation and stress.

OR56 altered no action, physics, state, geometry, or camera pose; it ran no
simulator episode and used no physical pixels as a composite, texture, or
background plate. Its candidate is a permanently episode-specific visual
diagnostic and supplies no physics, task-transfer, or promotion proof.

Focused verification: `6 passed` across OR56, OR55, and OR26.
