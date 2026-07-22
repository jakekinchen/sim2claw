from __future__ import annotations

import numpy as np

from sim2claw.pawn_bg_grasp_closeout import paired_bootstrap


def test_paired_bootstrap_is_deterministic_and_whole_episode() -> None:
    baseline = np.asarray([0, 0, 1, 0], dtype=np.int8)
    candidate = np.asarray([1, 0, 1, 1], dtype=np.int8)
    first = paired_bootstrap(baseline, candidate, seed=7, replicates=2000)
    second = paired_bootstrap(baseline, candidate, seed=7, replicates=2000)
    assert first == second
    assert first["point_mean_delta"] == 0.5
    assert first["unit"] == "whole_episode"
