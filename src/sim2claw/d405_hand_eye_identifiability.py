"""Screen admitted pose-plane receipts and fit only identifiable hand-eye terms."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT
from .physical_fk_frame import (
    load_physical_fk_contract,
    physical_fk_base_from_wrist,
)

CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/d405_hand_eye_identifiability_v2.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_hand_eye_identifiability_contract.v2"
RECEIPT_SCHEMA = "sim2claw.d405_hand_eye_identifiability_receipt.v2"
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


def _rank_condition(
    matrix: np.ndarray, relative_tolerance: float, *, center: bool = True
) -> dict[str, Any]:
    analyzed = (
        matrix - np.mean(matrix, axis=0, keepdims=True)
        if center
        else matrix
    )
    singular = np.linalg.svd(analyzed, compute_uv=False)
    threshold = (
        float(singular[0]) * relative_tolerance if singular.size else 0.0
    )
    retained = singular[singular > threshold]
    return {
        "shape": list(analyzed.shape),
        "centered": center,
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


def _angular_residuals(
    base_from_wrist: np.ndarray,
    wrist_from_camera: np.ndarray,
    camera_normals: np.ndarray,
    base_normal: np.ndarray,
) -> np.ndarray:
    predicted = np.einsum(
        "nij,jk,nk->ni",
        base_from_wrist[:, :3, :3],
        wrist_from_camera,
        camera_normals,
    )
    dots = np.clip(predicted @ base_normal, -1.0, 1.0)
    return np.degrees(np.arccos(dots))


def _fit_hand_eye(
    train_fk: np.ndarray,
    train_normals: np.ndarray,
    train_offsets: np.ndarray,
    held_fk: np.ndarray,
    held_normals: np.ndarray,
    held_offsets: np.ndarray,
    contract: dict[str, Any],
) -> dict[str, Any]:
    rotations = train_fk[:, :3, :3]

    def residual(rotation_vector: np.ndarray) -> np.ndarray:
        wrist_from_camera = Rotation.from_rotvec(rotation_vector).as_matrix()
        predicted = np.einsum(
            "nij,jk,nk->ni", rotations, wrist_from_camera, train_normals
        )
        base_normal = np.mean(predicted, axis=0)
        base_normal /= np.linalg.norm(base_normal)
        return (predicted - base_normal).ravel()

    starts = (
        np.zeros(3),
        np.asarray([math.pi / 2, 0, 0]),
        np.asarray([0, math.pi / 2, 0]),
        np.asarray([0, 0, math.pi / 2]),
    )
    solutions = [least_squares(residual, start, method="trf") for start in starts]
    solution = min(solutions, key=lambda item: float(np.sum(item.fun**2)))
    wrist_from_camera = Rotation.from_rotvec(solution.x).as_matrix()
    predicted = np.einsum(
        "nij,jk,nk->ni", rotations, wrist_from_camera, train_normals
    )
    base_normal = np.mean(predicted, axis=0)
    base_normal /= np.linalg.norm(base_normal)
    jacobian = _rank_condition(
        solution.jac,
        float(contract["rank_relative_tolerance"]),
        center=False,
    )
    training_angles = _angular_residuals(
        train_fk, wrist_from_camera, train_normals, base_normal
    )
    held_angles = _angular_residuals(
        held_fk, wrist_from_camera, held_normals, base_normal
    )
    rotation_passed = (
        jacobian["rank"] == 3
        and jacobian["condition_number_retained_subspace"]
        <= float(contract["maximum_rotation_jacobian_condition"])
        and float(np.max(training_angles))
        <= float(contract["maximum_training_normal_residual_degrees"])
        and float(np.max(held_angles))
        <= float(contract["maximum_held_out_normal_residual_degrees"])
    )

    translation_rows = np.column_stack(
        (
            np.einsum("j,njk->nk", base_normal, rotations),
            np.ones(len(train_fk)),
        )
    )
    translation_rhs = train_offsets - np.einsum(
        "j,nj->n", base_normal, train_fk[:, :3, 3]
    )
    translation_rank = _rank_condition(
        translation_rows,
        float(contract["rank_relative_tolerance"]),
        center=False,
    )
    translation_observable = (
        rotation_passed
        and translation_rank["rank"]
        >= int(contract["minimum_translation_design_rank"])
    )
    translation = None
    base_offset = None
    held_offset_residuals = None
    if translation_observable:
        parameters = np.linalg.lstsq(
            translation_rows, translation_rhs, rcond=None
        )[0]
        translation, base_offset = parameters[:3], float(parameters[3])
        held_design = np.column_stack(
            (
                np.einsum(
                    "j,njk->nk", base_normal, held_fk[:, :3, :3]
                ),
                np.ones(len(held_fk)),
            )
        )
        held_rhs = held_offsets - np.einsum(
            "j,nj->n", base_normal, held_fk[:, :3, 3]
        )
        held_offset_residuals = (held_design @ parameters - held_rhs).tolist()
    return {
        "rotation_identifiable": rotation_passed,
        "translation_identifiable": translation_observable,
        "rotation_jacobian": jacobian,
        "translation_design": translation_rank,
        "wrist_from_d405_depth_optical_rotation_matrix": (
            wrist_from_camera.tolist() if rotation_passed else None
        ),
        "wrist_from_d405_depth_optical_translation_m": (
            translation.tolist() if translation is not None else None
        ),
        "fixed_base_plane": {
            "normal": base_normal.tolist(),
            "offset_m": base_offset,
        }
        if rotation_passed
        else None,
        "training_normal_residual_degrees": training_angles.tolist(),
        "held_out_normal_residual_degrees": held_angles.tolist(),
        "held_out_plane_offset_residual_m": held_offset_residuals,
    }


def _representative(
    path: Path, contract: dict[str, Any]
) -> dict[str, Any]:
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
    required_admission = contract["required_plane_admission"]
    producer_path = (
        REPO_ROOT / required_admission["contract_path"]
    ).resolve()
    producer_contract = json.loads(producer_path.read_text(encoding="utf-8"))
    admission = value.get("plane_admission", {})
    admission_contract = admission.get("contract", {})
    observations = value.get("observations", [])
    rejected = value.get("rejected_observations", [])
    admission_checks = admission.get("checks", {})
    if not (
        admission.get("passed") is True
        and admission.get("surface_semantics")
        == required_admission["surface_semantics"]
        and admission_contract.get("schema_version")
        == required_admission["contract_schema"]
        and Path(admission_contract.get("path", "")).resolve() == producer_path
        and admission_contract.get("sha256") == sha256_file(producer_path)
        and producer_contract.get("schema_version")
        == required_admission["contract_schema"]
        and admission.get("minimum_accepted_frame_count")
        == producer_contract.get("minimum_accepted_frame_count")
        and isinstance(admission.get("authority"), dict)
        and admission["authority"] == producer_contract.get("authority")
        and isinstance(admission_checks, dict)
        and admission_checks
        and all(admission_checks.values())
        and admission.get("accepted_frame_count") == len(observations)
        and admission.get("rejected_frame_count") == len(rejected)
        and admission.get("input_frame_count")
        == len(observations) + len(rejected)
        and admission.get("accepted_frame_count", 0)
        >= admission.get("minimum_accepted_frame_count", math.inf)
        and all(item.get("admitted") is True for item in observations)
    ):
        raise D405HandEyeIdentifiabilityError(
            f"producer plane admission lineage failed closed: {path}"
        )
    joint = np.asarray(
        value["terminal_hold"]["joint_pose"]["mean_degrees"], dtype=np.float64
    )
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
        "plane_admission_contract_sha256": admission_contract["sha256"],
    }


def evaluate_d405_hand_eye_identifiability(
    receipt_paths: list[Path],
    *,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Validate producer admission, screen diversity, then fit if determined."""
    contract = load_contract(contract_path)
    rows = sorted(
        [_representative(path.resolve(), contract) for path in receipt_paths],
        key=lambda row: row["sha256"],
    )
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
        "producer_plane_admission": True,
    }
    diversity_passed = all(gates.values())
    fk_path = (REPO_ROOT / contract["physical_fk_frame_contract_path"]).resolve()
    fk_declaration = json.loads(fk_path.read_text(encoding="utf-8"))
    fk_contract: dict[str, Any] | None = None
    fit: dict[str, Any] | None = None
    train_lineage: list[dict[str, str]] = []
    held_lineage: list[dict[str, str]] = []
    if diversity_passed:
        fk_contract, _model = load_physical_fk_contract(fk_path)
        held_count = max(
            1, int(math.ceil(len(rows) * float(contract["held_out_fraction"])))
        )
        train, held = rows[:-held_count], rows[-held_count:]
        train_lineage = [
            {"path": row["path"], "sha256": row["sha256"]} for row in train
        ]
        held_lineage = [
            {"path": row["path"], "sha256": row["sha256"]} for row in held
        ]
        train_fk = np.asarray(
            [physical_fk_base_from_wrist(row["joint_degrees"]) for row in train]
        )
        held_fk = np.asarray(
            [physical_fk_base_from_wrist(row["joint_degrees"]) for row in held]
        )
        fit = _fit_hand_eye(
            train_fk,
            np.asarray([row["normal"] for row in train]),
            np.asarray([row["offset_m"] for row in train]),
            held_fk,
            np.asarray([row["normal"] for row in held]),
            np.asarray([row["offset_m"] for row in held]),
            contract,
        )
    rotation_identifiable = bool(fit and fit["rotation_identifiable"])
    translation_identifiable = bool(fit and fit["translation_identifiable"])
    if not diversity_passed:
        classification = "insufficient_observations"
    elif not rotation_identifiable:
        classification = "hand_eye_rotation_not_identifiable"
    elif not translation_identifiable:
        classification = "rotation_identifiable_translation_gauge_ambiguous"
    else:
        classification = "hand_eye_extrinsic_fit_diagnostic_only"
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
        "producer_plane_admission_contract": {
            "path": str(
                (
                    REPO_ROOT
                    / contract["required_plane_admission"]["contract_path"]
                ).resolve()
            ),
            "sha256": rows[0]["plane_admission_contract_sha256"],
            "schema_version": contract["required_plane_admission"][
                "contract_schema"
            ],
            "trusted_for_within_pose_frame_admission": True,
        },
        "diversity_metrics": metrics,
        "diversity_gates": gates,
        "diversity_passed": diversity_passed,
        "physical_fk_frame_contract": {
            "path": str(fk_path),
            "sha256": sha256_file(fk_path),
            "contract_id": fk_declaration["contract_id"],
            "unknown_to_fit": fk_declaration["unknown_to_fit"],
            "compiled_and_validated_for_fit": fk_contract is not None,
        },
        "fit_split": {
            "training": train_lineage,
            "held_out": held_lineage,
        },
        "rotation_identifiability_established": rotation_identifiable,
        "translation_identifiability_established": translation_identifiable,
        "screening_rank_is_not_calibration_jacobian_rank": True,
        "fit": (
            {"attempted": True, **fit}
            if fit is not None
            else {
                "attempted": False,
                "wrist_from_d405_depth_optical_rotation_matrix": None,
                "wrist_from_d405_depth_optical_translation_m": None,
                "fixed_base_plane": None,
                "held_out_normal_residual_degrees": None,
                "held_out_plane_offset_residual_m": None,
                "reason": "observation diversity gates failed",
            }
        ),
        "verdict": {
            "passed": rotation_identifiable,
            "classification": classification,
            "failure_reasons": (
                [name for name, passed in gates.items() if not passed]
                if not diversity_passed
                else (
                    ["rotation fit rank, conditioning, or residual gates failed"]
                    if not rotation_identifiable
                    else (
                        ["translation and base-plane offset are gauge ambiguous"]
                        if not translation_identifiable
                        else []
                    )
                )
            ),
            "camera_to_robot_extrinsic_fitted": translation_identifiable,
            "promotion_authority": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt
