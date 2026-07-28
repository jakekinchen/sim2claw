from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from sim2claw.d405_metric_surface_plane import (
    D405MetricSurfacePlaneError,
    evaluate_d405_metric_surface_plane,
    fit_metric_surface_plane,
    load_contract,
)
from sim2claw.paths import REPO_ROOT


def _intrinsics(width: int = 160, height: int = 120) -> dict:
    return {
        "width": width,
        "height": height,
        "focal_length_px": [140.0, 140.0],
        "principal_point_px": [(width - 1) / 2, (height - 1) / 2],
        "distortion_model": "Brown Conrady",
        "distortion_coefficients": [0.0] * 5,
    }


def _synthetic_depth(
    *,
    normal: np.ndarray = np.asarray([-0.16, 0.12, 0.98]),
    offset_m: float = -0.10,
    seed: int = 7,
) -> np.ndarray:
    intrinsics = _intrinsics()
    height, width = intrinsics["height"], intrinsics["width"]
    rows, columns = np.indices((height, width))
    fx, fy = intrinsics["focal_length_px"]
    ppx, ppy = intrinsics["principal_point_px"]
    rays = np.stack(
        ((columns - ppx) / fx, (rows - ppy) / fy, np.ones_like(rows)), axis=-1
    )
    normal = normal / np.linalg.norm(normal)
    depth = -offset_m / (rays @ normal)
    rng = np.random.default_rng(seed)
    depth += rng.normal(0.0, 0.00015, depth.shape)
    outliers = rng.random(depth.shape) < 0.25
    depth[outliers] += rng.uniform(0.005, 0.025, np.count_nonzero(outliers))
    depth[rng.random(depth.shape) < 0.05] = 0.0
    return depth


def _synthetic_contract() -> dict:
    contract = deepcopy(load_contract())
    contract["sample_stride_px"] = 2
    contract["ransac_iterations"] = 250
    contract["minimum_valid_pixel_fraction"] = 0.5
    contract["depth_range_m"] = [0.04, 0.3]
    return contract


def test_robust_plane_fit_recovers_metric_synthetic_surface() -> None:
    expected_normal = np.asarray([-0.16, 0.12, 0.98])
    expected_normal /= np.linalg.norm(expected_normal)

    result = fit_metric_surface_plane(
        _synthetic_depth(normal=expected_normal),
        _intrinsics(),
        _synthetic_contract(),
    )

    angle = np.degrees(
        np.arccos(np.clip(np.dot(result["normal_camera_unit"], expected_normal), -1, 1))
    )
    assert angle < 0.2
    assert result["camera_optical_origin_perpendicular_distance_m"] == pytest.approx(
        0.1, abs=0.0003
    )
    assert result["plane_inlier_fraction_of_valid"] > 0.65
    assert result["residuals_m"]["rms"] < 0.0003


def test_existing_stationary_metric_surface_plane_passes_bounded_proof() -> None:
    capture = REPO_ROOT / "runs" / "d405-rgbd-capture" / "20260725-stationary-v2"
    accepted = capture / "evaluation" / "receipt.json"
    if not accepted.is_file():
        pytest.skip("ignored accepted stationary D405 receipt is not present")

    receipt = evaluate_d405_metric_surface_plane(capture)

    assert receipt["verdict"]["passed"] is True
    assert receipt["proof_class"] == (
        "physical_stationary_metric_surface_plane_observation_only"
    )
    assert len(receipt["frames"]) == 2
    assert receipt["cross_frame_stability"][
        "maximum_adjacent_normal_angle_degrees"
    ] < 0.5
    assert receipt["rgb_grid_visibility"]["partial_grid"] is True
    assert receipt["rgb_grid_visibility"]["full_grid_registration"] is False
    assert all(value is False for value in receipt["authority"].values())


def test_existing_artifact_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    capture = REPO_ROOT / "runs" / "d405-rgbd-capture" / "20260725-stationary-v2"
    accepted = capture / "evaluation" / "receipt.json"
    if not accepted.is_file():
        pytest.skip("ignored accepted stationary D405 receipt is not present")
    value = json.loads(accepted.read_text())
    csv_item = next(
        item
        for item in value["lineage"]["capture_artifacts"]
        if item["path"].endswith(".csv")
    )
    csv_item["sha256"] = "0" * 64
    altered = tmp_path / "altered-receipt.json"
    altered.write_text(json.dumps(value))

    with pytest.raises(D405MetricSurfacePlaneError, match="hash mismatch"):
        evaluate_d405_metric_surface_plane(
            capture, capture_receipt_path=altered
        )


def test_existing_observation_fails_when_stability_threshold_is_tightened(
    tmp_path: Path,
) -> None:
    capture = REPO_ROOT / "runs" / "d405-rgbd-capture" / "20260725-stationary-v2"
    if not (capture / "evaluation" / "receipt.json").is_file():
        pytest.skip("ignored accepted stationary D405 receipt is not present")
    contract = load_contract()
    contract["maximum_cross_frame_normal_angle_degrees"] = 0.01
    strict_path = tmp_path / "strict-contract.json"
    strict_path.write_text(json.dumps(contract))

    receipt = evaluate_d405_metric_surface_plane(
        capture, contract_path=strict_path
    )

    assert receipt["verdict"]["passed"] is False
    assert receipt["checks"]["cross_frame_normal_angle"] is False
    assert "cross_frame_normal_angle" in receipt["verdict"]["failure_reasons"]
