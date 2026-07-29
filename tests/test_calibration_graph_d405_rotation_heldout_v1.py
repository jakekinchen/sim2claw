from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_d405_rotation_heldout_v1.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_d405_rotation_heldout_v1",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rotation_metrics_report_identity_trajectory() -> None:
    values = np.asarray([0.0, 0.5, 1.0, 0.5, 0.0])
    metrics = MODULE.rotation_trajectory_metrics(values, values)
    assert metrics["observed_over_simulated_rotation_rms_ratio"] == 1.0
    assert metrics["rotation_angle_rmse_degrees"] == 0.0
    assert metrics["rotation_angle_correlation"] == pytest.approx(1.0)


def test_rotation_metrics_report_scale_and_residual() -> None:
    observed = np.asarray([0.0, 0.5, 1.0, 0.5, 0.0])
    simulated = observed * 2.0
    metrics = MODULE.rotation_trajectory_metrics(observed, simulated)
    assert metrics["observed_over_simulated_rotation_rms_ratio"] == 0.5
    assert metrics["rotation_angle_rmse_degrees"] == pytest.approx(
        np.sqrt((0.25 + 1.0 + 0.25) / 5.0)
    )


def test_rotation_metrics_reject_malformed_arrays() -> None:
    with pytest.raises(RuntimeError, match="invalid"):
        MODULE.rotation_trajectory_metrics(
            np.zeros((2, 2)), np.zeros((2, 2))
        )
