"""Screen pose-plane receipts before any hand-eye fit is allowed.

The repository currently lacks approved physical FK and D405 wrist-mount frame
contracts. This evaluator therefore reports observation diversity and numerical
rank, but never substitutes simulator FK or invents a transform.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT

CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/d405_hand_eye_identifiability_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_hand_eye_identifiability_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_hand_eye_identifiability_receipt.v1"
INPUT_SCHEMA = "sim2claw.d405_pose_plane_capture_receipt.v1"
INPUT_PROOF = "physical_calibration_setup_pose_plane_observations_only"


class D405HandEyeIdentifiabilityError(RuntimeError):
    """A receipt set is malformed or crosses its proof boundary."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise D405HandEyeIdentifiabilityError("unexpected identifiability contract")
    if not value.get("authority") or any(value["authority"].values()):
        raise D405HandEyeIdentifiabilityError("identifiability authority widened")
    return value


def _rank_condition(matrix: np.ndarray, relative_tolerance: float) -> dict[str, Any]:
    centered = matrix - np.mean(matrix, axis=0, keepdims=True)
    singular = np.linalg.svd(centered, compute_uv=False)
    threshold = (
        float(singular[0]) * relative_tolerance if singular.size else 0.0
    )
    retained = singular[singular > threshold]
    return {
        "shape": list(centered.shape),
        "singular_values": singular.tolist(),
        "relative_rank_tolerance": relative_tolerance,
        "rank": int(len(retained)),
        "condition_number_retained_subspace": (
            float(retained[0] / retained[-1]) if len(retained) else None
        ),
    }


def _maximum_normal_angle(normals: np.ndarray) -> float:
    dots = np.clip(normals @ normals.T, -1.0, 1.0)
    return float(np.degrees(np.max(np.arccos(dots))))


def _representative(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema_version") != INPUT_SCHEMA
        or value.get("proof_class") != INPUT_PROOF
        or value.get("verdict", {}).get("passed") is not True
        or not value.get("authority")
        or any(value["authority"].values())
        or value.get("verdict", {}).get("camera_to_robot_extrinsic_fitted")
        is not False
    ):
        raise D405HandEyeIdentifiabilityError(
            f"input receipt is not bounded pose-plane evidence: {path}"
        )
    joint = np.asarray(
        value["terminal_hold"]["joint_pose"]["mean_degrees"], dtype=np.float64
    )
    observations = value.get("observations", [])
    normals = np.asarray(
        [item["plane"]["normal_camera_unit"] for item in observations],
        dtype=np.float64,
    )
    offsets = np.asarray(
        [item["plane"]["plane_equation"]["offset_m"] for item in observations],
        dtype=np.float64,
    )
    if (
        joint.shape != (6,)
        or normals.ndim != 2
        or normals.shape[1] != 3
        or len(normals) == 0
        or not np.all(np.isfinite(joint))
        or not np.all(np.isfinite(normals))
        or not np.all(np.isfinite(offsets))
    ):
        raise D405HandEyeIdentifiabilityError(f"nonfinite pose-plane data: {path}")
    norms = np.linalg.norm(normals, axis=1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1e-5) or np.any(
        normals[:, 2] <= 0.0
    ):
        raise D405HandEyeIdentifiabilityError(
            f"plane normals violate the camera-positive-Z convention: {path}"
        )
    normal = np.mean(normals, axis=0)
    normal /= np.linalg.norm(normal)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "joint_degrees": joint,
        "normal": normal,
        "offset_m": float(np.mean(offsets)),
        "within_pose_normal_angle_degrees": _maximum_normal_angle(normals),
        "within_pose_offset_drift_m": float(np.ptp(offsets)),
        "camera_identity": value["identity"]["database"],
        "calibration_receipt_sha256": value["calibration_lineage"][
            "accepted_capture_receipt_sha256"
        ],
    }


def evaluate_d405_hand_eye_identifiability(
    receipt_paths: list[Path],
    *,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Screen diversity and seal missing FK/frame prerequisites."""
    contract = load_contract(contract_path)
    rows = [_representative(path.resolve()) for path in receipt_paths]
    if not rows:
        raise D405HandEyeIdentifiabilityError("receipt set is empty")
    identities = {json.dumps(row["camera_identity"], sort_keys=True) for row in rows}
    calibrations = {row["calibration_receipt_sha256"] for row in rows}
    if len(identities) != 1 or len(calibrations) != 1:
        raise D405HandEyeIdentifiabilityError(
            "camera identity or calibration lineage changed across receipts"
        )

    joints = np.asarray([row["joint_degrees"] for row in rows])
    normals = np.asarray([row["normal"] for row in rows])
    offsets = np.asarray([row["offset_m"] for row in rows])
    tolerance = float(contract["rank_relative_tolerance"])
    joint_rank = _rank_condition(np.radians(joints), tolerance)
    normal_rank = _rank_condition(normals, tolerance)
    observation_matrix = np.column_stack(
        (np.radians(joints), normals, offsets / 0.1)
    )
    combined_rank = _rank_condition(observation_matrix, tolerance)
    metrics = {
        "receipt_count": len(rows),
        "joint_centered_rank": joint_rank,
        "normal_centered_rank": normal_rank,
        "combined_screening_rank": combined_rank,
        "maximum_joint_span_degrees": float(np.max(np.ptp(joints, axis=0))),
        "normal_angular_span_degrees": _maximum_normal_angle(normals),
        "plane_offset_span_m": float(np.ptp(offsets)),
        "maximum_within_pose_normal_angle_degrees": max(
            row["within_pose_normal_angle_degrees"] for row in rows
        ),
        "maximum_within_pose_offset_drift_m": max(
            row["within_pose_offset_drift_m"] for row in rows
        ),
    }
    gates = {
        "minimum_receipts": len(rows) >= int(contract["minimum_pose_receipts"]),
        "joint_rank": joint_rank["rank"]
        >= int(contract["minimum_joint_centered_rank"]),
        "joint_span": metrics["maximum_joint_span_degrees"]
        >= float(contract["minimum_joint_span_degrees"]),
        "normal_rank": normal_rank["rank"]
        >= int(contract["minimum_normal_centered_rank"]),
        "normal_span": metrics["normal_angular_span_degrees"]
        >= float(contract["minimum_normal_angular_span_degrees"]),
        "offset_span": metrics["plane_offset_span_m"]
        >= float(contract["minimum_plane_offset_span_m"]),
        "within_pose_normal_stability": metrics[
            "maximum_within_pose_normal_angle_degrees"
        ]
        <= float(contract["maximum_within_pose_normal_angle_degrees"]),
        "within_pose_offset_stability": metrics[
            "maximum_within_pose_offset_drift_m"
        ]
        <= float(contract["maximum_within_pose_offset_drift_m"]),
    }
    diversity_passed = all(gates.values())
    missing = [
        name
        for name, path in contract["required_prerequisites"].items()
        if path is None
    ]
    classification = (
        "insufficient_observations"
        if not diversity_passed
        else "diversity_passed_kinematic_camera_frame_contract_missing"
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "authority": contract["authority"],
        "input_lineage": [
            {"path": row["path"], "sha256": row["sha256"]} for row in rows
        ],
        "contract_lineage": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "diversity_metrics": metrics,
        "diversity_gates": gates,
        "diversity_passed": diversity_passed,
        "true_hand_eye_identifiability_established": False,
        "missing_prerequisites": missing,
        "screening_rank_is_not_calibration_jacobian_rank": True,
        "fit": {
            "attempted": False,
            "wrist_camera_rotation": None,
            "wrist_camera_translation_m": None,
            "fixed_base_plane": None,
            "held_out_residuals": None,
            "reason": (
                "observation diversity gates failed"
                if not diversity_passed
                else "approved physical FK and D405 wrist-mount frame contracts are absent"
            ),
        },
        "verdict": {
            "passed": False,
            "classification": classification,
            "failure_reasons": (
                [name for name, passed in gates.items() if not passed]
                if not diversity_passed
                else missing
            ),
            "camera_to_robot_extrinsic_fitted": False,
            "promotion_authority": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt
