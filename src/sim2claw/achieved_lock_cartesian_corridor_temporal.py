"""Dynamic adapter for the exact RP03C Cartesian-corridor actions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import achieved_lock_task_temporal as _base
from .paths import REPO_ROOT


class CartesianCorridorTemporalError(RuntimeError):
    """The RP03C dynamic contract or its bound evidence changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CartesianCorridorTemporalError(
            "RP03C temporal input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CartesianCorridorTemporalError(
            f"RP03C temporal input changed: {path}"
        )
    return path


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _causal_summaries(
    receipt: Mapping[str, Any],
    output_directory: Path,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for result in receipt["results"]:
        for plant in result["plant_paths"]:
            for robustness in plant["robustness"]:
                episode_path = REPO_ROOT / robustness[
                    "observable_episode"
                ]["path"]
                episode = json.loads(
                    episode_path.read_text(encoding="utf-8")
                )
                first_failed_gate = next(
                    (
                        name
                        for name, passed in robustness["checks"].items()
                        if not passed
                    ),
                    None,
                )
                summary = {
                    "schema_version": (
                        "sim2claw.rp03c_causal_summary.v1"
                    ),
                    "case_id": result["case_id"],
                    "direction": result["direction"],
                    "plant_path_id": plant["path_id"],
                    "variant_id": robustness["variant_id"],
                    "first_selected_contact_row_or_missing": episode[
                        "events"
                    ]["first_contact_sample_or_missing"],
                    "first_object_motion_row_or_missing": episode["events"][
                        "first_object_motion_sample_or_missing"
                    ],
                    "final_signed_progress_mm": robustness[
                        "signed_progress_mm"
                    ],
                    "maximum_selected_vertical_rise_mm": robustness[
                        "maximum_selected_vertical_rise_mm"
                    ],
                    "selected_contact_steps": robustness[
                        "selected_contact_steps"
                    ],
                    "maximum_excluded_displacement_mm": robustness[
                        "maximum_excluded_displacement_mm"
                    ],
                    "first_gate_failure_or_missing": first_failed_gate,
                    "requested_mapped_sent_applied_hashes": episode["action"],
                    "task_outcome": episode["events"][
                        "final_task_outcome_or_missing"
                    ],
                }
                path = (
                    output_directory
                    / "causal-summaries"
                    / result["case_id"]
                    / plant["path_id"]
                    / f"{robustness['variant_id']}.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                _write_json(path, summary)
                summaries.append(
                    {
                        "path": str(path.relative_to(REPO_ROOT)),
                        "sha256": _sha(path),
                        "case_id": result["case_id"],
                        "direction": result["direction"],
                        "plant_path_id": plant["path_id"],
                        "variant_id": robustness["variant_id"],
                    }
                )
    return summaries


def replay(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    """Run the exact two-direction, two-plant, five-reset RP03C gate."""

    if output_directory.exists():
        raise CartesianCorridorTemporalError(
            "immutable RP03C temporal output already exists"
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
        "base_temporal_implementation",
        "implementation",
        "cases",
        "live_seed",
        "materialization_directory",
        "output_directory",
        "unchanged",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.achieved_lock_cartesian_corridor_temporal.v1"
        or contract.get("status")
        != "frozen_after_rp03c_static_pass_before_dynamic_replay"
        or len(contract.get("cases", [])) != 2
        or {case["direction"] for case in contract["cases"]}
        != {"REAL_TO_SIM", "SIM_TO_REAL"}
        or not all(contract["unchanged"].values())
    ):
        raise CartesianCorridorTemporalError(
            "RP03C temporal contract widened"
        )
    base_temporal_path = _bound(contract["base_temporal_contract"])
    _bound(contract["static_contract"])
    static_receipt_path = _bound(contract["static_receipt"])
    _bound(contract["static_closeout"])
    base_implementation_path = _bound(
        contract["base_temporal_implementation"]
    )
    _bound(contract["implementation"])
    static = json.loads(
        static_receipt_path.read_text(encoding="utf-8")
    )
    if (
        static.get("status")
        != "parking_recovery_rp03c_cartesian_corridor_static_pass"
        or static.get("passed") is not True
        or static.get("direction_counts")
        != {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
        or static.get("statically_eligible_family_count") != 2
        or static.get("physical_task_attempts") != 0
    ):
        raise CartesianCorridorTemporalError(
            "RP03C static admission changed"
        )
    static_by_id = {row["case_id"]: row for row in static["selected"]}
    if set(static_by_id) != {
        case["case_id"] for case in contract["cases"]
    }:
        raise CartesianCorridorTemporalError(
            "RP03C dynamic cases changed from static freeze"
        )
    for case in contract["cases"]:
        frozen = static_by_id[case["case_id"]]
        if (
            case["direction"] != frozen["direction"]
            or case["action_sha256"] != frozen["action_sha256"]
            or case["action_shape"] != frozen["action_shape"]
            or case["action_path"] != frozen["action_path"]
        ):
            raise CartesianCorridorTemporalError(
                "RP03C dynamic action bytes changed"
            )

    materialization = (
        REPO_ROOT / contract["materialization_directory"]
    ).resolve()
    if materialization.exists():
        raise CartesianCorridorTemporalError(
            "immutable RP03C materialization already exists"
        )
    materialization.mkdir(parents=True)
    normalized_static = copy.deepcopy(static)
    normalized_static["status"] = "achieved_lock_task_freeze_pass"
    normalized_static_path = (
        materialization / "normalized_static_receipt.json"
    )
    _write_json(normalized_static_path, normalized_static)
    materialized_contract = {
        "schema_version": "sim2claw.achieved_lock_task_temporal.v1",
        "contract_id": (
            "rp03c-cartesian-corridor-temporal-materialized-20260729-v1"
        ),
        "status": (
            "frozen_after_exact_achieved_lock_static_pass_before_dynamic_replay"
        ),
        "proof_class": contract["proof_class"],
        "base_temporal_contract": contract["base_temporal_contract"],
        "static_receipt": {
            "path": str(normalized_static_path.relative_to(REPO_ROOT)),
            "sha256": _sha(normalized_static_path),
        },
        "static_closeout": contract["static_closeout"],
        "temporal_implementation": {
            "path": str(base_implementation_path.relative_to(REPO_ROOT)),
            "sha256": _sha(base_implementation_path),
        },
        "cases": contract["cases"],
        "live_seed": contract["live_seed"],
        "output_directory": contract["output_directory"],
        "unchanged_from_base": contract["unchanged"],
        "claim_boundary": contract["claim_boundary"],
    }
    materialized_contract_path = (
        materialization / "materialized_temporal_contract.json"
    )
    _write_json(materialized_contract_path, materialized_contract)
    base_temporal = json.loads(
        base_temporal_path.read_text(encoding="utf-8")
    )
    expected_episode_count = (
        len(contract["cases"])
        * len(base_temporal["plant_paths"])
        * len(base_temporal["robustness_variants"])
    )
    if expected_episode_count != 20:
        raise CartesianCorridorTemporalError(
            "RP03C dynamic denominator changed from 20"
        )

    receipt = _base.replay(
        materialized_contract_path, output_directory
    )
    summaries = _causal_summaries(receipt, output_directory)
    observed_episode_count = sum(
        len(path["robustness"])
        for result in receipt["results"]
        for path in result["plant_paths"]
    )
    passed = bool(receipt["passed"] and observed_episode_count == 20)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.achieved_lock_"
                "cartesian_corridor_temporal_receipt.v1"
            ),
            "status": (
                "achieved_lock_cartesian_corridor_temporal_pass"
                if passed
                else "achieved_lock_cartesian_corridor_temporal_reject"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "static_receipt_sha256": contract["static_receipt"]["sha256"],
            "materialized_contract": {
                "path": str(
                    materialized_contract_path.relative_to(REPO_ROOT)
                ),
                "sha256": _sha(materialized_contract_path),
            },
            "episode_count": observed_episode_count,
            "required_episode_count": 20,
            "causal_summaries": summaries,
            "passed": passed,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "claim_boundary": contract["claim_boundary"],
        }
    )
    _write_json(output_directory / "receipt.json", receipt)
    return receipt


__all__ = ["CartesianCorridorTemporalError", "replay"]
