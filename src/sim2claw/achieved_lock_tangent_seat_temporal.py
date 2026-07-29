"""Dynamic adapter for the exact RP03D tangent-seat action tensors."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import achieved_lock_cartesian_corridor_temporal as _corridor
from .paths import REPO_ROOT


class TangentSeatTemporalError(RuntimeError):
    """The RP03D dynamic contract or bound evidence changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise TangentSeatTemporalError(
            "RP03D temporal input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise TangentSeatTemporalError(
            f"RP03D temporal input changed: {path}"
        )
    return path


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def replay(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    """Run the exact 20-episode RP03D gate through the frozen evaluator."""

    if output_directory.exists():
        raise TangentSeatTemporalError(
            "immutable RP03D temporal output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_temporal_contract",
        "static_contract",
        "static_receipt",
        "static_closeout",
        "corridor_temporal_implementation",
        "implementation",
        "cases",
        "live_seed",
        "outer_materialization_directory",
        "inner_materialization_directory",
        "output_directory",
        "unchanged",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.achieved_lock_tangent_seat_temporal.v1"
        or contract.get("status")
        != "frozen_after_rp03d_static_pass_before_dynamic_replay"
        or len(contract.get("cases", [])) != 2
        or {case["direction"] for case in contract["cases"]}
        != {"REAL_TO_SIM", "SIM_TO_REAL"}
        or not all(contract["unchanged"].values())
    ):
        raise TangentSeatTemporalError(
            "RP03D temporal contract widened"
        )
    _bound(contract["base_temporal_contract"])
    _bound(contract["static_contract"])
    static_receipt_path = _bound(contract["static_receipt"])
    _bound(contract["static_closeout"])
    corridor_implementation = _bound(
        contract["corridor_temporal_implementation"]
    )
    _bound(contract["implementation"])
    static = json.loads(
        static_receipt_path.read_text(encoding="utf-8")
    )
    if (
        static.get("status")
        != "parking_recovery_rp03d_tangent_seat_static_pass"
        or static.get("passed") is not True
        or static.get("direction_counts")
        != {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
        or static.get("statically_eligible_family_count") != 2
        or static.get("physical_task_attempts") != 0
    ):
        raise TangentSeatTemporalError("RP03D static admission changed")
    static_by_id = {row["case_id"]: row for row in static["selected"]}
    for case in contract["cases"]:
        frozen = static_by_id.get(case["case_id"])
        if frozen is None or any(
            case[key] != frozen[key]
            for key in (
                "direction",
                "action_path",
                "action_sha256",
                "action_shape",
            )
        ):
            raise TangentSeatTemporalError(
                "RP03D dynamic action bytes changed"
            )

    materialization = (
        REPO_ROOT / contract["outer_materialization_directory"]
    ).resolve()
    if materialization.exists():
        raise TangentSeatTemporalError(
            "immutable RP03D outer materialization already exists"
        )
    materialization.mkdir(parents=True)
    normalized_static = copy.deepcopy(static)
    normalized_static["status"] = (
        "parking_recovery_rp03c_cartesian_corridor_static_pass"
    )
    normalized_static_path = (
        materialization / "normalized_static_receipt.json"
    )
    _write_json(normalized_static_path, normalized_static)

    materialized_contract = {
        "schema_version": (
            "sim2claw.achieved_lock_cartesian_corridor_temporal.v1"
        ),
        "contract_id": (
            "rp03d-tangent-seat-temporal-materialized-20260729-v1"
        ),
        "status": (
            "frozen_after_rp03c_static_pass_before_dynamic_replay"
        ),
        "proof_class": contract["proof_class"],
        "base_temporal_contract": contract["base_temporal_contract"],
        "static_contract": contract["static_contract"],
        "static_receipt": {
            "path": str(normalized_static_path.relative_to(REPO_ROOT)),
            "sha256": _sha(normalized_static_path),
        },
        "static_closeout": contract["static_closeout"],
        "base_temporal_implementation": {
            "path": "src/sim2claw/achieved_lock_task_temporal.py",
            "sha256": (
                "49e80b36a9dc71e07e68e0bffaf6df47e3e97a1088a74415309cd87c2fcb45f1"
            ),
        },
        "implementation": {
            "path": str(corridor_implementation.relative_to(REPO_ROOT)),
            "sha256": _sha(corridor_implementation),
        },
        "cases": contract["cases"],
        "live_seed": contract["live_seed"],
        "materialization_directory": contract[
            "inner_materialization_directory"
        ],
        "output_directory": contract["output_directory"],
        "unchanged": contract["unchanged"],
        "claim_boundary": contract["claim_boundary"],
    }
    materialized_contract_path = (
        materialization / "materialized_outer_contract.json"
    )
    _write_json(materialized_contract_path, materialized_contract)
    receipt = _corridor.replay(
        materialized_contract_path, output_directory
    )
    passed = bool(
        receipt["passed"]
        and receipt["episode_count"] == 20
        and receipt["direction_counts"]
        == {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
    )
    receipt.update(
        {
            "schema_version": (
                "sim2claw.achieved_lock_"
                "tangent_seat_temporal_receipt.v1"
            ),
            "status": (
                "achieved_lock_tangent_seat_temporal_pass"
                if passed
                else "achieved_lock_tangent_seat_temporal_reject"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "static_receipt_sha256": contract["static_receipt"]["sha256"],
            "outer_materialized_contract": {
                "path": str(
                    materialized_contract_path.relative_to(REPO_ROOT)
                ),
                "sha256": _sha(materialized_contract_path),
            },
            "passed": passed,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "claim_boundary": contract["claim_boundary"],
        }
    )
    _write_json(output_directory / "receipt.json", receipt)
    return receipt


__all__ = ["TangentSeatTemporalError", "replay"]
