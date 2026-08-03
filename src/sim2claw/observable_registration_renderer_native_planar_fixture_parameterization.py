"""Parameterize one complete retained-footage planar fixture without rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _apply_board_anchored_se2
from .observable_registration_board_grid_camera_sensor_roll_successor import _project_triangles_roll
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, quaternion_matrix_wxyz, sha256_file
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import _ray_plane_point
from .observable_registration_workcell_static_component_surface_identification import _detector


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_planar_fixture_parameterization_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_planar_fixture_parameterization_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_planar_fixture_parameterization_v1"


def load_planar_fixture_parameterization_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR126 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR126 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR126 split drifted")
    parameterization = contract["parameterization"]
    if parameterization["dictionary"] != "DICT_APRILTAG_36h11" or parameterization["procedural_cell_count_per_axis"] != 8:
        raise ValueError("OR126 procedural family drifted")
    if parameterization["selected_complete_component_index"] != 4 or parameterization["physical_pixel_texture_projection"] is not False:
        raise ValueError("OR126 component or texture boundary drifted")
    gates = contract["gates"]
    if gates["maximum_corroboration_corner_rms_px"] != 1.0 or gates["required_distinct_entry_count"] != 1:
        raise ValueError("OR126 no-refit gate drifted")
    resources = contract["resource_boundary"]
    zero = ("renders_allowed", "physical_pixel_texture_projections_allowed", "candidate_videos_allowed", "parameter_searches_allowed", "retries_allowed", "simulator_replays_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR126 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR126 authority must remain closed")
    return contract


def _procedural_cells(entry_index: int) -> list[list[int]]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    marker = cv2.aruco.generateImageMarker(dictionary, int(entry_index), 8, borderBits=1)
    cells = (marker > 0).astype(np.uint8)
    if cells.shape != (8, 8) or set(np.unique(cells).tolist()) - {0, 1}:
        raise ValueError("OR126 procedural cell generation drifted")
    return cells.astype(int).tolist()


def _tabletop_plane(
    scene: dict[str, Any], trace: dict[str, Any], frozen: dict[str, Any], support: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    frame = trace["frames"][0]
    positions = np.asarray(frame["p"], dtype=np.float64).reshape((-1, 3))
    quaternions = np.asarray(frame["q"], dtype=np.float64).reshape((-1, 4))
    rotations = [quaternion_matrix_wxyz(value) for value in quaternions]
    static = frozen["static_workcell_transform"]
    positions, rotations = _apply_board_anchored_se2(
        positions,
        rotations,
        anchor_body_id=int(static["anchor_body_id"]),
        transformed_body_ids=[int(value) for value in static["transformed_body_ids"]],
        vector=np.asarray(static["vector"], dtype=np.float64),
    )
    geom = [
        value
        for value in scene["geoms"]
        if int(value["id"]) == int(support["geom_id"]) and int(value["body_id"]) == int(support["body_id"])
    ]
    if len(geom) != 1 or geom[0]["name"] != support["geom_name"]:
        raise ValueError("OR126 support plane identity drifted")
    geom = geom[0]
    body_id = int(support["body_id"])
    rotation = rotations[body_id] @ quaternion_matrix_wxyz(geom["quaternion_wxyz"])
    center = positions[body_id] + rotations[body_id] @ np.asarray(geom["position"], dtype=np.float64)
    normal = rotation[:, 2]
    normal /= np.linalg.norm(normal)
    return center + normal * float(geom["size"][2]), normal


def _detect_complete_fixture(frame: np.ndarray) -> tuple[int, np.ndarray]:
    corners, ids, _ = _detector().detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    if ids is None or len(ids) != 1 or len(corners) != 1:
        raise ValueError("OR126 expected exactly one complete planar fixture")
    return int(ids.reshape(-1)[0]), corners[0].reshape(4, 2).astype(np.float64)


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR126 one-run receipt already exists")
    contract = load_planar_fixture_parameterization_contract(contract_path)
    predecessor = json.loads((REPO_ROOT / contract["sources"]["or125_receipt"]["path"]).read_text())
    if predecessor["artifact_sha256"] != contract["sources"]["or125_receipt"]["artifact_sha256"] or predecessor["selected_surface_family"] != "separate_static_planar_fixture":
        raise ValueError("OR126 OR125 prerequisite drifted")

    or95_path = REPO_ROOT / contract["sources"]["or95_contract"]["path"]
    or95 = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(or95_path)
    episodes = _episode_inventory(or95)
    by_position = {int(row["split_position"]): row for row in episodes}
    rows: list[dict[str, Any]] = []
    corners_by_position: dict[int, np.ndarray] = {}
    audit_frame: np.ndarray | None = None

    for position in contract["split"]["development_positions"] + contract["split"]["corroboration_positions"]:
        episode = by_position[position]
        video = episode["physical_video"]
        video_path = REPO_ROOT / video["path"]
        if sha256_file(video_path) != video["sha256"]:
            raise ValueError("OR126 physical video identity drifted")
        frame = cv2.flip(
            _decode_selected_frames(
                video_path,
                selected_indices=np.asarray([0], dtype=np.int64),
                expected_frame_count=int(video["frame_count"]),
                expected_width=int(video["width_px"]),
                expected_height=int(video["height_px"]),
                output_width=320,
                output_height=240,
            )[0],
            -1,
        )
        entry_index, corners = _detect_complete_fixture(frame)
        if position == 1:
            audit_frame = frame.copy()
        corners_by_position[position] = corners
        rows.append({
            "split_position": position,
            "split": "development" if position <= 7 else "corroboration",
            "recording_id": episode["recording_id"],
            "dictionary_entry_index": entry_index,
            "corners_px": corners.tolist(),
        })

    development = np.stack([corners_by_position[position] for position in contract["split"]["development_positions"]])
    median_corners = np.median(development, axis=0)
    entry_indices = {int(row["dictionary_entry_index"]) for row in rows}
    entry_index = min(entry_indices)
    for row in rows:
        corners = np.asarray(row["corners_px"], dtype=np.float64)
        row["corner_rms_vs_development_median_px"] = float(np.sqrt(np.mean(np.square(corners - median_corners))))

    scene = json.loads((REPO_ROOT / or95["sources"]["shared_scene_manifest"]["path"]).read_text())
    first_episode = by_position[1]
    trace = json.loads((REPO_ROOT / first_episode["state_trace"]["path"]).read_text())
    support = contract["support_plane"]
    plane_point, plane_normal = _tabletop_plane(scene, trace, or95["frozen_candidate"], support)
    camera = or95["frozen_candidate"]["camera"]
    world_corners = np.stack([
        _ray_plane_point(pixel, camera, 320, 240, plane_point, plane_normal) for pixel in median_corners
    ])
    projected, _ = _project_triangles_roll(np.repeat(world_corners[:, None, :], 3, axis=1), camera, 320, 240)
    reprojection_error = float(np.max(np.abs(projected[:, 0, :] - median_corners)))
    edge_lengths = [float(np.linalg.norm(world_corners[(index + 1) % 4] - world_corners[index])) for index in range(4)]
    corroboration_rms = [float(row["corner_rms_vs_development_median_px"]) for row in rows if row["split"] == "corroboration"]

    parameterization: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_planar_fixture_parameters.v1",
        "source_component_index": int(contract["parameterization"]["selected_complete_component_index"]),
        "procedural_pattern": {
            "dictionary": contract["parameterization"]["dictionary"],
            "dictionary_entry_index": entry_index,
            "border_cells": 1,
            "cells": _procedural_cells(entry_index),
            "physical_pixel_texture_projection": False,
        },
        "development_median_corners_px": median_corners.tolist(),
        "model_coordinate_corners": world_corners.tolist(),
        "model_coordinate_edge_lengths": edge_lengths,
        "support_plane": {"point": plane_point.tolist(), "normal": plane_normal.tolist(), **support},
        "camera": camera,
        "plane_projection_is_self_consistency_not_physical_metric_calibration": True,
    }
    parameterization["artifact_sha256"] = canonical_digest(parameterization)
    output_directory.mkdir(parents=True, exist_ok=True)
    parameter_path = output_directory / "planar-fixture-parameters.json"
    atomic_write_json(parameter_path, parameterization)

    if audit_frame is None:
        raise ValueError("OR126 audit frame missing")
    audit = np.full((240, 640, 3), 255, dtype=np.uint8)
    cells = np.asarray(parameterization["procedural_pattern"]["cells"], dtype=np.uint8)
    pattern = cv2.cvtColor(
        cv2.resize((cells * 255), (240, 240), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR
    )
    audit[:, 360:600] = pattern
    audit[:, :320] = audit_frame
    cv2.polylines(audit[:, :320], [np.rint(median_corners).astype(np.int32)], True, (0, 255, 0), 2, cv2.LINE_AA)
    audit_path = output_directory / "planar-fixture-parameterization-audit.png"
    ok, encoded = cv2.imencode(".png", audit, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR126 audit encoding failed")
    audit_path.write_bytes(encoded.tobytes())

    gates = {
        "exactly_one_dictionary_entry_across_all_episodes": len(entry_indices) == int(contract["gates"]["required_distinct_entry_count"]),
        "corroboration_corner_rms_within_gate": max(corroboration_rms) <= float(contract["gates"]["maximum_corroboration_corner_rms_px"]),
        "exact_backprojection_reprojection_self_consistency": reprojection_error <= float(contract["gates"]["maximum_reprojection_error_px"]),
        "procedural_cells_not_physical_pixel_texture": True,
        "zero_render_video_search_retry_replay_hardware_or_paid_compute": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_planar_fixture_parameterization_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_RENDERER_NATIVE_PLANAR_FIXTURE_PARAMETERIZED" if passed else "TERMINAL_PLANAR_FIXTURE_PARAMETERIZATION_FAILED",
        "proof_class": contract["proof_class"],
        "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]},
        "rows": rows,
        "parameterization": {"path": str(parameter_path.relative_to(REPO_ROOT)), "sha256": sha256_file(parameter_path), "artifact_sha256": parameterization["artifact_sha256"]},
        "audit": {"path": str(audit_path.relative_to(REPO_ROOT)), "sha256": sha256_file(audit_path), "layout": "physical_initial_frame_with_complete_fixture_quad_beside_procedural_cells"},
        "summary": {"dictionary_entry_index": entry_index, "maximum_corroboration_corner_rms_px": max(corroboration_rms), "maximum_reprojection_error_px": reprojection_error, "model_coordinate_edge_lengths": edge_lengths},
        "integrity_gates": gates,
        "execution": {"physical_video_decodes": 11, "physical_frame_reads": 11, "parameterizations": 1, "renders": 0, "physical_pixel_texture_projections": 0, "candidate_videos": 0, "parameter_searches": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_RENDERER_NATIVE_PLANAR_FIXTURE_RENDER" if passed else "STOP_PARAMETERIZATION_FAILED",
        "next_transition": "freeze_or127_renderer_native_planar_fixture_static_comparison" if passed else "stop_or126_parameterization_failed",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
