"""Parameterize the larger clipped planar fixture from development footage only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_planar_array_residual_motion_ownership_attribution import (
    _extract_components,
    load_motion_ownership_contract,
)
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import (
    _ray_plane_point,
)
from .observable_registration_renderer_native_planar_fixture_parameterization import _procedural_cells


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_clipped_planar_fixture_parameterization_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_clipped_planar_fixture_parameterization_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_clipped_planar_fixture_parameterization_v1"


def load_clipped_planar_fixture_parameterization_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR129 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR129 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR129 split drifted")
    if split["corroboration_requires_decisive_development"] is not True or split["corroboration_refit_allowed"] is not False:
        raise ValueError("OR129 corroboration boundary drifted")
    search = contract["development_search"]
    if search["dictionary"] != "DICT_APRILTAG_36h11" or search["dictionary_entry_indices"] != list(range(587)):
        raise ValueError("OR129 dictionary search drifted")
    if search["rotations_quarter_turns"] != [0, 1, 2, 3] or search["sample_offsets_within_cell"] != [0.3, 0.7]:
        raise ValueError("OR129 sampling drifted")
    if search["grayscale_threshold"] != 120 or search["score_weights"] != {"balanced_accuracy": 0.65, "contrast": 0.35}:
        raise ValueError("OR129 score drifted")
    if search["optimizer"] != {"name": "scipy_differential_evolution", "seed": 129, "max_iterations": 60, "population_size_multiplier": 8, "polish": False, "tolerance": 0.0}:
        raise ValueError("OR129 optimizer drifted")
    if contract["parameterization"]["physical_pixel_texture_projection"] is not False or contract["parameterization"]["screen_space_overlay"] is not False:
        raise ValueError("OR129 image-borrowing boundary drifted")
    resources = contract["resource_boundary"]
    zero = (
        "renders_allowed",
        "physical_pixel_texture_projections_allowed",
        "screen_space_candidate_overlays_allowed",
        "candidate_videos_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR129 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR129 authority must remain closed")
    return contract


def _sample_layout(offsets: list[float]) -> tuple[np.ndarray, np.ndarray]:
    points: list[list[float]] = []
    cells: list[list[int]] = []
    for row in range(8):
        for column in range(8):
            for dy in offsets:
                for dx in offsets:
                    points.append([column + dx, row + dy])
                    cells.append([row, column])
    return np.asarray(points, dtype=np.float32).reshape((-1, 1, 2)), np.asarray(cells, dtype=np.int32)


def _quad_is_valid(quad: np.ndarray, geometry: dict[str, Any]) -> bool:
    polygon = np.asarray(quad, dtype=np.float32).reshape((4, 2))
    if not cv2.isContourConvex(polygon):
        return False
    if abs(float(cv2.contourArea(polygon))) < float(geometry["minimum_quad_area_px2"]):
        return False
    lengths = [float(np.linalg.norm(polygon[(index + 1) % 4] - polygon[index])) for index in range(4)]
    if min(lengths) < float(geometry["minimum_edge_length_px"]) or max(lengths) > float(geometry["maximum_edge_length_px"]):
        return False
    if not (float(geometry["clipped_corner_y_minimum_px"]) <= polygon[2, 1] <= float(geometry["clipped_corner_y_maximum_px"])):
        return False
    return bool(np.all(polygon[[0, 1, 3], 0] >= 0) and np.all(polygon[[0, 1, 3], 0] < 320) and np.all(polygon[[0, 1, 3], 1] >= 0) and np.all(polygon[[0, 1, 3], 1] < 240))


def _frame_observations(frame_gray: np.ndarray, quad: np.ndarray, layout: np.ndarray, cell_indices: np.ndarray, cells: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source = np.asarray([[0, 0], [8, 0], [8, 8], [0, 8]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(source, np.asarray(quad, dtype=np.float32).reshape((4, 2)))
    xy = cv2.perspectiveTransform(layout, transform).reshape((-1, 2))
    valid = (xy[:, 0] >= 0) & (xy[:, 0] <= 319) & (xy[:, 1] >= 0) & (xy[:, 1] <= 239)
    if int(valid.sum()) == 0:
        return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.uint8)
    values = cv2.remap(
        frame_gray,
        xy[valid, 0].reshape((1, -1)),
        xy[valid, 1].reshape((1, -1)),
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    ).reshape(-1).astype(np.float64)
    indices = cell_indices[valid]
    expected = cells[indices[:, 0], indices[:, 1]].astype(np.uint8)
    return values, expected


def _pattern_score(frames_gray: list[np.ndarray], quad: np.ndarray, cells: np.ndarray, search: dict[str, Any]) -> dict[str, float | int]:
    layout, cell_indices = _sample_layout([float(value) for value in search["sample_offsets_within_cell"]])
    values: list[np.ndarray] = []
    expected: list[np.ndarray] = []
    for frame in frames_gray:
        observed, labels = _frame_observations(frame, quad, layout, cell_indices, cells)
        values.append(observed)
        expected.append(labels)
    observed = np.concatenate(values)
    labels = np.concatenate(expected)
    white = observed[labels == 1]
    black = observed[labels == 0]
    if len(white) == 0 or len(black) == 0:
        return {"score": -1.0, "balanced_accuracy": 0.0, "contrast": -1.0, "white_mean": 0.0, "black_mean": 255.0, "visible_sample_count": int(len(observed))}
    threshold = float(search["grayscale_threshold"])
    balanced_accuracy = 0.5 * (float(np.mean(white >= threshold)) + float(np.mean(black < threshold)))
    contrast = float((np.mean(white) - np.mean(black)) / 255.0)
    weights = search["score_weights"]
    score = float(weights["balanced_accuracy"] * balanced_accuracy + weights["contrast"] * contrast)
    return {
        "score": score,
        "balanced_accuracy": balanced_accuracy,
        "contrast": contrast,
        "white_mean": float(np.mean(white)),
        "black_mean": float(np.mean(black)),
        "visible_sample_count": int(len(observed)),
    }


def _rank_dictionary(frames_gray: list[np.ndarray], quad: np.ndarray, search: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry_index in search["dictionary_entry_indices"]:
        base = np.asarray(_procedural_cells(int(entry_index)), dtype=np.uint8)
        for rotation in search["rotations_quarter_turns"]:
            metrics = _pattern_score(frames_gray, quad, np.rot90(base, int(rotation)), search)
            rows.append({"dictionary_entry_index": int(entry_index), "rotation_quarter_turns": int(rotation), **metrics})
    rows.sort(key=lambda row: (-float(row["score"]), int(row["dictionary_entry_index"]), int(row["rotation_quarter_turns"])))
    return rows


def _optimize_quad(frames_gray: list[np.ndarray], cells: np.ndarray, contract: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    search = contract["development_search"]
    geometry = contract["geometry_bounds"]
    bounds = [tuple(float(value) for value in pair) for pair in geometry["corner_coordinate_bounds_flat_xy"]]

    def objective(flat: np.ndarray) -> float:
        quad = np.asarray(flat, dtype=np.float64).reshape((4, 2))
        if not _quad_is_valid(quad, geometry):
            return 2.0
        return -float(_pattern_score(frames_gray, quad, cells, search)["score"])

    optimizer = search["optimizer"]
    result = differential_evolution(
        objective,
        bounds,
        seed=int(optimizer["seed"]),
        maxiter=int(optimizer["max_iterations"]),
        popsize=int(optimizer["population_size_multiplier"]),
        polish=bool(optimizer["polish"]),
        tol=float(optimizer["tolerance"]),
        workers=1,
        updating="immediate",
    )
    quad = np.asarray(result.x, dtype=np.float64).reshape((4, 2))
    return quad, {"objective_value": float(result.fun), "function_evaluations": int(result.nfev), "iterations": int(result.nit), "success_flag": bool(result.success)}


def _decode_initial_frame(episode: dict[str, Any]) -> np.ndarray:
    video = episode["physical_video"]
    path = REPO_ROOT / video["path"]
    if sha256_file(path) != video["sha256"]:
        raise ValueError("OR129 physical video identity drifted")
    return cv2.flip(
        _decode_selected_frames(
            path,
            selected_indices=np.asarray([0], dtype=np.int64),
            expected_frame_count=int(video["frame_count"]),
            expected_width=int(video["width_px"]),
            expected_height=int(video["height_px"]),
            output_width=320,
            output_height=240,
        )[0],
        -1,
    )


def _component_coverages(quad: np.ndarray, contract: dict[str, Any]) -> list[dict[str, Any]]:
    ownership_contract = load_motion_ownership_contract(REPO_ROOT / contract["sources"]["or124_contract"]["path"])
    audit_path = REPO_ROOT / ownership_contract["sources"]["or123_audit"]["path"]
    audit = cv2.imread(str(audit_path), cv2.IMREAD_COLOR)
    if audit is None or audit.shape != (240, 1280, 3):
        raise ValueError("OR129 OR123 audit drifted")
    uncovered = audit[:, 960:1280, 2] > 0
    components = _extract_components(uncovered, ownership_contract["component_rule"])
    mask = np.zeros((240, 320), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(quad).astype(np.int32), 1)
    kernel = int(contract["component_support"]["polygon_dilation_kernel_px"])
    mask = cv2.dilate(mask, np.ones((kernel, kernel), dtype=np.uint8)) > 0
    rows: list[dict[str, Any]] = []
    for index, component in enumerate(components):
        rows.append({
            "component_index": index,
            "raw_pixel_count": int(component["raw_pixel_count"]),
            "quad_support_coverage": float(np.sum(component["raw_mask"] & mask) / component["raw_pixel_count"]),
        })
    return rows


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR129 one-run receipt already exists")
    contract = load_clipped_planar_fixture_parameterization_contract(contract_path)
    for key, expected_status in (
        ("or124c_receipt", "PASS_RESIDUAL_MOTION_OWNERSHIP_ATTRIBUTED"),
        ("or125_receipt", "PASS_WORKCELL_STATIC_SURFACE_FAMILY_IDENTIFIED"),
        ("or126_receipt", "PASS_RENDERER_NATIVE_PLANAR_FIXTURE_PARAMETERIZED"),
    ):
        receipt = json.loads((REPO_ROOT / contract["sources"][key]["path"]).read_text())
        if receipt["status"] != expected_status:
            raise ValueError(f"OR129 prerequisite status drifted: {key}")
    or128 = json.loads((REPO_ROOT / contract["sources"]["or128_receipt"]["path"]).read_text())
    if or128["artifact_sha256"] != contract["sources"]["or128_receipt"]["artifact_sha256"]:
        raise ValueError("OR129 OR128 artifact drifted")

    or95 = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    episodes = _episode_inventory(or95)
    by_position = {int(row["split_position"]): row for row in episodes}
    development_frames = [_decode_initial_frame(by_position[position]) for position in contract["split"]["development_positions"]]
    development_gray = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in development_frames]

    initial_quad = np.asarray(contract["geometry_bounds"]["initial_quad_px"], dtype=np.float64)
    ranking = _rank_dictionary(development_gray, initial_quad, contract["development_search"])
    winner = ranking[0]
    runner_up = ranking[1]
    base_cells = np.asarray(_procedural_cells(int(winner["dictionary_entry_index"])), dtype=np.uint8)
    cells = np.rot90(base_cells, int(winner["rotation_quarter_turns"]))
    fitted_quad, optimizer_row = _optimize_quad(development_gray, cells, contract)
    development_pooled = _pattern_score(development_gray, fitted_quad, cells, contract["development_search"])
    development_rows = [
        {"split_position": position, **_pattern_score([gray], fitted_quad, cells, contract["development_search"])}
        for position, gray in zip(contract["split"]["development_positions"], development_gray, strict=True)
    ]
    component_rows = _component_coverages(fitted_quad, contract)
    source_components = [int(value) for value in contract["component_support"]["source_component_indices"]]
    source_coverage = [float(component_rows[index]["quad_support_coverage"]) for index in source_components]

    gates = contract["gates"]
    winner_margin = float(winner["score"] - runner_up["score"])
    development_gates = {
        "dictionary_winner_margin": winner_margin >= float(gates["minimum_dictionary_winner_margin"]),
        "development_pooled_score": float(development_pooled["score"]) >= float(gates["minimum_development_pooled_score"]),
        "each_development_balanced_accuracy": min(float(row["balanced_accuracy"]) for row in development_rows) >= float(gates["minimum_each_development_balanced_accuracy"]),
        "source_component_quad_coverage": min(source_coverage) >= float(gates["minimum_source_component_quad_coverage"]),
        "quad_geometry_valid": _quad_is_valid(fitted_quad, contract["geometry_bounds"]),
    }
    development_decisive = all(development_gates.values())

    corroboration_frames: list[np.ndarray] = []
    corroboration_rows: list[dict[str, Any]] = []
    corroboration_pooled: dict[str, Any] | None = None
    corroboration_gates = {"corroboration_opened_only_after_decisive_development": development_decisive, "corroboration_no_refit": development_decisive}
    if development_decisive:
        corroboration_frames = [_decode_initial_frame(by_position[position]) for position in contract["split"]["corroboration_positions"]]
        corroboration_gray = [cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in corroboration_frames]
        corroboration_pooled = _pattern_score(corroboration_gray, fitted_quad, cells, contract["development_search"])
        corroboration_rows = [
            {"split_position": position, **_pattern_score([gray], fitted_quad, cells, contract["development_search"])}
            for position, gray in zip(contract["split"]["corroboration_positions"], corroboration_gray, strict=True)
        ]
        corroboration_gates.update({
            "corroboration_pooled_score": float(corroboration_pooled["score"]) >= float(gates["minimum_corroboration_pooled_score"]),
            "corroboration_score_regression": float(development_pooled["score"] - corroboration_pooled["score"]) <= float(gates["maximum_corroboration_score_regression"]),
            "each_corroboration_balanced_accuracy": min(float(row["balanced_accuracy"]) for row in corroboration_rows) >= float(gates["minimum_each_corroboration_balanced_accuracy"]),
        })
    else:
        corroboration_gates["corroboration_not_opened_after_failed_development"] = True

    complete_parameters = json.loads((REPO_ROOT / contract["sources"]["or126_parameters"]["path"]).read_text())
    support = complete_parameters["support_plane"]
    camera = complete_parameters["camera"]
    plane_point = np.asarray(support["point"], dtype=np.float64)
    plane_normal = np.asarray(support["normal"], dtype=np.float64)
    world_corners = np.stack([_ray_plane_point(pixel, camera, 320, 240, plane_point, plane_normal) for pixel in fitted_quad])
    from .observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll
    projected, _ = _project_triangles_roll(np.repeat(world_corners[:, None, :], 3, axis=1), camera, 320, 240)
    reprojection_error = float(np.max(np.abs(projected[:, 0, :] - fitted_quad)))
    reprojection_gate = reprojection_error <= float(gates["maximum_reprojection_error_px"])

    parameters: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_clipped_planar_fixture_parameters.v1",
        "source_component_indices": source_components,
        "source_raw_residual_pixel_count": int(sum(component_rows[index]["raw_pixel_count"] for index in source_components)),
        "procedural_pattern": {
            "dictionary": contract["development_search"]["dictionary"],
            "dictionary_entry_index": int(winner["dictionary_entry_index"]),
            "rotation_quarter_turns": int(winner["rotation_quarter_turns"]),
            "border_cells": 1,
            "cells": cells.astype(int).tolist(),
            "physical_pixel_texture_projection": False,
        },
        "development_fitted_corners_px": fitted_quad.tolist(),
        "model_coordinate_corners": world_corners.tolist(),
        "support_plane": support,
        "camera": camera,
        "clipped_in_physical_view": True,
        "plane_projection_is_self_consistency_not_physical_metric_calibration": True,
    }
    parameters["artifact_sha256"] = canonical_digest(parameters)
    output_directory.mkdir(parents=True, exist_ok=True)
    parameter_path = output_directory / "clipped-planar-fixture-parameters.json"
    atomic_write_json(parameter_path, parameters)

    all_frames = development_frames + corroboration_frames
    audit = np.full((len(all_frames) * 120, 320, 3), 255, dtype=np.uint8)
    for index, frame in enumerate(all_frames):
        panel = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
        polygon = np.rint(fitted_quad * np.asarray([0.5, 0.5])).astype(np.int32)
        cv2.polylines(panel, [polygon], True, (0, 255, 0) if index < 7 else (255, 180, 0), 1, cv2.LINE_AA)
        cell_panel = cv2.cvtColor(cv2.resize(cells * 255, (120, 120), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
        audit[index * 120 : (index + 1) * 120, :160] = panel
        audit[index * 120 : (index + 1) * 120, 180:300] = cell_panel
    audit_path = output_directory / "clipped-planar-fixture-parameterization-audit.png"
    ok, encoded = cv2.imencode(".png", audit, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR129 audit encoding failed")
    audit_path.write_bytes(encoded.tobytes())

    integrity_gates = {
        "exact_seven_development_frames": len(development_frames) == 7,
        "corroboration_condition_respected": (development_decisive and len(corroboration_frames) == 4) or (not development_decisive and len(corroboration_frames) == 0),
        "corroboration_no_refit": True,
        "exact_dictionary_and_rotation_search": len(ranking) == 587 * 4,
        "source_components_exactly_zero_one_two": source_components == [0, 1, 2],
        "source_raw_residual_pixel_count_exact": int(parameters["source_raw_residual_pixel_count"]) == 322,
        "procedural_cells_not_physical_pixel_texture": True,
        "zero_render_overlay_video_retry_replay_hardware_or_paid_compute": True,
        "backprojection_reprojection_self_consistency": reprojection_gate,
    }
    passed = development_decisive and all(corroboration_gates.values()) and all(integrity_gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_clipped_planar_fixture_parameterization_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_CLIPPED_PLANAR_FIXTURE_PARAMETERIZED" if passed else "TERMINAL_CLIPPED_PLANAR_FIXTURE_PARAMETERIZATION_FAILED",
        "proof_class": contract["proof_class"],
        "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]},
        "dictionary_ranking": {"winner": winner, "runner_up": runner_up, "winner_margin": winner_margin, "candidate_count": len(ranking)},
        "optimizer": optimizer_row,
        "development": {"pooled": development_pooled, "rows": development_rows, "gates": development_gates, "decisive": development_decisive},
        "corroboration": {"pooled": corroboration_pooled, "rows": corroboration_rows, "gates": corroboration_gates, "refit_performed": False},
        "component_support": component_rows,
        "parameterization": {"path": str(parameter_path.relative_to(REPO_ROOT)), "sha256": sha256_file(parameter_path), "artifact_sha256": parameters["artifact_sha256"]},
        "audit": {"path": str(audit_path.relative_to(REPO_ROOT)), "sha256": sha256_file(audit_path), "layout": "per_episode_physical_outline_beside_separate_procedural_cells"},
        "summary": {"dictionary_entry_index": int(winner["dictionary_entry_index"]), "rotation_quarter_turns": int(winner["rotation_quarter_turns"]), "fitted_corners_px": fitted_quad.tolist(), "reprojection_error_px": reprojection_error},
        "integrity_gates": integrity_gates,
        "execution": {"physical_video_decodes": len(all_frames), "physical_frame_reads": len(all_frames), "dictionary_candidates_scored": len(ranking), "geometry_optimizations": 1, "renders": 0, "physical_pixel_texture_projections": 0, "screen_space_candidate_overlays": 0, "candidate_videos": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_TWO_FIXTURE_SHARED_ZBUFFER_STATIC_COMPARISON" if passed else "STOP_CLIPPED_FIXTURE_PARAMETERIZATION_FAILED",
        "next_transition": "freeze_or130_two_fixture_shared_zbuffer_static_comparison" if passed else "stop_or129_parameterization_failed",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
