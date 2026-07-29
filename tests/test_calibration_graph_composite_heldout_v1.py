from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_composite_heldout_v1.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_composite_heldout_v1",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_trajectory_metrics_remove_only_constant_image_offset() -> None:
    simulated = np.asarray(
        [
            [0.0, 0.0],
            [2.0, 1.0],
            [4.0, 2.0],
            [0.0, 0.0],
            [0.0, 0.0],
        ],
        dtype=np.float64,
    )
    observed = simulated + np.asarray([20.0, -7.0])
    metrics = MODULE.trajectory_metrics(
        observed,
        simulated,
        np.asarray([True, False, False, True, True]),
    )
    assert metrics["reference_sample_count"] == 3
    assert metrics["displacement_residual_rmse_px"] == pytest.approx(0.0)
    assert metrics["flattened_displacement_correlation"] == pytest.approx(1.0)


def test_trajectory_metrics_require_three_reference_samples() -> None:
    with pytest.raises(RuntimeError, match="reference mask"):
        MODULE.trajectory_metrics(
            np.zeros((4, 2)),
            np.zeros((4, 2)),
            np.asarray([True, False, False, True]),
        )


def test_trajectory_metrics_report_exact_residual() -> None:
    simulated = np.asarray(
        [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        dtype=np.float64,
    )
    observed = simulated.copy()
    observed[1, 0] += 1.0
    reference = np.asarray([True, False, False, True, True])
    metrics = MODULE.trajectory_metrics(observed, simulated, reference)
    assert metrics["reference_sample_count"] == 3
    assert metrics["displacement_residual_rmse_px"] == pytest.approx(
        np.sqrt(1.0 / 5.0)
    )
    assert metrics["displacement_residual_max_px"] == pytest.approx(1.0)
