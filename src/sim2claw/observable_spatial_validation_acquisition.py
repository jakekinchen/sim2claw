"""Freeze and audit the post-service spatial-validation acquisition seam."""

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
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_spatial_validation_acquisition_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_spatial_validation_acquisition_readiness.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "acquisition"
    / "observable_spatial_validation_acquisition_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_spatial_validation_acquisition_v1"
    / "readiness.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_source(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        f"{label} path escaped repository",
    )
    path = (root / relative).resolve()
    _require(path.is_file(), f"{label} source is missing")
    _require(
        sha256_file(path) == binding.get("sha256"),
        f"{label} source hash changed",
    )
    return path


def load_spatial_validation_acquisition_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(
        path, label="observable spatial validation acquisition"
    )
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status") == "frozen_before_post_service_inputs",
        "contract status widened",
    )
    for source_id, binding in contract.get("sources", {}).items():
        _require(isinstance(binding, dict), f"invalid source {source_id}")
        _bound_source(binding, root=root, label=source_id)

    authority = contract.get("authority")
    _require(
        isinstance(authority, dict)
        and authority
        and not any(authority.values()),
        "contract grants authority",
    )
    policy = contract.get("successor_binding_policy")
    _require(
        isinstance(policy, dict)
        and policy.get("this_contract_may_be_edited_after_freeze") is False
        and policy.get("versioned_successor_required_to_bind_external_inputs")
        is True
        and all(
            policy.get(field) is False
            for field in (
                "route_or_action_compilation_allowed_by_this_contract",
                "camera_open_allowed_by_this_contract",
                "gateway_construction_allowed_by_this_contract",
                "physical_motion_allowed_by_this_contract",
                "validation_open_allowed_by_this_contract",
            )
        ),
        "successor binding policy widened",
    )
    return contract


def evaluate_spatial_validation_acquisition(
    contract: dict[str, Any],
    *,
    contract_sha256: str | None = None,
) -> dict[str, Any]:
    design = contract["pose_design"]
    targets = design["targets"]
    values = np.asarray(
        [target["physical_degrees_percent"] for target in targets],
        dtype=np.float64,
    )
    pan_interval = design["design_envelope"]["shoulder_pan_degrees"]
    lift_interval = design["design_envelope"]["shoulder_lift_degrees"]
    target_ids = [str(target["target_id"]) for target in targets]
    opaque_ids = [str(target["opaque_id"]) for target in targets]
    prohibited_ids = set(design["prohibited_prior_target_ids"])
    fixed = design["fixed_values"]

    pan_span = float(np.ptp(values[:, 0])) if values.shape == (4, 6) else 0.0
    lift_span = float(np.ptp(values[:, 1])) if values.shape == (4, 6) else 0.0
    design_gates = {
        "exactly_four_validation_targets": values.shape == (4, 6),
        "finite_joint_values": bool(np.all(np.isfinite(values))),
        "unique_target_ids": len(set(target_ids)) == 4,
        "unique_opaque_ids": len(set(opaque_ids)) == 4,
        "no_prior_target_id_reuse": prohibited_ids.isdisjoint(target_ids),
        "pan_span": pan_span
        >= float(design["minimum_shoulder_pan_span_degrees"]),
        "lift_span": lift_span
        >= float(design["minimum_shoulder_lift_span_degrees"]),
        "inside_declared_pan_envelope": bool(
            np.all(values[:, 0] >= float(pan_interval[0]))
            and np.all(values[:, 0] <= float(pan_interval[1]))
        ),
        "inside_declared_lift_envelope": bool(
            np.all(values[:, 1] >= float(lift_interval[0]))
            and np.all(values[:, 1] <= float(lift_interval[1]))
        ),
        "fixed_elbow": bool(
            np.all(values[:, 2] == float(fixed["elbow_flex_degrees"]))
        ),
        "fixed_wrist_flex": bool(
            np.all(values[:, 3] == float(fixed["wrist_flex_degrees"]))
        ),
        "fixed_wrist_roll": bool(
            np.all(values[:, 4] == float(fixed["wrist_roll_degrees"]))
        ),
        "fixed_gripper": bool(
            np.all(values[:, 5] == float(fixed["gripper_percent"]))
        ),
        "fresh_validation_only": (
            contract["role_separation"][
                "all_four_new_targets_are_validation_only"
            ]
            is True
            and contract["role_separation"][
                "candidate_must_be_frozen_before_any_validation_image_open"
            ]
            is True
            and contract["mission_scope"]["validation_images_opened"] is False
        ),
        "no_prior_evidence_reuse": (
            design["prior_images_annotations_outcomes_and_action_arrays_reused"]
            is False
        ),
        "no_hardware_authority": not any(contract["authority"].values()),
    }
    _require(all(design_gates.values()), "frozen acquisition design failed")

    external = contract["required_external_inputs"]
    missing = [
        input_id for input_id, binding in external.items() if binding is None
    ]
    _require(
        len(missing) == len(external),
        "v1 contract must remain frozen before all external inputs",
    )
    result = "BLOCKED_REQUIRED_EXTERNAL_INPUTS"
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "transaction_id": contract["transaction_id"],
        "contract_sha256": contract_sha256 or sha256_file(CONTRACT_PATH),
        "proof_class": contract["proof_class"],
        "status": result,
        "design_ready": True,
        "capture_ready": False,
        "pose_design": {
            "target_count": len(targets),
            "target_ids": target_ids,
            "opaque_ids": opaque_ids,
            "shoulder_pan_span_degrees": pan_span,
            "shoulder_lift_span_degrees": lift_span,
            "both_distal_jaw_endpoints_visible_required": contract[
                "camera_contract"
            ]["both_distal_jaw_endpoints_visible_required"],
            "d405_depth_required": contract["camera_contract"][
                "d405_depth_required"
            ],
        },
        "design_gates": design_gates,
        "missing_external_inputs": missing,
        "next_version_requirement": (
            "After elbow service and fresh authority, bind fresh torque-off "
            "identity/limits and a CPU/fp64 collision-camera route review in "
            "a versioned successor before compiling any action or opening a "
            "validation image."
        ),
        "actions_compiled": False,
        "camera_opened": False,
        "gateway_constructed": False,
        "physical_motion": False,
        "validation_images_opened": False,
        "fit_parameter_values_produced": False,
        "counted_physical_attempts": 0,
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_spatial_validation_acquisition_readiness(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_spatial_validation_acquisition_contract(
        contract_path, root=root
    )
    receipt = evaluate_spatial_validation_acquisition(
        contract,
        contract_sha256=sha256_file(contract_path),
    )
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_spatial_validation_acquisition_readiness",
    "evaluate_spatial_validation_acquisition",
    "load_spatial_validation_acquisition_contract",
]
