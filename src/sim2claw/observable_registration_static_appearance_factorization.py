"""Factor time-invariant renderer appearance from the OR55 video residual."""

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
    sha256_file,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_temporal_pixel_similarity import (
    _decode_video,
    _grayscale_similarity,
    _linear_similarity,
    _ssim_map,
    _summary,
    _tolerant_edge_f1,
)


SCHEMA = "sim2claw.observable_registration_static_appearance_factorization_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_static_appearance_factorization_receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_static_appearance_factorization_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_static_appearance_factorization_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_static_appearance_factorization_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _range_indices(ranges: list[list[int]]) -> list[int]:
    indices: list[int] = []
    for start, stop in ranges:
        _require(0 <= int(start) <= int(stop), "invalid sample range")
        indices.extend(range(int(start), int(stop) + 1))
    return indices


def load_static_appearance_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="static appearance factorization")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline["frame_count"] == 531
        and timeline["available_physical_sample_range_inclusive"] == [0, 515]
        and timeline["missing_physical_sample_range_inclusive"] == [516, 530]
        and timeline["width_px"] == 640
        and timeline["height_px"] == 480
        and timeline["fps"] == 20.0
        and timeline["selection_may_read_only_development"] is True,
        "timeline policy drifted",
    )
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    _require(
        len(set().union(*(set(values) for values in partitions.values()))) == 516
        and set().union(*(set(values) for values in partitions.values()))
        == set(range(516))
        and sum(len(values) for values in partitions.values()) == 516,
        "temporal partitions overlap or do not cover available samples",
    )
    family = contract["candidate_family"]
    _require(
        family["models"]
        == ["identity", "diagonal_bgr_affine", "full_bgr_affine"]
        and family["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
        and family["fit_pixel_grid_stride"] == 8
        and family["diagonal_gain_bounds"] == [0.5, 1.5]
        and family["cross_channel_coefficient_bounds"] == [-0.25, 0.25]
        and family["bias_bounds"] == [-64.0, 64.0]
        and family["one_transform_for_all_frames"] is True,
        "candidate family drifted",
    )
    evaluation = contract["evaluation"]
    _require(
        evaluation["inherit_or55_metric_and_acceptance_gates"] is True
        and evaluation[
            "minimum_validation_absolute_improvement_for_photometric_advance"
        ]
        == 0.02
        and evaluation["maximum_stress_absolute_regression"] == 0.005
        and evaluation["score_emitted_candidate_after_video_decode"] is True,
        "evaluation policy drifted",
    )
    _require(all(contract["prohibitions"].values()), "prohibition relaxed")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _blur(frame: np.ndarray, kernel: int) -> np.ndarray:
    if kernel == 1:
        return frame
    return cv2.GaussianBlur(frame, (kernel, kernel), 0.0)


def _identity_matrix() -> np.ndarray:
    return np.asarray(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        dtype=np.float64,
    )


def _fit_affine_matrix(
    physical_frames: list[np.ndarray],
    simulator_frames: list[np.ndarray],
    indices: list[int],
    *,
    kernel: int,
    stride: int,
    model: str,
    family: dict[str, Any],
) -> np.ndarray:
    _require(model in {"diagonal_bgr_affine", "full_bgr_affine"}, "bad fit model")
    if model == "diagonal_bgr_affine":
        matrix = np.zeros((3, 4), dtype=np.float64)
        gain_low, gain_high = [float(value) for value in family["diagonal_gain_bounds"]]
        bias_low, bias_high = [float(value) for value in family["bias_bounds"]]
        for channel in range(3):
            xtx = np.zeros((2, 2), dtype=np.float64)
            xty = np.zeros(2, dtype=np.float64)
            for index in indices:
                simulator = _blur(simulator_frames[index], kernel)[::stride, ::stride, channel]
                physical = physical_frames[index][::stride, ::stride, channel]
                x = simulator.astype(np.float64).reshape(-1)
                y = physical.astype(np.float64).reshape(-1)
                xtx[0, 0] += float(x @ x)
                xtx[0, 1] += float(np.sum(x))
                xtx[1, 0] = xtx[0, 1]
                xtx[1, 1] += float(x.size)
                xty[0] += float(x @ y)
                xty[1] += float(np.sum(y))
            coefficient = np.linalg.pinv(xtx) @ xty
            matrix[channel, channel] = float(np.clip(coefficient[0], gain_low, gain_high))
            matrix[channel, 3] = float(np.clip(coefficient[1], bias_low, bias_high))
        return matrix

    xtx = np.zeros((4, 4), dtype=np.float64)
    xty = np.zeros((4, 3), dtype=np.float64)
    for index in indices:
        simulator = _blur(simulator_frames[index], kernel)[::stride, ::stride]
        physical = physical_frames[index][::stride, ::stride]
        x = np.column_stack(
            (simulator.reshape(-1, 3).astype(np.float64), np.ones(simulator.shape[0] * simulator.shape[1]))
        )
        y = physical.reshape(-1, 3).astype(np.float64)
        xtx += x.T @ x
        xty += x.T @ y
    coefficient = np.linalg.pinv(xtx) @ xty
    matrix = coefficient.T
    gain_low, gain_high = [float(value) for value in family["diagonal_gain_bounds"]]
    cross_low, cross_high = [
        float(value) for value in family["cross_channel_coefficient_bounds"]
    ]
    bias_low, bias_high = [float(value) for value in family["bias_bounds"]]
    for output_channel in range(3):
        for input_channel in range(3):
            bounds = (
                (gain_low, gain_high)
                if output_channel == input_channel
                else (cross_low, cross_high)
            )
            matrix[output_channel, input_channel] = float(
                np.clip(matrix[output_channel, input_channel], *bounds)
            )
        matrix[output_channel, 3] = float(
            np.clip(matrix[output_channel, 3], bias_low, bias_high)
        )
    return matrix


def _apply_candidate(
    frame: np.ndarray, *, kernel: int, matrix: np.ndarray
) -> np.ndarray:
    blurred = _blur(frame, kernel).astype(np.float32)
    transformed = cv2.transform(blurred, matrix[:, :3].astype(np.float32))
    transformed += matrix[:, 3].astype(np.float32)
    return np.clip(np.rint(transformed), 0.0, 255.0).astype(np.uint8)


def _primary_partition_summary(
    physical_frames: list[np.ndarray],
    simulator_frames: list[np.ndarray],
    indices: list[int],
    *,
    kernel: int,
    matrix: np.ndarray,
) -> dict[str, float | int]:
    return _summary(
        [
            _linear_similarity(
                physical_frames[index],
                _apply_candidate(simulator_frames[index], kernel=kernel, matrix=matrix),
            )
            for index in indices
        ]
    )


def _score_candidate_video(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    *,
    contract: dict[str, Any],
    or26: dict[str, Any],
    or55_contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, bool]]:
    timeline = contract["timeline"]
    available = set(range(516))
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.int32,
    )
    board_mask_uint8 = np.zeros((480, 640), dtype=np.uint8)
    cv2.fillConvexPoly(board_mask_uint8, corners, 1)
    board_mask = board_mask_uint8 > 0
    metric = or55_contract["metric"]
    motion = metric["motion_union"]
    blur_kernel = int(motion["grayscale_gaussian_kernel_px"])
    motion_kernel = np.ones(
        (int(motion["dilation_kernel_px"]), int(motion["dilation_kernel_px"])),
        dtype=np.uint8,
    )
    rows: list[dict[str, Any]] = []
    previous_physical: np.ndarray | None = None
    previous_candidate: np.ndarray | None = None
    for index, (physical, candidate) in enumerate(
        zip(physical_frames, candidate_frames, strict=True)
    ):
        if index not in available:
            rows.append({"sample_index": index, "physical_frame_available": False})
            previous_physical = None
            previous_candidate = None
            continue
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        ssim = _ssim_map(physical_gray, candidate_gray, metric["ssim"])
        blurred_physical = cv2.GaussianBlur(
            physical_gray, (blur_kernel, blur_kernel), 0.0
        )
        blurred_candidate = cv2.GaussianBlur(
            candidate_gray, (blur_kernel, blur_kernel), 0.0
        )
        temporal_similarity: float | None = None
        motion_similarity: float | None = None
        motion_union_pixels = 0
        if previous_physical is not None and previous_candidate is not None:
            physical_delta = cv2.absdiff(blurred_physical, previous_physical)
            candidate_delta = cv2.absdiff(blurred_candidate, previous_candidate)
            temporal_similarity = _grayscale_similarity(physical_delta, candidate_delta)
            union = np.logical_or(
                physical_delta >= int(motion["physical_difference_threshold"]),
                candidate_delta >= int(motion["simulator_difference_threshold"]),
            )
            union = cv2.dilate(union.astype(np.uint8), motion_kernel) > 0
            motion_union_pixels = int(np.sum(union))
            if motion_union_pixels >= int(motion["minimum_union_pixels"]):
                motion_similarity = _linear_similarity(physical, candidate, union)
        previous_physical = blurred_physical
        previous_candidate = blurred_candidate
        rows.append(
            {
                "sample_index": index,
                "physical_frame_available": True,
                "full_frame_linear_pixel_similarity": _linear_similarity(physical, candidate),
                "board_grayscale_linear_pixel_similarity": _grayscale_similarity(
                    physical_gray, candidate_gray, board_mask
                ),
                "full_frame_grayscale_ssim": float(np.mean(ssim)),
                "board_grayscale_ssim": float(np.mean(ssim[board_mask])),
                "tolerant_edge_f1": _tolerant_edge_f1(
                    physical_gray, candidate_gray, metric["edge"]
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
    edge_summary = _summary([float(row["tolerant_edge_f1"]) for row in available_rows])
    phase_summaries: dict[str, dict[str, float | int]] = {}
    for phase in or55_contract["timeline"]["phases"]:
        start, stop = [int(value) for value in phase["sample_range_inclusive"]]
        phase_summaries[str(phase["name"])] = _summary(
            [
                float(row["full_frame_linear_pixel_similarity"])
                for row in available_rows
                if start <= int(row["sample_index"]) <= stop
            ]
        )
    diagnostics = {
        "board_grayscale_linear_pixel_similarity": _summary(
            [float(row["board_grayscale_linear_pixel_similarity"]) for row in available_rows]
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
    acceptance = or55_contract["acceptance"]
    gates = {
        "mean_full_frame_linear_pixel_similarity": float(primary["mean"])
        >= float(acceptance["minimum_mean_full_frame_linear_pixel_similarity"]),
        "p10_full_frame_linear_pixel_similarity": float(primary["p10"])
        >= float(acceptance["minimum_p10_full_frame_linear_pixel_similarity"]),
        "mean_motion_union_linear_pixel_similarity": float(motion_summary["mean"])
        >= float(acceptance["minimum_mean_motion_union_linear_pixel_similarity"]),
        "each_phase_mean_full_frame_linear_pixel_similarity": all(
            float(value["mean"])
            >= float(acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"])
            for value in phase_summaries.values()
        ),
        "mean_tolerant_edge_f1": float(edge_summary["mean"])
        >= float(acceptance["minimum_mean_tolerant_edge_f1"]),
    }
    metrics = {
        "full_frame_linear_pixel_similarity": primary,
        "motion_union_linear_pixel_similarity": motion_summary,
        "tolerant_edge_f1": edge_summary,
        "phase_full_frame_linear_pixel_similarity": phase_summaries,
        "diagnostics": diagnostics,
    }
    return metrics, rows, gates


def evaluate_static_appearance_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR56 one-run receipt already exists")
    contract = load_static_appearance_contract(contract_path, root=root)
    or55_contract = _bound_json(
        contract["sources"]["or55_contract"], root=root, label="OR55 contract"
    )
    or55_receipt = _bound_json(
        contract["sources"]["or55_receipt"], root=root, label="OR55 receipt"
    )
    or26 = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    _require(
        or55_receipt["status"] == "BASELINE_BELOW_TEMPORAL_PIXEL_SIMILARITY_TARGET"
        and or55_receipt["timeline"]["available_physical_frame_count"] == 516
        and not or55_receipt["all_acceptance_gates_pass"],
        "OR55 source boundary drifted",
    )
    timeline = contract["timeline"]
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
    _require(len(physical_frames) == len(simulator_frames) == 531, "video length drifted")
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    development = partitions["development"]
    family = contract["candidate_family"]
    candidates: list[dict[str, Any]] = []
    model_complexity = {"identity": 0, "diagonal_bgr_affine": 1, "full_bgr_affine": 2}
    for kernel in family["gaussian_blur_kernel_px"]:
        for model in family["models"]:
            matrix = (
                _identity_matrix()
                if model == "identity"
                else _fit_affine_matrix(
                    physical_frames,
                    simulator_frames,
                    development,
                    kernel=int(kernel),
                    stride=int(family["fit_pixel_grid_stride"]),
                    model=str(model),
                    family=family,
                )
            )
            summary = _primary_partition_summary(
                physical_frames,
                simulator_frames,
                development,
                kernel=int(kernel),
                matrix=matrix,
            )
            candidates.append(
                {
                    "model": model,
                    "gaussian_blur_kernel_px": int(kernel),
                    "matrix_bgr_affine": matrix.tolist(),
                    "development_full_frame_linear_pixel_similarity": summary,
                    "model_complexity": model_complexity[str(model)],
                }
            )
    selected = max(
        candidates,
        key=lambda item: (
            float(item["development_full_frame_linear_pixel_similarity"]["mean"]),
            float(item["development_full_frame_linear_pixel_similarity"]["p10"]),
            -int(item["model_complexity"]),
            -int(item["gaussian_blur_kernel_px"]),
        ),
    )
    selected_matrix = np.asarray(selected["matrix_bgr_affine"], dtype=np.float64)
    selected_kernel = int(selected["gaussian_blur_kernel_px"])
    identity = _identity_matrix()
    partition_scores: dict[str, Any] = {}
    for name, indices in partitions.items():
        baseline = _primary_partition_summary(
            physical_frames, simulator_frames, indices, kernel=1, matrix=identity
        )
        candidate = _primary_partition_summary(
            physical_frames,
            simulator_frames,
            indices,
            kernel=selected_kernel,
            matrix=selected_matrix,
        )
        partition_scores[name] = {
            "baseline": baseline,
            "selected_candidate": candidate,
            "absolute_mean_improvement": float(candidate["mean"]) - float(baseline["mean"]),
        }

    output_directory.mkdir(parents=True, exist_ok=True)
    candidate_video_path = output_directory / "simulator_candidate.mp4"
    writer = cv2.VideoWriter(
        str(candidate_video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(timeline["fps"]),
        (int(timeline["width_px"]), int(timeline["height_px"])),
    )
    _require(writer.isOpened(), "candidate video writer did not open")
    try:
        for frame in simulator_frames:
            writer.write(
                _apply_candidate(frame, kernel=selected_kernel, matrix=selected_matrix)
            )
    finally:
        writer.release()
    candidate_frames = _decode_video(
        candidate_video_path,
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    _require(len(candidate_frames) == 531, "candidate video decode length drifted")
    metrics, metric_rows, gates = _score_candidate_video(
        physical_frames,
        candidate_frames,
        contract=contract,
        or26=or26,
        or55_contract=or55_contract,
    )
    rows_document = {
        "schema_version": ROWS_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "rows": metric_rows,
    }
    rows_path = output_directory / "metric_rows.json"
    atomic_write_json(rows_path, rows_document)
    candidate_table_path = output_directory / "candidate_table.json"
    atomic_write_json(
        candidate_table_path,
        {
            "schema_version": "sim2claw.observable_registration_static_appearance_candidates.v1",
            "experiment_id": contract["experiment_id"],
            "selection_inputs": "development_only",
            "candidates": candidates,
            "selected": selected,
        },
    )
    evaluation = contract["evaluation"]
    photometric_advance = (
        float(partition_scores["validation"]["absolute_mean_improvement"])
        >= float(
            evaluation[
                "minimum_validation_absolute_improvement_for_photometric_advance"
            ]
        )
        and float(partition_scores["stress"]["absolute_mean_improvement"])
        >= -float(evaluation["maximum_stress_absolute_regression"])
    )
    passed = all(gates.values())
    status = (
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET"
        if passed
        else (
            "PASS_TIME_INVARIANT_APPEARANCE_ADVANCE_BELOW_TARGET"
            if photometric_advance
            else "TERMINAL_STATIC_APPEARANCE_INSUFFICIENT"
        )
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "partitions": {name: len(indices) for name, indices in partitions.items()},
        "selection": {
            "selection_inputs": "development_only",
            "candidate_count": len(candidates),
            "selected_model": selected["model"],
            "selected_gaussian_blur_kernel_px": selected_kernel,
            "selected_matrix_bgr_affine": selected["matrix_bgr_affine"],
            "validation_and_stress_used_for_selection": False,
        },
        "partition_scores": partition_scores,
        "photometric_advance_gate_pass": photometric_advance,
        "metrics": metrics,
        "acceptance_gates": gates,
        "all_acceptance_gates_pass": passed,
        "outputs": {
            "candidate_video_path": candidate_video_path.name,
            "candidate_video_sha256": sha256_file(candidate_video_path),
            "candidate_table_path": candidate_table_path.name,
            "candidate_table_sha256": sha256_file(candidate_table_path),
            "metric_rows_path": rows_path.name,
            "metric_rows_sha256": sha256_file(rows_path),
        },
        "execution": {
            "candidate_evaluations": len(candidates),
            "camera_response_fits": sum(
                1 for candidate in candidates if candidate["model"] != "identity"
            ),
            "emitted_candidate_videos": 1,
            "simulator_replays": 0,
            "action_changes": 0,
            "physics_changes": 0,
            "geometric_warps": 0,
            "per_frame_transforms": 0,
            "physical_pixel_composites": 0,
            "hardware_actions": 0,
        },
        "next_mechanism": (
            None
            if passed
            else "renderer_scene_composition_and_geometry_on_top_of_frozen_global_response"
        ),
        "claim_limits": {
            "episode_specific_visual_replay_only": True,
            "metric_camera_calibration": False,
            "physics_fidelity": False,
            "global_mapping_approval": False,
            "simulator_promotion": False,
            "task_transfer": False,
        },
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_static_appearance_once()


if __name__ == "__main__":
    main()
