"""Action-frozen SO-101 lift/elbow servo-deadband mechanism ablation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_reward import load_reward_contract
from .pawn_bg_timing_ablation import (
    BODY_JOINT_NAMES,
    _episode_metrics,
    _mapped_episode,
    _pool,
    _strip_arrays,
    _timestamp_aligned_zoh,
    _timing_consequence_episode,
    _write_episode_trace,
)


CONTRACT_PATH = REPO_ROOT / "configs" / "sysid" / "pawn_bg_servo_deadband_v1.json"
SCHEMA = "sim2claw.pawn_bg_servo_deadband.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_servo_deadband_receipt.v1"


class ServoDeadbandError(RuntimeError):
    """The deadband experiment violates its frozen evidence boundary."""


def load_servo_deadband_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServoDeadbandError(f"cannot read deadband contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise ServoDeadbandError("unexpected servo-deadband contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise ServoDeadbandError("servo-deadband authority widened")
    invariance = contract.get("action_invariance")
    if not isinstance(invariance, dict) or not invariance or not all(invariance.values()):
        raise ServoDeadbandError("action invariance is not fail closed")
    grid = [float(value) for value in contract["mechanism"]["shared_deadband_grid_degrees"]]
    if grid != sorted(set(grid)) or grid[0] != 0.0 or grid[-1] > 3.0:
        raise ServoDeadbandError("deadband grid is invalid")
    if contract["mechanism"]["target_joints"] != ["shoulder_lift", "elbow_flex"]:
        raise ServoDeadbandError("target joint set changed")
    members = [
        str(recording_id)
        for fold in contract["grouped_cross_validation"]["folds"]
        for recording_id in fold
    ]
    if len(members) != 11 or len(set(members)) != 11:
        raise ServoDeadbandError("grouped CV folds must cover 11 unique episodes")
    return contract


def _key(deadband_degrees: float) -> str:
    millidegrees = int(round(deadband_degrees * 1000.0))
    return f"deadband_{millidegrees:04d}mdeg"


def _target_mapping(contract: dict[str, Any], deadband_degrees: float) -> dict[str, float]:
    if deadband_degrees == 0.0:
        return {}
    return {
        str(name): float(deadband_degrees)
        for name in contract["mechanism"]["target_joints"]
    }


def _candidate_is_eligible(metrics: dict[str, Any], contract: dict[str, Any]) -> bool:
    acceptance = contract["acceptance"]
    minimum_stall = float(
        acceptance["fit_minimum_stall_reproduction_fraction_per_target_joint"]
    )
    ceiling = float(acceptance["fit_maximum_overall_joint_rms_degrees"])
    return bool(
        metrics["overall_joint_rms_degrees"] <= ceiling
        and all(
            metrics["stall_reproduction_fraction"][name] >= minimum_stall
            for name in contract["mechanism"]["target_joints"]
        )
    )


def _select_candidate(
    candidates: list[dict[str, Any]], contract: dict[str, Any]
) -> dict[str, Any]:
    eligible = [row for row in candidates if _candidate_is_eligible(row, contract)]
    if not eligible:
        raise ServoDeadbandError("no candidate satisfies the frozen fit constraints")
    return min(eligible, key=lambda row: (row["overall_joint_rms_degrees"], row["deadband_degrees"]))


def _evaluate_partition(
    payloads: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    candidate: Any,
    contract: dict[str, Any],
    grid: list[float],
    delay_seconds: float,
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    results: dict[str, dict[str, dict[str, Any]]] = {}
    mapped_by_id: dict[str, dict[str, Any]] = {}
    schedules: dict[str, dict[str, Any]] = {}
    settle_steps = 100
    for payload in payloads:
        mapped = _mapped_episode(payload, candidate)
        recording_id = str(mapped["episode"]["recording_id"])
        mapped_by_id[recording_id] = mapped
        results[recording_id] = {}
        schedules[recording_id] = {}
        for deadband_degrees in grid:
            key = _key(deadband_degrees)
            states, schedule = _timestamp_aligned_zoh(
                mapped,
                candidate,
                settle_steps=settle_steps,
                delay_seconds=delay_seconds,
                servo_deadband_degrees=_target_mapping(contract, deadband_degrees),
            )
            results[recording_id][key] = _episode_metrics(
                mapped, states, candidate, contract
            )
            schedules[recording_id][key] = schedule
    return results, mapped_by_id, schedules


def _pooled(
    results: dict[str, dict[str, dict[str, Any]]],
    recording_ids: Iterable[str],
    key: str,
) -> dict[str, Any]:
    return _pool(results[recording_id][key] for recording_id in recording_ids)


def _grid_rows(
    results: dict[str, dict[str, dict[str, Any]]],
    recording_ids: Iterable[str],
    grid: Iterable[float],
) -> list[dict[str, Any]]:
    ids = list(recording_ids)
    return [
        {
            "deadband_degrees": deadband_degrees,
            "variant": _key(deadband_degrees),
            **_pooled(results, ids, _key(deadband_degrees)),
        }
        for deadband_degrees in grid
    ]


def _consequence_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    return {
        "episode_count": len(materialized),
        "selected_piece_contact": sum(
            int(row["selected_piece_contact_observed"]) for row in materialized
        ),
        "lifted": sum(int(row["piece_lifted"]) for row in materialized),
        "task_consequence_successes": sum(
            int(row["task_consequence_success"]) for row in materialized
        ),
        "mean_minimum_pinch_to_selected_piece_m": float(
            np.mean([row["minimum_pinch_to_selected_piece_m"] for row in materialized])
        ),
        "mean_maximum_piece_rise_m": float(
            np.mean([row["maximum_piece_rise_m"] for row in materialized])
        ),
        "mean_final_target_distance_m": float(
            np.mean([row["final_target_distance_m"] for row in materialized])
        ),
    }


def run_servo_deadband_ablation(
    *,
    source_repository_root: Path,
    output_root: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_servo_deadband_contract(contract_path)
    timing_path = source_repository_root / contract["source"]["upstream_timing_receipt"]
    try:
        timing_receipt = json.loads(timing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServoDeadbandError(f"cannot read upstream timing receipt: {error}") from error
    delay_seconds = float(contract["source"]["required_application_delay_seconds"])
    if not timing_receipt["train_acceptance"]["accepted_as_timing_diagnostic"]:
        raise ServoDeadbandError("upstream timing diagnostic was not accepted")
    if abs(float(timing_receipt["selected_delay_seconds"]) - delay_seconds) > 1e-12:
        raise ServoDeadbandError("upstream timing delay differs from frozen deadband input")

    train_payloads, events = _load_partition(source_repository_root, "train")
    confirmation_payloads, _ = _load_partition(source_repository_root, "held_out")
    if len(train_payloads) != int(contract["source"]["expected_train_episode_count"]):
        raise ServoDeadbandError("train product episode inventory changed")
    if len(confirmation_payloads) != int(
        contract["source"]["expected_already_opened_confirmation_episode_count"]
    ):
        raise ServoDeadbandError("confirmation product episode inventory changed")
    _parent, candidate, stage_d_parameters, _details = _reconstruct_stage_d(
        train_payloads, events
    )
    grid = [float(value) for value in contract["mechanism"]["shared_deadband_grid_degrees"]]
    train_results, mapped_train, train_schedules = _evaluate_partition(
        train_payloads, candidate, contract, grid, delay_seconds
    )
    train_ids = sorted(train_results)
    folds = [
        list(map(str, fold)) for fold in contract["grouped_cross_validation"]["folds"]
    ]
    if {recording_id for fold in folds for recording_id in fold} != set(train_ids):
        raise ServoDeadbandError("CV fold identities differ from train episodes")

    all_train_grid = _grid_rows(train_results, train_ids, grid)
    selected = _select_candidate(all_train_grid, contract)
    selected_deadband = float(selected["deadband_degrees"])
    selected_key = str(selected["variant"])
    baseline = _pooled(train_results, train_ids, _key(0.0))

    cv_rows: list[dict[str, Any]] = []
    cv_selected_metrics: list[dict[str, Any]] = []
    for fold_index, validation_ids in enumerate(folds):
        fit_ids = [recording_id for recording_id in train_ids if recording_id not in validation_ids]
        fit_grid = _grid_rows(train_results, fit_ids, grid)
        fold_selected = _select_candidate(fit_grid, contract)
        fold_key = str(fold_selected["variant"])
        validation_baseline = _pooled(train_results, validation_ids, _key(0.0))
        validation_candidate = _pooled(train_results, validation_ids, fold_key)
        cv_selected_metrics.extend(
            train_results[recording_id][fold_key] for recording_id in validation_ids
        )
        cv_rows.append(
            {
                "fold_index": fold_index,
                "fit_episode_ids": fit_ids,
                "validation_episode_ids": validation_ids,
                "selected_deadband_degrees": fold_selected["deadband_degrees"],
                "fit_metrics": {key: value for key, value in fold_selected.items() if key != "variant"},
                "validation_baseline": validation_baseline,
                "validation_candidate": validation_candidate,
                "validation_joint_rms_relative_improvement": float(
                    (validation_baseline["overall_joint_rms_degrees"] - validation_candidate["overall_joint_rms_degrees"])
                    / validation_baseline["overall_joint_rms_degrees"]
                ),
            }
        )
    cv_baseline = _pool(
        train_results[recording_id][_key(0.0)]
        for fold in folds
        for recording_id in fold
    )
    cv_candidate = _pool(cv_selected_metrics)
    cv_improvement = float(
        (cv_baseline["overall_joint_rms_degrees"] - cv_candidate["overall_joint_rms_degrees"])
        / cv_baseline["overall_joint_rms_degrees"]
    )
    acceptance = contract["acceptance"]
    minimum_cv_stall = float(
        acceptance["minimum_cross_validated_stall_reproduction_fraction_per_target_joint"]
    )
    gates = {
        "action_invariance_gate": all(
            mapped["action_receipt"]["sha256"] == _array_sha256(mapped["actions"])
            for mapped in mapped_train.values()
        ),
        "cross_validated_joint_rms_ceiling_gate": cv_candidate["overall_joint_rms_degrees"]
        <= float(acceptance["maximum_cross_validated_overall_joint_rms_degrees"]),
        "cross_validated_joint_rms_no_regression_gate": (
            not bool(acceptance["require_cross_validated_joint_rms_no_regression_from_zero_deadband"])
            or cv_candidate["overall_joint_rms_degrees"] <= cv_baseline["overall_joint_rms_degrees"]
        ),
        "cross_validated_target_stall_gate": all(
            cv_candidate["stall_reproduction_fraction"][name] >= minimum_cv_stall
            for name in contract["mechanism"]["target_joints"]
        ),
    }
    diagnostic_accepted = all(gates.values())

    reward_contract = load_reward_contract()
    consequence_rows: dict[str, list[dict[str, Any]]] = {
        "timing_only_zero_deadband": [],
        "timing_plus_selected_deadband": [],
    }
    for recording_id in train_ids:
        mapped = mapped_train[recording_id]
        consequence_rows["timing_only_zero_deadband"].append(
            _timing_consequence_episode(
                mapped=mapped,
                candidate=candidate,
                reward_contract=reward_contract,
                mode="timestamp_aligned_zoh",
                delay_seconds=delay_seconds,
                settle_steps=100,
            )
        )
        consequence_rows["timing_plus_selected_deadband"].append(
            _timing_consequence_episode(
                mapped=mapped,
                candidate=candidate,
                reward_contract=reward_contract,
                mode="timestamp_aligned_zoh",
                delay_seconds=delay_seconds,
                settle_steps=100,
                servo_deadband_degrees=_target_mapping(contract, selected_deadband),
            )
        )
    consequences = {
        name: {"summary": _consequence_summary(rows), "episodes": rows}
        for name, rows in consequence_rows.items()
    }
    selected_consequence = consequences["timing_plus_selected_deadband"]["summary"]
    task_consequence_gate = (
        selected_consequence["task_consequence_successes"]
        == selected_consequence["episode_count"]
    )

    confirmation_results, mapped_confirmation, confirmation_schedules = _evaluate_partition(
        confirmation_payloads,
        candidate,
        contract,
        [0.0, selected_deadband],
        delay_seconds,
    )
    confirmation_ids = sorted(confirmation_results)
    confirmation = {
        "selection_use": "none_already_opened_regression_only",
        "zero_deadband": _pooled(confirmation_results, confirmation_ids, _key(0.0)),
        "selected_deadband": _pooled(confirmation_results, confirmation_ids, selected_key),
    }

    trace_rows = []
    for recording_id in train_ids:
        path = output_root.resolve() / "traces" / f"{recording_id}.json"
        variants = {
            "timing_only_zero_deadband": train_results[recording_id][_key(0.0)],
            "timing_plus_selected_deadband": train_results[recording_id][selected_key],
        }
        digest = _write_episode_trace(
            mapped=mapped_train[recording_id], variants=variants, output_path=path
        )
        trace_rows.append(
            {
                "recording_id": recording_id,
                "action": mapped_train[recording_id]["action_receipt"],
                "trace_path": str(path),
                "trace_sha256": digest,
                "schedules": {
                    name: train_schedules[recording_id][key]
                    for name, key in {
                        "timing_only_zero_deadband": _key(0.0),
                        "timing_plus_selected_deadband": selected_key,
                    }.items()
                },
                "metrics": {
                    name: _strip_arrays(metrics) for name, metrics in variants.items()
                },
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_actuator_model_diagnostic",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "upstream_timing_receipt": {"path": str(timing_path.resolve()), "sha256": sha256_file(timing_path)},
        "application_delay_seconds": delay_seconds,
        "stage_d_parameters": stage_d_parameters,
        "board_playing_side_m": float(contract["source"]["candidate_board_playing_side_m"]),
        "board_scale_status": contract["source"]["board_scale_status"],
        "train_episode_count": len(train_ids),
        "action_arrays_byte_identical_across_variants": gates["action_invariance_gate"],
        "zero_deadband_train_metrics": baseline,
        "candidate_grid": all_train_grid,
        "selected_deadband_degrees": selected_deadband,
        "selected_variant": selected_key,
        "selected_train_metrics": {key: value for key, value in selected.items() if key != "variant"},
        "grouped_cross_validation": {
            "folds": cv_rows,
            "pooled_baseline": cv_baseline,
            "pooled_candidate": cv_candidate,
            "pooled_joint_rms_relative_improvement": cv_improvement,
        },
        "train_acceptance": {
            "gates": gates,
            "accepted_as_actuator_model_diagnostic": diagnostic_accepted,
            "task_consequence_gate": task_consequence_gate,
            "accepted_as_composite_simulator_candidate": diagnostic_accepted
            and task_consequence_gate,
        },
        "action_frozen_consequence_replay": consequences,
        "already_opened_confirmation": confirmation,
        "traces": trace_rows,
        "confirmation_action_hashes": {
            recording_id: mapped["action_receipt"]
            for recording_id, mapped in mapped_confirmation.items()
        },
        "confirmation_schedules": confirmation_schedules,
        "authority": contract["authority"],
        "claim_boundary": (
            "The selected deadband is a cross-validated simulator actuator-model-class "
            "diagnostic under byte-identical source actions. It is not a measured firmware "
            "parameter, torque/current calibration, contact label, policy improvement, "
            "task result, composite simulator promotion, or physical-transfer result."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "servo_deadband_receipt.json", receipt)
    return receipt
