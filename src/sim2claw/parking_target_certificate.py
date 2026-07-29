"""Prospective static certificate for an elbow parking recovery target."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import directional_displacement_static as _directional
from .paths import REPO_ROOT


class ParkingTargetCertificateError(RuntimeError):
    """The parking-target certificate widened scope or failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ParkingTargetCertificateError(
            "parking-target input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise ParkingTargetCertificateError(
            f"bound parking-target input changed: {path}"
        )
    return path


def _materialize_angle_contract(
    template: Mapping[str, Any],
    *,
    angle_degrees: float,
    output_directory: Path,
) -> dict[str, Any]:
    """Change only the prospective elbow lock and derived evidence identity."""

    materialized = copy.deepcopy(dict(template))
    seed = list(materialized["live_seed"]["follower_position_degrees"])
    seed[2] = float(angle_degrees)
    angle_label = str(angle_degrees).replace(".", "p")
    materialized["contract_id"] = (
        f"parking-target-certificate-{angle_label}-20260729-v1"
    )
    materialized["proof_class"] = (
        "prospective_cpu_fp64_parking_angle_directional_displacement_static"
    )
    materialized["live_seed"] = {
        "source": "prospective_rp00_parking_angle_grid",
        "follower_position_degrees": seed,
        "locked_joint_name": "elbow_flex",
        "locked_joint_index": 2,
        "locked_value_degrees": float(angle_degrees),
    }
    materialized["output_directory"] = str(
        output_directory.relative_to(REPO_ROOT)
    )
    materialized["claim_boundary"] = (
        "RP00 static-only route-level certificate at a prospectively frozen "
        "elbow lock. All CC03K gates remain unchanged. This cannot authorize "
        "dynamic replay, mapping approval, cameras, gateway, serial, physical "
        "motion, pawn contact, a task attempt, or transfer."
    )
    return materialized


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the frozen six-angle route-level certificate exactly once."""

    if output_directory.exists():
        raise ParkingTargetCertificateError(
            "immutable parking-target output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "fable_recovery_review",
        "predecessor_contract",
        "predecessor_receipt",
        "predecessor_closeout",
        "implementation",
        "lock_angle_grid_degrees",
        "selection",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    expected_authority = {
        "model_loading": True,
        "static_simulation": True,
        "dynamic_simulation": False,
        "mapping_approval": False,
        "camera": False,
        "gateway": False,
        "serial": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "simulator_promotion": False,
        "transfer_claim": False,
    }
    expected_grid = [97.0, 95.0, 93.0, 91.0, 90.0, 88.0]
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.parking_target_certificate.v1"
        or contract.get("status")
        != "frozen_before_one_static_route_level_enumeration"
        or contract.get("lock_angle_grid_degrees") != expected_grid
        or contract.get("authority") != expected_authority
        or contract.get("selection")
        != {
            "minimum_distinct_families_per_direction": 1,
            "maximum_viable_lock_angle_is_threshold": True,
            "recommended_target_requires_at_least_2deg_lower_passing_angle": True,
            "dynamic_outcome_used": False,
            "physical_outcome_used": False,
            "grid_expansion_after_run": False,
        }
    ):
        raise ParkingTargetCertificateError(
            "parking-target contract widened or changed"
        )
    for key in (
        "fable_recovery_review",
        "predecessor_contract",
        "predecessor_receipt",
        "predecessor_closeout",
        "implementation",
    ):
        _bound(contract[key])

    template_path = _bound(contract["predecessor_contract"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    predecessor_receipt = json.loads(
        _bound(contract["predecessor_receipt"]).read_text(encoding="utf-8")
    )
    if (
        predecessor_receipt.get("passed") is not False
        or predecessor_receipt.get("elbow_lock", {}).get(
            "physical_value_degrees"
        )
        != 99.47252747252747
        or predecessor_receipt.get("statically_eligible_family_count") != 0
    ):
        raise ParkingTargetCertificateError(
            "CC03K predecessor is not the immutable terminal negative"
        )

    output_directory.mkdir(parents=True, exist_ok=False)
    angle_results: list[dict[str, Any]] = []
    evaluations_directory = REPO_ROOT / "configs/evaluations"
    for angle in expected_grid:
        angle_label = str(angle).replace(".", "p")
        angle_output = output_directory / f"elbow_{angle_label}_degrees"
        materialized = _materialize_angle_contract(
            template,
            angle_degrees=angle,
            output_directory=angle_output,
        )
        materialized_bytes = (
            json.dumps(materialized, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        materialized_sha = hashlib.sha256(materialized_bytes).hexdigest()
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".json",
                prefix="parking-target-angle-",
                dir=evaluations_directory,
                delete=False,
            ) as handle:
                handle.write(materialized_bytes)
                temporary_path = Path(handle.name)
            angle_receipt = _directional.enumerate_and_freeze(
                temporary_path.resolve(), angle_output.resolve()
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        materialized_path = angle_output / "materialized_contract.json"
        materialized_path.write_bytes(materialized_bytes)
        angle_receipt["contract_path"] = str(
            materialized_path.relative_to(REPO_ROOT)
        )
        angle_receipt["contract_sha256"] = materialized_sha
        (angle_output / "receipt.json").write_text(
            json.dumps(angle_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        angle_results.append(
            {
                "lock_angle_degrees": angle,
                "passed": bool(angle_receipt["passed"]),
                "family_count": int(angle_receipt["family_count"]),
                "grid_result_count": int(angle_receipt["grid_result_count"]),
                "statically_eligible_family_count": int(
                    angle_receipt["statically_eligible_family_count"]
                ),
                "direction_counts": angle_receipt["direction_counts"],
                "selected": angle_receipt["selected"],
                "receipt_path": str(
                    (angle_output / "receipt.json").relative_to(REPO_ROOT)
                ),
                "receipt_sha256": _sha(angle_output / "receipt.json"),
                "materialized_contract_path": str(
                    materialized_path.relative_to(REPO_ROOT)
                ),
                "materialized_contract_sha256": materialized_sha,
            }
        )

    viable = [row for row in angle_results if row["passed"]]
    maximum_viable = (
        float(viable[0]["lock_angle_degrees"]) if viable else None
    )
    recommended = None
    if maximum_viable is not None:
        for row in viable[1:]:
            candidate = float(row["lock_angle_degrees"])
            if maximum_viable - candidate >= 2.0:
                recommended = candidate
                break
    passed = bool(maximum_viable is not None and recommended is not None)
    receipt = {
        "schema_version": "sim2claw.parking_target_certificate_receipt.v1",
        "status": (
            "parking_target_certificate_pass"
            if passed
            else "parking_target_certificate_reject"
        ),
        "proof_class": (
            "cpu_fp64_static_route_level_parking_target_certificate"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "predecessor_cc03k_receipt_sha256": contract[
            "predecessor_receipt"
        ]["sha256"],
        "lock_angle_grid_degrees": expected_grid,
        "angle_results": angle_results,
        "maximum_viable_lock_angle_degrees": maximum_viable,
        "recommended_parking_lock_angle_degrees": recommended,
        "recommended_margin_degrees": (
            maximum_viable - recommended
            if maximum_viable is not None and recommended is not None
            else None
        ),
        "passed": passed,
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "ParkingTargetCertificateError",
    "_materialize_angle_contract",
    "enumerate_and_freeze",
]
