from __future__ import annotations

import numpy as np

from sim2claw.hil_evidence import _best_lag


def test_best_lag_recovers_delayed_signal() -> None:
    source = np.asarray([0.0, 0.0, 1.0, 2.0, 3.0, 3.0, 2.0, 1.0])
    target = np.asarray([0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 3.0, 2.0])
    result = _best_lag(source, target, sample_hz=20.0)
    assert result["lag_samples"] == 1
    assert result["lag_seconds"] == 0.05
    assert result["lag_aligned_rmse"] == 0.0


def test_best_lag_breaks_ties_toward_zero() -> None:
    source = np.zeros(20)
    target = np.zeros(20)
    result = _best_lag(source, target, sample_hz=20.0)
    assert result["lag_samples"] == 0
    assert result["lag_seconds"] == 0.0
