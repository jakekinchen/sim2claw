"""Screen task geometry at a bounded physically informed elbow-lock grid."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import directional_displacement_static as _directional
from .paths import REPO_ROOT


class ReachableLockTaskCertificateError(RuntimeError):
    """The RP04D task-lock screen changed or widened."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReachableLockTaskCertificateError(message)


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ReachableLockTaskCertificateError(
            "reachable-lock input escapes repository"
        ) from error
    _require(path.is_file(), f"reachable-lock input missing: {path}")
    _require(
        _sha(path) == entry["sha256"],
        f"reachable-lock input changed: {path}",
    )
    return path


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _materialize(
    template: Mapping[str, Any],
    *,
    lock_degrees: float,
    base_seed: list[float],
    output_directory: Path,
    claim_boundary: str,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(template))
    seed = list(base_seed)
    seed[2] = lock_degrees
    label = str(lock_degrees).replace(".", "p")
    result["contract_id"] = f"reachable-lock-{label}-20260729-v1"
    result["live_seed"] = {
        "source": "rp04d_prospective_reachable_elbow_lock_grid",
        "follower_position_degrees": seed,
        "locked_joint_name": "elbow_flex",
        "locked_joint_index": 2,
        "locked_value_degrees": lock_degrees,
    }
    result["output_directory"] = _display_path(output_directory)
    result["claim_boundary"] = claim_boundary
    return result


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the three-lock static task screen exactly once."""

    _require(
        not output_directory.exists(),
        "immutable reachable-lock output already exists",
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.reachable_lock_task_certificate.v1",
        "unexpected reachable-lock schema",
    )
    expected_grid = [85.0, 80.0, 77.5]
    _require(
        contract["lock_grid_degrees"] == expected_grid
        and contract["selection"]
        == {
            "preferred_lock_degrees": 80.0,
            "preferred_lock_requires_static_pass": True,
            "minimum_distinct_families_per_direction": 1,
            "dynamic_outcomes_used": False,
            "physical_task_outcomes_used": False,
            "grid_expansion_after_run": False,
        },
        "reachable-lock grid or selection changed",
    )
    _require(
        contract["authority"]
        == {
            "model_loading": True,
            "static_simulation": True,
            "dynamic_simulation": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "transfer_claim": False,
        },
        "reachable-lock authority changed",
    )
    for entry in contract["inputs"].values():
        _bound(entry)
    physical_closeout = json.loads(
        _bound(contract["inputs"]["physical_closeout"]).read_text(
            encoding="utf-8"
        )
    )
    _require(
        physical_closeout["status"]
        == "reachable_elbow_floor_identified_task_lock_screen_admitted"
        and physical_closeout["result"]["minimum_observed_elbow_degrees"]
        == 77.4065934065934
        and physical_closeout["result"]["physical_task_attempts"] == 0,
        "reachable physical floor changed",
    )
    template = json.loads(
        _bound(contract["inputs"]["template_contract"]).read_text(
            encoding="utf-8"
        )
    )
    base_seed = list(contract["base_seed_degrees_percent"])
    output_directory.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    for lock in expected_grid:
        label = str(lock).replace(".", "p")
        angle_output = output_directory / f"elbow_{label}_degrees"
        materialized = _materialize(
            template,
            lock_degrees=lock,
            base_seed=base_seed,
            output_directory=angle_output,
            claim_boundary=contract["claim_boundary"],
        )
        materialized_bytes = (
            json.dumps(materialized, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".json",
                prefix="reachable-lock-",
                dir=contract_path.parent,
                delete=False,
            ) as handle:
                handle.write(materialized_bytes)
                temporary_path = Path(handle.name)
            receipt = _directional.enumerate_and_freeze(
                temporary_path.resolve(), angle_output.resolve()
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        materialized_path = angle_output / "materialized_contract.json"
        materialized_path.write_bytes(materialized_bytes)
        receipt["contract_path"] = _display_path(materialized_path)
        receipt["contract_sha256"] = hashlib.sha256(
            materialized_bytes
        ).hexdigest()
        (angle_output / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        results.append(
            {
                "lock_degrees": lock,
                "passed": bool(receipt["passed"]),
                "statically_eligible_family_count": int(
                    receipt["statically_eligible_family_count"]
                ),
                "direction_counts": receipt["direction_counts"],
                "selected": receipt["selected"],
                "receipt_path": _display_path(
                    angle_output / "receipt.json"
                ),
                "receipt_sha256": _sha(angle_output / "receipt.json"),
            }
        )
    preferred = next(
        row
        for row in results
        if row["lock_degrees"]
        == contract["selection"]["preferred_lock_degrees"]
    )
    passed = bool(
        preferred["passed"]
        and all(
            preferred["direction_counts"].get(direction, 0) >= 1
            for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
        )
    )
    receipt = {
        "schema_version":
        "sim2claw.reachable_lock_task_certificate_receipt.v1",
        "contract_id": contract["contract_id"],
        "status": (
            "reachable_lock_task_certificate_pass"
            if passed
            else "reachable_lock_task_certificate_reject"
        ),
        "passed": passed,
        "lock_results": results,
        "preferred_lock_degrees": 80.0,
        "preferred_lock_passed": bool(preferred["passed"]),
        "preferred_selected": preferred["selected"],
        "dynamic_simulation": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "ReachableLockTaskCertificateError",
    "enumerate_and_freeze",
]
