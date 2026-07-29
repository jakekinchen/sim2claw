"""Fail-closed identifiability gate for retrospective contact parameters."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.realized_action_contact_identifiability_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_contact_identifiability_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_contact_identifiability_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "realized_action_contact_identifiability_v1"
    / "receipt.json"
)
OBSERVABLES = (
    "per_sample_contact_state",
    "metric_object_pose_path",
    "metric_robot_or_jaw_pose_path",
    "known_contact_or_applied_force",
    "metric_contact_deformation",
    "metric_object_orientation_path",
)


def _bound(
    root: Path, entry: Mapping[str, Any], label: str
) -> tuple[Path, dict[str, Any] | None]:
    path = root / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    payload = (
        load_json_object(path, label=label) if path.suffix == ".json" else None
    )
    return path, payload


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="contact identifiability contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported contact identifiability contract")
    for key, entry in contract.get("sources", {}).items():
        _bound(root, entry, key)
    names = [row.get("name") for row in contract.get("candidate_dimensions", [])]
    if len(names) != 5 or len(set(names)) != 5:
        raise FactoryArtifactError("contact candidate dimensions changed")
    if not contract.get("forbidden_inputs"):
        raise FactoryArtifactError("contact forbidden-input list is empty")
    if not all(contract.get("rules", {}).values()):
        raise FactoryArtifactError("contact identifiability rule widened")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise FactoryArtifactError("contact identifiability authority widened")
    return contract


def _metric_vector(value: Any, minimum_size: int) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= minimum_size
        and all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in value)
    )


def observable_flags(rows: list[Mapping[str, Any]]) -> dict[str, bool]:
    pose_rows = [
        row
        for row in rows
        if _metric_vector(row.get("selected_piece_pose_world"), 3)
    ]
    orientation_rows = [
        row
        for row in rows
        if _metric_vector(row.get("selected_piece_orientation"), 4)
        or _metric_vector(row.get("selected_piece_quaternion_wxyz"), 4)
    ]
    contact_rows = [
        row
        for row in rows
        if isinstance(row.get("contact_state"), (bool, str, dict))
        or isinstance(row.get("selected_piece_contact"), bool)
    ]
    deformation_rows = [
        row
        for row in rows
        if isinstance(row.get("gripper_contact_deflection"), (int, float))
        and not isinstance(row.get("gripper_contact_deflection"), bool)
        and math.isfinite(float(row["gripper_contact_deflection"]))
    ]
    robot_pose_rows = [
        row
        for row in rows
        if _metric_vector(row.get("end_effector_pose_world"), 3)
        or _metric_vector(row.get("continuous_target_pose_world"), 3)
    ]
    force_rows = [
        row
        for row in rows
        if _metric_vector(row.get("contact_force_newtons"), 3)
        or isinstance(row.get("applied_contact_force_newtons"), (int, float))
    ]
    return {
        "per_sample_contact_state": bool(contact_rows),
        "metric_object_pose_path": len(pose_rows) >= 2,
        "metric_robot_or_jaw_pose_path": len(robot_pose_rows) >= 2,
        "known_contact_or_applied_force": bool(force_rows),
        "metric_contact_deformation": bool(deformation_rows),
        "metric_object_orientation_path": len(orientation_rows) >= 2,
    }


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read contact source rows: {error}") from error


def evaluate(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    _, bundle_receipt = _bound(
        root, contract["sources"]["episode_twin_receipt"], "episode twin receipt"
    )
    assert bundle_receipt is not None
    if bundle_receipt.get("artifact_sha256") != contract["sources"][
        "episode_twin_receipt"
    ]["artifact_sha256"]:
        raise FactoryArtifactError("episode twin artifact changed")
    episodes = []
    for entry in bundle_receipt["bundles"]:
        bundle_path = root / entry["bundle_path"]
        if not bundle_path.is_file() or sha256_file(bundle_path) != entry[
            "bundle_file_sha256"
        ]:
            raise FactoryArtifactError("contact episode bundle changed")
        bundle = load_json_object(bundle_path, label="contact episode bundle")
        samples = bundle["source"]["samples_asset"]
        sample_path = root / samples["path"]
        if not sample_path.is_file() or sha256_file(sample_path) != samples["sha256"]:
            raise FactoryArtifactError("contact source samples changed")
        rows = _rows(sample_path)
        flags = observable_flags(rows)
        episodes.append(
            {
                "recording_id": bundle["recording_id"],
                "cohort_role": bundle["cohort_role"],
                "sample_count": len(rows),
                "observable_flags": flags,
                "motor_current_present_but_not_force": any(
                    isinstance(row.get("available_motor_current_raw"), dict)
                    for row in rows
                ),
                "observed_grasp_markers_present_but_forbidden": any(
                    row.get("gripper_contact_hold") is not None
                    or row.get("gripper_contact_deflection") is not None
                    for row in rows
                ),
            }
        )
    counts = {
        role: {
            observable: sum(
                row["cohort_role"] == role
                and row["observable_flags"][observable]
                for row in episodes
            )
            for observable in OBSERVABLES
        }
        for role in ("fit", "validation", "sealed")
    }
    minimum = contract["minimum_evidence"]
    dimensions = []
    for candidate in contract["candidate_dimensions"]:
        requirements = candidate["required_nonsealed_observables"]
        missing = [
            observable
            for observable in requirements
            if counts["fit"][observable]
            < int(minimum["fit_episodes_per_required_observable"])
            or counts["validation"][observable]
            < int(minimum["validation_episodes_per_required_observable"])
        ]
        dimensions.append(
            {
                "name": candidate["name"],
                "required_nonsealed_observables": requirements,
                "missing_or_insufficient_observables": missing,
                "eligible": not missing,
            }
        )
    eligible = [row for row in dimensions if row["eligible"]]
    result = (
        "ELIGIBLE_DIMENSION_REQUIRES_SEPARATE_PROSPECTIVE_FIT"
        if eligible
        else "TERMINAL_CONTACT_MODEL_NEGATIVE_INSUFFICIENT_NONSEALED_WITNESSES"
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "result": result,
        "episode_inventory": episodes,
        "observable_episode_counts": counts,
        "candidate_dimensions": dimensions,
        "eligible_dimension_count": len(eligible),
        "parameter_fit_performed": False,
        "selected_contact_model": None,
        "baseline": {
            "name": "current_mujoco_contact_defaults",
            "status": "unvalidated_baseline_not_parameter_authority",
            "may_run_as_c6_diagnostic": True,
            "may_promote_c6_outcome": False,
        },
        "new_evidence_required": [
            "at least two fit and one validation episodes with metric object pose paths",
            "per-sample contact state tied to metric jaw or end-effector pose",
            "an untouched validation consequence for any selected contact family",
            "known applied force or calibrated force sensing for friction, compliance, damping, mass, or center-of-mass identification"
        ],
        "sealed_used_for_selection": False,
        "claim_boundary": (
            "Fail-closed contact/object identifiability audit. No nonsealed "
            "candidate dimension has the required contact, metric object path, "
            "and force observables, so no parameter or grasp abstraction is "
            "fit or promoted. Current MuJoCo contact remains an unvalidated "
            "diagnostic baseline."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
