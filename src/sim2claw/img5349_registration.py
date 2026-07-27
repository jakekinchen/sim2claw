"""Fail-closed IMG_5349 3DGS-to-simulation visual registration."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np


REGISTRATION_CONTRACT = Path(
    "configs/evaluations/img5349_3dgs_board_registration_v1.json"
)
SCHEMA = "sim2claw.img5349_3dgs_board_registration.v1"

# MuJoCo uses Z-up. The Studio calibration renderer uses Three.js Y-up and
# already applies this same basis change to its reviewed MuJoCo scene layer.
MUJOCO_TO_THREE = np.asarray(
    (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, -1.0, 0.0),
    ),
    dtype=np.float64,
)


def _vector(value: Any, *, length: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (length,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must contain {length} finite values")
    return result


def _matrix(value: Any, *, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (3, 3) or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be a finite 3x3 matrix")
    return result


def load_registration_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported IMG_5349 registration schema")
    return contract


def validated_studio_registration(
    contract: dict[str, Any],
    *,
    release_manifest: dict[str, Any],
    model_name: str,
    model_sha256: str,
) -> dict[str, Any]:
    """Validate the fit and return a Three.js-ready, non-authoritative Sim(3)."""

    source = contract.get("source_binding", {})
    if (
        contract.get("status") != "accepted_visual_registration_diagnostic"
        or source.get("release_tag") != release_manifest.get("release_tag")
        or source.get("source_video_sha256")
        != release_manifest.get("source", {}).get("sha256")
        or source.get("splat_name") != model_name
        or source.get("splat_sha256") != model_sha256
    ):
        raise ValueError("registration source binding does not match release")

    authority = contract.get("authority", {})
    forbidden_authority = (
        "metric_scale",
        "measured_robot_geometry",
        "collision_geometry",
        "contact",
        "actuator_or_load_path",
        "task_consequence",
        "physical_robot_control",
    )
    if any(bool(authority.get(name)) for name in forbidden_authority):
        raise ValueError("visual registration cannot grant downstream authority")

    fit = contract.get("fit", {})
    scale = float(fit.get("scale_m_per_sfm_unit"))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("registration scale must be positive and finite")
    rotation = _matrix(
        fit.get("rotation_source_to_mujoco"),
        label="rotation_source_to_mujoco",
    )
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-9):
        raise ValueError("registration rotation must be orthonormal")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-9):
        raise ValueError("registration rotation must be proper")
    translation = _vector(
        fit.get("translation_mujoco_m"),
        length=3,
        label="translation_mujoco_m",
    )

    source_corners = np.asarray(
        fit.get("source_playing_corners_sfm"), dtype=np.float64
    )
    target_names = fit.get("source_corner_target_names")
    target_lookup = contract.get("target_binding", {}).get(
        "corners_mujoco_m", {}
    )
    if source_corners.shape != (4, 3) or not np.all(np.isfinite(source_corners)):
        raise ValueError("source_playing_corners_sfm must be finite 4x3")
    if not isinstance(target_names, list) or len(target_names) != 4:
        raise ValueError("source_corner_target_names must contain four names")
    targets = np.stack(
        [
            _vector(target_lookup.get(name), length=3, label=f"target {name}")
            for name in target_names
        ]
    )
    transformed = scale * (rotation @ source_corners.T).T + translation
    corner_rms = float(np.sqrt(np.mean(np.sum((transformed - targets) ** 2, axis=1))))
    if corner_rms > 1e-6:
        raise ValueError("registration no longer reproduces target board corners")

    validation = contract.get("validation", {})
    heldout = validation.get("heldout_frames", [])
    corner_count = sum(int(row["corner_count"]) for row in heldout)
    weighted_rms = math.sqrt(
        sum(int(row["corner_count"]) * float(row["rms_px"]) ** 2 for row in heldout)
        / corner_count
    )
    if (
        corner_count != int(validation.get("heldout_corner_count"))
        or not math.isclose(
            weighted_rms,
            float(validation.get("heldout_weighted_rms_px")),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("held-out registration summary is internally inconsistent")
    if validation.get("supersedes") != "all_segment_sim3_and_3.21px_claim":
        raise ValueError("superseded global-camera result must remain retracted")

    palette = contract.get("visual_overlay_palette", {})
    expected_palette = {
        "checker_even_parity_rgba": [0.27, 0.105, 0.025, 1.0],
        "checker_odd_parity_rgba": [0.83, 0.63, 0.36, 1.0],
        "logical_brown_pawn_display_rgba": [0.78, 0.62, 0.40, 1.0],
        "logical_tan_pawn_display_rgba": [0.42, 0.24, 0.13, 1.0],
    }
    if (
        palette.get("status") != "accepted_current_physical_visual_only"
        or palette.get("semantic_piece_ids_changed") is not False
        or palette.get("shared_scene_or_evaluator_changed") is not False
        or any(palette.get(key) != value for key, value in expected_palette.items())
    ):
        raise ValueError("registered visual-only palette contract drifted")
    frame_hashes = palette.get("current_c922_frame_sha256", {})
    if set(frame_hashes) != {"H", "I", "D"} or any(
        not isinstance(value, str) or len(value) != 64
        for value in frame_hashes.values()
    ):
        raise ValueError("visual-only palette requires three bound C922 frames")

    three_rotation = MUJOCO_TO_THREE @ rotation
    three_translation = MUJOCO_TO_THREE @ translation
    linear = scale * three_rotation
    matrix_rows = np.eye(4, dtype=np.float64)
    matrix_rows[:3, :3] = linear
    matrix_rows[:3, 3] = three_translation

    target_center_mujoco = np.mean(targets, axis=0)
    target_center_three = MUJOCO_TO_THREE @ target_center_mujoco
    return {
        "schema_version": SCHEMA,
        "status": contract["status"],
        "proof_class": contract["proof_class"],
        "source_to_three_matrix_rows": matrix_rows.tolist(),
        "target_center_three": target_center_three.tolist(),
        "scale_m_per_sfm_unit": scale,
        "corner_fit_rms_m": corner_rms,
        "heldout_weighted_rms_px": weighted_rms,
        "heldout_corner_count": corner_count,
        "accepted_camera_component": fit["accepted_camera_component"],
        "rejected_camera_segments": validation["rejected_camera_segments"],
        "d4_mapping": [
            f"source[{index}]->{name}" for index, name in enumerate(target_names)
        ],
        "automatic_overlay": True,
        "visual_overlay_palette": {
            "status": palette["status"],
            **expected_palette,
            "current_c922_frame_sha256": frame_hashes,
            "semantic_piece_ids_changed": False,
            "shared_scene_or_evaluator_changed": False,
        },
        "authority": authority,
    }


def load_validated_studio_registration(
    repo_root: Path,
    *,
    release_manifest: dict[str, Any],
    model_name: str,
    model_sha256: str,
) -> dict[str, Any] | None:
    path = repo_root / REGISTRATION_CONTRACT
    try:
        contract = load_registration_contract(path)
        return validated_studio_registration(
            contract,
            release_manifest=release_manifest,
            model_name=model_name,
            model_sha256=model_sha256,
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
