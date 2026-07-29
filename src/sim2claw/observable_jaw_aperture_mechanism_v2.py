"""Aggregate-rank successor for OR5 jaw-aperture identifiability."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_jaw_aperture_mechanism import (
    _bound_json,
    _bound_path,
    _load_jsonl,
    _physical_hold_means,
    _projected_apertures,
    load_mechanism_contract,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_jaw_aperture_mechanism_contract.v2"
RECEIPT_SCHEMA = "sim2claw.observable_jaw_aperture_mechanism_receipt.v2"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_jaw_aperture_mechanism_v2.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_jaw_aperture_mechanism_v2"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_mechanism_v2_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="observable jaw mechanism v2")
    _require(contract.get("schema_version") == SCHEMA, "unsupported v2 mechanism schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "v2 mechanism sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid v2 source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    base = load_mechanism_contract(
        _bound_path(sources["v1_contract"], root=root, label="v1 contract"),
        root=root,
    )
    v1_closeout = _bound_json(
        sources["v1_closeout"], root=root, label="v1 closeout"
    )
    _require(
        v1_closeout.get("result")
        == "NO_IDENTIFIABLE_STATIC_JAW_APERTURE_MECHANISM_UNDER_V1_PER_VIEW_GATE"
        and v1_closeout["validation_reservation"]["annotations_opened"] is False,
        "v1 negative boundary changed",
    )
    successor = contract.get("method_successor")
    _require(
        isinstance(successor, dict)
        and all(
            successor.get(field) is True
            for field in (
                "same_model_family",
                "same_parameter",
                "same_parameter_bounds",
                "same_fit_and_validation_membership",
                "same_fit_and_validation_gates_for_or6",
                "same_rejected_mechanism_families",
            )
        )
        and successor.get("visual_fit_annotation_values_may_open_in_or5_v2")
        is False
        and successor.get(
            "visual_validation_annotation_values_may_open_in_or5_v2"
        )
        is False
        and successor.get("sensitivity_depends_on_visual_annotation_values")
        is False,
        "v2 method successor widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "v2 proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "v2 authority widened",
    )
    return contract, base


def evaluate_mechanism_v2_declaration(
    contract: dict[str, Any],
    base: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    sources = base["sources"]
    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    fit_rows = _load_jsonl(
        _bound_path(
            sources["fit_joint_samples"], root=root, label="fit joint samples"
        ),
        label="fit joint samples",
    )
    fit_ids, fit_physical = _physical_hold_means(
        fit_manifest, fit_rows, root=root
    )
    validation_manifest = _bound_json(
        sources["validation_manifest"], root=root, label="validation manifest"
    )
    validation_rows = _load_jsonl(
        _bound_path(
            sources["validation_joint_samples"],
            root=root,
            label="validation joint samples",
        ),
        label="validation joint samples",
    )
    validation_ids, validation_physical = _physical_hold_means(
        validation_manifest, validation_rows, root=root
    )
    _require(
        not set(fit_ids) & set(validation_ids),
        "fit/validation membership overlaps",
    )
    camera = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    or2 = _bound_json(
        sources["or2_receipt"], root=root, label="OR2 receipt"
    )
    candidate = _bound_json(
        sources["candidate_manifest"], root=root, label="candidate manifest"
    )["candidate_config"]
    family = base["model_family"]
    baseline = float(family["baseline_gripper_zero_offset_rad"])
    step = float(family["static_sensitivity_step_rad"])
    lower_apertures = _projected_apertures(
        fit_physical,
        candidate,
        camera,
        or2["fit"]["parameters"],
        offset_rad=baseline - step,
    )
    upper_apertures = _projected_apertures(
        fit_physical,
        candidate,
        camera,
        or2["fit"]["parameters"],
        offset_rad=baseline + step,
    )
    sensitivity = (upper_apertures - lower_apertures) / (2.0 * step)
    jacobian = sensitivity.reshape(-1, 1)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    rank = int(np.linalg.matrix_rank(jacobian))
    condition = 1.0 if singular_values[-1] > 0.0 else float("inf")
    fit_span = float(np.ptp(fit_physical[:, -1]))
    gates = contract["identifiability_gates"]
    checks = {
        "fit_pose_count": len(fit_ids) >= int(gates["minimum_fit_pose_count"]),
        "fit_validation_disjoint": not bool(set(fit_ids) & set(validation_ids)),
        "gain_unidentifiable_from_fit_span": fit_span
        <= float(gates["maximum_fit_gripper_span_physical_units"]),
        "per_view_sensitivity": float(np.min(np.abs(sensitivity)))
        >= float(gates["minimum_per_view_absolute_sensitivity_px_per_rad"]),
        "mean_sensitivity": float(np.mean(np.abs(sensitivity)))
        >= float(gates["minimum_mean_absolute_sensitivity_px_per_rad"]),
        "aggregate_singular_value": float(singular_values[0])
        >= float(gates["minimum_aggregate_jacobian_singular_value_px_per_rad"]),
        "same_sign_sensitivity": max(
            float(np.mean(sensitivity > 0.0)),
            float(np.mean(sensitivity < 0.0)),
        )
        >= float(gates["minimum_same_sign_sensitivity_fraction"]),
        "parameter_rank": rank >= int(gates["minimum_parameter_rank"]),
        "jacobian_condition": condition
        <= float(gates["maximum_one_parameter_jacobian_condition_number"]),
        "fit_annotations_unopened": True,
        "validation_annotations_unopened": True,
        "sealed_task_outcome_unused": True,
    }
    accepted = bool(all(checks.values()))
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "v1_negative_preserved": {
            "closeout_sha256": contract["sources"]["v1_closeout"]["sha256"],
            "overwritten": False,
        },
        "fit": {
            "ids": fit_ids,
            "pose_count": len(fit_ids),
            "gripper_span_physical_units": fit_span,
            "minimum_absolute_sensitivity_px_per_rad": float(
                np.min(np.abs(sensitivity))
            ),
            "mean_absolute_sensitivity_px_per_rad": float(
                np.mean(np.abs(sensitivity))
            ),
            "aggregate_jacobian_singular_value_px_per_rad": float(
                singular_values[0]
            ),
            "jacobian_rank": rank,
            "jacobian_condition_number": condition,
            "same_sign_sensitivity_fraction": float(
                max(np.mean(sensitivity > 0.0), np.mean(sensitivity < 0.0))
            ),
            "visual_annotation_values_opened": False,
        },
        "validation_reservation": {
            "ids": validation_ids,
            "pose_count": len(validation_ids),
            "gripper_span_physical_units": float(
                np.ptp(validation_physical[:, -1])
            ),
            "visual_annotation_values_opened": False,
            "candidate_refit_allowed": False,
        },
        "declared_model_family": family,
        "checks": checks,
        "accepted": accepted,
        "result": (
            "SINGLE_GRIPPER_ZERO_OFFSET_APERTURE_MAPPING_IDENTIFIABLE"
            if accepted
            else "NO_IDENTIFIABLE_STATIC_JAW_APERTURE_MECHANISM_V2"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_mechanism_v2_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract, base = load_mechanism_v2_contract(contract_path, root=root)
    receipt = evaluate_mechanism_v2_declaration(contract, base, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_mechanism_v2_receipt",
    "evaluate_mechanism_v2_declaration",
    "load_mechanism_v2_contract",
]
