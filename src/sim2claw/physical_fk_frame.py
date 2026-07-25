"""Versioned physical-joint FK through the bound compiled MuJoCo candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .learning_factory_artifacts import sha256_file
from .paths import REPO_ROOT
from .recorded_replay import _compile_model

CONTRACT_PATH = (
    REPO_ROOT / "configs/calibration/so101_d405_physical_fk_frame_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.so101_d405_physical_fk_frame_contract.v1"


class PhysicalFKFrameError(RuntimeError):
    """The versioned candidate, adapter, or frame binding drifted."""


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _kinematic_signature(
    model: mujoco.MjModel,
    joint_names: list[str],
    base_body: str,
    wrist_body: str,
) -> str:
    joints = []
    for name in joint_names:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise PhysicalFKFrameError(f"compiled model lacks joint {name}")
        joints.append(
            {
                "name": name,
                "type": int(model.jnt_type[joint_id]),
                "qpos_address": int(model.jnt_qposadr[joint_id]),
                "body_id": int(model.jnt_bodyid[joint_id]),
                "position": model.jnt_pos[joint_id].tolist(),
                "axis": model.jnt_axis[joint_id].tolist(),
            }
        )
    bodies = []
    for name in (base_body, wrist_body):
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body_id < 0:
            raise PhysicalFKFrameError(f"compiled model lacks body {name}")
        lineage = []
        cursor = body_id
        while cursor:
            lineage.append(
                {
                    "name": mujoco.mj_id2name(
                        model, mujoco.mjtObj.mjOBJ_BODY, cursor
                    ),
                    "parent_id": int(model.body_parentid[cursor]),
                    "position": model.body_pos[cursor].tolist(),
                    "quaternion_wxyz": model.body_quat[cursor].tolist(),
                }
            )
            cursor = int(model.body_parentid[cursor])
        bodies.append({"frame": name, "lineage_to_world": lineage})
    return _canonical_hash(
        {
            "nq": model.nq,
            "nv": model.nv,
            "joints": joints,
            "bodies": bodies,
        }
    )


def load_physical_fk_contract(
    path: Path = CONTRACT_PATH,
) -> tuple[dict[str, Any], mujoco.MjModel]:
    path = path.resolve()
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise PhysicalFKFrameError("unexpected physical FK contract schema")
    if not contract.get("authority") or any(contract["authority"].values()):
        raise PhysicalFKFrameError("physical FK contract widened authority")
    manifest_path = (
        REPO_ROOT / contract["candidate_manifest"]["path"]
    ).resolve()
    if sha256_file(manifest_path) != contract["candidate_manifest"]["sha256"]:
        raise PhysicalFKFrameError("candidate manifest hash drifted")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lineage = contract["candidate_manifest"]
    if (
        manifest.get("candidate_digest") != lineage["candidate_digest"]
        or manifest.get("candidate_config_sha256")
        != lineage["candidate_config_sha256"]
    ):
        raise PhysicalFKFrameError("candidate manifest identity drifted")
    candidate = manifest["candidate_config"]
    adapter_section = candidate["physical_adapter"]
    adapter = adapter_section["joint_transform"]
    source_rows = adapter["joints"]
    transform = contract["physical_to_model_transform"]
    if (
        [row["source_joint"] for row in source_rows]
        != contract["physical_joint_order"]
        or [row["simulator_joint"] for row in source_rows]
        != contract["model_joint_order"]
        or [row["sign"] for row in source_rows] != transform["sign"]
        or [row["scale"] for row in source_rows] != transform["scale"]
        or [row["zero_offset"] for row in source_rows]
        != transform["zero_offset"]
        or [row["input_unit"] for row in source_rows]
        != transform["input_units"]
        or adapter_section.get("joint_transform_sha256")
        != transform["source_joint_transform_sha256"]
    ):
        raise PhysicalFKFrameError("candidate physical adapter drifted")
    model, current_scene = _compile_model(candidate, base_directory=None)
    if not current_scene:
        raise PhysicalFKFrameError("FK contract requires the current scene")
    signature = _kinematic_signature(
        model,
        contract["model_joint_order"],
        contract["frames"]["base"]["mujoco_body"],
        contract["frames"]["wrist"]["mujoco_body"],
    )
    if signature != contract["compiled_kinematic_model_sha256"]:
        raise PhysicalFKFrameError("compiled kinematic model hash drifted")
    return contract, model


def physical_fk_base_from_wrist(
    physical_joint_values: np.ndarray | list[float],
    *,
    contract_path: Path = CONTRACT_PATH,
) -> np.ndarray:
    """Return the deterministic 4x4 base-from-wrist transform."""
    contract, model = load_physical_fk_contract(contract_path)
    physical = np.asarray(physical_joint_values, dtype=np.float64)
    if physical.shape != (6,) or not np.all(np.isfinite(physical)):
        raise PhysicalFKFrameError("physical FK requires six finite joints")
    transform = contract["physical_to_model_transform"]
    qpos = (
        physical
        * np.asarray(transform["scale"])
        * np.asarray(transform["sign"])
        + np.asarray(transform["zero_offset"])
    )
    data = mujoco.MjData(model)
    for name, value in zip(contract["model_joint_order"], qpos, strict=True):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
    mujoco.mj_forward(model, data)
    base_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        contract["frames"]["base"]["mujoco_body"],
    )
    wrist_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        contract["frames"]["wrist"]["mujoco_body"],
    )
    world_rotation_base = data.xmat[base_id].reshape(3, 3)
    world_rotation_wrist = data.xmat[wrist_id].reshape(3, 3)
    rotation = world_rotation_base.T @ world_rotation_wrist
    translation = world_rotation_base.T @ (
        data.xpos[wrist_id] - data.xpos[base_id]
    )
    result = np.eye(4)
    result[:3, :3], result[:3, 3] = rotation, translation
    return result
