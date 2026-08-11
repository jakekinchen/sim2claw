"""Read-only audit of OR34 pawn coordinate and compiled landmark semantics."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .capture import load_capture_config
from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path
from .observable_registration_measured_state_visual_twin import (
    load_measured_state_visual_twin_contract,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import (
    _project_world_to_registered_pixel,
    _scaled_camera,
    load_visible_divergence_video_contract,
)
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .scene import scene_geometry


SCHEMA = "sim2claw.observable_registration_or34_coordinate_landmark_audit_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_or34_coordinate_landmark_audit_receipt.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_or34_coordinate_landmark_audit_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_or34_coordinate_landmark_audit_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_coordinate_landmark_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR151 coordinate landmark audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR151 contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    audit = contract["audit"]
    _require(
        audit["selected_piece"] == "brown_pawn_d1"
        and audit["source_square"] == "d1"
        and audit["primary_coordinate_system"] == "board_file_rank_coordinates"
        and audit["compile_or18_scene_with_canonical_piece_reset"] is True,
        "OR151 audit identity widened",
    )
    _require(not any(contract["claim_limits"].values()), "OR151 claim boundary widened")
    return contract


def board_coordinate_to_scene_world(
    board_coordinate: np.ndarray, *, scene_path: Path
) -> np.ndarray:
    """Transport a retained file/rank coordinate through one scene's board basis."""

    coordinate = np.asarray(board_coordinate, dtype=np.float64)
    _require(
        coordinate.shape == (2,) and bool(np.isfinite(coordinate).all()),
        "board coordinate must be finite 2D",
    )
    a1 = np.asarray(current_square_center("a1", config_path=scene_path), dtype=np.float64)
    b1 = np.asarray(current_square_center("b1", config_path=scene_path), dtype=np.float64)
    a2 = np.asarray(current_square_center("a2", config_path=scene_path), dtype=np.float64)
    return a1 + ((coordinate[0] - 0.5) * (b1 - a1)) + ((coordinate[1] - 0.5) * (a2 - a1))


def build_coordinate_landmark_audit(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_coordinate_landmark_audit_contract(contract_path, root=root)
    source_hashes_before = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }

    or34_contract_path = _bound_path(
        contract["sources"]["or34_contract"], root=root, label="OR34 contract"
    )
    or34_contract = load_measured_state_visual_twin_contract(or34_contract_path, root=root)
    or34_receipt = load_json_object(
        _bound_path(contract["sources"]["or34_receipt"], root=root, label="OR34 receipt"),
        label="OR34 receipt",
    )
    endpoint = load_json_object(
        _bound_path(
            contract["sources"]["physical_endpoint_receipt"],
            root=root,
            label="physical endpoint",
        ),
        label="physical endpoint",
    )
    or19_path = _bound_path(
        contract["sources"]["or19_contract"], root=root, label="OR19 contract"
    )
    or19, c6 = load_unilateral_push_dynamic_replay_contract(or19_path, root=root)
    scene_path = _bound_path(
        contract["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    _require(
        or19["sources"]["or18_scene"]["sha256"]
        == contract["sources"]["or18_scene"]["sha256"],
        "OR18 scene lineage changed",
    )

    coordinate = np.asarray(
        endpoint["observations"]["initial"]["board_coordinate"], dtype=np.float64
    )
    legacy_world = np.asarray(
        c6["initialization"]["physical_d1_world_position_m"], dtype=np.float64
    )
    transported_world = board_coordinate_to_scene_world(coordinate, scene_path=scene_path)
    d1_world = np.asarray(current_square_center("d1", config_path=scene_path), dtype=np.float64)

    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    selected_piece = contract["audit"]["selected_piece"]
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_piece)
    joint_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_piece}_free"
    )
    _require(body_id >= 0 and joint_id >= 0, "selected pawn binding missing")
    qpos_address = int(model.jnt_qposadr[joint_id])
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    canonical_qpos = np.asarray(data.qpos[qpos_address : qpos_address + 3]).copy()
    canonical_xpos = np.asarray(data.xpos[body_id]).copy()
    landmark_delta = float(np.linalg.norm(canonical_qpos - canonical_xpos))

    config = load_capture_config(scene_path)
    geometry = scene_geometry(config)
    legacy_d1_error = float(np.linalg.norm(legacy_world[:2] - d1_world[:2]))
    transported_d1_error = float(
        np.linalg.norm(transported_world[:2] - d1_world[:2])
    )
    required_xy_change = float(
        np.linalg.norm(transported_world[:2] - legacy_world[:2])
    )

    or26_path = _bound_path(
        or34_contract["sources"]["or26_contract"], root=root, label="OR26 contract"
    )
    or26 = load_visible_divergence_video_contract(or26_path, root=root)
    camera, simulator_corners, camera_values, _ = _scaled_camera(or26, root=root)
    board_projection = load_json_object(
        _bound_path(
            or26["sources"]["physical_board_projection"],
            root=root,
            label="physical board projection",
        ),
        label="physical board projection",
    )
    physical_corners = np.asarray(
        board_projection["board_lattice"]["playing_corners_px"], dtype=np.float64
    )
    display_homography = cv2.getPerspectiveTransform(
        simulator_corners.astype(np.float32), physical_corners.astype(np.float32)
    )
    observed_pixel = np.asarray(
        endpoint["observations"]["initial"]["pixel_base_center"], dtype=np.float64
    )
    legacy_replay_world = np.asarray(
        [legacy_world[0], legacy_world[1], d1_world[2]], dtype=np.float64
    )
    legacy_pixel = _project_world_to_registered_pixel(
        legacy_replay_world,
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )
    transported_pixel = _project_world_to_registered_pixel(
        transported_world,
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )

    acceptance = contract["acceptance"]
    gates = {
        "source_hashes_match": all(
            source_hashes_before[name] == binding["sha256"]
            for name, binding in contract["sources"].items()
        ),
        "body_xpos_equals_free_joint_translation": landmark_delta
        <= float(acceptance["body_xpos_equals_free_joint_translation_tolerance_m"]),
        "legacy_world_copy_exposes_material_d1_error": legacy_d1_error
        >= float(acceptance["legacy_world_copy_offset_from_or18_d1_minimum_m"]),
        "board_coordinate_transport_preserves_observed_within_square_offset": transported_d1_error
        <= float(acceptance["remapped_offset_from_or18_d1_maximum_m"]),
        "mujoco_step_calls_zero": True,
    }
    source_hashes_after = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    gates["bound_sources_unchanged"] = source_hashes_after == source_hashes_before
    status = (
        "PASS_COORDINATE_FRAME_MISMATCH_CONFIRMED"
        if all(gates.values())
        else "TERMINAL_COORDINATE_LANDMARK_AUDIT_FAILED"
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "sources": source_hashes_before,
        "scene_geometry": {
            "board_center_world_xy_m": list(map(float, geometry.board_center)),
            "board_side_m": float(geometry.board_side),
            "square_side_m": float(geometry.square_size),
            "board_yaw_world_degrees": float(geometry.board_yaw_degrees),
            "board_thickness_m": float(geometry.board_thickness),
            "support_plane_z_m": float(d1_world[2]),
        },
        "coordinate_audit": {
            "physical_board_coordinate": coordinate.tolist(),
            "or18_d1_center_world_m": d1_world.tolist(),
            "legacy_copied_world_m": legacy_world.tolist(),
            "legacy_replay_world_after_support_z_replacement_m": legacy_replay_world.tolist(),
            "transported_world_m": transported_world.tolist(),
            "legacy_d1_planar_error_m": legacy_d1_error,
            "transported_d1_planar_error_m": transported_d1_error,
            "required_initial_xy_change_m": required_xy_change,
        },
        "landmark_audit": {
            "canonical_free_joint_translation_m": canonical_qpos.tolist(),
            "canonical_body_xpos_m": canonical_xpos.tolist(),
            "body_to_free_joint_translation_error_m": landmark_delta,
            "body_origin_is_base_landmark_supported": landmark_delta
            <= float(acceptance["body_xpos_equals_free_joint_translation_tolerance_m"]),
            "legacy_support_z_minus_or18_support_plane_m": float(legacy_world[2] - d1_world[2]),
            "or34_replay_replaced_stored_z_with_scene_support_z": True,
        },
        "nominal_projection_diagnostic": {
            "calibration_claimed": False,
            "observed_initial_base_center_px": observed_pixel.tolist(),
            "legacy_projected_px": legacy_pixel.tolist(),
            "transported_projected_px": transported_pixel.tolist(),
            "legacy_residual_px": float(np.linalg.norm(legacy_pixel - observed_pixel)),
            "transported_residual_px": float(np.linalg.norm(transported_pixel - observed_pixel)),
            "or34_reported_legacy_residual_px": float(
                or34_receipt["visible_comparison"]["registered_initial_pawn_error_px"]
            ),
        },
        "execution": {
            "mujoco_forward_calls": 1,
            "mujoco_step_calls": 0,
            "simulator_replays": 0,
            "fits": 0,
            "parameter_searches": 0,
        },
        "gates": gates,
        "successor": {
            "admitted": status == "PASS_COORDINATE_FRAME_MISMATCH_CONFIRMED",
            "sole_allowed_factor": "selected_pawn_initial_xy_board_coordinate_transport_into_or18_scene",
            "or34_mutable": False,
        },
        "claim_limits": contract["claim_limits"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


__all__ = [
    "board_coordinate_to_scene_world",
    "build_coordinate_landmark_audit",
    "load_coordinate_landmark_audit_contract",
]
