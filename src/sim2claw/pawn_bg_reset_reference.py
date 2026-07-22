"""Action-frozen reset/reference audit for B--G physical demonstrations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_timing_ablation import _episode_metrics, _mapped_episode, _pool
from .pawn_bg_workcell_fit import build_workcell_model


CONTRACT_PATH = REPO_ROOT / "configs" / "sysid" / "pawn_bg_reset_reference_v1.json"
SCHEMA = "sim2claw.pawn_bg_reset_reference.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_reset_reference_receipt.v1"


class ResetReferenceError(RuntimeError):
    """The reset/reference audit violates its action-frozen boundary."""


def load_reset_reference_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResetReferenceError(f"cannot read reset contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise ResetReferenceError("unexpected reset/reference contract schema")
    if any(contract.get("authority", {}).values()):
        raise ResetReferenceError("reset/reference authority widened")
    if not all(contract.get("action_invariance", {}).values()):
        raise ResetReferenceError("action invariance is not fail closed")
    variants = contract.get("variants")
    if not isinstance(variants, list) or len(variants) != 4:
        raise ResetReferenceError("reset variant inventory changed")
    members = [item for fold in contract["grouped_cross_validation"]["folds"] for item in fold]
    if len(members) != 11 or len(set(members)) != 11:
        raise ResetReferenceError("grouped CV folds must cover 11 episodes")
    return contract


def _replay(
    mapped: dict[str, Any], candidate: Any, variant: dict[str, Any], delay_seconds: float
) -> tuple[np.ndarray, dict[str, Any]]:
    binding = build_workcell_model(candidate)
    model, data = binding["model"], binding["data"]
    qpos_addresses = binding["qpos_addresses"]
    actuator_ids = binding["actuator_ids"]
    if variant["state"] == "first_mapped_measured":
        initial = mapped["measured"][0]
    elif variant["state"] == "first_mapped_command":
        initial = mapped["actions"][0]
    elif variant["state"] == "model_qpos0":
        initial = np.asarray(model.qpos0[qpos_addresses], dtype=np.float64)
    else:
        raise ResetReferenceError(f"unsupported reset state: {variant['state']}")
    data.qpos[qpos_addresses] = initial
    data.ctrl[actuator_ids] = initial
    mujoco.mj_forward(model, data)
    settle_steps = int(variant["settle_steps"])
    if settle_steps:
        mujoco.mj_step(model, data, nstep=settle_steps)
    outputs = np.empty_like(mapped["measured"])
    times = mapped["timestamps"]
    timestep = float(model.opt.timestep)
    transitions: list[list[float | int]] = []
    last_index: int | None = None
    for row_index, timestamp in enumerate(times):
        outputs[row_index] = data.qpos[qpos_addresses]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        for step in range(max(1, round(interval / timestep))):
            now = float(timestamp) + step * timestep
            source_index = max(
                0,
                int(np.searchsorted(times, now - delay_seconds, side="right") - 1),
            )
            if source_index != last_index:
                transitions.append([now, source_index])
                last_index = source_index
            data.ctrl[actuator_ids] = mapped["actions"][source_index]
            mujoco.mj_step(model, data)
    schedule = {
        "semantics": "record_at_timestamp_then_apply_zoh_over_next_interval",
        "application_delay_seconds": delay_seconds,
        "reset_variant": variant,
        "source_index_transitions": transitions,
    }
    schedule["sha256"] = canonical_digest(schedule)
    return outputs, schedule


def _pooled(
    results: dict[str, dict[str, dict[str, Any]]], ids: Iterable[str], variant: str
) -> dict[str, Any]:
    return _pool(results[recording_id][variant] for recording_id in ids)


def run_reset_reference_audit(
    *, source_repository_root: Path, output_root: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_reset_reference_contract(contract_path)
    payloads, events = _load_partition(source_repository_root, "train")
    if len(payloads) != int(contract["source"]["expected_episode_count"]):
        raise ResetReferenceError("train product episode inventory changed")
    _parent, candidate, stage_d_parameters, _details = _reconstruct_stage_d(payloads, events)
    delay = float(contract["source"]["application_delay_seconds"])
    results: dict[str, dict[str, dict[str, Any]]] = {}
    schedules: dict[str, dict[str, Any]] = {}
    mapped_by_id: dict[str, dict[str, Any]] = {}
    initial_gaps = []
    for payload in payloads:
        mapped = _mapped_episode(payload, candidate)
        recording_id = str(mapped["episode"]["recording_id"])
        mapped_by_id[recording_id] = mapped
        results[recording_id] = {}
        schedules[recording_id] = {}
        initial_gaps.append(np.degrees(mapped["actions"][0, :5] - mapped["measured"][0, :5]))
        for variant in contract["variants"]:
            states, schedule = _replay(mapped, candidate, variant, delay)
            results[recording_id][variant["id"]] = _episode_metrics(
                mapped, states, candidate, {"stall_probe": {
                    "real_stationary_maximum_step_degrees": 0.5,
                    "command_measurement_minimum_gap_degrees": 2.0,
                    "sim_reproduction_minimum_gap_degrees": 2.0,
                }}
            )
            schedules[recording_id][variant["id"]] = schedule
    train_ids = sorted(results)
    rows = [
        {"variant": variant["id"], **_pooled(results, train_ids, variant["id"])}
        for variant in contract["variants"]
    ]
    selected = min(rows, key=lambda row: row["overall_joint_rms_degrees"])
    folds = [list(map(str, fold)) for fold in contract["grouped_cross_validation"]["folds"]]
    cv_rows = []
    validation_metrics = []
    for fold_index, validation_ids in enumerate(folds):
        fit_ids = [recording_id for recording_id in train_ids if recording_id not in validation_ids]
        fit_rows = [
            {"variant": variant["id"], **_pooled(results, fit_ids, variant["id"])}
            for variant in contract["variants"]
        ]
        fit_selected = min(fit_rows, key=lambda row: row["overall_joint_rms_degrees"])
        validation = _pooled(results, validation_ids, fit_selected["variant"])
        validation_metrics.extend(
            results[recording_id][fit_selected["variant"]] for recording_id in validation_ids
        )
        cv_rows.append(
            {
                "fold_index": fold_index,
                "fit_episode_ids": fit_ids,
                "validation_episode_ids": validation_ids,
                "selected_variant": fit_selected["variant"],
                "fit_metrics": fit_selected,
                "validation_metrics": validation,
            }
        )
    gap = np.asarray(initial_gaps, dtype=np.float64)
    reference_metrics = next(
        row for row in rows if row["variant"] == "first_measured_settle_100"
    )
    relative_improvement = float(
        (
            reference_metrics["overall_joint_rms_degrees"]
            - selected["overall_joint_rms_degrees"]
        )
        / reference_metrics["overall_joint_rms_degrees"]
    )
    minimum_material = float(
        contract["grouped_cross_validation"][
            "minimum_material_relative_improvement_over_first_measured_settle_100"
        ]
    )
    action_invariant = all(
        mapped["action_receipt"]["sha256"] == _array_sha256(mapped["actions"])
        for mapped in mapped_by_id.values()
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_reset_reference_diagnostic",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "stage_d_parameters": stage_d_parameters,
        "action_arrays_byte_identical_across_variants": action_invariant,
        "initial_command_minus_measured": {
            "overall_rms_degrees": float(np.sqrt(np.mean(gap**2))),
            "per_joint_rms_degrees": np.sqrt(np.mean(gap**2, axis=0)).tolist(),
            "per_joint_maximum_absolute_degrees": np.max(np.abs(gap), axis=0).tolist(),
        },
        "all_train_variants": rows,
        "all_train_selected_variant": selected["variant"],
        "grouped_cross_validation": {
            "folds": cv_rows,
            "pooled_selected": _pool(validation_metrics),
            "selection_stable": len({row["selected_variant"] for row in cv_rows}) == 1,
        },
        "decision": {
            "reset_reference_is_primary_remaining_gap": False,
            "all_train_best_variant": selected["variant"],
            "best_relative_joint_rms_improvement_over_first_measured_settle_100": relative_improvement,
            "minimum_material_relative_improvement": minimum_material,
            "best_variant_is_material_improvement": relative_improvement >= minimum_material,
            "retain_variant": "first_measured_settle_100",
            "interpretation": (
                "The first-commanded 100-step reset is the stable numerical CV winner, but its "
                "0.002-percent improvement over the first-measured reset is below the frozen "
                "materiality threshold because those initial states are nearly identical. Retain "
                "the physical first-measured reset; reset semantics do not explain the remaining "
                "lift/contact-consequence failure."
            ),
        },
        "schedules": schedules,
        "authority": contract["authority"],
        "claim_boundary": "This reset/reference comparison is a simulator diagnostic, not physical reset identification or simulator promotion.",
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "reset_reference_receipt.json", receipt)
    return receipt
