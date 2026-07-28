#!/usr/bin/env python3
"""Freeze and once-evaluate the current-camera four-tag Pi bundle."""

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

from tools.fit_pi_dual_link_tag_bundle import Bundle, pose_vector, transform


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CANDIDATE = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-three-link-fresh-validation-v1/candidate.json"
)
TRAINING = {
    "old_pose_f": ROOT
    / "runs/pi-link-tag-calibration/20260726-current-camera-pose-f-v1/stage-1",
    "old_pose_h": ROOT
    / "runs/pi-link-tag-calibration/20260726-current-camera-pose-h-v1/stage-1",
    "old_pose_i": ROOT
    / "runs/pi-link-tag-calibration/20260726-current-camera-pose-i-v1/stage-1",
    "new_pose_h": ROOT
    / "runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-h-v1/stage-1",
    "new_pose_i": ROOT
    / "runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-i-v1/stage-1",
}
HELDOUT = (
    ROOT
    / "runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-d-v1/stage-1"
)
CONSUMED_JOINT_REFIT_EVALUATION = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-four-tag-v1/heldout-evaluation.json"
)
FIXED_BODY_MAP = {
    0: "left_shoulder",
    1: "left_upper_arm",
    2: "left_wrist",
}
TAG3_BODY_CANDIDATES = (
    "left_base",
    "left_shoulder",
    "left_upper_arm",
)
TAG_START = {2: 6, 1: 12, 0: 18, 3: 24}
OFFSET_START = 30
OFFSET_BOUND_DEGREES = 8.0
RMSE_GATE_PX = 8.0
MAX_GATE_PX = 15.0
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_tags(path: Path) -> dict[int, np.ndarray]:
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError(f"invalid Pi image: {path}")
    corners, identifiers, _ = cv2.aruco.ArucoDetector(
        DICTIONARY
    ).detectMarkers(image)
    found: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(
            identifiers.ravel(), corners, strict=True
        ):
            tag_id = int(identifier)
            if tag_id in (0, 1, 2, 3) and float(
                np.mean(corner[0, :, 1])
            ) < 450.0:
                found.setdefault(tag_id, []).append(
                    corner[0].astype(np.float64)
                )
    return {
        tag_id: rows[0]
        for tag_id, rows in found.items()
        if len(rows) == 1
    }


def observations(name: str, directory: Path) -> list[dict[str, Any]]:
    receipt_path = directory / "execution_receipt.json"
    image_path = directory / "pi_imx708_torque_on_hold.jpg"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "completed_wrist_view_reposition_stage"
        or receipt.get("physical_follower_torque_enabled") is not False
        or (receipt.get("pi_hold_still") or {}).get("sha256")
        != sha256(image_path)
    ):
        raise RuntimeError(f"unadmitted Pi observation: {name}")
    return [
        {
            "name": name,
            "tag_id": tag_id,
            "receipt_path": receipt_path,
            "receipt_sha256": sha256(receipt_path),
            "image_path": image_path,
            "image_sha256": sha256(image_path),
            "joint_degrees": np.asarray(
                receipt["final_actual_degrees"], dtype=np.float64
            ),
            "corners": corners,
        }
        for tag_id, corners in sorted(detect_tags(image_path).items())
    ]


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


def error_metrics(
    bundle: "FourTagBundle",
    parameters: np.ndarray,
    rows: list[dict[str, Any]],
    body_map: dict[int, str],
) -> dict[str, Any]:
    by_tag: dict[str, dict[str, float]] = {}
    all_errors: list[np.ndarray] = []
    for tag_id in sorted({row["tag_id"] for row in rows}):
        tag_errors = np.concatenate(
            [
                np.linalg.norm(
                    bundle.project(parameters, row, body_map)
                    - row["corners"],
                    axis=1,
                )
                for row in rows
                if row["tag_id"] == tag_id
            ]
        )
        all_errors.append(tag_errors)
        by_tag[str(tag_id)] = {
            "corner_count": int(len(tag_errors)),
            "corner_rmse_px": float(np.sqrt(np.mean(tag_errors**2))),
            "corner_max_px": float(np.max(tag_errors)),
        }
    errors = np.concatenate(all_errors)
    return {
        "corner_count": int(len(errors)),
        "corner_rmse_px": float(np.sqrt(np.mean(errors**2))),
        "corner_max_px": float(np.max(errors)),
        "by_tag": by_tag,
    }


class FourTagBundle:
    def __init__(self, focal: float) -> None:
        self.bundle = Bundle()
        self.bundle.set_focal(focal)
        for body in (
            "left_base",
            "left_shoulder",
            "left_upper_arm",
            "left_wrist",
        ):
            self.bundle.body_ids[body] = mujoco.mj_name2id(
                self.bundle.model, mujoco.mjtObj.mjOBJ_BODY, body
            )

    def project(
        self,
        parameters: np.ndarray,
        row: dict[str, Any],
        body_map: dict[int, str],
    ) -> np.ndarray:
        start = TAG_START[row["tag_id"]]
        camera_points = (
            transform(parameters[:3], parameters[3:6])
            @ self.bundle.body_pose(
                body_map[row["tag_id"]],
                row["joint_degrees"],
                parameters[OFFSET_START : OFFSET_START + 5],
            )
            @ transform(
                parameters[start : start + 3],
                parameters[start + 3 : start + 6],
            )
            @ self.bundle.tag_points
        )[:3]
        normalized = camera_points[:2] / camera_points[2:3]
        return np.column_stack(
            (
                self.bundle.focal * normalized[0] + 768.0,
                self.bundle.focal * normalized[1] + 432.0,
            )
        )

    def initial(
        self,
        rows: list[dict[str, Any]],
        body_map: dict[int, str],
        source: dict[str, Any],
    ) -> np.ndarray:
        old = source["parameters"]
        camera_world = transform(
            np.asarray(old["camera_world_rotation_vector_radians"]),
            np.asarray(old["camera_world_translation_m"]),
        )
        offsets = np.asarray(
            old["joint_zero_offsets_degrees"], dtype=np.float64
        )
        mounts = {
            tag_id: transform(
                np.asarray(
                    old["tag_mounts"][str(tag_id)][
                        "body_tag_rotation_vector_radians"
                    ]
                ),
                np.asarray(
                    old["tag_mounts"][str(tag_id)][
                        "body_tag_translation_m"
                    ]
                ),
            )
            for tag_id in (0, 1, 2)
        }
        tag3_row = next(row for row in rows if row["tag_id"] == 3)
        mounts[3] = np.linalg.inv(
            camera_world
            @ self.bundle.body_pose(
                body_map[3], tag3_row["joint_degrees"], offsets
            )
        ) @ self.bundle.camera_tag(tag3_row)
        camera_parameters = np.concatenate(
            [
                np.asarray(
                    old["camera_world_rotation_vector_radians"],
                    dtype=np.float64,
                ),
                np.asarray(
                    old["camera_world_translation_m"],
                    dtype=np.float64,
                ),
            ]
        )
        fixed_mount_parameters = {
            tag_id: np.concatenate(
                [
                    np.asarray(
                        old["tag_mounts"][str(tag_id)][
                            "body_tag_rotation_vector_radians"
                        ],
                        dtype=np.float64,
                    ),
                    np.asarray(
                        old["tag_mounts"][str(tag_id)][
                            "body_tag_translation_m"
                        ],
                        dtype=np.float64,
                    ),
                ]
            )
            for tag_id in (0, 1, 2)
        }
        return np.concatenate(
            [
                camera_parameters,
                fixed_mount_parameters[2],
                fixed_mount_parameters[1],
                fixed_mount_parameters[0],
                pose_vector(mounts[3]),
                offsets,
            ]
        )

    def fit(
        self,
        rows: list[dict[str, Any]],
        body_map: dict[int, str],
        source: dict[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:
        initial = self.initial(rows, body_map, source)
        tag3_rows = [row for row in rows if row["tag_id"] == 3]
        if not tag3_rows:
            raise RuntimeError("tag 3 mount fit requires at least one observation")
        lower = np.asarray([-math.pi] * 3 + [-0.25] * 3)
        upper = -lower

        def residual(tag3_mount: np.ndarray) -> np.ndarray:
            parameters = initial.copy()
            parameters[TAG_START[3] : TAG_START[3] + 6] = tag3_mount
            return np.concatenate(
                [
                    (
                        self.project(parameters, row, body_map)
                        - row["corners"]
                    ).ravel()
                    for row in tag3_rows
                ]
            )

        result = least_squares(
            residual,
            np.clip(
                initial[TAG_START[3] : TAG_START[3] + 6],
                lower + 1e-8,
                upper - 1e-8,
            ),
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=2.0,
            max_nfev=8000,
        )
        parameters = initial.copy()
        parameters[TAG_START[3] : TAG_START[3] + 6] = result.x
        metrics = error_metrics(self, parameters, rows, body_map)
        metrics["optimizer_optimality"] = float(result.optimality)
        metrics["optimized_parameter_scope"] = "tag3_mount_only"
        return parameters, metrics


def body_map(tag3_body: str) -> dict[int, str]:
    return {**FIXED_BODY_MAP, 3: tag3_body}


def _mounts(parameters: np.ndarray) -> dict[str, Any]:
    return {
        str(tag_id): {
            "body_tag_rotation_vector_radians": parameters[
                TAG_START[tag_id] : TAG_START[tag_id] + 3
            ].tolist(),
            "body_tag_translation_m": parameters[
                TAG_START[tag_id] + 3 : TAG_START[tag_id] + 6
            ].tolist(),
        }
        for tag_id in (0, 1, 2, 3)
    }


def freeze(output: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    source = json.loads(SOURCE_CANDIDATE.read_text(encoding="utf-8"))
    rows = [
        row
        for name, directory in TRAINING.items()
        for row in observations(name, directory)
    ]
    if sorted({row["tag_id"] for row in rows}) != [0, 1, 2, 3]:
        raise RuntimeError("training corpus does not cover tags 0, 1, 2, and 3")
    if {row["name"] for row in rows if row["tag_id"] == 3} != {
        "new_pose_h",
        "new_pose_i",
    }:
        raise RuntimeError("tag 3 training must be bound only to new H and I")
    focal = float(source["intrinsics"]["focal_pixels"])
    bundle = FourTagBundle(focal)
    candidates: dict[str, Any] = {}
    for tag3_body in TAG3_BODY_CANDIDATES:
        mapping = body_map(tag3_body)
        folds = []
        for heldout_pose in sorted(TRAINING):
            fit_rows = [row for row in rows if row["name"] != heldout_pose]
            test_rows = [row for row in rows if row["name"] == heldout_pose]
            parameters, _ = bundle.fit(fit_rows, mapping, source)
            folds.append(
                {
                    "heldout_training_pose": heldout_pose,
                    **error_metrics(bundle, parameters, test_rows, mapping),
                }
            )
        parameters, metrics = bundle.fit(rows, mapping, source)
        candidates[tag3_body] = {
            "tag3_body": tag3_body,
            "folds": folds,
            "mean_fold_rmse_px": float(
                np.mean([fold["corner_rmse_px"] for fold in folds])
            ),
            "full_training_metrics": metrics,
            "full_training_parameter_vector": parameters.tolist(),
        }
    training_loo_best = min(
        candidates,
        key=lambda name: candidates[name]["mean_fold_rmse_px"],
    )
    selected = "left_shoulder"
    parameters = np.asarray(
        candidates[selected]["full_training_parameter_vector"],
        dtype=np.float64,
    )
    mapping = body_map(selected)
    candidate = {
        "schema_version": "sim2claw.pi_current_four_tag_candidate.v1",
        "proof_class": "physical_static_current_camera_four_tag_training_diagnostic",
        "status": "retrospective_training_candidate_pose_d_already_consumed",
        "source_three_tag_candidate": {
            "path": str(SOURCE_CANDIDATE),
            "sha256": sha256(SOURCE_CANDIDATE),
        },
        "intrinsics": source["intrinsics"],
        "training": [public_row(row) for row in rows],
        "body_selection": {
            "method": "training_pose_leave_one_out_tag3_only",
            "fixed_tags": {
                str(tag_id): body
                for tag_id, body in FIXED_BODY_MAP.items()
            },
            "tag3_candidates": candidates,
            "selected_tag3_body": selected,
            "training_loo_best_tag3_body": training_loo_best,
            "selection_basis": (
                "owner-observed tag3 image-x motion tracks tag0 shoulder-pan "
                "across N/H/I/D; training LOO remains disclosed but does not "
                "override the physical attachment classification"
            ),
            "pose_d_heldout_accessed_by_prior_rejected_candidate": True,
            "fresh_heldout_authority": False,
        },
        "tag_model": {
            "family": "tag36h11",
            "black_edge_m": 0.020,
            "tags": {
                str(tag_id): {"body": body}
                for tag_id, body in mapping.items()
            },
        },
        "training_metrics": candidates[selected]["full_training_metrics"],
        "parameters": {
            "camera_world_rotation_vector_radians": parameters[:3].tolist(),
            "camera_world_translation_m": parameters[3:6].tolist(),
            "tag_mounts": _mounts(parameters),
            "joint_zero_offsets_degrees": parameters[
                OFFSET_START : OFFSET_START + 5
            ].tolist(),
            "parameter_vector": parameters.tolist(),
        },
        "frozen_gates": {
            "overall_corner_rmse_max_px": RMSE_GATE_PX,
            "overall_corner_max_px": MAX_GATE_PX,
            "joint_offset_absolute_bound_degrees": OFFSET_BOUND_DEGREES,
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "physical_task": False,
            "policy": False,
        },
        "consumed_heldout_provenance": {
            "joint_refit_evaluation_path": str(
                CONSUMED_JOINT_REFIT_EVALUATION
            ),
            "joint_refit_evaluation_sha256": sha256(
                CONSUMED_JOINT_REFIT_EVALUATION
            ),
            "joint_refit_status": "heldout_rejected_no_promotion",
            "joint_refit_corner_rmse_px": 70.50116852878797,
            "pose_d_may_not_be_reopened": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate


def rows_from_consumed_evaluation(
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "name": row["name"],
            "tag_id": int(row["tag_id"]),
            "receipt_path": Path(row["receipt_path"]),
            "receipt_sha256": row["receipt_sha256"],
            "image_path": Path(row["image_path"]),
            "image_sha256": row["image_sha256"],
            "joint_degrees": np.asarray(
                row["joint_degrees"], dtype=np.float64
            ),
            "corners": np.asarray(
                row["corners_pixels"], dtype=np.float64
            ),
        }
        for row in evaluation["heldout"]
    ]


def evaluate_retrospective(candidate_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if (
        candidate.get("schema_version")
        != "sim2claw.pi_current_four_tag_candidate.v1"
        or candidate.get("status")
        != "retrospective_training_candidate_pose_d_already_consumed"
        or candidate["body_selection"].get("fresh_heldout_authority") is not False
    ):
        raise RuntimeError("invalid frozen four-tag candidate")
    consumed = json.loads(
        CONSUMED_JOINT_REFIT_EVALUATION.read_text(encoding="utf-8")
    )
    if (
        consumed.get("status") != "heldout_rejected_no_promotion"
        or consumed.get("metrics", {}).get("corner_rmse_px")
        != 70.50116852878797
    ):
        raise RuntimeError("consumed pose-D evaluation provenance changed")
    rows = rows_from_consumed_evaluation(consumed)
    parameters = np.asarray(
        candidate["parameters"]["parameter_vector"], dtype=np.float64
    )
    mapping = {
        int(tag_id): specification["body"]
        for tag_id, specification in candidate["tag_model"]["tags"].items()
    }
    bundle = FourTagBundle(float(candidate["intrinsics"]["focal_pixels"]))
    metrics = error_metrics(bundle, parameters, rows, mapping)
    offsets = parameters[OFFSET_START : OFFSET_START + 5]
    passed = (
        metrics["corner_rmse_px"] <= RMSE_GATE_PX
        and metrics["corner_max_px"] <= MAX_GATE_PX
        and bool(np.all(np.abs(offsets) < OFFSET_BOUND_DEGREES - 1e-3))
    )
    shared_rows = [row for row in rows if row["tag_id"] in (0, 1, 2)]
    shared_metrics = error_metrics(bundle, parameters, shared_rows, mapping)
    receipt = {
        "schema_version": "sim2claw.pi_current_four_tag_evaluation.v1",
        "proof_class": "physical_static_current_camera_four_tag_pose_d_consumed_retrospective",
        "status": (
            "consumed_retrospective_gates_passed_no_promotion"
            if passed
            else "consumed_retrospective_rejected_no_promotion"
        ),
        "candidate": {
            "path": str(candidate_path),
            "sha256": sha256(candidate_path),
        },
        "consumed_evaluation": {
            "path": str(CONSUMED_JOINT_REFIT_EVALUATION),
            "sha256": sha256(CONSUMED_JOINT_REFIT_EVALUATION),
            "pose_d_reopened": False,
        },
        "heldout": [public_row(row) for row in rows],
        "selected_tag3_body": candidate["body_selection"][
            "selected_tag3_body"
        ],
        "metrics": metrics,
        "prior_three_tag_shared_tag_comparison": {
            "shared_tag_ids": sorted(
                {row["tag_id"] for row in shared_rows}
            ),
            "prior_three_tag_metrics": shared_metrics,
            "expanded_four_tag_metrics_on_shared_tags": shared_metrics,
            "corner_rmse_improvement_px": 0.0,
            "interpretation": (
                "Camera, tags 0-2, and joint offsets are byte-for-parameter "
                "frozen, so the expanded bundle does not change shared-tag error."
            ),
        },
        "joint_zero_offsets_degrees": offsets.tolist(),
        "all_gates_passed": passed,
        "selection": {
            "promoted": False,
            "reason": (
                "Pose D was already consumed by the rejected joint-refit "
                "candidate; this score is retrospective and has no fresh "
                "heldout or automatic promotion authority."
            ),
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "physical_task": False,
            "policy": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("freeze", "evaluate-retrospective"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    arguments = parser.parse_args()
    if arguments.phase == "freeze":
        if arguments.candidate is not None:
            raise RuntimeError("--candidate is evaluate-only")
        result = freeze(arguments.output)
    else:
        if arguments.candidate is None:
            raise RuntimeError("evaluate requires --candidate")
        result = evaluate_retrospective(arguments.candidate, arguments.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
