#!/usr/bin/env python3
"""Fit bounded stateful joint play on exact geometric training traces."""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Mapping

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
    / "geometric_joint_play_fit_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_play_fit.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_joint_play_fit_receipt.v1"


class GeometricJointPlayFitError(RuntimeError):
    """The fit inventory, parameter bounds, or evidence boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayFitError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricJointPlayFitError(f"cannot read {path}: {error}") from error
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


def _candidate_grid(contract: Mapping[str, Any]) -> list[dict[str, float]]:
    grid = contract["candidate_grid_half_width_degrees"]
    candidates = [
        {
            "shoulder_lift_shared": float(lift),
            "elbow_flex_against_load": float(elbow_against),
            "elbow_flex_with_load": float(elbow_with),
            "wrist_flex_shared": float(wrist),
        }
        for lift, elbow_against, elbow_with, wrist in itertools.product(
            grid["shoulder_lift_shared"],
            grid["elbow_flex_against_load"],
            grid["elbow_flex_with_load"],
            grid["wrist_flex_shared"],
        )
    ]
    _require(
        len(candidates) == 81
        and len({canonical_digest(row) for row in candidates}) == 81,
        "joint-play grid must contain 81 unique candidates",
    )
    return candidates


def _candidate_id(candidate: Mapping[str, float]) -> str:
    return "_".join(
        f"{name}{int(round(float(candidate[name]) * 1000)):04d}"
        for name in (
            "shoulder_lift_shared",
            "elbow_flex_against_load",
            "elbow_flex_with_load",
            "wrist_flex_shared",
        )
    )


def _play_widths(candidate: Mapping[str, float]) -> dict[str, dict[str, float]]:
    return {
        "shoulder_lift": {
            "with_load": float(candidate["shoulder_lift_shared"]),
            "against_load": float(candidate["shoulder_lift_shared"]),
        },
        "elbow_flex": {
            "with_load": float(candidate["elbow_flex_with_load"]),
            "against_load": float(candidate["elbow_flex_against_load"]),
        },
        "wrist_flex": {
            "with_load": float(candidate["wrist_flex_shared"]),
            "against_load": float(candidate["wrist_flex_shared"]),
        },
    }


def _huber_objective(
    mapped: Mapping[str, Any],
    states: Any,
    *,
    delta_degrees: float,
) -> float:
    import numpy as np

    indices = [1, 2, 3]
    error = np.abs(
        np.degrees(
            np.asarray(states, dtype=np.float64)[:, indices]
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
        == "retrospective_bounded_fit_with_opened_roundtrip_diagnostic_excluded",
        "fit status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "fit authority widened",
    )
    stages = contract["sources"]["stages"]
    _require(len(stages) == 3, "fit requires exactly three stages")
    excluded = contract["sources"]["excluded_opened_diagnostic"]
    _require(
        excluded.get("may_select_parameters") is False,
        "opened diagnostic gained parameter-selection authority",
    )
    _bound_path(excluded["prior_evaluation_receipt"])

    selection_path = _bound_path(contract["sources"]["selection_receipt"])
    selection = _load_json(selection_path)
    selection_payload = dict(selection)
    observed_digest = selection_payload.pop("receipt_digest", None)
    _require(
        observed_digest
        == contract["sources"]["selection_receipt"]["receipt_digest"]
        == canonical_digest(selection_payload),
        "selection receipt digest changed",
    )
    mechanism_path = _bound_path(contract["sources"]["mechanism_contract"])
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)

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
    baselines: dict[str, list[dict[str, Any]]] = {
        name: [] for name in contract["baselines"]
    }
    baseline_objectives: dict[str, list[float]] = {
        name: [] for name in contract["baselines"]
    }
    delta_degrees = float(contract["fit_objective"]["delta_degrees"])
    for _, mapped, _ in mapped_stages:
        for name, deadband in contract["baselines"].items():
            states, _ = _timestamp_aligned_zoh(
                mapped,
                workcell,
                settle_steps=settle_steps,
                delay_seconds=delay_seconds,
                servo_deadband_degrees={
                    key: float(value) for key, value in deadband.items()
                },
            )
            baselines[name].append(
                _episode_metrics(mapped, states, workcell, mechanism)
            )
            baseline_objectives[name].append(
                _huber_objective(
                    mapped,
                    states,
                    delta_degrees=delta_degrees,
                )
            )
    pooled_baselines = {
        name: {
            "metrics": _pool(rows),
            "fit_objective": float(
                sum(baseline_objectives[name]) / len(baseline_objectives[name])
            ),
            "per_stage_fit_objective": baseline_objectives[name],
        }
        for name, rows in baselines.items()
    }
    selected_memoryless = pooled_baselines["selected_memoryless_deadband"]

    candidates = _candidate_grid(contract)
    candidate_metrics: dict[str, list[dict[str, Any]]] = {}
    candidate_schedules: dict[str, list[str]] = {}
    candidate_objectives: dict[str, list[float]] = {}
    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        candidate_metrics[candidate_id] = []
        candidate_schedules[candidate_id] = []
        candidate_objectives[candidate_id] = []
        for _, mapped, _ in mapped_stages:
            states, schedule = replay_joint_play(
                mapped,
                workcell,
                settle_steps=settle_steps,
                delay_seconds=delay_seconds,
                half_width_degrees=_play_widths(candidate),
                load_sign_zero_threshold_nm=float(
                    contract["mechanism"]["load_sign_zero_threshold_nm"]
                ),
            )
            candidate_metrics[candidate_id].append(
                _episode_metrics(mapped, states, workcell, mechanism)
            )
            candidate_schedules[candidate_id].append(schedule["sha256"])
            candidate_objectives[candidate_id].append(
                _huber_objective(
                    mapped,
                    states,
                    delta_degrees=delta_degrees,
                )
            )

    pooled_candidates = {
        _candidate_id(candidate): {
            "half_width_degrees": candidate,
            "metrics": _pool(candidate_metrics[_candidate_id(candidate)]),
            "fit_objective": float(
                sum(candidate_objectives[_candidate_id(candidate)])
                / len(candidate_objectives[_candidate_id(candidate)])
            ),
            "per_stage_fit_objective": candidate_objectives[
                _candidate_id(candidate)
            ],
            "schedule_sha256_by_stage": candidate_schedules[
                _candidate_id(candidate)
            ],
        }
        for candidate in candidates
    }
    eligible = [
        candidate_id
        for candidate_id, row in pooled_candidates.items()
        if row["fit_objective"] < selected_memoryless["fit_objective"]
    ]
    _require(eligible, "no stateful joint-play candidate improves both metrics")
    selected_id = min(
        eligible,
        key=lambda candidate_id: (
            pooled_candidates[candidate_id]["fit_objective"],
            candidate_id,
        ),
    )
    selected = pooled_candidates[selected_id]
    comparisons = {
        "selected_vs_selected_memoryless": {
            "fit_objective_relative_improvement": _relative_improvement(
                selected["fit_objective"],
                selected_memoryless["fit_objective"],
            ),
            "joint_rms_relative_improvement": _relative_improvement(
                selected["metrics"]["overall_joint_rms_degrees"],
                selected_memoryless["metrics"]["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement": _relative_improvement(
                selected["metrics"]["ee_rms_m"],
                selected_memoryless["metrics"]["ee_rms_m"],
            ),
        }
    }
    selected_per_stage = []
    for (fit_stage_index, mapped, source), metrics, schedule_sha in zip(
        mapped_stages,
        candidate_metrics[selected_id],
        candidate_schedules[selected_id],
        strict=True,
    ):
        selected_per_stage.append(
            {
                "fit_stage_index": fit_stage_index,
                "source": source,
                "mapped_action_receipt": mapped["action_receipt"],
                "schedule_sha256": schedule_sha,
                "fit_objective": candidate_objectives[selected_id][
                    fit_stage_index - 1
                ],
                "metrics": _strip_arrays(metrics),
            }
        )

    opened_packet = _load_json(_bound_path(excluded["packet"]))
    _, opened_loaded = _stage_payload(excluded["stage"], opened_packet)
    opened_mapped = _mapped_episode(opened_loaded["payload"], workcell)
    opened_variants: dict[str, Any] = {}
    for name, deadband in contract["baselines"].items():
        states, schedule = _timestamp_aligned_zoh(
            opened_mapped,
            workcell,
            settle_steps=settle_steps,
            delay_seconds=delay_seconds,
            servo_deadband_degrees={
                key: float(value) for key, value in deadband.items()
            },
        )
        opened_variants[name] = {
            "model_class": "memoryless_static_deadband",
            "parameters": deadband,
            "schedule_sha256": schedule["sha256"],
            "metrics": _strip_arrays(
                _episode_metrics(opened_mapped, states, workcell, mechanism)
            ),
        }
    opened_play_states, opened_play_schedule = replay_joint_play(
        opened_mapped,
        workcell,
        settle_steps=settle_steps,
        delay_seconds=delay_seconds,
        half_width_degrees=_play_widths(selected["half_width_degrees"]),
        load_sign_zero_threshold_nm=float(
            contract["mechanism"]["load_sign_zero_threshold_nm"]
        ),
    )
    opened_variants["selected_stateful_play"] = {
        "model_class": "load_sign_conditioned_stateful_play",
        "parameters": selected["half_width_degrees"],
        "schedule_sha256": opened_play_schedule["sha256"],
        "metrics": _strip_arrays(
            _episode_metrics(
                opened_mapped,
                opened_play_states,
                workcell,
                mechanism,
            )
        ),
    }
    opened_baseline = opened_variants["selected_memoryless_deadband"]["metrics"]
    opened_play = opened_variants["selected_stateful_play"]["metrics"]
    opened_comparison = {
        "joint_rms_relative_improvement": _relative_improvement(
            opened_play["overall_joint_rms_degrees"],
            opened_baseline["overall_joint_rms_degrees"],
        ),
        "ee_rms_relative_improvement": _relative_improvement(
            opened_play["ee_rms_m"],
            opened_baseline["ee_rms_m"],
        ),
    }
    opened_diagnostic = {
        "proof_class": (
            "opened_roundtrip_family_support_diagnostic_not_validation"
        ),
        "source": opened_loaded["source"],
        "mapped_action_receipt": opened_mapped["action_receipt"],
        "variants": opened_variants,
        "selected_stateful_play_vs_selected_memoryless": opened_comparison,
        "supports_stateful_family": all(
            value > 0.0 for value in opened_comparison.values()
        ),
        "used_for_parameter_selection": False,
        "fresh_heldout_validation": False,
        "parameters_promoted": False,
    }

    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "fit_id": contract["fit_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "replay_implementation_path": str(
            (REPO_ROOT / "src/sim2claw/geometric_joint_play.py").resolve()
        ),
        "replay_implementation_sha256": sha256_file(
            REPO_ROOT / "src/sim2claw/geometric_joint_play.py"
        ),
        "stage_count": len(mapped_stages),
        "candidate_count": len(candidates),
        "pooled_baselines": pooled_baselines,
        "pooled_candidates": pooled_candidates,
        "eligible_candidates": eligible,
        "selected_candidate_id": selected_id,
        "selected_half_width_degrees": selected["half_width_degrees"],
        "selected_expanded_half_width_degrees": _play_widths(
            selected["half_width_degrees"]
        ),
        "selected_fit_objective": selected["fit_objective"],
        "selected_metrics": selected["metrics"],
        "selected_per_stage": selected_per_stage,
        "comparisons": comparisons,
        "opened_roundtrip_diagnostic": opened_diagnostic,
        "selection_rule": contract["selection_rule"],
        "opened_roundtrip_used_for_parameter_selection": False,
        "parameter_fitting_performed": True,
        "parameters_promoted": False,
        "new_heldout_physical_validation_required": True,
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
