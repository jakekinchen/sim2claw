"""Evaluator-owned temporal pixel similarity for physical/simulator videos."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)


SCHEMA = "sim2claw.observable_registration_temporal_pixel_similarity_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_temporal_pixel_similarity_receipt.v1"
)
ROWS_SCHEMA = "sim2claw.observable_registration_temporal_pixel_similarity_rows.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_temporal_pixel_similarity_baseline_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_temporal_pixel_similarity_baseline_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _summary(values: list[float]) -> dict[str, float | int]:
    _require(bool(values), "empty metric population")
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "minimum": float(np.min(array)),
        "p10": float(np.quantile(array, 0.1)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "maximum": float(np.max(array)),
    }


def _linear_similarity(
    physical: np.ndarray, simulator: np.ndarray, mask: np.ndarray | None = None
) -> float:
    difference = np.abs(
        physical.astype(np.float32) - simulator.astype(np.float32)
    )
    selected = difference if mask is None else difference[mask]
    _require(bool(selected.size), "empty pixel mask")
    return 1.0 - float(np.mean(selected) / 255.0)


def _grayscale_similarity(
    physical_gray: np.ndarray,
    simulator_gray: np.ndarray,
    mask: np.ndarray | None = None,
) -> float:
    difference = np.abs(
        physical_gray.astype(np.float32) - simulator_gray.astype(np.float32)
    )
    selected = difference if mask is None else difference[mask]
    _require(bool(selected.size), "empty grayscale mask")
    return 1.0 - float(np.mean(selected) / 255.0)


def _ssim_map(
    physical_gray: np.ndarray,
    simulator_gray: np.ndarray,
    config: dict[str, Any],
) -> np.ndarray:
    physical = physical_gray.astype(np.float64)
    simulator = simulator_gray.astype(np.float64)
    window = tuple(int(value) for value in config["gaussian_window_px"])
    sigma = float(config["gaussian_sigma"])
    physical_mean = cv2.GaussianBlur(physical, window, sigma)
    simulator_mean = cv2.GaussianBlur(simulator, window, sigma)
    physical_variance = (
        cv2.GaussianBlur(physical * physical, window, sigma)
        - physical_mean * physical_mean
    )
    simulator_variance = (
        cv2.GaussianBlur(simulator * simulator, window, sigma)
        - simulator_mean * simulator_mean
    )
    covariance = (
        cv2.GaussianBlur(physical * simulator, window, sigma)
        - physical_mean * simulator_mean
    )
    c1 = (float(config["k1"]) * 255.0) ** 2
    c2 = (float(config["k2"]) * 255.0) ** 2
    return (
        (2.0 * physical_mean * simulator_mean + c1)
        * (2.0 * covariance + c2)
        / (
            (physical_mean * physical_mean + simulator_mean * simulator_mean + c1)
            * (physical_variance + simulator_variance + c2)
        )
    )


def _tolerant_edge_f1(
    physical_gray: np.ndarray,
    simulator_gray: np.ndarray,
    config: dict[str, Any],
) -> float:
    low = int(config["canny_low_threshold"])
    high = int(config["canny_high_threshold"])
    physical = cv2.Canny(physical_gray, low, high) > 0
    simulator = cv2.Canny(simulator_gray, low, high) > 0
    kernel_size = int(config["tolerance_dilation_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    physical_dilated = cv2.dilate(physical.astype(np.uint8), kernel) > 0
    simulator_dilated = cv2.dilate(simulator.astype(np.uint8), kernel) > 0
    denominator = int(np.sum(physical)) + int(np.sum(simulator))
    if denominator == 0:
        return 1.0
    bidirectional_matches = int(np.sum(physical & simulator_dilated)) + int(
        np.sum(simulator & physical_dilated)
    )
    return float(bidirectional_matches / denominator)


def _decode_video(path: Path, *, width: int, height: int) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    _require(capture.isOpened(), f"cannot open video {path.name}")
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        _require(frame.shape == (height, width, 3), "video frame shape drifted")
        frames.append(frame)
    capture.release()
    return frames


def load_temporal_pixel_similarity_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="temporal pixel similarity")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline["expected_frame_count"] == 531
        and timeline["expected_available_physical_frame_count"] == 516
        and timeline["expected_missing_physical_frame_count"] == 15
        and timeline["width_px"] == 640
        and timeline["height_px"] == 480
        and timeline["fps"] == 20.0
        and timeline["missing_frames_excluded_not_filled"] is True,
        "timeline policy drifted",
    )
    metric = contract["metric"]
    _require(
        metric["primary_formula"]
        == "1_minus_mean_absolute_bgr_error_divided_by_255"
        and metric["additional_geometric_warp_allowed"] is False
        and metric["color_fit_allowed"] is False
        and metric["per_frame_transform_allowed"] is False
        and metric["physical_pixel_compositing_allowed"] is False
        and metric["physical_pixels_as_simulator_texture_allowed"] is False,
        "metric policy widened",
    )
    acceptance = contract["acceptance"]
    _require(
        acceptance["minimum_mean_full_frame_linear_pixel_similarity"] == 0.80
        and acceptance["minimum_p10_full_frame_linear_pixel_similarity"] == 0.75
        and acceptance["minimum_mean_motion_union_linear_pixel_similarity"]
        == 0.75
        and acceptance[
            "minimum_each_phase_mean_full_frame_linear_pixel_similarity"
        ]
        == 0.78
        and acceptance["minimum_mean_tolerant_edge_f1"] == 0.40
        and acceptance["all_gates_required"] is True,
        "acceptance gates drifted",
    )
    execution = contract["execution"]
    _require(
        all(value == 0 for key, value in execution.items() if key != "heldout_open_allowed")
        and execution["heldout_open_allowed"] is False,
        "baseline execution boundary widened",
    )
    _require(not any(contract["claim_limits"].values()), "claim boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def evaluate_temporal_pixel_similarity_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR55 one-run receipt already exists")
    contract = load_temporal_pixel_similarity_contract(contract_path, root=root)
    or26 = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    curves = _bound_json(
        contract["sources"]["motion_curves"], root=root, label="motion curves"
    )["rows"]
    _require(
        or26["status"] == "PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO"
        and or26["trace_playback"]["actions_changed"] is False
        and or26["trace_playback"]["physics_rerun"] is False
        and or26["timeline"]["frame_count"] == 531,
        "OR26 source boundary drifted",
    )
    timeline = contract["timeline"]
    frame_count = int(timeline["expected_frame_count"])
    _require(
        len(curves) == frame_count
        and [int(row["sample_index"]) for row in curves] == list(range(frame_count)),
        "motion curve timeline drifted",
    )
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    simulator_frames = _decode_video(
        _bound_path(contract["sources"]["simulator_video"], root=root, label="simulator"),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    _require(
        len(physical_frames) == len(simulator_frames) == frame_count,
        "decoded video length drifted",
    )
    available = [bool(row["physical_frame_available"]) for row in curves]
    _require(
        sum(available) == int(timeline["expected_available_physical_frame_count"])
        and available.count(False)
        == int(timeline["expected_missing_physical_frame_count"]),
        "physical availability mask drifted",
    )
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.int32,
    )
    board_mask_uint8 = np.zeros(
        (int(timeline["height_px"]), int(timeline["width_px"])), dtype=np.uint8
    )
    cv2.fillConvexPoly(board_mask_uint8, corners, 1)
    board_mask = board_mask_uint8 > 0
    _require(int(np.sum(board_mask)) > 50000, "board mask is implausibly small")

    metric = contract["metric"]
    motion = metric["motion_union"]
    blur_kernel = int(motion["grayscale_gaussian_kernel_px"])
    dilation = int(motion["dilation_kernel_px"])
    motion_kernel = np.ones((dilation, dilation), dtype=np.uint8)
    rows: list[dict[str, Any]] = []
    previous_physical: np.ndarray | None = None
    previous_simulator: np.ndarray | None = None
    for index, (physical, simulator, is_available) in enumerate(
        zip(physical_frames, simulator_frames, available, strict=True)
    ):
        if not is_available:
            rows.append({"sample_index": index, "physical_frame_available": False})
            previous_physical = None
            previous_simulator = None
            continue
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        simulator_gray = cv2.cvtColor(simulator, cv2.COLOR_BGR2GRAY)
        ssim = _ssim_map(physical_gray, simulator_gray, metric["ssim"])
        temporal_similarity: float | None = None
        motion_similarity: float | None = None
        motion_union_pixels = 0
        blurred_physical = cv2.GaussianBlur(
            physical_gray, (blur_kernel, blur_kernel), 0.0
        )
        blurred_simulator = cv2.GaussianBlur(
            simulator_gray, (blur_kernel, blur_kernel), 0.0
        )
        if previous_physical is not None and previous_simulator is not None:
            physical_delta = cv2.absdiff(blurred_physical, previous_physical)
            simulator_delta = cv2.absdiff(blurred_simulator, previous_simulator)
            temporal_similarity = _grayscale_similarity(
                physical_delta, simulator_delta
            )
            union = np.logical_or(
                physical_delta >= int(motion["physical_difference_threshold"]),
                simulator_delta >= int(motion["simulator_difference_threshold"]),
            )
            union = cv2.dilate(union.astype(np.uint8), motion_kernel) > 0
            motion_union_pixels = int(np.sum(union))
            if motion_union_pixels >= int(motion["minimum_union_pixels"]):
                motion_similarity = _linear_similarity(physical, simulator, union)
        previous_physical = blurred_physical
        previous_simulator = blurred_simulator
        rows.append(
            {
                "sample_index": index,
                "physical_frame_available": True,
                "full_frame_linear_pixel_similarity": _linear_similarity(
                    physical, simulator
                ),
                "board_grayscale_linear_pixel_similarity": _grayscale_similarity(
                    physical_gray, simulator_gray, board_mask
                ),
                "full_frame_grayscale_ssim": float(np.mean(ssim)),
                "board_grayscale_ssim": float(np.mean(ssim[board_mask])),
                "tolerant_edge_f1": _tolerant_edge_f1(
                    physical_gray, simulator_gray, metric["edge"]
                ),
                "temporal_delta_grayscale_similarity": temporal_similarity,
                "motion_union_linear_pixel_similarity": motion_similarity,
                "motion_union_pixel_count": motion_union_pixels,
            }
        )

    available_rows = [row for row in rows if row["physical_frame_available"]]
    primary = _summary(
        [float(row["full_frame_linear_pixel_similarity"]) for row in available_rows]
    )
    motion_summary = _summary(
        [
            float(row["motion_union_linear_pixel_similarity"])
            for row in available_rows
            if row["motion_union_linear_pixel_similarity"] is not None
        ]
    )
    edge_summary = _summary(
        [float(row["tolerant_edge_f1"]) for row in available_rows]
    )
    phase_summaries: dict[str, dict[str, float | int]] = {}
    for phase in timeline["phases"]:
        start, stop = [int(value) for value in phase["sample_range_inclusive"]]
        values = [
            float(row["full_frame_linear_pixel_similarity"])
            for row in available_rows
            if start <= int(row["sample_index"]) <= stop
        ]
        phase_summaries[str(phase["name"])] = _summary(values)
    diagnostics = {
        "board_grayscale_linear_pixel_similarity": _summary(
            [
                float(row["board_grayscale_linear_pixel_similarity"])
                for row in available_rows
            ]
        ),
        "full_frame_grayscale_ssim": _summary(
            [float(row["full_frame_grayscale_ssim"]) for row in available_rows]
        ),
        "board_grayscale_ssim": _summary(
            [float(row["board_grayscale_ssim"]) for row in available_rows]
        ),
        "temporal_delta_grayscale_similarity": _summary(
            [
                float(row["temporal_delta_grayscale_similarity"])
                for row in available_rows
                if row["temporal_delta_grayscale_similarity"] is not None
            ]
        ),
    }
    acceptance = contract["acceptance"]
    gates = {
        "mean_full_frame_linear_pixel_similarity": float(primary["mean"])
        >= float(acceptance["minimum_mean_full_frame_linear_pixel_similarity"]),
        "p10_full_frame_linear_pixel_similarity": float(primary["p10"])
        >= float(acceptance["minimum_p10_full_frame_linear_pixel_similarity"]),
        "mean_motion_union_linear_pixel_similarity": float(motion_summary["mean"])
        >= float(acceptance["minimum_mean_motion_union_linear_pixel_similarity"]),
        "each_phase_mean_full_frame_linear_pixel_similarity": all(
            float(value["mean"])
            >= float(
                acceptance[
                    "minimum_each_phase_mean_full_frame_linear_pixel_similarity"
                ]
            )
            for value in phase_summaries.values()
        ),
        "mean_tolerant_edge_f1": float(edge_summary["mean"])
        >= float(acceptance["minimum_mean_tolerant_edge_f1"]),
    }
    passed = all(gates.values())
    status = (
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET"
        if passed
        else "BASELINE_BELOW_TEMPORAL_PIXEL_SIMILARITY_TARGET"
    )
    rows_document = {
        "schema_version": ROWS_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "rows": rows,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "metric_rows.json"
    atomic_write_json(rows_path, rows_document)
    rows_sha256 = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    deficits = {
        "mean_full_frame_linear_pixel_similarity": max(
            0.0,
            float(acceptance["minimum_mean_full_frame_linear_pixel_similarity"])
            - float(primary["mean"]),
        ),
        "mean_motion_union_linear_pixel_similarity": max(
            0.0,
            float(acceptance["minimum_mean_motion_union_linear_pixel_similarity"])
            - float(motion_summary["mean"]),
        ),
        "mean_tolerant_edge_f1": max(
            0.0,
            float(acceptance["minimum_mean_tolerant_edge_f1"])
            - float(edge_summary["mean"]),
        ),
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "timeline": {
            "decoded_frame_count": frame_count,
            "available_physical_frame_count": len(available_rows),
            "missing_physical_frame_count": available.count(False),
            "missing_frames_filled": False,
        },
        "metrics": {
            "full_frame_linear_pixel_similarity": primary,
            "motion_union_linear_pixel_similarity": motion_summary,
            "tolerant_edge_f1": edge_summary,
            "phase_full_frame_linear_pixel_similarity": phase_summaries,
            "diagnostics": diagnostics,
        },
        "acceptance_gates": gates,
        "all_acceptance_gates_pass": passed,
        "target_deficits": deficits,
        "next_mechanism": (
            None
            if passed
            else "factor_static_renderer_appearance_from_geometry_before_any_physics_change"
        ),
        "metric_rows_sha256": rows_sha256,
        "execution": {
            "simulator_replays": 0,
            "candidate_renders": 0,
            "geometric_registration_changes": 0,
            "color_fits": 0,
            "parameter_changes": 0,
            "physical_frame_substitutions": 0,
            "hardware_actions": 0,
            "heldout_opened": False,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    result = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, result)
    return result


def main() -> None:
    evaluate_temporal_pixel_similarity_once()


if __name__ == "__main__":
    main()
