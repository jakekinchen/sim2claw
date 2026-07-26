#!/usr/bin/env python3
"""Fit a diagnostic fixed-Pi/follower-tag bundle from torque-on pose receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
TRAIN = {
    "pose_a": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-a-v1/stage-1",
    "pose_b": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-b-v2/stage-1",
    "pose_c": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-c-v6/stage-1",
    "pose_e": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-e-v1/stage-1",
    "pose_f": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-f-v1/stage-1",
}
HELD_OUT = {
    "pose_d": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-d-heldout-v1/stage-1"
}
TAG_SIZE_M = 0.020
TAG_ID = 2
BODY_NAME = "left_gripper"
FULL_SENSOR_WIDTH = 4608.0
MODE_CROP_WIDTH = 3072.0
OUTPUT_WIDTH = 1536.0
OUTPUT_HEIGHT = 864.0
FULL_HORIZONTAL_FOV_DEGREES = 102.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transform(rotation_vector: np.ndarray, translation: np.ndarray) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = Rotation.from_rotvec(rotation_vector).as_matrix()
    value[:3, 3] = translation
    return value


def pose_vector(value: np.ndarray) -> np.ndarray:
    return np.concatenate(
        [Rotation.from_matrix(value[:3, :3]).as_rotvec(), value[:3, 3]]
    )


def detect(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError(f"invalid Pi image: {path}")
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    )
    corners, identifiers, _ = detector.detectMarkers(image)
    if identifiers is None:
        raise RuntimeError(f"tag {TAG_ID} absent: {path}")
    matches = [
        corner[0].astype(np.float64)
        for identifier, corner in zip(identifiers.ravel(), corners, strict=True)
        if int(identifier) == TAG_ID
    ]
    if len(matches) != 1:
        raise RuntimeError(f"tag {TAG_ID} is not unique: {path}")
    return matches[0]


def load_observations(paths: dict[str, Path]) -> list[dict[str, Any]]:
    rows = []
    for name, directory in paths.items():
        receipt_path = directory / "execution_receipt.json"
        image_path = directory / "pi_imx708_torque_on_hold.jpg"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (
            receipt.get("status") != "completed_wrist_view_reposition_stage"
            or receipt.get("physical_follower_torque_enabled") is not False
            or (receipt.get("pi_hold_still") or {}).get("status")
            != "captured_while_follower_torque_on"
            or (receipt.get("pi_hold_still") or {}).get("sha256")
            != sha256(image_path)
        ):
            raise RuntimeError(f"unadmitted torque-on observation: {name}")
        rows.append(
            {
                "name": name,
                "directory": directory,
                "receipt_path": receipt_path,
                "receipt_sha256": sha256(receipt_path),
                "image_path": image_path,
                "image_sha256": sha256(image_path),
                "joint_degrees": np.asarray(
                    receipt["final_actual_degrees"], dtype=np.float64
                ),
                "corners": detect(image_path),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise RuntimeError(f"refusing to overwrite {arguments.output}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, BODY_NAME)
    joint_names = config["bindings"]["joint_names"]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    training = load_observations(TRAIN)
    held_out = load_observations(HELD_OUT)

    full_half = FULL_SENSOR_WIDTH / 2.0
    full_focal_pixels = full_half / math.tan(
        math.radians(FULL_HORIZONTAL_FOV_DEGREES / 2.0)
    )
    focal = full_focal_pixels * (OUTPUT_WIDTH / MODE_CROP_WIDTH)
    camera_matrix = np.asarray(
        [[focal, 0.0, OUTPUT_WIDTH / 2.0], [0.0, focal, OUTPUT_HEIGHT / 2.0], [0, 0, 1]],
        dtype=np.float64,
    )
    tag_points = np.asarray(
        [
            [-TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0, 1.0],
            [TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0, 1.0],
            [TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0, 1.0],
            [-TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0, 1.0],
        ],
        dtype=np.float64,
    ).T

    def body_pose(joints: np.ndarray, offsets: np.ndarray) -> np.ndarray:
        physical = (joints + np.pad(offsets, (0, 1)))[None, :]
        qpos = _physical_to_model_position(physical, config)[0]
        for index, joint_id in enumerate(joint_ids):
            data.qpos[int(model.jnt_qposadr[joint_id])] = qpos[index]
        data.qvel[:] = 0
        mujoco.mj_forward(model, data)
        value = np.eye(4)
        value[:3, :3] = data.xmat[body_id].reshape(3, 3)
        value[:3, 3] = data.xpos[body_id]
        return value

    first = training[0]
    ok, first_rvec, first_tvec = cv2.solvePnP(
        np.ascontiguousarray(tag_points[:3].T),
        np.ascontiguousarray(first["corners"]),
        camera_matrix,
        np.zeros(5),
        flags=cv2.SOLVEPNP_IPPE_SQUARE,
    )
    if not ok:
        raise RuntimeError("initial tag pose solve failed")
    camera_tag = transform(first_rvec.ravel(), first_tvec.ravel())
    rng = np.random.default_rng(20260726)

    def project(
        parameters: np.ndarray,
        row: dict[str, Any],
        with_offsets: bool,
        with_intrinsics: bool,
    ) -> np.ndarray:
        camera_world = transform(parameters[:3], parameters[3:6])
        body_tag = transform(parameters[6:9], parameters[9:12])
        offsets = parameters[12:17] if with_offsets else np.zeros(5)
        camera_points = (
            camera_world @ body_pose(row["joint_degrees"], offsets) @ body_tag @ tag_points
        )[:3]
        normalized = (camera_points[:2] / camera_points[2:3]).T
        if with_intrinsics:
            start = 17 if with_offsets else 12
            log_fx, log_fy, delta_cx, delta_cy, k1, k2 = parameters[start : start + 6]
            fx = focal * math.exp(float(log_fx))
            fy = focal * math.exp(float(log_fy))
            cx = OUTPUT_WIDTH / 2.0 + delta_cx
            cy = OUTPUT_HEIGHT / 2.0 + delta_cy
        else:
            fx = fy = focal
            cx, cy = OUTPUT_WIDTH / 2.0, OUTPUT_HEIGHT / 2.0
            k1 = k2 = 0.0
        radius2 = np.sum(normalized**2, axis=1)
        radial = 1.0 + k1 * radius2 + k2 * radius2**2
        return np.column_stack(
            [fx * normalized[:, 0] * radial + cx, fy * normalized[:, 1] * radial + cy]
        )

    def fit(with_offsets: bool, with_intrinsics: bool = False) -> dict[str, Any]:
        best = None
        for seed in range(4):
            body_tag = transform(
                rng.uniform(-math.pi, math.pi, 3),
                rng.uniform(-0.12, 0.12, 3),
            )
            camera_world = (
                camera_tag
                @ np.linalg.inv(body_pose(first["joint_degrees"], np.zeros(5)) @ body_tag)
            )
            initial = np.concatenate([pose_vector(camera_world), pose_vector(body_tag)])
            if with_offsets:
                initial = np.concatenate([initial, np.zeros(5)])
            if with_intrinsics:
                initial = np.concatenate([initial, np.zeros(6)])

            def residual(parameters: np.ndarray) -> np.ndarray:
                pixels = np.concatenate(
                    [
                        (
                            project(parameters, row, with_offsets, with_intrinsics)
                            - row["corners"]
                        ).ravel()
                        for row in training
                    ]
                )
                if with_offsets:
                    pixels = np.concatenate([pixels, parameters[12:17] / 2.0])
                if with_intrinsics:
                    start = 17 if with_offsets else 12
                    priors = parameters[start : start + 6] / np.asarray(
                        [0.10, 0.10, 30.0, 30.0, 0.30, 0.30]
                    )
                    pixels = np.concatenate([pixels, priors])
                return pixels

            lower = np.asarray([-math.pi] * 3 + [-3] * 3 + [-math.pi] * 3 + [-0.2] * 3)
            upper = np.asarray([math.pi] * 3 + [3] * 3 + [math.pi] * 3 + [0.2] * 3)
            if with_offsets:
                lower = np.concatenate([lower, np.full(5, -8.0)])
                upper = np.concatenate([upper, np.full(5, 8.0)])
            if with_intrinsics:
                lower = np.concatenate(
                    [lower, np.asarray([-0.30, -0.30, -100, -100, -1.0, -1.0])]
                )
                upper = np.concatenate(
                    [upper, np.asarray([0.30, 0.30, 100, 100, 1.0, 1.0])]
                )
            result = least_squares(
                residual,
                np.clip(initial, lower + 1e-8, upper - 1e-8),
                bounds=(lower, upper),
                loss="soft_l1",
                f_scale=2.0,
                max_nfev=3000,
            )
            train_errors = np.concatenate(
                [
                    np.linalg.norm(
                        project(result.x, row, with_offsets, with_intrinsics)
                        - row["corners"],
                        axis=1,
                    )
                    for row in training
                ]
            )
            score = float(np.sqrt(np.mean(train_errors**2)))
            if best is None or score < best[0]:
                best = (score, result.x, train_errors, result.optimality)
        assert best is not None
        score, parameters, train_errors, optimality = best
        held_errors = np.concatenate(
            [
                np.linalg.norm(
                    project(parameters, row, with_offsets, with_intrinsics)
                    - row["corners"],
                    axis=1,
                )
                for row in held_out
            ]
        )
        return {
            "family": (
                "bounded_joint_offsets_and_camera"
                if with_offsets and with_intrinsics
                else "bounded_joint_offsets"
                if with_offsets
                else "nominal_joint_zeros"
            ),
            "train_corner_rmse_px": score,
            "train_corner_max_px": float(np.max(train_errors)),
            "held_out_corner_rmse_px": float(np.sqrt(np.mean(held_errors**2))),
            "held_out_corner_max_px": float(np.max(held_errors)),
            "camera_world": {
                "rotation_vector_radians": parameters[:3].tolist(),
                "translation_m": parameters[3:6].tolist(),
            },
            "body_tag": {
                "body": BODY_NAME,
                "rotation_vector_radians": parameters[6:9].tolist(),
                "translation_m": parameters[9:12].tolist(),
            },
            "joint_zero_offsets_degrees": (
                parameters[12:17].tolist() if with_offsets else [0.0] * 5
            ),
            "fitted_camera": (
                {
                    "fx_pixels": focal
                    * math.exp(float(parameters[17 if with_offsets else 12])),
                    "fy_pixels": focal
                    * math.exp(float(parameters[(17 if with_offsets else 12) + 1])),
                    "principal_point_pixels": [
                        OUTPUT_WIDTH / 2.0
                        + float(parameters[(17 if with_offsets else 12) + 2]),
                        OUTPUT_HEIGHT / 2.0
                        + float(parameters[(17 if with_offsets else 12) + 3]),
                    ],
                    "radial_k1_k2": parameters[
                        (17 if with_offsets else 12) + 4 :
                        (17 if with_offsets else 12) + 6
                    ].tolist(),
                }
                if with_intrinsics
                else None
            ),
            "optimizer_optimality": float(optimality),
        }

    fits = [fit(False), fit(True), fit(True, True)]
    receipt = {
        "schema_version": "sim2claw.pi_link_tag_bundle_fit.v1",
        "proof_class": "physical_static_tag_bundle_fit_diagnostic_only",
        "status": "held_out_evaluated",
        "candidate_manifest": {"path": str(MANIFEST), "sha256": sha256(MANIFEST)},
        "camera_model": {
            "camera": "imx708_wide",
            "output_size": [1536, 864],
            "full_sensor_horizontal_fov_degrees": FULL_HORIZONTAL_FOV_DEGREES,
            "full_sensor_width_pixels": FULL_SENSOR_WIDTH,
            "mode_crop_width_pixels": MODE_CROP_WIDTH,
            "focal_pixels": focal,
            "principal_point_pixels": [768.0, 432.0],
            "distortion_fitted": False,
            "source": "Raspberry Pi official 102 degree horizontal wide-FoV specification plus the live 3072/4608 mode crop",
        },
        "tag": {"family": "tag36h11", "id": TAG_ID, "black_edge_m": TAG_SIZE_M},
        "training": [
            {
                "name": row["name"],
                "receipt_path": str(row["receipt_path"]),
                "receipt_sha256": row["receipt_sha256"],
                "image_path": str(row["image_path"]),
                "image_sha256": row["image_sha256"],
                "joint_degrees": row["joint_degrees"].tolist(),
                "corners_pixels": row["corners"].tolist(),
            }
            for row in training
        ],
        "held_out": [
            {
                "name": row["name"],
                "receipt_path": str(row["receipt_path"]),
                "receipt_sha256": row["receipt_sha256"],
                "image_path": str(row["image_path"]),
                "image_sha256": row["image_sha256"],
                "joint_degrees": row["joint_degrees"].tolist(),
                "corners_pixels": row["corners"].tolist(),
            }
            for row in held_out
        ],
        "fits": fits,
        "selection": {
            "promoted": False,
            "reason": "Five fitting poses and one held-out pose remain diagnostic; promotion requires a second untouched held-out pose and non-boundary parameters.",
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
