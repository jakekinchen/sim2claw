"""Frozen zero-motion scene registration for bidirectional pawn pushes."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .recorded_replay import _compile_model
from .scene import (
    BOARD_D4_TRANSFORMS,
    CURRENT_TASK_PIECE_LAYOUT,
    board_square_center,
    build_scene_spec,
    load_capture_config,
    scene_geometry,
    transform_board_square,
)
from .wrist_view_reposition import _physical_to_model_position

DATASET_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_registration_dataset_v1.json"
)
CANDIDATE_PATH = (
    REPO_ROOT
    / "configs"
    / "scenes"
    / "bidirectional_pawn_push_scene_registration_v4.json"
)


class BidirectionalSceneRegistrationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def load_candidate(path: Path = CANDIDATE_PATH) -> dict[str, Any]:
    candidate = _load_json(path)
    if (
        candidate.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_scene_registration.v4"
    ):
        raise BidirectionalSceneRegistrationError("unexpected v4 candidate schema")
    return candidate


def physical_square_center(
    square: str,
    candidate: dict[str, Any],
    *,
    contact_height_m: float = 0.0,
) -> np.ndarray:
    mapped = transform_board_square(square, candidate["board_d4_transform"])
    center = board_square_center(
        mapped,
        board_center_in_table_frame_xy_m=tuple(
            candidate["board_center_in_table_frame_xy_m"]
        ),
        board_yaw_relative_to_table_degrees=float(
            candidate["board_yaw_relative_to_table_degrees"]
        ),
    )
    return np.asarray(center, dtype=np.float64) + [0.0, 0.0, contact_height_m]


def build_registered_scene(
    candidate: dict[str, Any] | None = None,
) -> tuple[mujoco.MjModel, mujoco.MjData]:
    if candidate is None:
        candidate = load_candidate()
    spec = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        piece_square_transform=candidate["board_d4_transform"],
        board_center_in_table_frame_xy_m=tuple(
            candidate["board_center_in_table_frame_xy_m"]
        ),
        board_yaw_relative_to_table_degrees=float(
            candidate["board_yaw_relative_to_table_degrees"]
        ),
    )
    model = spec.compile()
    return model, mujoco.MjData(model)


def reproduce_fit() -> dict[str, Any]:
    """Recompute the Q02 candidate from fit inputs without opening held-out data."""

    dataset = _load_json(DATASET_PATH)
    inputs = {entry["id"]: entry for entry in dataset["inputs"]}
    fit_ids = {
        "fit_c2_counted_action",
        "fit_current_scene_prior",
        "fit_current_mapping_prior",
    }
    if any(inputs[name]["split"] != "fit" for name in fit_ids):
        raise BidirectionalSceneRegistrationError("Q02 input escaped fit split")
    for name in fit_ids:
        path = REPO_ROOT / inputs[name]["path"]
        if sha256_file(path) != inputs[name]["sha256"]:
            raise BidirectionalSceneRegistrationError(f"fit input changed: {name}")

    action_path = REPO_ROOT / inputs["fit_c2_counted_action"]["path"]
    action = np.load(action_path, allow_pickle=False)
    mapping_manifest = _load_json(
        REPO_ROOT / inputs["fit_current_mapping_prior"]["path"]
    )
    mapping = mapping_manifest["candidate_config"]
    model, _ = _compile_model(mapping, base_directory=None)
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in mapping["bindings"]["joint_names"]
    ]
    qpos = np.asarray([model.jnt_qposadr[joint_id] for joint_id in joint_ids])
    mapped_action = _physical_to_model_position(action, mapping)
    data.qpos[qpos] = mapped_action[0]
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")
    pinch_points = []
    for row in mapped_action:
        data.qpos[qpos] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        pinch_points.append(_pinch_point(model, data, "left", pinch_local).copy())
    pinch_points = np.asarray(pinch_points)

    scene_config = load_capture_config(
        REPO_ROOT / inputs["fit_current_scene_prior"]["path"]
    )
    geometry = scene_geometry(scene_config)
    prior_center = np.asarray(
        scene_config["simulation_estimates"]["board"][
            "center_in_table_frame_xy_m"
        ],
        dtype=np.float64,
    )
    prior_yaw = float(
        scene_config["simulation_estimates"]["board"][
            "yaw_relative_to_table_degrees"
        ]
    )
    table_angle = math.radians(geometry.table_yaw_degrees)
    table_to_world = np.asarray(
        [
            [math.cos(table_angle), -math.sin(table_angle)],
            [math.sin(table_angle), math.cos(table_angle)],
        ]
    )

    grasp_rows = range(150, 301)
    contact_height_m = 0.051
    bound_m = float(
        dataset["candidate_family_constraints_for_q02"][
            "board_center_delta_bound_m"
        ]
    )
    candidates = []
    for orientation_index, orientation in enumerate(BOARD_D4_TRANSFORMS):
        mapped_square = transform_board_square("c2", orientation)
        target = np.asarray(
            board_square_center(
                mapped_square,
                config_path=REPO_ROOT / inputs["fit_current_scene_prior"]["path"],
                board_center_in_table_frame_xy_m=tuple(prior_center),
                board_yaw_relative_to_table_degrees=prior_yaw,
            )
        ) + [0.0, 0.0, contact_height_m]
        for row_index in grasp_rows:
            world_delta = pinch_points[row_index, :2] - target[:2]
            table_delta = table_to_world.T @ world_delta
            within_bounds = bool(np.all(np.abs(table_delta) <= bound_m))
            if not within_bounds:
                continue
            residual_m = abs(float(pinch_points[row_index, 2] - target[2]))
            candidates.append(
                (
                    residual_m,
                    float(np.linalg.norm(table_delta)),
                    orientation_index,
                    row_index,
                    orientation,
                    mapped_square,
                    table_delta,
                )
            )
    if not candidates:
        raise BidirectionalSceneRegistrationError("no bounded D4 candidate")
    (
        residual_m,
        _,
        _,
        row_index,
        orientation,
        mapped_square,
        table_delta,
    ) = min(candidates)
    center = prior_center + table_delta
    return {
        "board_d4_transform": orientation,
        "mapped_fit_square": mapped_square,
        "board_center_delta_table_xy_m": table_delta.tolist(),
        "board_center_in_table_frame_xy_m": center.tolist(),
        "board_yaw_relative_to_table_degrees": prior_yaw,
        "joint_zero_offsets_changed": False,
        "fit_grasp_row": row_index,
        "fit_contact_height_m": contact_height_m,
        "fit_residual_mm": residual_m * 1000.0,
        "canonical_action_npy_sha256": sha256_file(action_path),
        "canonical_action_raw_float64le_sha256": hashlib.sha256(
            np.asarray(action, dtype="<f8", order="C").tobytes(order="C")
        ).hexdigest(),
    }
