"""Freeze static task actions at the exact successful parking hold pose."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import directional_displacement_static as _directional
from .paths import REPO_ROOT


class AchievedLockTaskFreezeError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise AchievedLockTaskFreezeError(
            "achieved-lock input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise AchievedLockTaskFreezeError(
            f"achieved-lock input changed: {path}"
        )
    return path


def _achieved_seed(receipt: Mapping[str, Any]) -> list[float]:
    if (
        receipt.get("passed") is not True
        or receipt.get("physical_task_attempts") != 0
        or receipt.get("pawn_contact") is not False
        or receipt.get("failure") is not None
        or receipt.get("ladder", {}).get("outcome")
        != "deep_request_success"
        or receipt.get("ladder", {}).get("hold", {}).get("passed") is not True
    ):
        raise AchievedLockTaskFreezeError(
            "parking receipt is not the exact successful held result"
        )
    seed = list(receipt["gateway_open"]["setup_command_anchor_degrees"])
    seed[2] = float(receipt["ladder"]["final_elbow_degrees"])
    return seed


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise AchievedLockTaskFreezeError(
            "immutable achieved-lock output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.achieved_lock_task_freeze.v1"
        or contract.get("status")
        != "frozen_before_one_static_only_exact_lock_enumeration"
        or contract.get("authority")
        != {
            "model_loading": True,
            "static_simulation": True,
            "dynamic_simulation": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        }
    ):
        raise AchievedLockTaskFreezeError(
            "achieved-lock contract changed or widened"
        )
    for binding in contract["inputs"].values():
        _bound(binding)
    parking = json.loads(
        _bound(contract["inputs"]["parking_execution_receipt"]).read_text(
            encoding="utf-8"
        )
    )
    template = json.loads(
        _bound(contract["inputs"]["template_contract"]).read_text(
            encoding="utf-8"
        )
    )
    seed = _achieved_seed(parking)
    materialized = copy.deepcopy(template)
    materialized["contract_id"] = (
        "achieved-lock-task-freeze-20260729-v1-materialized"
    )
    materialized["live_seed"] = {
        "source": "rp02d_successful_torque_on_held_pose",
        "follower_position_degrees": seed,
        "locked_joint_name": "elbow_flex",
        "locked_joint_index": 2,
        "locked_value_degrees": seed[2],
    }
    materialized["output_directory"] = str(
        output_directory.relative_to(REPO_ROOT)
    )
    materialized["claim_boundary"] = contract["claim_boundary"]
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="achieved-lock-",
            dir=contract_path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(materialized, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_path = Path(handle.name)
        receipt = _directional.enumerate_and_freeze(
            temporary_path.resolve(), output_directory.resolve()
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    materialized_path = output_directory / "materialized_contract.json"
    materialized_path.write_text(
        json.dumps(materialized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt.update(
        {
            "schema_version": "sim2claw.achieved_lock_task_freeze_receipt.v1",
            "status": (
                "achieved_lock_task_freeze_pass"
                if receipt["passed"]
                else "achieved_lock_task_freeze_reject"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "parking_execution_receipt_sha256": contract["inputs"][
                "parking_execution_receipt"
            ]["sha256"],
            "exact_achieved_seed_degrees_percent": seed,
            "materialized_contract_path": str(
                materialized_path.relative_to(REPO_ROOT)
            ),
            "materialized_contract_sha256": _sha(materialized_path),
            "physical_motion": False,
            "physical_task_attempts": 0,
            "authority": contract["authority"],
            "claim_boundary": contract["claim_boundary"],
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "AchievedLockTaskFreezeError",
    "_achieved_seed",
    "enumerate_and_freeze",
]
