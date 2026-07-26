#!/usr/bin/env python3
"""Calibrate the current Pi view from the printed 20 mm fiducial sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


SHEET_TAG_IDS = (5, 6, 8, 11, 12, 14)
FULL_SIZE = (4608, 2592)
OUTPUT_SIZE = (1536, 864)
TAG_BLACK_HALF_SIZE_M = 0.008
TAG_COLUMN_PITCH_M = 0.035
TAG_ROW_PITCH_M = 0.041
PRINCIPAL_POINT = (2304.0, 1296.0)
FOCAL_SEED_PX = 655.0848213719449 * 3.0
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def object_corners(tag_id: int) -> np.ndarray:
    center_x = (tag_id % 5) * TAG_COLUMN_PITCH_M
    center_y = (tag_id // 5) * TAG_ROW_PITCH_M
    half = TAG_BLACK_HALF_SIZE_M
    # The camera image is hflip+vflip. ArUco's image-top-left ordering maps to
    # page bottom-right, bottom-left, top-left, top-right.
    return np.asarray(
        [
            [center_x + half, center_y + half, 0.0],
            [center_x - half, center_y + half, 0.0],
            [center_x - half, center_y - half, 0.0],
            [center_x + half, center_y - half, 0.0],
        ],
        dtype=np.float32,
    )


def detect_sheet(image: np.ndarray) -> dict[int, np.ndarray]:
    parameters = cv2.aruco.DetectorParameters()
    parameters.minMarkerPerimeterRate = 0.005
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.adaptiveThreshWinSizeMax = 53
    corners, identifiers, _ = cv2.aruco.ArucoDetector(
        DICTIONARY, parameters
    ).detectMarkers(image)
    found: dict[int, np.ndarray] = {}
    if identifiers is not None:
        for identifier, corner in zip(
            identifiers.ravel(), corners, strict=True
        ):
            tag_id = int(identifier)
            if (
                tag_id in SHEET_TAG_IDS
                and float(np.mean(corner[0, :, 1])) > 1300.0
            ):
                found[tag_id] = corner[0].astype(np.float32)
    if sorted(found) != list(SHEET_TAG_IDS):
        raise RuntimeError(
            f"expected sheet tags {SHEET_TAG_IDS}, found {sorted(found)}"
        )
    return found


def calibration_flags(model: str) -> int:
    result = (
        cv2.CALIB_USE_INTRINSIC_GUESS
        | cv2.CALIB_FIX_ASPECT_RATIO
        | cv2.CALIB_FIX_PRINCIPAL_POINT
        | cv2.CALIB_ZERO_TANGENT_DIST
        | cv2.CALIB_FIX_K3
        | cv2.CALIB_FIX_K4
        | cv2.CALIB_FIX_K5
        | cv2.CALIB_FIX_K6
    )
    if model == "zero":
        result |= cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2
    return result


def fit(
    tags: dict[int, np.ndarray], training_ids: list[int], model: str
) -> dict[str, Any]:
    object_points = np.concatenate(
        [object_corners(tag_id) for tag_id in training_ids]
    )
    image_points = np.concatenate([tags[tag_id] for tag_id in training_ids])
    seed = np.asarray(
        [
            [FOCAL_SEED_PX, 0.0, PRINCIPAL_POINT[0]],
            [0.0, FOCAL_SEED_PX, PRINCIPAL_POINT[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(
        [object_points],
        [image_points],
        FULL_SIZE,
        seed,
        np.zeros(8, dtype=np.float64),
        flags=calibration_flags(model),
    )
    return {
        "rms_px": float(rms),
        "camera_matrix": matrix,
        "distortion": distortion.ravel(),
        "rotation": rotations[0].ravel(),
        "translation": translations[0].ravel(),
    }


def project(tag_id: int, fitted: dict[str, Any]) -> np.ndarray:
    pixels, _ = cv2.projectPoints(
        object_corners(tag_id),
        fitted["rotation"],
        fitted["translation"],
        fitted["camera_matrix"],
        fitted["distortion"],
    )
    return pixels[:, 0]


def cross_validate(
    tags: dict[int, np.ndarray], model: str
) -> dict[str, Any]:
    folds = []
    for heldout in SHEET_TAG_IDS:
        fitted = fit(
            tags,
            [tag_id for tag_id in SHEET_TAG_IDS if tag_id != heldout],
            model,
        )
        errors = np.linalg.norm(
            project(heldout, fitted) - tags[heldout], axis=1
        )
        folds.append(
            {
                "heldout_tag_id": heldout,
                "corner_rmse_px": float(np.sqrt(np.mean(errors**2))),
                "corner_max_px": float(np.max(errors)),
                "focal_pixels": float(fitted["camera_matrix"][0, 0]),
                "radial_coefficients": fitted["distortion"][:2].tolist(),
            }
        )
    return {
        "folds": folds,
        "mean_fold_rmse_px": float(
            np.mean([row["corner_rmse_px"] for row in folds])
        ),
        "maximum_fold_corner_error_px": float(
            np.max([row["corner_max_px"] for row in folds])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.overlay.exists():
        raise RuntimeError("refusing to overwrite calibration outputs")
    image = cv2.imread(str(arguments.image))
    if image is None or image.shape[:2] != (FULL_SIZE[1], FULL_SIZE[0]):
        raise RuntimeError("expected one 4608x2592 Pi image")
    tags = detect_sheet(image)
    validation = {
        model: cross_validate(tags, model) for model in ("zero", "radial")
    }
    selected_model = min(
        validation,
        key=lambda model: validation[model]["mean_fold_rmse_px"],
    )
    fitted = fit(tags, list(SHEET_TAG_IDS), selected_model)
    scale = OUTPUT_SIZE[0] / FULL_SIZE[0]
    output_matrix = fitted["camera_matrix"].copy()
    output_matrix[:2] *= scale
    receipt = {
        "schema_version": "sim2claw.pi_fiducial_sheet_intrinsics.v1",
        "proof_class": "physical_static_planar_sheet_intrinsics_diagnostic",
        "status": "frozen",
        "image": {
            "path": str(arguments.image),
            "sha256": sha256(arguments.image),
            "size_px": list(FULL_SIZE),
            "capture_mode": {
                "camera": "imx708_wide",
                "autofocus_mode": "manual",
                "lens_position_reciprocal_m": 4.0,
                "horizontal_flip": True,
                "vertical_flip": True,
            },
        },
        "sheet": {
            "family": "tag36h11",
            "layout": "5_columns_by_4_rows",
            "black_square_size_m": 2.0 * TAG_BLACK_HALF_SIZE_M,
            "column_pitch_m": TAG_COLUMN_PITCH_M,
            "row_pitch_m": TAG_ROW_PITCH_M,
            "detected_tag_ids": list(SHEET_TAG_IDS),
            "planar_pose_independently_measured": False,
        },
        "model_validation": validation,
        "selection": {
            "selected_model": selected_model,
            "criterion": "minimum_leave_one_tag_out_mean_corner_rmse",
            "radial_model_rejected": selected_model != "radial",
        },
        "full_resolution": {
            "camera_matrix": fitted["camera_matrix"].tolist(),
            "distortion_coefficients": fitted["distortion"].tolist(),
            "training_rms_px": fitted["rms_px"],
        },
        "output_resolution": {
            "size_px": list(OUTPUT_SIZE),
            "camera_matrix": output_matrix.tolist(),
            "distortion_coefficients": fitted["distortion"].tolist(),
            "validation_mean_rmse_px": validation[selected_model][
                "mean_fold_rmse_px"
            ]
            * scale,
            "validation_max_corner_px": validation[selected_model][
                "maximum_fold_corner_error_px"
            ]
            * scale,
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "physical_task": False,
            "policy": False,
        },
        "limitations": {
            "single_planar_sheet_view": True,
            "lens_focus_matches_torque_on_autofocus_exactly": False,
            "camera_to_robot_extrinsic": False,
        },
    }
    overlay = image.copy()
    for tag_id in SHEET_TAG_IDS:
        observed = np.rint(tags[tag_id]).astype(np.int32).reshape(-1, 1, 2)
        predicted = np.rint(project(tag_id, fitted)).astype(np.int32).reshape(
            -1, 1, 2
        )
        cv2.polylines(overlay, [observed], True, (40, 255, 40), 7)
        cv2.polylines(overlay, [predicted], True, (255, 255, 255), 4)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.overlay.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not cv2.imwrite(str(arguments.overlay), overlay):
        raise RuntimeError("failed to write calibration overlay")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
