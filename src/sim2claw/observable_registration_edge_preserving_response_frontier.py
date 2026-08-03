"""Build a retained-video-only global response versus edge Pareto frontier."""

from __future__ import annotations

import shutil
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
from .observable_registration_static_appearance_factorization import (
    _apply_candidate,
    _range_indices,
    _score_candidate_video,
)
from .observable_registration_temporal_pixel_similarity import (
    _decode_video,
    _linear_similarity,
    _summary,
    _tolerant_edge_f1,
)


SCHEMA = (
    "sim2claw.observable_registration_edge_preserving_response_frontier_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_edge_preserving_response_frontier_receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_edge_preserving_response_frontier_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_edge_preserving_response_frontier_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_edge_preserving_response_frontier_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_edge_preserving_response_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="edge preserving response frontier")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline["frame_count"] == 531
        and timeline["available_physical_sample_range_inclusive"] == [0, 515]
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
        sum(len(indices) for indices in partitions.values()) == 516
        and set().union(*(set(indices) for indices in partitions.values()))
        == set(range(516)),
        "temporal partitions drifted",
    )
    family = contract["candidate_family"]
    _require(
        family["common_bgr_gain"] == [0.2, 0.3, 0.4, 0.5, 0.6]
        and family["common_bgr_bias"] == [48.0, 64.0, 80.0, 96.0, 112.0]
        and family["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
        and family["candidate_count"] == 100
        and family["minimum_development_mean_full_frame_linear_pixel_similarity"]
        == 0.80
        and family["one_transform_for_all_frames"] is True,
        "candidate family drifted",
    )
    spatial = contract["spatial_residual"]
    _require(
        spatial["tile_columns"] == 8 and spatial["tile_rows"] == 6,
        "spatial residual grid drifted",
    )
    resources = contract["resource_boundary"]
    _require(
        resources["minimum_free_space_for_renderer_or_dependency_install_bytes"]
        == 1073741824
        and resources["renderer_allowed"] is False
        and resources["dependency_install_allowed"] is False
        and resources["colima_start_allowed"] is False,
        "resource boundary widened",
    )
    _require(all(contract["prohibitions"].values()), "prohibition relaxed")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _matrix(gain: float, bias: float) -> np.ndarray:
    return np.asarray(
        [
            [gain, 0.0, 0.0, bias],
            [0.0, gain, 0.0, bias],
            [0.0, 0.0, gain, bias],
        ],
        dtype=np.float64,
    )


def _partition_summary(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    indices: list[int],
    *,
    edge_config: dict[str, Any],
) -> dict[str, dict[str, float | int]]:
    primary: list[float] = []
    edges: list[float] = []
    for index in indices:
        physical = physical_frames[index]
        candidate = candidate_frames[index]
        primary.append(_linear_similarity(physical, candidate))
        edges.append(
            _tolerant_edge_f1(
                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                edge_config,
            )
        )
    return {
        "full_frame_linear_pixel_similarity": _summary(primary),
        "tolerant_edge_f1": _summary(edges),
    }


def _spatial_residual_rows(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    *,
    edge_config: dict[str, Any],
    tile_columns: int,
    tile_rows: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tile_width = 640 // tile_columns
    tile_height = 480 // tile_rows
    for row_index in range(tile_rows):
        for column_index in range(tile_columns):
            x0 = column_index * tile_width
            x1 = (column_index + 1) * tile_width
            y0 = row_index * tile_height
            y1 = (row_index + 1) * tile_height
            primary: list[float] = []
            edges: list[float] = []
            for frame_index in range(516):
                physical = physical_frames[frame_index][y0:y1, x0:x1]
                candidate = candidate_frames[frame_index][y0:y1, x0:x1]
                primary.append(_linear_similarity(physical, candidate))
                edges.append(
                    _tolerant_edge_f1(
                        cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                        cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                        edge_config,
                    )
                )
            rows.append(
                {
                    "tile_row": row_index,
                    "tile_column": column_index,
                    "bounds_xyxy": [x0, y0, x1, y1],
                    "full_frame_linear_pixel_similarity": _summary(primary),
                    "tolerant_edge_f1": _summary(edges),
                }
            )
    return rows


def evaluate_edge_preserving_response_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR58 one-run receipt already exists")
    contract = load_edge_preserving_response_contract(contract_path, root=root)
    or55_contract = _bound_json(
        contract["sources"]["or55_contract"], root=root, label="OR55 contract"
    )
    or56_receipt = _bound_json(
        contract["sources"]["or56_receipt"], root=root, label="OR56 receipt"
    )
    or57_closeout = _bound_json(
        contract["sources"]["or57_closeout"], root=root, label="OR57 closeout"
    )
    or26_receipt = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    _require(
        or56_receipt["status"] == "PASS_TIME_INVARIANT_APPEARANCE_ADVANCE_BELOW_TARGET"
        and or57_closeout["status"] == "TERMINAL_RENDER_RUNTIME_UNAVAILABLE_NO_CANDIDATE",
        "predecessor boundary drifted",
    )
    timeline = contract["timeline"]
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=640,
        height=480,
    )
    simulator_frames = _decode_video(
        _bound_path(contract["sources"]["simulator_video"], root=root, label="simulator"),
        width=640,
        height=480,
    )
    or56_frames = _decode_video(
        _bound_path(
            contract["sources"]["or56_candidate_video"], root=root, label="OR56 candidate"
        ),
        width=640,
        height=480,
    )
    _require(
        len(physical_frames) == len(simulator_frames) == len(or56_frames) == 531,
        "video length drifted",
    )
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    development = partitions["development"]
    family = contract["candidate_family"]
    edge_config = or55_contract["metric"]["edge"]
    candidates: list[dict[str, Any]] = []
    for kernel in family["gaussian_blur_kernel_px"]:
        for gain in family["common_bgr_gain"]:
            for bias in family["common_bgr_bias"]:
                matrix = _matrix(float(gain), float(bias))
                primary: list[float] = []
                edges: list[float] = []
                for index in development:
                    transformed = _apply_candidate(
                        simulator_frames[index], kernel=int(kernel), matrix=matrix
                    )
                    physical = physical_frames[index]
                    primary.append(_linear_similarity(physical, transformed))
                    edges.append(
                        _tolerant_edge_f1(
                            cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                            cv2.cvtColor(transformed, cv2.COLOR_BGR2GRAY),
                            edge_config,
                        )
                    )
                primary_summary = _summary(primary)
                candidates.append(
                    {
                        "common_bgr_gain": float(gain),
                        "common_bgr_bias": float(bias),
                        "gaussian_blur_kernel_px": int(kernel),
                        "development_full_frame_linear_pixel_similarity": primary_summary,
                        "development_tolerant_edge_f1": _summary(edges),
                        "eligible_mean_target": float(primary_summary["mean"])
                        >= float(
                            family[
                                "minimum_development_mean_full_frame_linear_pixel_similarity"
                            ]
                        ),
                    }
                )
    eligible = [candidate for candidate in candidates if candidate["eligible_mean_target"]]
    selection_pool = eligible if eligible else candidates
    selected = max(
        selection_pool,
        key=lambda item: (
            float(item["development_tolerant_edge_f1"]["mean"]),
            float(item["development_full_frame_linear_pixel_similarity"]["p10"]),
            float(item["development_full_frame_linear_pixel_similarity"]["mean"]),
            -int(item["gaussian_blur_kernel_px"]),
        ),
    )
    selected_matrix = _matrix(
        float(selected["common_bgr_gain"]), float(selected["common_bgr_bias"])
    )
    selected_frames = [
        _apply_candidate(
            frame,
            kernel=int(selected["gaussian_blur_kernel_px"]),
            matrix=selected_matrix,
        )
        for frame in simulator_frames
    ]
    output_directory.mkdir(parents=True, exist_ok=True)
    candidate_video_path = output_directory / "simulator_candidate.mp4"
    writer = cv2.VideoWriter(
        str(candidate_video_path), cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (640, 480)
    )
    _require(writer.isOpened(), "candidate video writer did not open")
    try:
        for frame in selected_frames:
            writer.write(frame)
    finally:
        writer.release()
    decoded_candidate = _decode_video(candidate_video_path, width=640, height=480)
    _require(len(decoded_candidate) == 531, "candidate video decode length drifted")
    partition_scores: dict[str, Any] = {}
    for name, indices in partitions.items():
        baseline = _partition_summary(
            physical_frames, or56_frames, indices, edge_config=edge_config
        )
        candidate_score = _partition_summary(
            physical_frames, decoded_candidate, indices, edge_config=edge_config
        )
        partition_scores[name] = {
            "or56_baseline": baseline,
            "selected_candidate": candidate_score,
            "absolute_mean_pixel_improvement": float(
                candidate_score["full_frame_linear_pixel_similarity"]["mean"]
            )
            - float(baseline["full_frame_linear_pixel_similarity"]["mean"]),
            "absolute_mean_edge_f1_improvement": float(
                candidate_score["tolerant_edge_f1"]["mean"]
            )
            - float(baseline["tolerant_edge_f1"]["mean"]),
        }
    metrics, metric_rows, gates = _score_candidate_video(
        physical_frames,
        decoded_candidate,
        contract=contract,
        or26=or26_receipt,
        or55_contract=or55_contract,
    )
    spatial = contract["spatial_residual"]
    spatial_rows = _spatial_residual_rows(
        physical_frames,
        decoded_candidate,
        edge_config=edge_config,
        tile_columns=int(spatial["tile_columns"]),
        tile_rows=int(spatial["tile_rows"]),
    )
    spatial_rows.sort(
        key=lambda row: (
            float(row["tolerant_edge_f1"]["mean"]),
            float(row["full_frame_linear_pixel_similarity"]["mean"]),
        )
    )
    rows_path = output_directory / "metric_rows.json"
    atomic_write_json(
        rows_path,
        {
            "schema_version": ROWS_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "rows": metric_rows,
        },
    )
    candidate_table_path = output_directory / "candidate_table.json"
    atomic_write_json(
        candidate_table_path,
        {
            "schema_version": "sim2claw.observable_registration_edge_preserving_response_candidates.v1",
            "experiment_id": contract["experiment_id"],
            "selection_inputs": "development_only",
            "eligible_candidate_count": len(eligible),
            "candidates": candidates,
            "selected": selected,
        },
    )
    spatial_path = output_directory / "spatial_residual_rows.json"
    atomic_write_json(
        spatial_path,
        {
            "schema_version": "sim2claw.observable_registration_spatial_residual_rows.v1",
            "experiment_id": contract["experiment_id"],
            "rows_ranked_worst_first": spatial_rows,
        },
    )
    passed = all(gates.values())
    mean_and_distribution_pass = all(
        gates[name]
        for name in (
            "mean_full_frame_linear_pixel_similarity",
            "p10_full_frame_linear_pixel_similarity",
            "mean_motion_union_linear_pixel_similarity",
            "each_phase_mean_full_frame_linear_pixel_similarity",
        )
    )
    status = (
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET"
        if passed
        else (
            "PASS_MEAN_AND_TEMPORAL_PIXEL_TARGET_EDGE_GATE_REMAINS"
            if mean_and_distribution_pass
            else "TERMINAL_GLOBAL_RESPONSE_FRONTIER_BELOW_FULL_TARGET"
        )
    )
    free_space = int(shutil.disk_usage(root).free)
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
            "eligible_mean_target_candidate_count": len(eligible),
            "selected_common_bgr_gain": selected["common_bgr_gain"],
            "selected_common_bgr_bias": selected["common_bgr_bias"],
            "selected_gaussian_blur_kernel_px": selected["gaussian_blur_kernel_px"],
            "validation_and_stress_used_for_selection": False,
        },
        "partition_scores": partition_scores,
        "metrics": metrics,
        "acceptance_gates": gates,
        "mean_and_temporal_distribution_gates_pass": mean_and_distribution_pass,
        "all_acceptance_gates_pass": passed,
        "spatial_residual": {
            "tile_count": len(spatial_rows),
            "worst_five_tiles": spatial_rows[:5],
        },
        "outputs": {
            "candidate_video_path": candidate_video_path.name,
            "candidate_video_sha256": sha256_file(candidate_video_path),
            "candidate_table_path": candidate_table_path.name,
            "candidate_table_sha256": sha256_file(candidate_table_path),
            "metric_rows_path": rows_path.name,
            "metric_rows_sha256": sha256_file(rows_path),
            "spatial_residual_rows_path": spatial_path.name,
            "spatial_residual_rows_sha256": sha256_file(spatial_path),
        },
        "resource_boundary": {
            "host_free_space_bytes_at_receipt": free_space,
            "renderer_runs": 0,
            "dependency_installs": 0,
            "colima_starts": 0,
        },
        "execution": {
            "candidate_evaluations": len(candidates),
            "emitted_candidate_videos": 1,
            "renderer_runs": 0,
            "physics_integrations": 0,
            "action_changes": 0,
            "state_changes": 0,
            "geometric_warps": 0,
            "per_frame_transforms": 0,
            "physical_pixel_composites": 0,
            "hardware_actions": 0,
        },
        "next_mechanism": (
            None
            if passed
            else "spatial_scene_geometry_residual_from_tile_report_pending_render_runtime"
        ),
        "claim_limits": {
            "mean_only_target_is_full_video_match": False,
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
    evaluate_edge_preserving_response_once()


if __name__ == "__main__":
    main()
