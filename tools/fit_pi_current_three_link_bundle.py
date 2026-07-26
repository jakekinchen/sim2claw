#!/usr/bin/env python3
"""Fit and evaluate the current Pi camera with three follower fiducials."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares

from tools.fit_pi_dual_link_tag_bundle import (
    Bundle,
    pose_vector,
    transform,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CANDIDATE = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-dual-link-fit-v4-wrist-body/candidate.json"
)
INTRINSICS = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-camera-intrinsics-v1/receipt.json"
)
TRAINING = {
    "pose_h_current": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-camera-pose-h-v1/stage-1",
    "pose_i_current": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-camera-pose-i-v1/stage-1",
    "pose_f_current": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-camera-pose-f-v1/stage-1",
}
HELDOUT = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-camera-pose-m-heldout-v1/stage-1"
)
PRIOR_EVALUATION = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-three-link-v2/heldout-evaluation.json"
)
BODY_MAPS = {
    "shoulder_upper": {
        0: "left_shoulder",
        1: "left_upper_arm",
        2: "left_wrist",
    },
    "shoulder_lower": {
        0: "left_shoulder",
        1: "left_lower_arm",
        2: "left_wrist",
    },
    "upper_upper": {
        0: "left_upper_arm",
        1: "left_upper_arm",
        2: "left_wrist",
    },
    "upper_lower": {
        0: "left_upper_arm",
        1: "left_lower_arm",
        2: "left_wrist",
    },
}
TAG_PARAMETER_START = {2: 6, 1: 12, 0: 18}
OFFSET_START = 24
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


def detect_robot_tags(path: Path) -> dict[int, np.ndarray]:
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError(f"invalid current Pi image: {path}")
    corners, identifiers, _ = cv2.aruco.ArucoDetector(
        DICTIONARY
    ).detectMarkers(image)
    found: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(
            identifiers.ravel(), corners, strict=True
        ):
            tag_id = int(identifier)
            if tag_id in (0, 1, 2) and float(np.mean(corner[0, :, 1])) < 450:
                found.setdefault(tag_id, []).append(
                    corner[0].astype(np.float64)
                )
    return {
        tag_id: matches[0]
        for tag_id, matches in found.items()
        if len(matches) == 1
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
        raise RuntimeError(f"unadmitted current-camera observation: {name}")
    tags = detect_robot_tags(image_path)
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
            "corners": tags[tag_id],
        }
        for tag_id in sorted(tags)
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


class ThreeLinkBundle:
    def __init__(self, focal: float) -> None:
        self.bundle = Bundle()
        self.bundle.set_focal(focal)
        for body in sorted(
            {body for mapping in BODY_MAPS.values() for body in mapping.values()}
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
        start = TAG_PARAMETER_START[row["tag_id"]]
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
            [
                self.bundle.focal * normalized[0] + 768.0,
                self.bundle.focal * normalized[1] + 432.0,
            ]
        )

    def initial(
        self,
        rows: list[dict[str, Any]],
        body_map: dict[int, str],
        source: dict[str, Any],
    ) -> np.ndarray:
        values = source["parameters"]
        offsets = np.asarray(
            values["joint_zero_offsets_degrees"], dtype=np.float64
        )
        tag2_mount = transform(
            np.asarray(values["distal_body_tag_rotation_vector_radians"]),
            np.asarray(values["distal_body_tag_translation_m"]),
        )
        tag2_row = next(row for row in rows if row["tag_id"] == 2)
        camera_tag2 = self.bundle.camera_tag(tag2_row)
        camera_world = camera_tag2 @ np.linalg.inv(
            self.bundle.body_pose(
                body_map[2], tag2_row["joint_degrees"], offsets
            )
            @ tag2_mount
        )
        mounts: dict[int, np.ndarray] = {2: tag2_mount}
        for tag_id in (1, 0):
            row = next(row for row in rows if row["tag_id"] == tag_id)
            camera_tag = self.bundle.camera_tag(row)
            mounts[tag_id] = np.linalg.inv(
                camera_world
                @ self.bundle.body_pose(
                    body_map[tag_id], row["joint_degrees"], offsets
                )
            ) @ camera_tag
        return np.concatenate(
            [
                pose_vector(camera_world),
                pose_vector(mounts[2]),
                pose_vector(mounts[1]),
                pose_vector(mounts[0]),
                offsets,
            ]
        )

    def fit(
        self,
        rows: list[dict[str, Any]],
        body_map: dict[int, str],
        source: dict[str, Any],
    ) -> tuple[np.ndarray, dict[str, float]]:
        initial = self.initial(rows, body_map, source)
        lower = np.asarray(
            [-math.pi] * 3
            + [-3.0] * 3
            + (
                [-math.pi] * 3
                + [-0.25] * 3
            )
            * 3
            + [-OFFSET_BOUND_DEGREES] * 5
        )
        upper = -lower

        def residual(parameters: np.ndarray) -> np.ndarray:
            pixels = np.concatenate(
                [
                    (
                        self.project(parameters, row, body_map)
                        - row["corners"]
                    ).ravel()
                    for row in rows
                ]
            )
            return np.concatenate(
                [pixels, parameters[OFFSET_START : OFFSET_START + 5] / 2.0]
            )

        result = least_squares(
            residual,
            np.clip(initial, lower + 1e-8, upper - 1e-8),
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=2.0,
            max_nfev=8000,
        )
        errors = np.concatenate(
            [
                np.linalg.norm(
                    self.project(result.x, row, body_map) - row["corners"],
                    axis=1,
                )
                for row in rows
            ]
        )
        return result.x, {
            "corner_rmse_px": float(np.sqrt(np.mean(errors**2))),
            "corner_max_px": float(np.max(errors)),
            "optimizer_optimality": float(result.optimality),
        }


def freeze(output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    source = json.loads(SOURCE_CANDIDATE.read_text(encoding="utf-8"))
    intrinsics = json.loads(INTRINSICS.read_text(encoding="utf-8"))
    focal = float(
        intrinsics["output_resolution"]["camera_matrix"][0][0]
    )
    rows = [
        row
        for name, directory in TRAINING.items()
        for row in observations(name, directory)
    ]
    if sorted({row["tag_id"] for row in rows}) != [0, 1, 2]:
        raise RuntimeError("training corpus does not cover tags 0, 1, and 2")
    bundle = ThreeLinkBundle(focal)
    cross_validation = {}
    pose_names = sorted(TRAINING)
    for map_name, body_map in BODY_MAPS.items():
        folds = []
        for heldout_name in pose_names:
            fit_rows = [
                row for row in rows if row["name"] != heldout_name
            ]
            test_rows = [
                row for row in rows if row["name"] == heldout_name
            ]
            parameters, _ = bundle.fit(fit_rows, body_map, source)
            errors = np.concatenate(
                [
                    np.linalg.norm(
                        bundle.project(parameters, row, body_map)
                        - row["corners"],
                        axis=1,
                    )
                    for row in test_rows
                ]
            )
            folds.append(
                {
                    "heldout_training_pose": heldout_name,
                    "tag_ids": sorted(
                        {row["tag_id"] for row in test_rows}
                    ),
                    "corner_rmse_px": float(
                        np.sqrt(np.mean(errors**2))
                    ),
                    "corner_max_px": float(np.max(errors)),
                }
            )
        cross_validation[map_name] = {
            "body_map": {str(key): value for key, value in body_map.items()},
            "folds": folds,
            "mean_fold_rmse_px": float(
                np.mean([row["corner_rmse_px"] for row in folds])
            ),
        }
        full_parameters, full_metrics = bundle.fit(rows, body_map, source)
        cross_validation[map_name]["full_training_metrics"] = full_metrics
        cross_validation[map_name][
            "full_training_parameter_vector"
        ] = full_parameters.tolist()
    selected = min(
        cross_validation,
        key=lambda name: cross_validation[name]["mean_fold_rmse_px"],
    )
    body_map = BODY_MAPS[selected]
    parameters = np.asarray(
        cross_validation[selected]["full_training_parameter_vector"],
        dtype=np.float64,
    )
    metrics = cross_validation[selected]["full_training_metrics"]
    candidate = {
        "schema_version": "sim2claw.pi_current_three_link_candidate.v1",
        "proof_class": "physical_static_current_camera_three_link_training_diagnostic",
        "status": "training_candidate_frozen_heldout_unopened",
        "source_candidate": {
            "path": str(SOURCE_CANDIDATE),
            "sha256": sha256(SOURCE_CANDIDATE),
        },
        "intrinsics": {
            "path": str(INTRINSICS),
            "sha256": sha256(INTRINSICS),
            "focal_pixels": focal,
            "distortion_coefficients": intrinsics["output_resolution"][
                "distortion_coefficients"
            ],
        },
        "training": [public_row(row) for row in rows],
        "body_selection": {
            "method": "training_pose_leave_one_out",
            "candidates": cross_validation,
            "selected": selected,
            "heldout_pose_m_accessed": False,
        },
        "tag_model": {
            "family": "tag36h11",
            "black_edge_m": 0.020,
            "tags": {
                str(tag_id): {"body": body}
                for tag_id, body in body_map.items()
            },
        },
        "training_metrics": metrics,
        "parameters": {
            "camera_world_rotation_vector_radians": parameters[:3].tolist(),
            "camera_world_translation_m": parameters[3:6].tolist(),
            "tag_mounts": {
                str(tag_id): {
                    "body_tag_rotation_vector_radians": parameters[
                        TAG_PARAMETER_START[tag_id] : TAG_PARAMETER_START[tag_id]
                        + 3
                    ].tolist(),
                    "body_tag_translation_m": parameters[
                        TAG_PARAMETER_START[tag_id]
                        + 3 : TAG_PARAMETER_START[tag_id]
                        + 6
                    ].tolist(),
                }
                for tag_id in (0, 1, 2)
            },
            "joint_zero_offsets_degrees": parameters[
                OFFSET_START : OFFSET_START + 5
            ].tolist(),
            "parameter_vector": parameters.tolist(),
        },
        "frozen_gates": {
            "per_pose_corner_rmse_max_px": RMSE_GATE_PX,
            "per_pose_corner_max_px": MAX_GATE_PX,
            "joint_offset_absolute_bound_degrees": OFFSET_BOUND_DEGREES,
            "no_offset_at_bound": True,
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "physical_task": False,
            "policy": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(candidate, indent=2, sort_keys=True))


def refreeze(
    candidate_path: Path,
    body_map_family: str,
    output: Path,
) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    source = json.loads(candidate_path.read_text(encoding="utf-8"))
    prior_evaluation = json.loads(
        PRIOR_EVALUATION.read_text(encoding="utf-8")
    )
    if (
        source.get("schema_version")
        != "sim2claw.pi_current_three_link_candidate.v1"
        or source.get("status")
        != "training_candidate_frozen_heldout_unopened"
        or prior_evaluation.get("candidate", {}).get("sha256")
        != sha256(candidate_path)
        or prior_evaluation.get("status") != "heldout_rejected_no_promotion"
    ):
        raise RuntimeError("invalid rejected source candidate or evaluation")
    choices = source["body_selection"]["candidates"]
    if body_map_family not in choices:
        raise RuntimeError(
            f"unknown body-map family {body_map_family!r}; "
            f"expected one of {sorted(choices)}"
        )
    if (
        prior_evaluation.get("best_retrospective_body_map")
        != body_map_family
    ):
        raise RuntimeError(
            "refreeze family must match the recorded retrospective best"
        )
    selection = choices[body_map_family]
    parameters = np.asarray(
        selection["full_training_parameter_vector"], dtype=np.float64
    )
    result = copy.deepcopy(source)
    result["proof_class"] = (
        "physical_static_current_camera_three_link_fresh_validation_candidate"
    )
    result["status"] = (
        "physics_map_candidate_frozen_fresh_heldout_unopened"
    )
    result["body_selection"] = {
        "method": (
            "physical_tag_attachment_map_confirmed_after_rejected_heldout;"
            "requires_new_heldout_for_any_promotion"
        ),
        "selected": body_map_family,
        "candidates": choices,
        "prior_heldout_used_for_selection": True,
        "fresh_heldout_accessed": False,
    }
    body_map = {
        int(tag_id): body
        for tag_id, body in selection["body_map"].items()
    }
    result["tag_model"]["tags"] = {
        str(tag_id): {"body": body}
        for tag_id, body in body_map.items()
    }
    result["training_metrics"] = selection["full_training_metrics"]
    result["parameters"] = {
        "camera_world_rotation_vector_radians": parameters[:3].tolist(),
        "camera_world_translation_m": parameters[3:6].tolist(),
        "tag_mounts": {
            str(tag_id): {
                "body_tag_rotation_vector_radians": parameters[
                    TAG_PARAMETER_START[tag_id] : TAG_PARAMETER_START[tag_id]
                    + 3
                ].tolist(),
                "body_tag_translation_m": parameters[
                    TAG_PARAMETER_START[tag_id]
                    + 3 : TAG_PARAMETER_START[tag_id]
                    + 6
                ].tolist(),
            }
            for tag_id in (0, 1, 2)
        },
        "joint_zero_offsets_degrees": parameters[
            OFFSET_START : OFFSET_START + 5
        ].tolist(),
        "parameter_vector": parameters.tolist(),
    }
    result["selection_provenance"] = {
        "rejected_candidate": {
            "path": str(candidate_path),
            "sha256": sha256(candidate_path),
        },
        "rejected_evaluation": {
            "path": str(PRIOR_EVALUATION),
            "sha256": sha256(PRIOR_EVALUATION),
        },
        "retrospective_heldout_metrics": prior_evaluation[
            "body_map_family_results"
        ][body_map_family],
        "fresh_validation_required": True,
    }
    result["authority"] = {
        "simulator_parameter_promotion": False,
        "physical_task": False,
        "policy": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def evaluate(
    candidate_path: Path,
    output: Path,
    heldout_directory: Path,
    heldout_name: str,
) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if (
        candidate.get("schema_version")
        != "sim2claw.pi_current_three_link_candidate.v1"
        or candidate.get("status")
        not in {
            "training_candidate_frozen_heldout_unopened",
            "physics_map_candidate_frozen_fresh_heldout_unopened",
        }
    ):
        raise RuntimeError("invalid frozen current-camera candidate")
    rows = observations(heldout_name, heldout_directory)
    if not rows:
        raise RuntimeError("heldout pose M has no unique follower tags")
    focal = float(candidate["intrinsics"]["focal_pixels"])
    bundle = ThreeLinkBundle(focal)
    body_map = {
        int(tag_id): specification["body"]
        for tag_id, specification in candidate["tag_model"]["tags"].items()
    }
    parameters = np.asarray(
        candidate["parameters"]["parameter_vector"], dtype=np.float64
    )
    errors_by_tag = {}
    all_errors = []
    for row in rows:
        errors = np.linalg.norm(
            bundle.project(parameters, row, body_map) - row["corners"],
            axis=1,
        )
        all_errors.append(errors)
        errors_by_tag[str(row["tag_id"])] = {
            "corner_rmse_px": float(np.sqrt(np.mean(errors**2))),
            "corner_max_px": float(np.max(errors)),
        }
    errors = np.concatenate(all_errors)
    rmse = float(np.sqrt(np.mean(errors**2)))
    maximum = float(np.max(errors))
    offsets = parameters[OFFSET_START : OFFSET_START + 5]
    no_offset_at_bound = bool(
        np.all(OFFSET_BOUND_DEGREES - np.abs(offsets) > 1e-3)
    )
    passed = (
        rmse <= RMSE_GATE_PX
        and maximum <= MAX_GATE_PX
        and no_offset_at_bound
    )
    family_results = {}
    for map_name, specification in candidate["body_selection"][
        "candidates"
    ].items():
        family_body_map = {
            int(tag_id): body
            for tag_id, body in specification["body_map"].items()
        }
        family_parameters = np.asarray(
            specification["full_training_parameter_vector"],
            dtype=np.float64,
        )
        family_errors = np.concatenate(
            [
                np.linalg.norm(
                    bundle.project(
                        family_parameters, row, family_body_map
                    )
                    - row["corners"],
                    axis=1,
                )
                for row in rows
            ]
        )
        family_results[map_name] = {
            "corner_rmse_px": float(
                np.sqrt(np.mean(family_errors**2))
            ),
            "corner_max_px": float(np.max(family_errors)),
        }
    best_retrospective = min(
        family_results,
        key=lambda name: family_results[name]["corner_rmse_px"],
    )
    receipt = {
        "schema_version": "sim2claw.pi_current_three_link_evaluation.v1",
        "proof_class": "physical_static_current_camera_three_link_heldout_diagnostic",
        "status": (
            "heldout_gates_passed_no_automatic_promotion"
            if passed
            else "heldout_rejected_no_promotion"
        ),
        "candidate": {
            "path": str(candidate_path),
            "sha256": sha256(candidate_path),
        },
        "heldout_directory": str(heldout_directory),
        "heldout": [public_row(row) for row in rows],
        "detected_tag_ids": [row["tag_id"] for row in rows],
        "corner_rmse_px": rmse,
        "corner_max_px": maximum,
        "errors_by_tag": errors_by_tag,
        "body_map_family_results": family_results,
        "best_retrospective_body_map": best_retrospective,
        "retrospective_selection_has_fresh_promotion_authority": False,
        "joint_zero_offsets_degrees": offsets.tolist(),
        "no_offset_at_bound": no_offset_at_bound,
        "all_gates_passed": passed,
        "selection": {
            "promoted": False,
            "reason": (
                "All heldout gates passed, but this diagnostic has no promotion authority."
                if passed
                else "Heldout reprojection or parameter-bound gates failed."
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
    print(json.dumps(receipt, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase", choices=("freeze", "refreeze", "evaluate"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--body-map-family")
    parser.add_argument("--heldout-directory", type=Path, default=HELDOUT)
    parser.add_argument("--heldout-name", default="pose_m_heldout")
    arguments = parser.parse_args()
    if arguments.phase == "freeze":
        if arguments.candidate is not None or arguments.body_map_family:
            raise RuntimeError(
                "--candidate and --body-map-family are not used by freeze"
            )
        freeze(arguments.output)
    elif arguments.phase == "refreeze":
        if arguments.candidate is None or not arguments.body_map_family:
            raise RuntimeError(
                "refreeze requires --candidate and --body-map-family"
            )
        refreeze(
            arguments.candidate,
            arguments.body_map_family,
            arguments.output,
        )
    else:
        if arguments.candidate is None:
            raise RuntimeError("--candidate is required for evaluation")
        if arguments.body_map_family:
            raise RuntimeError("--body-map-family is refreeze-only")
        evaluate(
            arguments.candidate,
            arguments.output,
            arguments.heldout_directory,
            arguments.heldout_name,
        )


if __name__ == "__main__":
    main()
