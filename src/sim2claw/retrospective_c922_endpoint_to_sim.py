"""Hash-bound C922 endpoint observation transfer into the current simulator."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .current_workcell import build_current_workcell_spec, current_square_center
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import _piece_bodies


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "retrospective_c922_endpoint_to_sim_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "retrospective_c922_endpoint_to_sim_v1"
SCHEMA = "sim2claw.retrospective_c922_endpoint_to_sim.v1"
RECEIPT_SCHEMA = "sim2claw.retrospective_c922_endpoint_to_sim_receipt.v1"


class C922EndpointTransferError(RuntimeError):
    """The frozen endpoint transfer cannot run without changing its contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise C922EndpointTransferError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise C922EndpointTransferError(f"{path} must contain an object")
    return value


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise C922EndpointTransferError(f"bound evidence hash rejected: {path}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _read_json(path)
    if contract.get("schema_version") != SCHEMA:
        raise C922EndpointTransferError("unexpected C922 endpoint schema")
    for key in (
        "source",
        "registration",
        "annotations",
        "evaluator",
        "replay",
        "authority",
    ):
        if not isinstance(contract.get(key), dict):
            raise C922EndpointTransferError(f"contract section is missing: {key}")
    source = contract["source"]
    registration = contract["registration"]
    replay = contract["replay"]
    authority = contract["authority"]
    _require_hash(
        REPO_ROOT / source["recording_directory"] / "recording_receipt.json",
        str(source["recording_receipt_sha256"]),
    )
    _require_hash(
        REPO_ROOT / source["recording_directory"] / "phase_a_comparison_receipt.json",
        str(source["phase_a_receipt_sha256"]),
    )
    _require_hash(
        REPO_ROOT / source["c922_video_path"],
        str(source["c922_video_sha256"]),
    )
    for key in (
        "fit_annotations",
        "canonical_task_plane_receipt",
        "hard_cutover",
        "current_workcell_implementation",
    ):
        binding = registration[key]
        _require_hash(REPO_ROOT / binding["path"], str(binding["sha256"]))
    if registration["playing_corner_order"] != [
        "a8_outer",
        "h8_outer",
        "h1_outer",
        "a1_outer",
    ]:
        raise C922EndpointTransferError("playing-corner order changed")
    if (
        registration.get("candidate_refit_allowed") is not False
        or registration.get("homography_refit_allowed") is not False
    ):
        raise C922EndpointTransferError("registration refit was enabled")
    if source.get("orientation_rotation_degrees") != 180:
        raise C922EndpointTransferError("C922 source orientation changed")
    if replay != {
        "terminal_xy_source": (
            "metric_unprojection_of_frozen_C922_terminal_base_center_annotation"
        ),
        "terminal_z_source": "current_simulator_D2_support_plane",
        "terminal_orientation_source": (
            "camera_reviewed_upright_with_current_simulator_board_yaw"
        ),
        "destination_xy_forcing_allowed": False,
        "action_or_joint_trace_used": False,
        "contact_parameter_fit_allowed": False,
        "timing_offset_search_allowed": False,
        "post_spawn_free_physics_required": True,
    }:
        raise C922EndpointTransferError("endpoint replay semantics changed")
    if authority != {
        "camera_open": False,
        "gateway": False,
        "serial": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "simulator_replay": True,
    }:
        raise C922EndpointTransferError("endpoint authority widened")
    if contract["annotations"].get("status") != (
        "frozen_before_metric_endpoint_evaluation"
    ):
        raise C922EndpointTransferError("endpoint annotations are not frozen")
    return contract


def board_homography(playing_corners_px: np.ndarray) -> np.ndarray:
    corners = np.asarray(playing_corners_px, dtype=np.float32)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise C922EndpointTransferError("playing corners must be finite 4x2")
    board_coordinates = np.asarray(
        [[0.0, 8.0], [8.0, 8.0], [8.0, 0.0], [0.0, 0.0]],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(corners, board_coordinates)
    if not np.isfinite(homography).all() or abs(np.linalg.det(homography)) <= 1e-12:
        raise C922EndpointTransferError("pixel-to-board homography is singular")
    return homography


def unproject_pixel(homography: np.ndarray, pixel: np.ndarray) -> np.ndarray:
    point = np.asarray(pixel, dtype=np.float32)
    if point.shape != (2,) or not np.isfinite(point).all():
        raise C922EndpointTransferError("endpoint pixel must be finite 2D")
    result = cv2.perspectiveTransform(point.reshape(1, 1, 2), homography)
    return np.asarray(result[0, 0], dtype=np.float64)


def board_coordinate_to_world(board_coordinate: np.ndarray) -> np.ndarray:
    coordinate = np.asarray(board_coordinate, dtype=np.float64)
    if coordinate.shape != (2,) or not np.isfinite(coordinate).all():
        raise C922EndpointTransferError("board coordinate must be finite 2D")
    a1 = np.asarray(current_square_center("a1"), dtype=np.float64)
    b1 = np.asarray(current_square_center("b1"), dtype=np.float64)
    a2 = np.asarray(current_square_center("a2"), dtype=np.float64)
    return (
        a1
        + ((coordinate[0] - 0.5) * (b1 - a1))
        + ((coordinate[1] - 0.5) * (a2 - a1))
    )


def _annotation(
    annotations: dict[str, Any],
    key: str,
    *,
    maximum_disagreement_px: float,
) -> tuple[np.ndarray, float]:
    value = annotations[key]
    first = np.asarray(value["pass_a"], dtype=np.float64)
    second = np.asarray(value["pass_b"], dtype=np.float64)
    if (
        first.shape != (2,)
        or second.shape != (2,)
        or not np.isfinite(first).all()
        or not np.isfinite(second).all()
    ):
        raise C922EndpointTransferError(f"invalid endpoint annotation: {key}")
    disagreement = float(np.linalg.norm(first - second))
    if disagreement > maximum_disagreement_px:
        raise C922EndpointTransferError(f"annotation disagreement rejected: {key}")
    return (first + second) / 2.0, disagreement


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _extract_frame(
    *,
    video_path: Path,
    frame_index: int,
    expected_frame_count: int,
    expected_sha256: str,
    output_path: Path,
) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise C922EndpointTransferError("cannot open bound C922 video")
    try:
        observed_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if observed_count != expected_frame_count:
            raise C922EndpointTransferError("C922 frame count changed")
        if not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise C922EndpointTransferError("cannot seek bound C922 frame")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise C922EndpointTransferError("cannot decode bound C922 frame")
    finally:
        capture.release()
    rotated = cv2.rotate(frame, cv2.ROTATE_180)
    ok, encoded = cv2.imencode(".png", rotated)
    if not ok:
        raise C922EndpointTransferError("cannot encode bound C922 frame")
    payload = encoded.tobytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise C922EndpointTransferError("decoded C922 frame bytes changed")
    _atomic_write_bytes(output_path, payload)
    return {
        "frame_index_zero_based": frame_index,
        "width": int(rotated.shape[1]),
        "height": int(rotated.shape[0]),
        "rotated_png_path": str(output_path.relative_to(REPO_ROOT)),
        "rotated_png_sha256": digest,
    }


def _tilt_degrees(data: mujoco.MjData, body_id: int) -> float:
    rotation = np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3)
    return math.degrees(math.acos(float(np.clip(rotation[2, 2], -1.0, 1.0))))


def _hold_robot_controls(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    for actuator_id in range(model.nu):
        joint_id = int(model.actuator_trnid[actuator_id, 0])
        if joint_id < 0:
            continue
        joint_type = int(model.jnt_type[joint_id])
        if joint_type not in (
            int(mujoco.mjtJoint.mjJNT_HINGE),
            int(mujoco.mjtJoint.mjJNT_SLIDE),
        ):
            continue
        data.ctrl[actuator_id] = data.qpos[int(model.jnt_qposadr[joint_id])]


def _simulate_endpoint(
    *,
    observed_terminal_world: np.ndarray,
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    model = build_current_workcell_spec().compile()
    data = mujoco.MjData(model)
    selected_name = "brown_pawn_d1"
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise C922EndpointTransferError("current workcell selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    mujoco.mj_forward(model, data)
    _hold_robot_controls(model, data)
    mujoco.mj_step(model, data, nstep=100)
    pieces = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }
    settled_support_z = float(data.qpos[selected_qpos + 2])
    settled_upright_quaternion = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7],
        dtype=np.float64,
    ).copy()
    data.qpos[selected_qpos : selected_qpos + 2] = observed_terminal_world[:2]
    data.qpos[selected_qpos + 2] = settled_support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = settled_upright_quaternion
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    mujoco.mj_forward(model, data)
    _hold_robot_controls(model, data)
    timestep = float(model.opt.timestep)
    settle_steps = round(float(evaluator["free_settle_seconds"]) / timestep)
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    target = np.asarray(current_square_center("d2"), dtype=np.float64)
    final_position = np.asarray(data.xpos[selected_body], dtype=np.float64).copy()
    final_velocity = np.asarray(
        data.qvel[selected_dof : selected_dof + 6], dtype=np.float64
    ).copy()
    other_displacement = max(
        (
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_positions[name]
                )
            )
            for name, body_id in pieces.items()
            if name != selected_name
        ),
        default=0.0,
    )
    center_error = float(np.linalg.norm(final_position[:2] - target[:2]))
    tilt = _tilt_degrees(data, selected_body)
    linear_speed = float(np.linalg.norm(final_velocity[:3]))
    angular_speed = float(np.linalg.norm(final_velocity[3:]))
    gates = {
        "final_square_center": center_error
        <= float(evaluator["maximum_simulated_final_square_center_error_m"]),
        "upright": tilt <= float(evaluator["maximum_upright_tilt_degrees"]),
        "other_pieces_stationary": other_displacement
        <= float(evaluator["maximum_other_piece_displacement_m"]),
        "settled_linear": linear_speed
        <= float(evaluator["maximum_final_linear_speed_m_s"]),
        "settled_angular": angular_speed
        <= float(evaluator["maximum_final_angular_speed_rad_s"]),
    }
    return {
        "spawn_xy_source": "metric_C922_terminal_annotation",
        "spawn_xy_m": observed_terminal_world[:2].astype(float).tolist(),
        "spawn_z_source": "current_simulator_support_plane",
        "final_position_m": final_position.astype(float).tolist(),
        "target_position_m": target.astype(float).tolist(),
        "final_square_center_error_m": center_error,
        "final_upright_tilt_degrees": tilt,
        "final_linear_speed_m_s": linear_speed,
        "final_angular_speed_rad_s": angular_speed,
        "maximum_other_piece_displacement_m": other_displacement,
        "gates": gates,
        "success": all(gates.values()),
    }


def evaluate(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    source = contract["source"]
    registration = contract["registration"]
    evaluator = contract["evaluator"]
    video_path = REPO_ROOT / source["c922_video_path"]
    output_directory.mkdir(parents=True, exist_ok=True)
    extracted = {
        key: _extract_frame(
            video_path=video_path,
            frame_index=int(source[f"{key}_frame"]["frame_index_zero_based"]),
            expected_frame_count=int(source["frame_count"]),
            expected_sha256=str(source[f"{key}_frame"]["rotated_png_sha256"]),
            output_path=output_directory / f"{key}_rotated.png",
        )
        for key in ("initial", "terminal")
    }
    fit_annotations = _read_json(
        REPO_ROOT / registration["fit_annotations"]["path"]
    )
    canonical_receipt = _read_json(
        REPO_ROOT / registration["canonical_task_plane_receipt"]["path"]
    )
    if canonical_receipt.get("status") != "canonical_task_plane_registration_pass":
        raise C922EndpointTransferError("canonical task-plane registration regressed")
    lattice = fit_annotations.get("board_lattice", {})
    if lattice.get("playing_corner_order") != registration["playing_corner_order"]:
        raise C922EndpointTransferError("fit playing-corner order changed")
    homography = board_homography(
        np.asarray(lattice["playing_corners_px"], dtype=np.float64)
    )
    maximum_disagreement = float(
        evaluator["maximum_two_pass_disagreement_px"]
    )
    initial_pixel, initial_disagreement = _annotation(
        contract["annotations"],
        "initial_d1_base_center_px",
        maximum_disagreement_px=maximum_disagreement,
    )
    terminal_pixel, terminal_disagreement = _annotation(
        contract["annotations"],
        "terminal_d2_base_center_px",
        maximum_disagreement_px=maximum_disagreement,
    )
    initial_board = unproject_pixel(homography, initial_pixel)
    terminal_board = unproject_pixel(homography, terminal_pixel)
    initial_world = board_coordinate_to_world(initial_board)
    terminal_world = board_coordinate_to_world(terminal_board)
    d1 = np.asarray(current_square_center("d1"), dtype=np.float64)
    d2 = np.asarray(current_square_center("d2"), dtype=np.float64)
    initial_error = float(np.linalg.norm(initial_world[:2] - d1[:2]))
    terminal_error = float(np.linalg.norm(terminal_world[:2] - d2[:2]))
    observation_gates = {
        "initial_annotation_agreement": initial_disagreement
        <= maximum_disagreement,
        "terminal_annotation_agreement": terminal_disagreement
        <= maximum_disagreement,
        "initial_d1_registration_validation": initial_error
        <= float(evaluator["maximum_initial_square_center_error_m"]),
        "terminal_d2_metric_endpoint": terminal_error
        <= float(evaluator["maximum_terminal_square_center_error_m"]),
        "terminal_upright_reviewed": contract["annotations"]["terminal_upright"]
        is True,
    }
    simulation = _simulate_endpoint(
        observed_terminal_world=terminal_world,
        evaluator=evaluator,
    )
    success = all(observation_gates.values()) and bool(simulation["success"])
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path.resolve().relative_to(REPO_ROOT)),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "source": {
            "recording_id": source["recording_id"],
            "video_path": source["c922_video_path"],
            "video_sha256": source["c922_video_sha256"],
            "extracted_frames": extracted,
            "physical_terminal_square_reviewed": source["destination_square"],
            "physical_terminal_upright_reviewed": True,
        },
        "registration": {
            "playing_corner_order": registration["playing_corner_order"],
            "playing_corners_px": lattice["playing_corners_px"],
            "pixel_to_board_homography": homography.astype(float).tolist(),
            "canonical_task_plane_receipt_sha256": registration[
                "canonical_task_plane_receipt"
            ]["sha256"],
            "candidate_refit": False,
            "homography_refit": False,
            "global_physical_model_mapping_approved": False,
        },
        "observations": {
            "initial": {
                "square": "d1",
                "pixel_base_center": initial_pixel.astype(float).tolist(),
                "two_pass_disagreement_px": initial_disagreement,
                "board_coordinate": initial_board.astype(float).tolist(),
                "world_position_m": initial_world.astype(float).tolist(),
                "square_center_error_m": initial_error,
            },
            "terminal": {
                "square": "d2",
                "pixel_base_center": terminal_pixel.astype(float).tolist(),
                "two_pass_disagreement_px": terminal_disagreement,
                "board_coordinate": terminal_board.astype(float).tolist(),
                "world_position_m": terminal_world.astype(float).tolist(),
                "square_center_error_m": terminal_error,
            },
            "gates": observation_gates,
        },
        "simulation": simulation,
        "ledger": {
            "camera_endpoint_states_real_to_sim": {
                "successes": 2 if success else 0,
                "attempts": 2,
            },
            "camera_endpoint_episodes_real_to_sim": {
                "successes": int(success),
                "attempts": 1,
            },
            "strict_pure_action_only_real_to_sim": {
                "successes": 0,
                "attempts": 0,
            },
            "physical_task_attempts_added": 0,
            "sim_to_real_added": 0,
        },
        "verdict": (
            "C922_ENDPOINT_REAL_TO_SIM_TRANSFER_1_OF_1"
            if success
            else "C922_ENDPOINT_REAL_TO_SIM_TRANSFER_NEGATIVE"
        ),
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "C922EndpointTransferError",
    "board_coordinate_to_world",
    "board_homography",
    "evaluate",
    "load_contract",
    "unproject_pixel",
]
