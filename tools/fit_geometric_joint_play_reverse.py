#!/usr/bin/env python3
"""Fit only the newly observed lift and wrist reverse-play branches."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.geometric_joint_play import replay_joint_play
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import load_servo_load_bias_contract
from sim2claw.pawn_bg_timing_ablation import (
    BODY_JOINT_NAMES,
    _episode_metrics,
    _mapped_episode,
    _pool,
    _strip_arrays,
)
from tools.evaluate_geometric_micro_actuator_response import _stage_payload


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_play_reverse_fit_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_play_reverse_fit.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_joint_play_reverse_fit_receipt.v1"


class GeometricJointPlayReverseFitError(RuntimeError):
    """The bounded reverse-branch fit evidence changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayReverseFitError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricJointPlayReverseFitError(
            f"cannot read {path}: {error}"
        ) from error
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


def _candidate_grid(contract: Mapping[str, Any]) -> list[dict[str, float]]:
    grid = contract["candidate_grid_half_width_degrees"]
    rows = [
        {
            "shoulder_lift_against_load": float(lift),
            "wrist_flex_against_load": float(wrist),
        }
        for lift, wrist in itertools.product(
            grid["shoulder_lift_against_load"],
            grid["wrist_flex_against_load"],
        )
    ]
    _require(
        len(rows) == 16 and len({canonical_digest(row) for row in rows}) == 16,
        "reverse-branch grid must contain 16 unique candidates",
    )
    return rows


def _candidate_id(candidate: Mapping[str, float]) -> str:
    return "_".join(
        f"{name}{int(round(float(candidate[name]) * 1000)):04d}"
        for name in (
            "shoulder_lift_against_load",
            "wrist_flex_against_load",
        )
    )


def _expanded(
    retained: Mapping[str, float],
    candidate: Mapping[str, float],
) -> dict[str, dict[str, float]]:
    return {
        "shoulder_pan": {
            "with_load": float(retained["shoulder_pan_shared"]),
            "against_load": float(retained["shoulder_pan_shared"]),
        },
        "shoulder_lift": {
            "with_load": float(retained["shoulder_lift_with_load"]),
            "against_load": float(
                candidate["shoulder_lift_against_load"]
            ),
        },
        "elbow_flex": {
            "with_load": float(retained["elbow_flex_with_load"]),
            "against_load": float(retained["elbow_flex_against_load"]),
        },
        "wrist_flex": {
            "with_load": float(retained["wrist_flex_with_load"]),
            "against_load": float(candidate["wrist_flex_against_load"]),
        },
    }


def _objective(
    mapped: Mapping[str, Any],
    states: np.ndarray,
    *,
    selected_joints: list[str],
    delta_degrees: float,
) -> float:
    indices = [BODY_JOINT_NAMES.index(name) for name in selected_joints]
    error = np.abs(
        np.degrees(
            states[:, indices]
            - np.asarray(mapped["measured"], dtype=np.float64)[:, indices]
        )
    )
    delta = float(delta_degrees)
    huber = np.where(
        error <= delta,
        0.5 * error**2,
        delta * (error - 0.5 * delta),
    )
    return float(np.mean(np.mean(huber, axis=0)))


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
        == "bounded_refit_after_two_opened_roundtrip_failures",
        "fit status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "fit authority widened",
    )
    _require(
        contract.get("proof_boundary")
        == {
            "vertical_roundtrip_is_fit_not_validation": True,
            "lateral_roundtrip_is_fit_not_validation": True,
            "fresh_heldout_required": True,
        },
        "opened-source boundary changed",
    )

    sources = contract["sources"]
    parent_contract_path = _bound_path(sources["parent_fit_contract"])
    parent_contract = _load_json(parent_contract_path)
    parent_receipt_path = _bound_path(sources["parent_fit_receipt"])
    parent_receipt = _load_json(parent_receipt_path)
    digest_payload = dict(parent_receipt)
    observed_digest = digest_payload.pop("receipt_digest", None)
    _require(
        observed_digest
        == sources["parent_fit_receipt"]["receipt_digest"]
        == canonical_digest(digest_payload)
        and parent_receipt.get("contract_sha256")
        == sha256_file(parent_contract_path),
        "parent fit binding changed",
    )
    pan_receipt_path = _bound_path(sources["independent_pan_play_receipt"])
    pan_contract_path = REPO_ROOT / sources["independent_pan_play_receipt"][
        "contract_path"
    ]
    pan_receipt = _load_json(pan_receipt_path)
    _require(
        pan_contract_path.is_file()
        and sha256_file(pan_contract_path)
        == sources["independent_pan_play_receipt"]["contract_sha256"]
        and pan_receipt.get("status")
        == "retrospective_validation_passed_no_promotion"
        and pan_receipt.get("selection", {}).get("selected_radius_degrees")
        == 0.4
        and pan_receipt.get("retrospective_validation", {}).get("passed")
        is True,
        "independent pan-play binding changed",
    )
    retained = contract["retained_half_width_degrees"]
    _require(
        retained
        == {
            "shoulder_pan_shared": 0.4,
            "shoulder_lift_with_load": 2.125,
            "elbow_flex_against_load": 0.125,
            "elbow_flex_with_load": 2.125,
            "wrist_flex_with_load": 1.0,
        },
        "retained parent parameters changed",
    )

    selection_path = _bound_path(parent_contract["sources"]["selection_receipt"])
    selection = _load_json(selection_path)
    mechanism_path = _bound_path(parent_contract["sources"]["mechanism_contract"])
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)
    stages = sources["stages"]
    _require(len(stages) == 5, "reverse fit requires exactly five stages")
    mapped_stages: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for source in stages:
        packet = _load_json(_bound_path(source["packet"]))
        _, loaded = _stage_payload(source, packet)
        mapped_stages.append(
            (
                int(source["fit_stage_index"]),
                _mapped_episode(loaded["payload"], workcell),
                loaded["source"],
            )
        )

    settle_steps = int(mechanism["candidate_grid"]["initial_settle_steps"])
    delay_seconds = float(
        mechanism["source"]["required_application_delay_seconds"]
    )
    objective = contract["fit_objective"]
    selected_joints = [str(value) for value in objective["selected_joints"]]
    delta_degrees = float(objective["delta_degrees"])
    parent_expanded = {
        **parent_receipt["selected_expanded_half_width_degrees"],
        "shoulder_pan": {
            "with_load": float(retained["shoulder_pan_shared"]),
            "against_load": float(retained["shoulder_pan_shared"]),
        },
    }
    parent_metrics: list[dict[str, Any]] = []
    parent_objectives: list[float] = []
    for _, mapped, _ in mapped_stages:
        states, _ = replay_joint_play(
            mapped,
            workcell,
            settle_steps=settle_steps,
            delay_seconds=delay_seconds,
            half_width_degrees=parent_expanded,
        )
        parent_metrics.append(
            _episode_metrics(mapped, states, workcell, mechanism)
        )
        parent_objectives.append(
            _objective(
                mapped,
                states,
                selected_joints=selected_joints,
                delta_degrees=delta_degrees,
            )
        )
    parent_objective = float(np.mean(parent_objectives))

    candidates = _candidate_grid(contract)
    results: dict[str, dict[str, Any]] = {}
    per_candidate_metrics: dict[str, list[dict[str, Any]]] = {}
    per_candidate_schedules: dict[str, list[str]] = {}
    per_candidate_objectives: dict[str, list[float]] = {}
    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        metrics_rows: list[dict[str, Any]] = []
        schedules: list[str] = []
        objectives: list[float] = []
        expanded = _expanded(retained, candidate)
        for _, mapped, _ in mapped_stages:
            states, schedule = replay_joint_play(
                mapped,
                workcell,
                settle_steps=settle_steps,
                delay_seconds=delay_seconds,
                half_width_degrees=expanded,
            )
            metrics_rows.append(
                _episode_metrics(mapped, states, workcell, mechanism)
            )
            schedules.append(schedule["sha256"])
            objectives.append(
                _objective(
                    mapped,
                    states,
                    selected_joints=selected_joints,
                    delta_degrees=delta_degrees,
                )
            )
        per_candidate_metrics[candidate_id] = metrics_rows
        per_candidate_schedules[candidate_id] = schedules
        per_candidate_objectives[candidate_id] = objectives
        results[candidate_id] = {
            "candidate": candidate,
            "expanded_half_width_degrees": expanded,
            "fit_objective": float(np.mean(objectives)),
            "per_stage_fit_objective": objectives,
            "pooled_metrics": _pool(metrics_rows),
            "schedule_sha256_by_stage": schedules,
        }

    eligible = [
        candidate_id
        for candidate_id, row in results.items()
        if row["fit_objective"] < parent_objective
    ]
    _require(eligible, "no reverse-branch candidate improves the parent")
    selected_id = min(
        eligible,
        key=lambda candidate_id: (results[candidate_id]["fit_objective"], candidate_id),
    )
    selected = results[selected_id]
    selected_per_stage = [
        {
            "fit_stage_index": stage_index,
            "source": source,
            "mapped_action_receipt": mapped["action_receipt"],
            "schedule_sha256": per_candidate_schedules[selected_id][index],
            "fit_objective": per_candidate_objectives[selected_id][index],
            "metrics": _strip_arrays(per_candidate_metrics[selected_id][index]),
        }
        for index, (stage_index, mapped, source) in enumerate(mapped_stages)
    ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "fit_id": contract["fit_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "parent_fit_receipt_path": str(parent_receipt_path),
        "parent_fit_receipt_sha256": sha256_file(parent_receipt_path),
        "independent_pan_play_receipt_path": str(pan_receipt_path),
        "independent_pan_play_receipt_sha256": sha256_file(pan_receipt_path),
        "stage_count": len(mapped_stages),
        "candidate_count": len(candidates),
        "parent_fit_objective": parent_objective,
        "parent_pooled_metrics": _pool(parent_metrics),
        "candidates": results,
        "eligible_candidates": eligible,
        "selected_candidate_id": selected_id,
        "selected_candidate": selected["candidate"],
        "selected_expanded_half_width_degrees": selected[
            "expanded_half_width_degrees"
        ],
        "selected_fit_objective": selected["fit_objective"],
        "selected_pooled_metrics": selected["pooled_metrics"],
        "selected_per_stage": selected_per_stage,
        "fit_objective_relative_improvement_vs_parent": float(
            (parent_objective - selected["fit_objective"]) / parent_objective
        ),
        "selection_rule": contract["selection_rule"],
        "opened_roundtrips_used_for_fit": True,
        "fresh_heldout_required": True,
        "parameter_fitting_performed": True,
        "parameters_promoted": False,
        "source_actions_modified": False,
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
