#!/usr/bin/env python3
"""Fit a bounded three-joint deadband candidate on exact geometric traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import load_servo_load_bias_contract
from sim2claw.pawn_bg_timing_ablation import (
    _episode_metrics,
    _mapped_episode,
    _pool,
    _strip_arrays,
    _timestamp_aligned_zoh,
)
from tools.evaluate_geometric_micro_actuator_response import _stage_payload


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_deadband_fit_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_deadband_fit.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_joint_deadband_fit_receipt.v1"


class GeometricJointDeadbandFitError(RuntimeError):
    """The frozen fit inventory or proof boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointDeadbandFitError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricJointDeadbandFitError(f"cannot read {path}: {error}") from error
    _require(isinstance(value, dict), f"JSON source is not an object: {path}")
    return value


def _bound_path(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source path escaped the repository",
    )
    path = REPO_ROOT / relative
    _require(
        path.is_file() and sha256_file(path) == binding.get("sha256"),
        f"hash-bound source changed: {relative}",
    )
    return path


def _relative_improvement(candidate: float, baseline: float) -> float:
    _require(baseline > 0.0, "baseline metric must be positive")
    return float((baseline - candidate) / baseline)


def fit(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path,
) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = _load_json(contract_path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == "retrospective_bounded_fit_for_prospective_validation",
        "fit status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "fit authority widened",
    )
    stages = (contract.get("sources") or {}).get("stages") or []
    _require(len(stages) == 3, "fit requires exactly three executed stages")

    selection_path = _bound_path(contract["sources"]["selection_receipt"])
    selection = _load_json(selection_path)
    digest_payload = dict(selection)
    observed_digest = digest_payload.pop("receipt_digest", None)
    _require(
        observed_digest
        == contract["sources"]["selection_receipt"]["receipt_digest"]
        == canonical_digest(digest_payload),
        "selection receipt digest changed",
    )
    workcell = _workcell_candidate(selection)
    experiment_path = _bound_path(contract["sources"]["mechanism_contract"])
    experiment = load_servo_load_bias_contract(experiment_path)

    mapped_stages: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for source in stages:
        packet = _load_json(_bound_path(source["packet"]))
        episode, loaded = _stage_payload(source, packet)
        mapped_stages.append(
            (
                int(source["fit_stage_index"]),
                _mapped_episode(loaded["payload"], workcell),
                loaded["source"],
            )
        )

    per_variant: dict[str, list[dict[str, Any]]] = {
        name: [] for name in contract["variants"]
    }
    stage_rows: list[dict[str, Any]] = []
    for fit_stage_index, mapped, source in mapped_stages:
        variants: dict[str, Any] = {}
        for name, deadband in contract["variants"].items():
            states, schedule = _timestamp_aligned_zoh(
                mapped,
                workcell,
                settle_steps=int(
                    experiment["candidate_grid"]["initial_settle_steps"]
                ),
                delay_seconds=float(
                    experiment["source"]["required_application_delay_seconds"]
                ),
                servo_deadband_degrees={
                    key: float(value) for key, value in deadband.items()
                },
            )
            metrics = _episode_metrics(mapped, states, workcell, experiment)
            per_variant[name].append(metrics)
            variants[name] = {
                "deadband_degrees": deadband,
                "schedule_sha256": schedule["sha256"],
                "metrics": _strip_arrays(metrics),
            }
        stage_rows.append(
            {
                "fit_stage_index": fit_stage_index,
                "source": source,
                "mapped_action_receipt": mapped["action_receipt"],
                "variants": variants,
            }
        )

    pooled = {name: _pool(rows) for name, rows in per_variant.items()}
    rigid = pooled["rigid"]
    prior = pooled["prior_lift_elbow_deadband"]
    comparisons: dict[str, Any] = {}
    for name, metrics in pooled.items():
        comparisons[name] = {
            "joint_rms_relative_improvement_vs_rigid": _relative_improvement(
                metrics["overall_joint_rms_degrees"],
                rigid["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement_vs_rigid": _relative_improvement(
                metrics["ee_rms_m"], rigid["ee_rms_m"]
            ),
            "joint_rms_relative_improvement_vs_prior": _relative_improvement(
                metrics["overall_joint_rms_degrees"],
                prior["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement_vs_prior": _relative_improvement(
                metrics["ee_rms_m"], prior["ee_rms_m"]
            ),
        }

    eligible = [
        name
        for name, metrics in pooled.items()
        if name not in {"rigid", "prior_lift_elbow_deadband"}
        and metrics["overall_joint_rms_degrees"]
        < prior["overall_joint_rms_degrees"]
        and metrics["ee_rms_m"] < prior["ee_rms_m"]
    ]
    _require(eligible, "no bounded candidate improves both metrics over prior")
    selected_name = min(
        eligible,
        key=lambda name: (
            pooled[name]["overall_joint_rms_degrees"],
            pooled[name]["ee_rms_m"],
            name,
        ),
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "fit_id": contract["fit_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "stage_count": len(stage_rows),
        "stages": stage_rows,
        "pooled": pooled,
        "comparisons": comparisons,
        "selection_rule": contract["selection_rule"],
        "eligible_variants": eligible,
        "selected_variant": selected_name,
        "selected_deadband_degrees": contract["variants"][selected_name],
        "parameter_fitting_performed": True,
        "parameters_promoted": False,
        "action_correction_performed": False,
        "held_out_physical_validation_required": True,
        "pawn_contact_admitted": False,
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_path.resolve(), receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            fit(contract_path=args.contract, output_path=args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
