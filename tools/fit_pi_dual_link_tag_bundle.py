#!/usr/bin/env python3
"""Freeze and evaluate a diagnostic fixed-Pi two-link AprilTag bundle."""

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
TAG2_TRAIN = {
    "pose_a": ROOT / "runs/pi-link-tag-calibration/20260726-pose-a-v1/stage-1",
    "pose_b": ROOT / "runs/pi-link-tag-calibration/20260726-pose-b-v2/stage-1",
    "pose_c": ROOT / "runs/pi-link-tag-calibration/20260726-pose-c-v6/stage-1",
    "pose_e": ROOT / "runs/pi-link-tag-calibration/20260726-pose-e-v1/stage-1",
    "pose_f": ROOT / "runs/pi-link-tag-calibration/20260726-pose-f-v1/stage-1",
    "pose_i": ROOT / "runs/pi-link-tag-calibration/20260726-pose-i-v1/stage-1",
    "pose_j": ROOT / "runs/pi-link-tag-calibration/20260726-pose-j-v1/stage-1",
}
TAG1_TRAIN_NAMES = {"pose_e", "pose_f", "pose_i", "pose_j"}
HELDOUT = {
    "pose_d": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-d-heldout-v1/stage-1",
    "pose_h": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-h-heldout-v1/stage-1",
    "pose_k": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-k-heldout-v1/stage-1",
    "pose_l": ROOT
    / "runs/pi-link-tag-calibration/20260726-pose-l-heldout-v1/stage-1",
}
PROXIMAL_BODY = "left_upper_arm"
DISTAL_BODIES = ("left_wrist", "left_gripper")
TAG_SIZE_M = 0.020
OFFSET_BOUND_DEGREES = 8.0
RMSE_GATE_PX = 8.0
MAX_GATE_PX = 15.0
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


def detect(path: Path) -> dict[int, np.ndarray]:
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError(f"invalid Pi image: {path}")
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    )
    corners, identifiers, _ = detector.detectMarkers(image)
    found: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(identifiers.ravel(), corners, strict=True):
            found.setdefault(int(identifier), []).append(corner[0].astype(np.float64))
    return {
        identifier: matches[0]
        for identifier, matches in found.items()
        if identifier in (1, 2) and len(matches) == 1
    }


def observation(name: str, directory: Path, tag_id: int) -> dict[str, Any]:
    receipt_path = directory / "execution_receipt.json"
    image_path = directory / "pi_imx708_torque_on_hold.jpg"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "completed_wrist_view_reposition_stage"
        or receipt.get("physical_follower_torque_enabled") is not False
        or (receipt.get("pi_hold_still") or {}).get("status")
        != "captured_while_follower_torque_on"
        or (receipt.get("pi_hold_still") or {}).get("sha256") != sha256(image_path)
    ):
        raise RuntimeError(f"unadmitted torque-on observation: {name}")
    tags = detect(image_path)
    if tag_id not in tags:
        raise RuntimeError(f"unique tag {tag_id} absent: {name}")
    return {
        "name": name,
        "tag_id": tag_id,
        "receipt_path": receipt_path,
        "receipt_sha256": sha256(receipt_path),
        "image_path": image_path,
        "image_sha256": sha256(image_path),
        "joint_degrees": np.asarray(receipt["final_actual_degrees"], dtype=np.float64),
        "corners": tags[tag_id],
    }


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "tag_id": row["tag_id"],
        "receipt_path": str(row["receipt_path"]),
        "receipt_sha256": row["receipt_sha256"],
        "image_path": str(row["image_path"]),
        "image_sha256": row["image_sha256"],
        "joint_degrees": row["joint_degrees"].tolist(),
        "corners_pixels": row["corners"].tolist(),
    }


class Bundle:
    def __init__(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.config = manifest["candidate_config"]
        self.model, _ = _compile_model(self.config, base_directory=None)
        self.data = mujoco.MjData(self.model)
        self.body_ids = {
            name: mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
            for name in (PROXIMAL_BODY, *DISTAL_BODIES)
        }
        self.joint_ids = [
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            for name in self.config["bindings"]["joint_names"]
        ]
        full_focal = (FULL_SENSOR_WIDTH / 2.0) / math.tan(
            math.radians(FULL_HORIZONTAL_FOV_DEGREES / 2.0)
        )
        self.focal = full_focal * OUTPUT_WIDTH / MODE_CROP_WIDTH
        self.camera_matrix = np.asarray(
            [
                [self.focal, 0.0, OUTPUT_WIDTH / 2.0],
                [0.0, self.focal, OUTPUT_HEIGHT / 2.0],
                [0.0, 0.0, 1.0],
            ]
        )
        self.tag_points = np.asarray(
            [
                [-TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0, 1.0],
                [TAG_SIZE_M / 2, TAG_SIZE_M / 2, 0.0, 1.0],
                [TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0, 1.0],
                [-TAG_SIZE_M / 2, -TAG_SIZE_M / 2, 0.0, 1.0],
            ],
            dtype=np.float64,
        ).T

    def set_focal(self, focal: float) -> None:
        self.focal = float(focal)
        self.camera_matrix[0, 0] = self.focal
        self.camera_matrix[1, 1] = self.focal

    def calibrate_focal(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        object_points = [
            np.ascontiguousarray(self.tag_points[:3].T.astype(np.float32))
            for _ in rows
        ]
        image_points = [
            np.ascontiguousarray(row["corners"].astype(np.float32)) for row in rows
        ]
        seed = self.focal
        flags = (
            cv2.CALIB_USE_INTRINSIC_GUESS
            | cv2.CALIB_FIX_ASPECT_RATIO
            | cv2.CALIB_FIX_PRINCIPAL_POINT
            | cv2.CALIB_ZERO_TANGENT_DIST
            | cv2.CALIB_FIX_K1
            | cv2.CALIB_FIX_K2
            | cv2.CALIB_FIX_K3
            | cv2.CALIB_FIX_K4
            | cv2.CALIB_FIX_K5
            | cv2.CALIB_FIX_K6
        )
        rms, camera, _, _, _ = cv2.calibrateCamera(
            object_points,
            image_points,
            (int(OUTPUT_WIDTH), int(OUTPUT_HEIGHT)),
            self.camera_matrix.copy(),
            np.zeros(8),
            flags=flags,
        )
        self.set_focal(float(camera[0, 0]))
        return {
            "official_fov_seed_focal_pixels": seed,
            "calibrated_focal_pixels": self.focal,
            "opencv_rms_px": float(rms),
            "view_count": len(rows),
        }

    def body_pose(
        self, body_name: str, joints: np.ndarray, offsets: np.ndarray
    ) -> np.ndarray:
        physical = (joints + np.pad(offsets, (0, 1)))[None, :]
        qpos = _physical_to_model_position(physical, self.config)[0]
        for index, joint_id in enumerate(self.joint_ids):
            self.data.qpos[int(self.model.jnt_qposadr[joint_id])] = qpos[index]
        self.data.qvel[:] = 0
        mujoco.mj_forward(self.model, self.data)
        body_id = self.body_ids[body_name]
        value = np.eye(4)
        value[:3, :3] = self.data.xmat[body_id].reshape(3, 3)
        value[:3, 3] = self.data.xpos[body_id]
        return value

    def camera_tag(self, row: dict[str, Any]) -> np.ndarray:
        ok, rvec, tvec = cv2.solvePnP(
            np.ascontiguousarray(self.tag_points[:3].T),
            np.ascontiguousarray(row["corners"]),
            self.camera_matrix,
            np.zeros(5),
            flags=cv2.SOLVEPNP_IPPE_SQUARE,
        )
        if not ok:
            raise RuntimeError(f"PnP initialization failed: {row['name']}")
        return transform(rvec.ravel(), tvec.ravel())

    def project(
        self,
        parameters: np.ndarray,
        row: dict[str, Any],
        proximal_body: str,
        distal_body: str,
    ) -> np.ndarray:
        camera_world = transform(parameters[:3], parameters[3:6])
        body_tag = (
            transform(parameters[6:9], parameters[9:12])
            if row["tag_id"] == 2
            else transform(parameters[12:15], parameters[15:18])
        )
        body_name = distal_body if row["tag_id"] == 2 else proximal_body
        camera_points = (
            camera_world
            @ self.body_pose(body_name, row["joint_degrees"], parameters[18:23])
            @ body_tag
            @ self.tag_points
        )[:3]
        normalized = camera_points[:2] / camera_points[2:3]
        return np.column_stack(
            [
                self.focal * normalized[0] + OUTPUT_WIDTH / 2.0,
                self.focal * normalized[1] + OUTPUT_HEIGHT / 2.0,
            ]
        )

    def fit(
        self,
        rows: list[dict[str, Any]],
        proximal_body: str,
        distal_body: str,
        *,
        seeds: int = 3,
    ) -> tuple[np.ndarray, dict[str, float]]:
        tag2_first = next(row for row in rows if row["tag_id"] == 2)
        tag1_first = next(row for row in rows if row["tag_id"] == 1)
        camera_tag2 = self.camera_tag(tag2_first)
        camera_tag1 = self.camera_tag(tag1_first)
        rng = np.random.default_rng(20260726)
        best: tuple[float, np.ndarray, np.ndarray, float] | None = None
        lower = np.asarray(
            [-math.pi] * 3
            + [-3.0] * 3
            + [-math.pi] * 3
            + [-0.2] * 3
            + [-math.pi] * 3
            + [-0.2] * 3
            + [-OFFSET_BOUND_DEGREES] * 5
        )
        upper = -lower
        for _ in range(seeds):
            distal_tag = transform(
                rng.uniform(-math.pi, math.pi, 3), rng.uniform(-0.10, 0.10, 3)
            )
            camera_world = camera_tag2 @ np.linalg.inv(
                self.body_pose(distal_body, tag2_first["joint_degrees"], np.zeros(5))
                @ distal_tag
            )
            proximal_tag = np.linalg.inv(
                camera_world
                @ self.body_pose(
                    proximal_body, tag1_first["joint_degrees"], np.zeros(5)
                )
            ) @ camera_tag1
            initial = np.concatenate(
                [
                    pose_vector(camera_world),
                    pose_vector(distal_tag),
                    pose_vector(proximal_tag),
                    np.zeros(5),
                ]
            )

            def pixel_residual(parameters: np.ndarray) -> np.ndarray:
                return np.concatenate(
                    [
                        (
                            self.project(parameters, row, proximal_body, distal_body)
                            - row["corners"]
                        ).ravel()
                        for row in rows
                    ]
                )

            def nominal_residual(parameters: np.ndarray) -> np.ndarray:
                return pixel_residual(
                    np.concatenate([parameters, np.zeros(5, dtype=np.float64)])
                )

            nominal = least_squares(
                nominal_residual,
                np.clip(initial[:18], lower[:18] + 1e-8, upper[:18] - 1e-8),
                bounds=(lower[:18], upper[:18]),
                loss="soft_l1",
                f_scale=2.0,
                max_nfev=3500,
            )
            offset_initial = np.concatenate(
                [nominal.x, np.zeros(5, dtype=np.float64)]
            )

            def residual(parameters: np.ndarray) -> np.ndarray:
                pixels = np.concatenate(
                    [
                        (
                            self.project(parameters, row, proximal_body, distal_body)
                            - row["corners"]
                        ).ravel()
                        for row in rows
                    ]
                )
                return np.concatenate([pixels, parameters[18:23] / 2.0])

            result = least_squares(
                residual,
                np.clip(offset_initial, lower + 1e-8, upper - 1e-8),
                bounds=(lower, upper),
                loss="soft_l1",
                f_scale=2.0,
                max_nfev=3500,
            )
            errors = np.concatenate(
                [
                    np.linalg.norm(
                        self.project(result.x, row, proximal_body, distal_body)
                        - row["corners"],
                        axis=1,
                    )
                    for row in rows
                ]
            )
            score = float(np.sqrt(np.mean(errors**2)))
            if best is None or score < best[0]:
                best = (score, result.x, errors, float(result.optimality))
        assert best is not None
        score, parameters, errors, optimality = best
        return parameters, {
            "corner_rmse_px": score,
            "corner_max_px": float(np.max(errors)),
            "optimizer_optimality": optimality,
        }


def freeze(output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    bundle = Bundle()
    rows = [
        observation(name, directory, 2) for name, directory in TAG2_TRAIN.items()
    ]
    rows.extend(
        observation(name, TAG2_TRAIN[name], 1) for name in sorted(TAG1_TRAIN_NAMES)
    )
    focal_calibration = bundle.calibrate_focal(rows)
    tag2_rows = [row for row in rows if row["tag_id"] == 2]
    cross_validation: dict[str, Any] = {}
    for body in DISTAL_BODIES:
        folds = []
        for held in tag2_rows:
            fold_rows = [
                row
                for row in rows
                if row["tag_id"] == 1 or row["name"] != held["name"]
            ]
            parameters, _ = bundle.fit(
                fold_rows, PROXIMAL_BODY, body, seeds=2
            )
            errors = np.linalg.norm(
                bundle.project(parameters, held, PROXIMAL_BODY, body)
                - held["corners"],
                axis=1,
            )
            folds.append(
                {
                    "held_out_training_pose": held["name"],
                    "corner_rmse_px": float(np.sqrt(np.mean(errors**2))),
                    "corner_max_px": float(np.max(errors)),
                }
            )
        cross_validation[body] = {
            "folds": folds,
            "mean_fold_rmse_px": float(
                np.mean([fold["corner_rmse_px"] for fold in folds])
            ),
        }
    selected_body = min(
        DISTAL_BODIES,
        key=lambda name: cross_validation[name]["mean_fold_rmse_px"],
    )
    parameters, training_metrics = bundle.fit(
        rows, PROXIMAL_BODY, selected_body, seeds=4
    )
    candidate = {
        "schema_version": "sim2claw.pi_dual_link_tag_candidate.v1",
        "proof_class": "physical_static_two_link_tag_training_fit_diagnostic_only",
        "status": "training_candidate_frozen_heldouts_unopened",
        "candidate_manifest": {"path": str(MANIFEST), "sha256": sha256(MANIFEST)},
        "camera_model": {
            "camera": "imx708_wide",
            "output_size": [1536, 864],
            "focal_pixels": bundle.focal,
            "principal_point_pixels": [768.0, 432.0],
            "distortion_fitted": False,
            "training_only_focal_calibration": focal_calibration,
        },
        "tag_model": {
            "family": "tag36h11",
            "black_edge_m": TAG_SIZE_M,
            "distal": {"id": 2, "body": selected_body},
            "proximal": {"id": 1, "body": PROXIMAL_BODY},
        },
        "body_selection": {
            "method": "tag2_leave_one_pose_out_training_only",
            "candidates": cross_validation,
            "selected": selected_body,
            "heldout_pose_d_h_or_k_accessed": False,
        },
        "training": [public_row(row) for row in rows],
        "training_metrics": training_metrics,
        "parameters": {
            "camera_world_rotation_vector_radians": parameters[:3].tolist(),
            "camera_world_translation_m": parameters[3:6].tolist(),
            "distal_body_tag_rotation_vector_radians": parameters[6:9].tolist(),
            "distal_body_tag_translation_m": parameters[9:12].tolist(),
            "proximal_body_tag_rotation_vector_radians": parameters[12:15].tolist(),
            "proximal_body_tag_translation_m": parameters[15:18].tolist(),
            "joint_zero_offsets_degrees": parameters[18:23].tolist(),
        },
        "frozen_gates": {
            "per_pose_corner_rmse_max_px": RMSE_GATE_PX,
            "per_pose_corner_max_px": MAX_GATE_PX,
            "joint_offset_absolute_bound_degrees": OFFSET_BOUND_DEGREES,
            "no_offset_at_bound": True,
            "all_heldout_poses_must_pass": True,
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    print(json.dumps(candidate, indent=2, sort_keys=True))


def evaluate(candidate_path: Path, output: Path, heldout_set: str) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if (
        candidate.get("schema_version") != "sim2claw.pi_dual_link_tag_candidate.v1"
        or candidate.get("status") != "training_candidate_frozen_heldouts_unopened"
    ):
        raise RuntimeError("invalid frozen candidate")
    bundle = Bundle()
    bundle.set_focal(float(candidate["camera_model"]["focal_pixels"]))
    p = candidate["parameters"]
    parameters = np.asarray(
        p["camera_world_rotation_vector_radians"]
        + p["camera_world_translation_m"]
        + p["distal_body_tag_rotation_vector_radians"]
        + p["distal_body_tag_translation_m"]
        + p["proximal_body_tag_rotation_vector_radians"]
        + p["proximal_body_tag_translation_m"]
        + p["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    proximal_body = candidate["tag_model"]["proximal"]["body"]
    distal_body = candidate["tag_model"]["distal"]["body"]
    if heldout_set == "dh":
        heldout_rows = [observation("pose_d", HELDOUT["pose_d"], 2)]
        h_tags = detect(HELDOUT["pose_h"] / "pi_imx708_torque_on_hold.jpg")
        if 1 not in h_tags or 2 not in h_tags:
            raise RuntimeError("heldout pose H lacks unique tags 1 and 2")
        heldout_rows.extend(
            observation("pose_h", HELDOUT["pose_h"], tag_id) for tag_id in (1, 2)
        )
        pose_names = ("pose_d", "pose_h")
    else:
        pose_name = "pose_k" if heldout_set == "k" else "pose_l"
        tags = detect(HELDOUT[pose_name] / "pi_imx708_torque_on_hold.jpg")
        heldout_rows = [
            observation(pose_name, HELDOUT[pose_name], tag_id)
            for tag_id in (1, 2)
            if tag_id in tags
        ]
        pose_names = (pose_name,)
    pose_results = []
    for pose_name in pose_names:
        rows = [row for row in heldout_rows if row["name"] == pose_name]
        expected_tag_ids = (
            [1, 2] if pose_name in ("pose_h", "pose_k", "pose_l") else [2]
        )
        detected_tag_ids = [row["tag_id"] for row in rows]
        if detected_tag_ids != expected_tag_ids:
            pose_results.append(
                {
                    "name": pose_name,
                    "tag_ids": detected_tag_ids,
                    "expected_tag_ids": expected_tag_ids,
                    "detection_gate_passed": False,
                    "corner_rmse_px": None,
                    "corner_max_px": None,
                    "passed": False,
                }
            )
            continue
        errors = np.concatenate(
            [
                np.linalg.norm(
                    bundle.project(
                        parameters, row, proximal_body, distal_body
                    )
                    - row["corners"],
                    axis=1,
                )
                for row in rows
            ]
        )
        rmse = float(np.sqrt(np.mean(errors**2)))
        maximum = float(np.max(errors))
        pose_results.append(
            {
                "name": pose_name,
                "tag_ids": detected_tag_ids,
                "expected_tag_ids": expected_tag_ids,
                "detection_gate_passed": True,
                "corner_rmse_px": rmse,
                "corner_max_px": maximum,
                "passed": rmse <= RMSE_GATE_PX and maximum <= MAX_GATE_PX,
            }
        )
    offsets = np.asarray(p["joint_zero_offsets_degrees"])
    offset_margin = OFFSET_BOUND_DEGREES - np.abs(offsets)
    no_offset_at_bound = bool(np.all(offset_margin > 1e-3))
    passed = all(row["passed"] for row in pose_results) and no_offset_at_bound
    receipt = {
        "schema_version": "sim2claw.pi_dual_link_tag_evaluation.v1",
        "proof_class": "physical_static_two_link_tag_heldout_diagnostic_only",
        "status": (
            "heldout_gates_passed_no_automatic_promotion"
            if passed
            else "heldout_rejected_no_promotion"
        ),
        "candidate": {"path": str(candidate_path), "sha256": sha256(candidate_path)},
        "heldout": [public_row(row) for row in heldout_rows],
        "pose_results": pose_results,
        "joint_zero_offsets_degrees": offsets.tolist(),
        "minimum_offset_bound_margin_degrees": float(np.min(offset_margin)),
        "no_offset_at_bound": no_offset_at_bound,
        "all_gates_passed": passed,
        "selection": {
            "promoted": False,
            "reason": (
                "Heldout calibration gates passed, but acquisition/evaluation code has no promotion authority."
                if passed
                else "One or more frozen heldout or parameter-bound gates failed."
            ),
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("freeze", "evaluate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--heldout", choices=("dh", "k", "l"))
    arguments = parser.parse_args()
    if arguments.phase == "freeze":
        if arguments.candidate is not None or arguments.heldout is not None:
            raise RuntimeError("--candidate and --heldout are evaluation-only")
        freeze(arguments.output)
    else:
        if arguments.candidate is None or arguments.heldout is None:
            raise RuntimeError("--candidate and --heldout are required for evaluation")
        evaluate(arguments.candidate, arguments.output, arguments.heldout)


if __name__ == "__main__":
    main()
