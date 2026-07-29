from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_d405_corner_shape_heldout_v2.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_d405_corner_shape_heldout_v2",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_shape_metrics_report_scale_invariant_identity() -> None:
    observed = np.asarray([0.0, 2.0, 4.0, 2.0, 0.0])
    simulated = observed * 0.5
    metrics = MODULE.trajectory_shape_metrics(observed, simulated)
    assert metrics["normalized_shape_rmse"] == 0.0
    assert metrics["normalized_shape_max_error"] == 0.0
    assert metrics["normalized_shape_correlation"] == pytest.approx(1.0)


def test_shape_metrics_report_temporal_mismatch() -> None:
    observed = np.asarray([0.0, 1.0, 2.0, 1.0, 0.0])
    simulated = np.asarray([0.0, 0.0, 1.0, 2.0, 1.0])
    metrics = MODULE.trajectory_shape_metrics(observed, simulated)
    assert metrics["normalized_shape_rmse"] > 0.0
    assert metrics["normalized_shape_correlation"] < 1.0


def test_shape_metrics_reject_no_signal() -> None:
    with pytest.raises(RuntimeError, match="no signal"):
        MODULE.trajectory_shape_metrics(
            np.zeros(5, dtype=np.float64),
            np.ones(5, dtype=np.float64),
        )
