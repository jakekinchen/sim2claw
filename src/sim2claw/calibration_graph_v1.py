"""Minimum gauge-fixed calibration graph for current mapping admission."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .paths import REPO_ROOT


class CalibrationGraphError(RuntimeError):
    """The frozen calibration graph failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CalibrationGraphError(
            "calibration graph input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CalibrationGraphError(
            f"calibration graph input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def evaluate(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise CalibrationGraphError(
            "immutable calibration graph output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "sources",
        "implementation",
        "variables",
        "factors",
        "gates",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.calibration_graph.v1"
        or contract["authority"]
        != {
            "read_existing_evidence": True,
            "fit_mapping_diagnostic": True,
            "mapping_approval": False,
            "evaluator_v2_freeze": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        }
    ):
        raise CalibrationGraphError("calibration graph contract widened")
    sources = {
        name: _json(binding) for name, binding in contract["sources"].items()
    }
    _bound(contract["implementation"])
    registration = sources["accepted_task_plane_registration"]
    differential = sources["one_joint_differential"]
    mapping = sources["prior_mapping_evaluation"]
    if (
        registration.get("status")
        != "canonical_task_plane_registration_pass"
        or differential.get("status")
        != "retrospective_joint_image_jacobian_diagnostic_completed"
        or mapping.get("status")
        != "identifiability_failed_no_mapping_verdict"
    ):
        raise CalibrationGraphError(
            "calibration graph source admission changed"
        )
    joint_order = list(contract["variables"]["active_joint_scales"])
    jacobian = np.zeros((2 * len(joint_order), len(joint_order)))
    observations = np.zeros(2 * len(joint_order))
    factors = []
    estimates: dict[str, float] = {}
    for index, joint_name in enumerate(joint_order):
        row = differential["joint_results"][joint_name]
        observed = np.asarray(
            row["observed_slope_xy_pixels_per_degree"], dtype=np.float64
        )
        simulated = np.asarray(
            row["simulated_slope_xy_pixels_per_degree"], dtype=np.float64
        )
        scale = float(
            np.dot(simulated, observed) / np.dot(simulated, simulated)
        )
        residual = observed - scale * simulated
        jacobian[2 * index : 2 * index + 2, index] = simulated
        observations[2 * index : 2 * index + 2] = observed
        estimates[joint_name] = scale
        factors.append(
            {
                "factor_id": f"differential:{joint_name}",
                "observed_xy_px_per_degree": observed.tolist(),
                "simulated_xy_px_per_degree": simulated.tolist(),
                "estimated_scale": scale,
                "residual_xy_px_per_degree": residual.tolist(),
                "residual_norm_px_per_degree": float(
                    np.linalg.norm(residual)
                ),
                "direction_difference_degrees": float(
                    row["direction_difference_degrees"]
                ),
                "observed_r_squared": float(row["observed_r_squared"]),
            }
        )
    singular_values = np.linalg.svd(
        jacobian, compute_uv=False
    ).astype(float)
    rank = int(np.linalg.matrix_rank(jacobian))
    condition = float(singular_values[0] / singular_values[-1])
    covariance = np.linalg.inv(jacobian.T @ jacobian)
    standard = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(standard, standard)
    scale_low, scale_high = contract["gates"]["joint_scale_bounds"]
    factor_checks = {
        row["factor_id"]: {
            "scale_in_bounds": scale_low
            <= row["estimated_scale"]
            <= scale_high,
            "direction_passed": row["direction_difference_degrees"]
            <= contract["gates"]["direction_difference_max_degrees"],
            "r_squared_passed": row["observed_r_squared"]
            >= contract["gates"]["observed_r_squared_minimum"],
        }
        for row in factors
    }
    hold_factors = {
        pose: {
            "maximum_absolute_drift_degrees": float(
                value["hold"]["maximum_absolute_drift_degrees"]
            ),
            "passed": bool(value["hold"]["gate_passed"]),
        }
        for pose, value in mapping["fit_poses"].items()
    }
    heldout = {
        "status": mapping["heldout"]["status"],
        "passed": bool(mapping["fresh_m_hold_gate_passed"]),
        "mapping_score": mapping["heldout"]["mapping_score"],
        "untouched_composite_available": False,
    }
    rank_passed = rank == len(joint_order)
    factor_gates_passed = all(
        all(checks.values()) for checks in factor_checks.values()
    )
    mapping_approved = (
        rank_passed
        and condition <= contract["gates"]["condition_number_maximum"]
        and factor_gates_passed
        and all(row["passed"] for row in hold_factors.values())
        and heldout["passed"]
        and heldout["untouched_composite_available"]
    )
    receipt = {
        "schema_version": "sim2claw.calibration_graph_receipt.v1",
        "status": (
            "physical_model_mapping_approved"
            if mapping_approved
            else "physical_model_mapping_rejected"
        ),
        "proof_class": "gauge_fixed_existing_evidence_mapping_diagnostic",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "gauge": {
            "fixed_camera_board": True,
            "fixed_robot_to_board_rigid_transform": True,
            "fixed_joint_signs_and_zero_offsets": True,
            "fixed_jaw_reference": True,
            "active_variables": [
                f"joint_scale:{name}" for name in joint_order
            ],
        },
        "variable_estimates": {
            "joint_scales": estimates,
            "fixed_variables": contract["variables"]["fixed"],
        },
        "factor_residuals": factors,
        "factor_checks": factor_checks,
        "hold_factors": hold_factors,
        "jacobian": {
            "shape": list(jacobian.shape),
            "rank": rank,
            "required_rank": len(joint_order),
            "singular_values": singular_values.tolist(),
            "condition_number": condition,
            "correlation_matrix": correlation.tolist(),
        },
        "bounds": {
            "joint_scale": [scale_low, scale_high],
        },
        "heldout": heldout,
        "physical_model_mapping_approved": mapping_approved,
        "rejection_reasons": [
            reason
            for reason, failed in (
                ("active_jacobian_rank", not rank_passed),
                (
                    "active_jacobian_condition",
                    condition
                    > contract["gates"]["condition_number_maximum"],
                ),
                ("differential_factor_gates", not factor_gates_passed),
                (
                    "encoder_hold_gates",
                    not all(row["passed"] for row in hold_factors.values()),
                ),
                ("untouched_composite_heldout_missing", not heldout["passed"]),
            )
            if failed
        ],
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    output_directory.mkdir(parents=True)
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["CalibrationGraphError", "evaluate"]
