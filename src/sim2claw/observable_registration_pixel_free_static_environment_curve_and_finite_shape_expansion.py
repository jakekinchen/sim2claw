"""Freeze and score pixel-free curved static-environment primitives."""

from __future__ import annotations

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
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_json, _bound_path
from .observable_registration_pixel_free_environment_primitive_edge_headroom import _edge_f1
from .observable_registration_static_appearance_factorization import _range_indices
from .observable_registration_temporal_pixel_similarity import _decode_video, _summary


SCHEMA = "sim2claw.observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_contract.v1"
SCENE_SCHEMA = "sim2claw.observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_scene.v1"
ROWS_SCHEMA = "sim2claw.observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_rows.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_receipt.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_curve_and_finite_shape_expansion_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="curve and finite-shape expansion")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    _require(
        timeline["decoded_frame_count"] == 531
        and timeline["scored_sample_range_inclusive"] == [0, 515]
        and timeline["selection_may_read_only_development"] is True
        and {name: len(indices) for name, indices in partitions.items()}
        == {"development": 220, "validation": 180, "stress": 116}
        and set().union(*(set(indices) for indices in partitions.values())) == set(range(516)),
        "timeline partitions drifted",
    )
    extraction = contract["extraction"]
    _require(
        extraction == {
            "canny_low_threshold": 50,
            "canny_high_threshold": 150,
            "board_exclusion_dilation_px": 7,
            "minimum_development_physical_edge_occurrence": 0.35,
            "maximum_development_simulator_edge_occurrence": 0.10,
            "initial_residual_closing_kernel_px": 3,
            "or63_line_neighborhood_exclusion_kernel_px": 7,
            "post_exclusion_closing_kernel_px": 5,
            "contour_retrieval": "external",
            "minimum_contour_perimeter_px": 20.0,
            "minimum_bounding_extent_px": 8,
            "simplification_minimum_epsilon_px": 1.5,
            "simplification_perimeter_fraction": 0.015,
            "closed_polylines": True,
            "line_width_px": 1,
            "maximum_primitives": 32,
            "maximum_total_vertices": 512,
            "ranking": "descending_development_contour_perimeter_then_bbox_then_vertices",
        },
        "extraction drifted",
    )
    evaluation = contract["evaluation"]
    _require(
        evaluation == {
            "union_with_decoded_or58_simulator_canny_edges": True,
            "union_with_all_24_or63_line_skeletons": True,
            "evaluate_full_frozen_family_only": True,
            "selection_on_validation_or_stress_allowed": False,
            "tolerance_dilation_kernel_px": 3,
            "edge_gate_reference": 0.40,
        },
        "evaluation drifted",
    )
    _require(contract["acceptance"]["target_pass_allowed"] is False, "counterfactual cannot pass target")
    _require(not any(contract["resource_boundary"].values()), "resource boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _edges(frame: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(
        gray,
        int(config["canny_low_threshold"]),
        int(config["canny_high_threshold"]),
    ) > 0


def _line_mask(scene: dict[str, Any]) -> np.ndarray:
    mask = np.zeros((480, 640), dtype=np.uint8)
    for primitive in scene["line_primitives"]:
        x0, y0, x1, y1 = [int(value) for value in primitive["endpoints_xyxy_px"]]
        cv2.line(mask, (x0, y0), (x1, y1), 1, 1, cv2.LINE_8)
    return mask > 0


def _extract_primitives(
    stable_residual: np.ndarray, line_mask: np.ndarray, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    exclusion_size = int(config["or63_line_neighborhood_exclusion_kernel_px"])
    excluded_lines = cv2.dilate(
        line_mask.astype(np.uint8), np.ones((exclusion_size, exclusion_size), dtype=np.uint8)
    ) > 0
    post_line_residual = stable_residual & (~excluded_lines)
    close_size = int(config["post_exclusion_closing_kernel_px"])
    connected = cv2.morphologyEx(
        post_line_residual.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((close_size, close_size), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        perimeter = float(cv2.arcLength(contour, True))
        x, y, width, height = [int(value) for value in cv2.boundingRect(contour)]
        if perimeter < float(config["minimum_contour_perimeter_px"]):
            continue
        if max(width, height) < int(config["minimum_bounding_extent_px"]):
            continue
        epsilon = max(
            float(config["simplification_minimum_epsilon_px"]),
            float(config["simplification_perimeter_fraction"]) * perimeter,
        )
        approximation = cv2.approxPolyDP(contour, epsilon, True)
        vertices = [[int(xy[0]), int(xy[1])] for xy in approximation[:, 0, :]]
        candidates.append(
            {
                "vertices_xy_px": vertices,
                "closed": True,
                "development_contour_perimeter_px": perimeter,
                "development_bounding_box_xywh_px": [x, y, width, height],
                "development_simplification_epsilon_px": float(epsilon),
            }
        )
    candidates.sort(
        key=lambda row: (
            -float(row["development_contour_perimeter_px"]),
            row["development_bounding_box_xywh_px"],
            row["vertices_xy_px"],
        )
    )
    selected: list[dict[str, Any]] = []
    total_vertices = 0
    for candidate in candidates:
        vertices = len(candidate["vertices_xy_px"])
        if total_vertices + vertices > int(config["maximum_total_vertices"]):
            continue
        candidate = {"primitive_id": f"outside_contour_{len(selected):02d}", **candidate}
        selected.append(candidate)
        total_vertices += vertices
        if len(selected) == int(config["maximum_primitives"]):
            break
    return selected, int(np.sum(post_line_residual))


def _polyline_mask(primitives: list[dict[str, Any]], width: int) -> np.ndarray:
    mask = np.zeros((480, 640), dtype=np.uint8)
    for primitive in primitives:
        points = np.asarray(primitive["vertices_xy_px"], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(mask, [points], True, 1, width, cv2.LINE_8)
    return mask > 0


def evaluate_curve_and_finite_shape_expansion_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR66 one-run receipt already exists")
    contract = load_curve_and_finite_shape_expansion_contract(contract_path, root=root)
    or26 = _bound_json(contract["sources"]["or26_receipt"], root=root, label="OR26 receipt")
    or58 = _bound_json(contract["sources"]["or58_receipt"], root=root, label="OR58 receipt")
    scene = _bound_json(contract["sources"]["or63_scene_spec"], root=root, label="OR63 scene spec")
    or64 = _bound_json(contract["sources"]["or64_receipt"], root=root, label="OR64 receipt")
    or65 = _bound_json(contract["sources"]["or65_closeout"], root=root, label="OR65 closeout")
    _require(
        or58["all_acceptance_gates_pass"] is False
        and len(scene["line_primitives"]) == 24
        and scene["physical_pixels_embedded"] is False
        and scene["background_plate"] is False
        and scene["texture"] is False
        and or64["target_pass_allowed"] is False
        and or65["result"]["selected_residual_class"] == "nonmotion_outside_board",
        "predecessor boundary drifted",
    )
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=640,
        height=480,
    )
    simulator_frames = _decode_video(
        _bound_path(contract["sources"]["or58_candidate_video"], root=root, label="OR58 candidate"),
        width=640,
        height=480,
    )
    _require(len(physical_frames) == len(simulator_frames) == 531, "decoded video length drifted")
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    extraction = contract["extraction"]
    development = partitions["development"]
    physical_occurrence = np.zeros((480, 640), dtype=np.uint16)
    simulator_occurrence = np.zeros((480, 640), dtype=np.uint16)
    for index in development:
        physical_occurrence += _edges(physical_frames[index], extraction)
        simulator_occurrence += _edges(simulator_frames[index], extraction)
    board = np.zeros((480, 640), dtype=np.uint8)
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"], dtype=np.int32
    )
    cv2.fillConvexPoly(board, corners, 1)
    board_size = int(extraction["board_exclusion_dilation_px"])
    outside = ~(cv2.dilate(board, np.ones((board_size, board_size), dtype=np.uint8)) > 0)
    stable_residual = (
        (physical_occurrence / len(development))
        >= float(extraction["minimum_development_physical_edge_occurrence"])
    ) & (
        (simulator_occurrence / len(development))
        <= float(extraction["maximum_development_simulator_edge_occurrence"])
    ) & outside
    initial_size = int(extraction["initial_residual_closing_kernel_px"])
    stable_residual = cv2.morphologyEx(
        stable_residual.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((initial_size, initial_size), dtype=np.uint8),
    ) > 0
    lines = _line_mask(scene)
    primitives, post_line_residual_pixel_count = _extract_primitives(stable_residual, lines, extraction)
    _require(len(primitives) <= int(extraction["maximum_primitives"]), "primitive budget exceeded")
    total_vertices = sum(len(row["vertices_xy_px"]) for row in primitives)
    _require(total_vertices <= int(extraction["maximum_total_vertices"]), "vertex budget exceeded")
    curves = _polyline_mask(primitives, int(extraction["line_width_px"]))

    evaluation = contract["evaluation"]
    kernel_size = int(evaluation["tolerance_dilation_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    baseline_values: list[float] = []
    line_values: list[float] = []
    expanded_values: list[float] = []
    rows: list[dict[str, Any]] = []
    for sample_index in range(516):
        physical_edges = _edges(physical_frames[sample_index], extraction)
        simulator_edges = _edges(simulator_frames[sample_index], extraction)
        baseline = _edge_f1(physical_edges, simulator_edges, kernel)
        line = _edge_f1(physical_edges, simulator_edges | lines, kernel)
        expanded = _edge_f1(physical_edges, simulator_edges | lines | curves, kernel)
        baseline_values.append(baseline)
        line_values.append(line)
        expanded_values.append(expanded)
        rows.append(
            {
                "sample_index": sample_index,
                "or58_tolerant_edge_f1": baseline,
                "or64_line_tolerant_edge_f1": line,
                "expanded_tolerant_edge_f1": expanded,
            }
        )
    or58_mean = float(np.mean(np.asarray(baseline_values, dtype=np.float64)))
    line_mean = float(np.mean(np.asarray(line_values, dtype=np.float64)))
    expected_or58 = float(or58["metrics"]["tolerant_edge_f1"]["mean"])
    expected_line = float(
        or64["prefix_summaries"]["24"]["full_timeline_counterfactual_tolerant_edge_f1"]["mean"]
    )
    _require(abs(or58_mean - expected_or58) < 1e-12, "OR58 edge metric did not reproduce")
    _require(abs(line_mean - expected_line) < 1e-12, "OR64 line metric did not reproduce")
    partition_scores: dict[str, Any] = {}
    for name, indices in partitions.items():
        line_summary = _summary([line_values[index] for index in indices])
        expanded_summary = _summary([expanded_values[index] for index in indices])
        partition_scores[name] = {
            "or64_line_tolerant_edge_f1": line_summary,
            "expanded_tolerant_edge_f1": expanded_summary,
            "absolute_mean_improvement_over_or64": float(expanded_summary["mean"])
            - float(line_summary["mean"]),
        }
    full_summary = _summary(expanded_values)
    validation_advance = float(
        partition_scores["validation"]["absolute_mean_improvement_over_or64"]
    ) >= float(
        contract["acceptance"]["minimum_validation_absolute_mean_edge_f1_improvement_over_or64"]
    )
    primitive_gate = len(primitives) >= int(contract["acceptance"]["minimum_frozen_primitives"])
    advance = validation_advance and primitive_gate
    status = (
        "PASS_PIXEL_FREE_CURVE_AND_FINITE_SHAPE_EDGE_HEADROOM_ADVANCE"
        if advance
        else "TERMINAL_CURVE_AND_FINITE_SHAPE_EDGE_HEADROOM_INSUFFICIENT"
    )
    scene_document = {
        "schema_version": SCENE_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "coordinate_system": "physical_video_screen_pixels_xy_origin_top_left",
        "selection_inputs": "development_only",
        "metric_3d_geometry": False,
        "physical_pixels_embedded": False,
        "background_plate": False,
        "texture": False,
        "mask_embedded": False,
        "predecessor_line_primitive_count": 24,
        "curve_and_finite_shape_primitives": primitives,
        "total_vertices": total_vertices,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    scene_path = output_directory / "curve_and_finite_shape_scene_spec.json"
    rows_path = output_directory / "edge_headroom_rows.json"
    atomic_write_json(scene_path, scene_document)
    atomic_write_json(rows_path, {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": rows})
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {name: binding["sha256"] for name, binding in contract["sources"].items()},
        "development_freeze": {
            "stable_residual_pixels_before_line_exclusion": int(np.sum(stable_residual)),
            "post_line_residual_pixels": post_line_residual_pixel_count,
            "frozen_primitive_count": len(primitives),
            "frozen_total_vertices": total_vertices,
        },
        "predecessor_reproduction": {
            "or58_mean_frame_tolerant_edge_f1": or58_mean,
            "or58_expected_mean_frame_tolerant_edge_f1": expected_or58,
            "or58_exact_within_1e_12": True,
            "or64_full_24_line_mean_frame_tolerant_edge_f1": line_mean,
            "or64_expected_full_24_line_mean_frame_tolerant_edge_f1": expected_line,
            "or64_exact_within_1e_12": True,
        },
        "partition_scores": partition_scores,
        "full_timeline_expanded_tolerant_edge_f1": full_summary,
        "full_timeline_absolute_mean_improvement_over_or64": float(full_summary["mean"]) - line_mean,
        "remaining_gap_to_edge_gate": max(0.0, float(evaluation["edge_gate_reference"]) - float(full_summary["mean"])),
        "counterfactual_edge_gate_reached": float(full_summary["mean"]) >= float(evaluation["edge_gate_reference"]),
        "acceptance_gates": {
            "minimum_frozen_primitives": primitive_gate,
            "minimum_validation_absolute_mean_edge_f1_improvement_over_or64": validation_advance,
        },
        "mechanism_headroom_advance": advance,
        "target_pass_allowed": False,
        "outputs": {
            "scene_spec_path": scene_path.name,
            "scene_spec_sha256": sha256_file(scene_path),
            "edge_headroom_rows_path": rows_path.name,
            "edge_headroom_rows_sha256": sha256_file(rows_path),
        },
        "execution": {
            "development_frame_evaluations": 220,
            "validation_frame_evaluations": 180,
            "stress_frame_evaluations": 116,
            "renderer_runs": 0,
            "simulator_replays": 0,
            "candidate_videos": 0,
            "mask_outputs": 0,
            "bgr_pixel_outputs": 0,
            "image_outputs": 0,
            "texture_outputs": 0,
            "physical_pixel_composites": 0,
            "geometric_warps": 0,
            "scene_mutations": 0,
            "action_changes": 0,
            "state_changes": 0,
            "validation_or_stress_selections": 0,
            "hardware_actions": 0,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_curve_and_finite_shape_expansion_once()


if __name__ == "__main__":
    main()
