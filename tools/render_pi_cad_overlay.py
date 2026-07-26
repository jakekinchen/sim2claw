#!/usr/bin/env python3
"""Render the exact MuJoCo follower geometry into a torque-on Pi frame."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
BODY_COLORS = {
    "left_shoulder": (70, 210, 255),
    "left_upper_arm": (70, 255, 120),
    "left_lower_arm": (255, 210, 60),
    "left_wrist": (255, 100, 80),
    "left_gripper": (220, 80, 255),
    "left_moving_jaw_so101_v1": (180, 80, 255),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transform(rotation_vector: list[float], translation: list[float]) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = Rotation.from_rotvec(rotation_vector).as_matrix()
    value[:3, 3] = translation
    return value


def box_points(size: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            [x * size[0], y * size[1], z * size[2]]
            for x in (-1.0, 1.0)
            for y in (-1.0, 1.0)
            for z in (-1.0, 1.0)
        ],
        dtype=np.float64,
    )


def primitive_points(geom_type: int, size: np.ndarray) -> np.ndarray:
    if geom_type == int(mujoco.mjtGeom.mjGEOM_BOX):
        return box_points(size)
    if geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE):
        radius = float(size[0])
        return np.asarray(
            [
                [radius * np.cos(a) * np.sin(b), radius * np.sin(a) * np.sin(b), radius * np.cos(b)]
                for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)
                for b in np.linspace(0, np.pi, 8)
            ]
        )
    radius = float(size[0])
    half = float(size[1])
    return np.asarray(
        [
            [radius * np.cos(a), radius * np.sin(a), z]
            for a in np.linspace(0, 2 * np.pi, 20, endpoint=False)
            for z in (-half, half)
        ],
        dtype=np.float64,
    )


def geom_points(model: mujoco.MjModel, data: mujoco.MjData, geom_id: int) -> np.ndarray:
    geom_type = int(model.geom_type[geom_id])
    if geom_type == int(mujoco.mjtGeom.mjGEOM_MESH):
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        local = np.asarray(model.mesh_vert[start : start + count], dtype=np.float64)
    else:
        local = primitive_points(geom_type, np.asarray(model.geom_size[geom_id]))
    rotation = data.geom_xmat[geom_id].reshape(3, 3)
    return local @ rotation.T + data.geom_xpos[geom_id]


def project(points: np.ndarray, camera_world: np.ndarray, focal: float) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    camera = (camera_world @ homogeneous.T)[:3]
    valid = camera[2] > 1e-5
    normalized = camera[:2, valid] / camera[2:3, valid]
    return np.column_stack(
        [focal * normalized[0] + 768.0, focal * normalized[1] + 432.0]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.output_receipt.exists():
        raise RuntimeError("refusing to overwrite CAD overlay output")

    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    execution = json.loads(arguments.receipt.read_text(encoding="utf-8"))
    image = cv2.imread(str(arguments.image))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError("expected one 1536x864 Pi image")
    if (
        execution.get("status") != "completed_wrist_view_reposition_stage"
        or (execution.get("pi_hold_still") or {}).get("sha256")
        != sha256(arguments.image)
    ):
        raise RuntimeError("image is not bound to an admitted torque-on receipt")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    qpos = _physical_to_model_position(
        np.asarray([execution["final_actual_degrees"]], dtype=np.float64), config
    )[0]
    for index, name in enumerate(config["bindings"]["joint_names"]):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[int(model.jnt_qposadr[joint_id])] = qpos[index]
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)

    parameters = candidate["parameters"]
    camera_world = transform(
        parameters["camera_world_rotation_vector_radians"],
        parameters["camera_world_translation_m"],
    )
    focal = float(candidate["camera_model"]["focal_pixels"])
    layer = image.copy()
    projected_bodies: dict[str, dict[str, Any]] = {}
    for body_name, color in BODY_COLORS.items():
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        body_pixels = []
        geom_count = 0
        for geom_id in range(model.ngeom):
            if int(model.geom_bodyid[geom_id]) != body_id:
                continue
            pixels = project(geom_points(model, data, geom_id), camera_world, focal)
            pixels = pixels[
                (pixels[:, 0] >= -100)
                & (pixels[:, 0] <= 1636)
                & (pixels[:, 1] >= -100)
                & (pixels[:, 1] <= 964)
            ]
            if len(pixels) < 3:
                continue
            hull = cv2.convexHull(np.rint(pixels).astype(np.int32))
            cv2.fillConvexPoly(layer, hull, color)
            cv2.polylines(image, [hull], True, color, 2, cv2.LINE_AA)
            body_pixels.append(pixels)
            geom_count += 1
        if body_pixels:
            pixels = np.concatenate(body_pixels)
            projected_bodies[body_name] = {
                "geom_count": geom_count,
                "pixel_bounds": [
                    float(np.min(pixels[:, 0])),
                    float(np.min(pixels[:, 1])),
                    float(np.max(pixels[:, 0])),
                    float(np.max(pixels[:, 1])),
                ],
            }
    overlay = cv2.addWeighted(layer, 0.28, image, 0.72, 0.0)
    cv2.putText(
        overlay,
        "CAD projection | tag 1: upper arm | tag 2: wrist",
        (28, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(arguments.output), overlay):
        raise RuntimeError("failed to write CAD overlay")
    receipt = {
        "schema_version": "sim2claw.pi_cad_overlay.v1",
        "proof_class": "physical_image_cad_projection_diagnostic_only",
        "status": "rendered",
        "candidate": {
            "path": str(arguments.candidate),
            "sha256": sha256(arguments.candidate),
        },
        "execution_receipt": {
            "path": str(arguments.receipt),
            "sha256": sha256(arguments.receipt),
        },
        "physical_image": {
            "path": str(arguments.image),
            "sha256": sha256(arguments.image),
        },
        "output": {
            "path": str(arguments.output),
            "sha256": sha256(arguments.output),
        },
        "focal_pixels": focal,
        "joint_degrees": execution["final_actual_degrees"],
        "projected_bodies": projected_bodies,
        "limitations": {
            "silhouette_fit_performed": False,
            "occlusion_reasoning_performed": False,
            "second_arm_segmented": False,
            "simulator_parameter_promotion": False,
            "task_or_policy_evidence": False,
        },
    }
    arguments.output_receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
