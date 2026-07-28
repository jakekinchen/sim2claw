#!/usr/bin/env python3
"""Fit one lower-bounded wrist load-sign hysteresis threshold."""

from __future__ import annotations

import argparse
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
    _strip_arrays,
)
from tools.evaluate_geometric_micro_actuator_response import _stage_payload


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_play_hysteresis_fit_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_play_hysteresis_fit.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_joint_play_hysteresis_fit_receipt.v1"


class GeometricJointPlayHysteresisFitError(RuntimeError):
    """The bounded hysteresis fit evidence changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayHysteresisFitError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricJointPlayHysteresisFitError(
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


def _receipt_digest(receipt: Mapping[str, Any]) -> str | None:
    payload = dict(receipt)
    observed = payload.pop("receipt_digest", None)
    return observed if observed == canonical_digest(payload) else None


def _crossing_objective(
    mapped: Mapping[str, Any],
    states: np.ndarray,
    *,
    crossing_indices: list[int],
    radius: int,
    delta_degrees: float,
) -> tuple[float, list[float]]:
    wrist_index = BODY_JOINT_NAMES.index("wrist_flex")
    error = np.abs(
        np.degrees(
            states[:, wrist_index]
            - np.asarray(mapped["measured"], dtype=np.float64)[:, wrist_index]
        )
    )
    crossing_losses: list[float] = []
    for index in crossing_indices:
        start = max(0, int(index) - radius)
        stop = min(error.size, int(index) + radius + 1)
        window = error[start:stop]
        huber = np.where(
            window <= delta_degrees,
            0.5 * window**2,
            delta_degrees * (window - 0.5 * delta_degrees),
        )
        crossing_losses.append(float(np.mean(huber)))
    return float(np.mean(crossing_losses)), crossing_losses


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
        == "bounded_one_parameter_fit_after_two_opened_heldouts",
        "fit status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "fit authority widened",
    )
    _require(
        contract.get("proof_boundary")
        == {
            "both_heldouts_are_opened_fit_sources": True,
            "threshold_is_lower_bounded_not_point_identified": True,
            "fresh_opposite_direction_heldout_required": True,
        },
        "fit proof boundary changed",
    )

    sources = contract["sources"]
    _bound_path(sources["joint_play_implementation"])
    parent_contract_path = _bound_path(sources["parent_fit_contract"])
    parent_contract = _load_json(parent_contract_path)
    parent_receipt_path = _bound_path(sources["parent_fit_receipt"])
    parent_receipt = _load_json(parent_receipt_path)
    _require(
        _receipt_digest(parent_receipt)
        == sources["parent_fit_receipt"]["receipt_digest"]
        and parent_receipt.get("contract_sha256")
        == sha256_file(parent_contract_path),
        "parent fit receipt changed",
    )
    frozen_parent = contract["frozen_parent"]
    _require(
        parent_receipt.get("selected_expanded_half_width_degrees")
        == frozen_parent["selected_expanded_half_width_degrees"],
        "parent play widths changed",
    )

    original_fit_contract_path = _bound_path(
        parent_contract["sources"]["parent_fit_contract"]
    )
    original_fit_contract = _load_json(original_fit_contract_path)
    selection_path = _bound_path(
        original_fit_contract["sources"]["selection_receipt"]
    )
    selection = _load_json(selection_path)
    mechanism_path = _bound_path(
        original_fit_contract["sources"]["mechanism_contract"]
    )
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)
    settle_steps = int(mechanism["candidate_grid"]["initial_settle_steps"])
    delay_seconds = float(
        mechanism["source"]["required_application_delay_seconds"]
    )
    _require(
        delay_seconds == float(frozen_parent["application_delay_seconds"]),
        "frozen application delay changed",
    )

    mapped_stages: list[tuple[dict[str, Any], dict[str, Any], list[int]]] = []
    for source in sources["stages"]:
        packet = _load_json(_bound_path(source["packet"]))
        _, loaded = _stage_payload(source, packet)
        mapped_stages.append(
            (
                _mapped_episode(loaded["payload"], workcell),
                loaded["source"],
                [int(value) for value in source["wrist_crossing_source_indices"]],
            )
        )
    _require(
        len(mapped_stages) == 2
        and [len(row[2]) for row in mapped_stages] == [2, 4],
        "fit requires the frozen two- and four-crossing traces",
    )

    objective = contract["fit_objective"]
    radius = int(objective["crossing_window_radius_samples"])
    delta = float(objective["delta_degrees"])
    candidates: dict[str, Any] = {}
    for threshold_value in contract[
        "candidate_wrist_load_sign_hysteresis_nm"
    ]:
        threshold = float(threshold_value)
        trace_objectives: list[float] = []
        stage_rows: list[dict[str, Any]] = []
        for mapped, source, crossings in mapped_stages:
            states, schedule = replay_joint_play(
                mapped,
                workcell,
                settle_steps=settle_steps,
                delay_seconds=delay_seconds,
                half_width_degrees=frozen_parent[
                    "selected_expanded_half_width_degrees"
                ],
                load_sign_zero_threshold_nm=float(
                    frozen_parent["load_sign_zero_threshold_nm"]
                ),
                load_sign_hysteresis_nm={"wrist_flex": threshold},
            )
            trace_objective, crossing_objectives = _crossing_objective(
                mapped,
                states,
                crossing_indices=crossings,
                radius=radius,
                delta_degrees=delta,
            )
            trace_objectives.append(trace_objective)
            stage_rows.append(
                {
                    "source": source,
                    "crossing_indices": crossings,
                    "crossing_objectives": crossing_objectives,
                    "trace_objective": trace_objective,
                    "schedule_sha256": schedule["sha256"],
                    "metrics": _strip_arrays(
                        _episode_metrics(
                            mapped, states, workcell, mechanism
                        )
                    ),
                }
            )
        candidate_id = f"wrist_hysteresis_{int(round(threshold * 1000)):03d}mNm"
        candidates[candidate_id] = {
            "threshold_nm": threshold,
            "fit_objective": float(np.mean(trace_objectives)),
            "per_stage": stage_rows,
        }

    ranked = sorted(
        candidates.items(),
        key=lambda item: (
            float(item[1]["fit_objective"]),
            float(item[1]["threshold_nm"]),
        ),
    )
    selected_id, selected = ranked[0]
    best_objective = float(selected["fit_objective"])
    best_plateau = [
        name
        for name, row in ranked
        if abs(float(row["fit_objective"]) - best_objective) <= 1e-15
    ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "fit_id": contract["fit_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "joint_play_implementation_sha256": sha256_file(
            _bound_path(sources["joint_play_implementation"])
        ),
        "parent_fit_receipt_path": str(parent_receipt_path),
        "parent_fit_receipt_sha256": sha256_file(parent_receipt_path),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selected_candidate_id": selected_id,
        "selected_wrist_load_sign_hysteresis_nm": float(
            selected["threshold_nm"]
        ),
        "selected_fit_objective": best_objective,
        "best_plateau_candidate_ids": best_plateau,
        "selection_rule": objective["selection"],
        "threshold_is_lower_bounded_not_point_identified": True,
        "source_actions_modified": False,
        "parameter_fitting_performed": True,
        "parameters_promoted": False,
        "fresh_opposite_direction_heldout_required": True,
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
