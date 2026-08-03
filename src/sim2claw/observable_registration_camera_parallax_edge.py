"""Evaluate board-preserving camera parallax against the OR55 edge gate."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_c922_pixel_lattice_refinement import project_camera_family
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
from .observable_registration_visible_divergence_video import (
    _candidate_config,
    _scaled_camera,
    _source_pose_by_sample,
    load_visible_divergence_video_contract,
)
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .real_to_sim_transfer import _configure_camera


SCHEMA = "sim2claw.observable_registration_camera_parallax_edge_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_camera_parallax_edge_receipt.v1"
ROWS_SCHEMA = "sim2claw.observable_registration_camera_parallax_edge_rows.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_camera_parallax_edge_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_camera_parallax_edge_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_camera_parallax_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="camera parallax edge")
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
        family["board_to_camera_translation_scale"] == [0.85, 1.0, 1.15]
        and family["focal_length_scale"] == [0.85, 1.0, 1.15]
        and family["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
        and family["candidate_count"] == 36
        and family["preserve_camera_rotation"] is True
        and family["preserve_principal_point"] is True
        and family["recompute_single_board_plane_display_homography"] is True
        and family["minimum_development_mean_full_frame_linear_pixel_similarity"]
        == 0.78,
        "candidate family drifted",
    )
    _require(all(contract["prohibitions"].values()), "prohibition relaxed")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _camera_candidate(
    base_camera: dict[str, Any],
    base_values: np.ndarray,
    *,
    translation_scale: float,
    focal_scale: float,
    board_origin_world: np.ndarray,
    board_points: np.ndarray,
    principal_point: np.ndarray,
    physical_corners: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    values = base_values.copy()
    values[0] *= focal_scale
    values[4:7] *= translation_scale
    camera_cv_to_world = np.asarray(base_camera["camera_cv_to_world"], dtype=np.float64)
    world_to_camera = camera_cv_to_world.T
    world_translation = values[4:7] - world_to_camera @ board_origin_world
    camera_center_world = -world_to_camera.T @ world_translation
    camera = {
        "position_world": camera_center_world,
        "camera_cv_to_world": camera_cv_to_world,
        "fovy_degrees": math.degrees(
            2.0 * math.atan(480.0 / (2.0 * float(values[0])))
        ),
    }
    projected, _ = project_camera_family(
        board_points,
        values,
        principal_point_px=principal_point,
        radial_term_count=0,
    )
    homography = cv2.getPerspectiveTransform(
        projected.astype(np.float32), physical_corners.astype(np.float32)
    )
    return camera, homography, projected


def _render_indices(
    renderer: mujoco.Renderer,
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    qpos_addresses: np.ndarray,
    applied_model: np.ndarray,
    selected_qpos: int,
    poses: dict[int, tuple[np.ndarray, np.ndarray]],
    camera: dict[str, Any],
    homography: np.ndarray,
    indices: list[int],
) -> list[np.ndarray]:
    _configure_camera(model, data, camera)
    frames: list[np.ndarray] = []
    for index in indices:
        data.qpos[qpos_addresses] = applied_model[index]
        pawn_position, pawn_quaternion = poses[index]
        data.qpos[selected_qpos : selected_qpos + 3] = pawn_position
        data.qpos[selected_qpos + 3 : selected_qpos + 7] = pawn_quaternion
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera="workcell")
        raw = cv2.cvtColor(renderer.render().copy(), cv2.COLOR_RGB2BGR)
        frames.append(
            cv2.warpPerspective(
                raw,
                homography,
                (640, 480),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(205, 205, 205),
            )
        )
    return frames


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


def evaluate_camera_parallax_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR57 one-run receipt already exists")
    contract = load_camera_parallax_contract(contract_path, root=root)
    or26_contract = load_visible_divergence_video_contract(
        _bound_path(contract["sources"]["or26_contract"], root=root, label="OR26 contract"),
        root=root,
    )
    or26_receipt = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    or56_contract = _bound_json(
        contract["sources"]["or56_contract"], root=root, label="OR56 contract"
    )
    or56_receipt = _bound_json(
        contract["sources"]["or56_receipt"], root=root, label="OR56 receipt"
    )
    or55_contract = _bound_json(
        or56_contract["sources"]["or55_contract"], root=root, label="OR55 contract"
    )
    _require(
        or56_receipt["status"] == "PASS_TIME_INVARIANT_APPEARANCE_ADVANCE_BELOW_TARGET"
        and not or56_receipt["all_acceptance_gates_pass"],
        "OR56 source boundary drifted",
    )
    timeline = contract["timeline"]
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
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
    _require(len(physical_frames) == len(or56_frames) == 531, "video length drifted")
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }

    or19 = _bound_json(
        or26_contract["sources"]["or19_contract"], root=root, label="OR19 contract"
    )
    c6, candidate_config, _, applied_model = _candidate_config(or19, root=root)
    internal_trace = _bound_json(
        or26_contract["sources"]["or21_internal_trace"], root=root, label="OR21 internal"
    )
    source_trace = _bound_json(
        or26_contract["sources"]["or21_source_trace"], root=root, label="OR21 source"
    )
    poses = _source_pose_by_sample(internal_trace, source_trace)
    scene_path = _bound_path(
        or26_contract["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(scene_path, pawn_height_m=0.034, canonical_piece_reset=True).compile()
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate_config["bindings"]["joint_names"]
    ]
    _require(min(joint_ids) >= 0, "robot joint binding incomplete")
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids], dtype=np.int64
    )
    selected_name = c6["initialization"]["selected_piece"]
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(selected_joint >= 0, "selected pawn binding incomplete")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    base_camera, _, base_values, camera_report = _scaled_camera(or26_contract, root=root)
    board_origin_world = np.asarray(camera_report["board_origin_world_m"], dtype=np.float64)
    side = float(or26_contract["camera_and_display_registration"]["measured_playing_side_m"])
    board_points = np.asarray(
        [[0.0, 0.0, 0.0], [side, 0.0, 0.0], [side, side, 0.0], [0.0, side, 0.0]],
        dtype=np.float64,
    )
    or10 = _bound_json(
        or26_contract["sources"]["or10_camera_receipt"], root=root, label="OR10 camera"
    )
    principal_point = np.asarray(
        or10["pooled_board_plane_candidate"]["principal_point_px"], dtype=np.float64
    )
    physical_corners = np.asarray(
        or26_receipt["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.float64,
    )
    family = contract["candidate_family"]
    response = np.asarray(family["frozen_bgr_affine_matrix"], dtype=np.float64)
    edge_config = or55_contract["metric"]["edge"]
    development = partitions["development"]
    candidates: list[dict[str, Any]] = []
    try:
        renderer = mujoco.Renderer(model, height=480, width=640)
    except Exception as error:
        output_directory.mkdir(parents=True, exist_ok=True)
        unsigned = {
            "schema_version": RECEIPT_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "status": "TERMINAL_RENDER_RUNTIME_UNAVAILABLE_NO_CANDIDATE",
            "proof_class": contract["proof_class"],
            "source_bindings": {
                name: binding["sha256"]
                for name, binding in contract["sources"].items()
            },
            "runtime_failure": {
                "exception_type": type(error).__name__,
                "message": str(error),
                "macos_plain_python_cgl_available": False,
                "mjpython_uv_standalone_shared_library_compatible": False,
                "linux_container_completed": False,
                "linux_container_failure": "full_project_sync_selected_unneeded_cuda_stack_and_container_storage_returned_io_error",
                "gpt_pro_advisor_available": False,
            },
            "selection": None,
            "metrics": None,
            "acceptance_gates": None,
            "all_acceptance_gates_pass": False,
            "execution": {
                "camera_candidate_count": 0,
                "camera_blur_candidate_evaluations": 0,
                "development_state_renders": 0,
                "selected_full_state_renders": 0,
                "physics_integrations": 0,
                "action_changes": 0,
                "state_changes": 0,
                "scene_geometry_changes": 0,
                "hardware_actions": 0,
            },
            "next_mechanism": "retained_video_only_spatial_edge_residual_factorization",
            "claim_limits": {
                "episode_specific_visual_replay_only": False,
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
    try:
        for translation_scale in family["board_to_camera_translation_scale"]:
            for focal_scale in family["focal_length_scale"]:
                camera, homography, projected = _camera_candidate(
                    base_camera,
                    base_values,
                    translation_scale=float(translation_scale),
                    focal_scale=float(focal_scale),
                    board_origin_world=board_origin_world,
                    board_points=board_points,
                    principal_point=principal_point,
                    physical_corners=physical_corners,
                )
                raw_frames = _render_indices(
                    renderer,
                    model,
                    data,
                    qpos_addresses=qpos_addresses,
                    applied_model=applied_model,
                    selected_qpos=selected_qpos,
                    poses=poses,
                    camera=camera,
                    homography=homography,
                    indices=development,
                )
                for blur_kernel in family["gaussian_blur_kernel_px"]:
                    primary: list[float] = []
                    edges: list[float] = []
                    for index, raw in zip(development, raw_frames, strict=True):
                        transformed = _apply_candidate(
                            raw, kernel=int(blur_kernel), matrix=response
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
                            "board_to_camera_translation_scale": float(translation_scale),
                            "focal_length_scale": float(focal_scale),
                            "gaussian_blur_kernel_px": int(blur_kernel),
                            "development_full_frame_linear_pixel_similarity": primary_summary,
                            "development_tolerant_edge_f1": _summary(edges),
                            "eligible_mean_floor": float(primary_summary["mean"])
                            >= float(
                                family[
                                    "minimum_development_mean_full_frame_linear_pixel_similarity"
                                ]
                            ),
                            "camera_position_world_m": np.asarray(
                                camera["position_world"], dtype=np.float64
                            ).tolist(),
                            "vertical_fov_degrees": float(camera["fovy_degrees"]),
                            "simulator_playing_corners_before_warp_px": projected.tolist(),
                            "display_homography": homography.tolist(),
                        }
                    )
        eligible = [candidate for candidate in candidates if candidate["eligible_mean_floor"]]
        selection_pool = eligible if eligible else candidates
        selected = max(
            selection_pool,
            key=lambda item: (
                float(item["development_tolerant_edge_f1"]["mean"]),
                float(item["development_full_frame_linear_pixel_similarity"]["mean"]),
                -abs(float(item["board_to_camera_translation_scale"]) - 1.0),
                -abs(float(item["focal_length_scale"]) - 1.0),
                -int(item["gaussian_blur_kernel_px"]),
            ),
        )
        selected_camera, selected_homography, _ = _camera_candidate(
            base_camera,
            base_values,
            translation_scale=float(selected["board_to_camera_translation_scale"]),
            focal_scale=float(selected["focal_length_scale"]),
            board_origin_world=board_origin_world,
            board_points=board_points,
            principal_point=principal_point,
            physical_corners=physical_corners,
        )
        raw_full = _render_indices(
            renderer,
            model,
            data,
            qpos_addresses=qpos_addresses,
            applied_model=applied_model,
            selected_qpos=selected_qpos,
            poses=poses,
            camera=selected_camera,
            homography=selected_homography,
            indices=list(range(531)),
        )
    finally:
        renderer.close()
    selected_frames = [
        _apply_candidate(
            frame,
            kernel=int(selected["gaussian_blur_kernel_px"]),
            matrix=response,
        )
        for frame in raw_full
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
    metrics, rows, gates = _score_candidate_video(
        physical_frames,
        decoded_candidate,
        contract=contract,
        or26=or26_receipt,
        or55_contract=or55_contract,
    )
    rows_path = output_directory / "metric_rows.json"
    atomic_write_json(
        rows_path,
        {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": rows},
    )
    candidate_table_path = output_directory / "candidate_table.json"
    atomic_write_json(
        candidate_table_path,
        {
            "schema_version": "sim2claw.observable_registration_camera_parallax_edge_candidates.v1",
            "experiment_id": contract["experiment_id"],
            "selection_inputs": "development_only",
            "eligible_candidate_count": len(eligible),
            "candidates": candidates,
            "selected": selected,
        },
    )
    evaluation = contract["evaluation"]
    validation = partition_scores["validation"]
    stress = partition_scores["stress"]
    mechanism_advance = (
        float(validation["absolute_mean_edge_f1_improvement"])
        >= float(evaluation["minimum_validation_absolute_edge_f1_improvement"])
        and float(
            validation["selected_candidate"]["full_frame_linear_pixel_similarity"]["mean"]
        )
        >= float(evaluation["minimum_validation_mean_full_frame_linear_pixel_similarity"])
        and float(stress["absolute_mean_pixel_improvement"])
        >= -float(evaluation["maximum_stress_mean_regression_from_or56"])
    )
    passed = all(gates.values())
    status = (
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET"
        if passed
        else (
            "PASS_CAMERA_PARALLAX_EDGE_ADVANCE_BELOW_TARGET"
            if mechanism_advance
            else "TERMINAL_CAMERA_PARALLAX_EDGE_INSUFFICIENT"
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
            "eligible_candidate_count": len(eligible),
            "selected_board_to_camera_translation_scale": selected[
                "board_to_camera_translation_scale"
            ],
            "selected_focal_length_scale": selected["focal_length_scale"],
            "selected_gaussian_blur_kernel_px": selected["gaussian_blur_kernel_px"],
            "validation_and_stress_used_for_selection": False,
        },
        "partition_scores": partition_scores,
        "camera_parallax_edge_advance_gate_pass": mechanism_advance,
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
            "camera_candidate_count": 9,
            "camera_blur_candidate_evaluations": len(candidates),
            "development_state_renders": 9 * len(development),
            "selected_full_state_renders": 531,
            "physics_integrations": 0,
            "action_changes": 0,
            "state_changes": 0,
            "scene_geometry_changes": 0,
            "hardware_actions": 0,
        },
        "next_mechanism": (
            None
            if passed
            else "renderer_scene_geometry_and_robot_silhouette_factorization"
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
    evaluate_camera_parallax_once()


if __name__ == "__main__":
    main()
