"""Preregistered action-frozen prospective simulator discrimination campaign."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from ..pawn_bg_action_frozen_gap import _array_sha256
from ..pawn_bg_timing_ablation import BODY_JOINT_NAMES, _episode_metrics
from ..pawn_bg_workcell_fit import WorkcellCandidate, build_workcell_model
from .contracts import REPO_ROOT, SailContractError

CONFIG_SCHEMA = "sim2claw.sail_prospective_simulator_campaign.v1"
EXPERIMENT_SCHEMA = "sim2claw.sail_prospective_simulator_experiment.v1"
GRAPH_SCHEMA = "sim2claw.sail_prospective_graph_delta.v1"
FREEZE_SCHEMA = "sim2claw.sail_phase2_prediction_freeze.v1"
TRIAL_SCHEMA = "sim2claw.sail_prospective_simulator_trial.v1"
RECEIPT_SCHEMA = "sim2claw.sail_prospective_simulator_receipt.v1"


class ProspectiveSimulatorError(SailContractError):
    """The prospective campaign crossed its preregistered boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProspectiveSimulatorError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ProspectiveSimulatorError(f"{label} escapes repository") from error
    return path


def load_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL prospective simulator config")
    _require(config.get("schema_version") == CONFIG_SCHEMA, "unsupported prospective simulator schema")
    _require(
        config.get("proof_class") == "action_frozen_prospective_simulator_experiment",
        "prospective proof class changed",
    )
    authority = config.get("authority")
    _require(isinstance(authority, dict) and authority and not any(authority.values()), "prospective authority widened")
    for name, binding in config["source_bindings"].items():
        source = _repo_path(repo_root, binding["path"], name)
        _require(source.is_file(), f"prospective source missing: {name}")
        _require(sha256_file(source) == binding["sha256"], f"prospective source changed: {name}")

    acquisition = load_json_object(
        _repo_path(repo_root, config["source_bindings"]["acquisition_ranking"]["path"], "acquisition ranking"),
        label="SAIL acquisition ranking",
    )
    _require(
        acquisition["selected_simulator_probe"] == config["acquisition_decision"]["selected_probe_id"],
        "prospective probe differs from acquisition selection",
    )
    trial_ids = [row["trial_id"] for row in config["declared_trials"]]
    _require(trial_ids == config["acceptance"]["required_trial_ids"], "declared trial inventory changed")
    _require(len(trial_ids) == len(set(trial_ids)) == 4, "factorial must contain four unique trials")
    observed_factorial = {
        (int(row["command_update_stride"]), float(row["elbow_load_bias_coefficient"]))
        for row in config["declared_trials"]
    }
    _require(observed_factorial == {(1, 0.0), (2, 0.0), (1, -1.5), (2, -1.5)}, "factorial boundary changed")
    budget = config["budget_and_stops"]
    _require(
        budget["exact_trial_count"] == budget["maximum_trial_count"] == len(trial_ids)
        and budget["maximum_episode_count"] == 1
        and budget["maximum_retries_per_trial"] == 0
        and budget["post_hoc_grid_expansion_allowed"] is False,
        "prospective budget or expansion boundary changed",
    )
    action = config["action_contract"]
    _require(
        action["shape"] == [368, 6]
        and action["dtype"] == "float64"
        and action["sha256"] == config["acceptance"]["expected_action_sha256"],
        "frozen action identity changed",
    )
    required_action_guards = (
        "require_exact_evidence_trace_equality",
        "no_resampling",
        "no_reordering",
        "no_value_change",
        "no_clipping",
        "no_ik",
        "no_offsets",
        "no_corrective_suffix",
        "no_assistance",
    )
    _require(all(action.get(name) is True for name in required_action_guards), "action invariance is not fail closed")
    freeze = config["phase2_prediction_freeze"]
    _require(
        freeze["frozen_before_any_phase2_physical_observation"] is True
        and freeze["physical_observations_consumed"] == 0
        and len(freeze["predictions"]) == 3,
        "Phase 2 predictions are not frozen before observation",
    )
    return config


def _load_sources(config: Mapping[str, Any], repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: load_json_object(_repo_path(repo_root, binding["path"], name), label=name)
        for name, binding in config["source_bindings"].items()
    }


def _workcell(receipt: Mapping[str, Any]) -> WorkcellCandidate:
    value = receipt["stage_d_parameters"]
    return WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(value["board_yaw_relative_to_table_degrees"]),
        board_center_in_table_frame_xy_m=tuple(float(item) for item in value["board_center_in_table_frame_xy_m"]),
        joint_zero_offsets_rad=tuple(float(item) for item in value["joint_zero_offsets_rad"]),
        joint_range_envelope_rad=tuple(tuple(float(item) for item in pair) for pair in value["joint_range_envelope_rad"]),
        base_z_offset_m=float(value["base_z_offset_m"]),
        base_roll_offset_degrees=float(value["base_roll_offset_degrees"]),
        base_pitch_offset_degrees=float(value["base_pitch_offset_degrees"]),
    )


def _mapped_trace(config: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    trace = sources["retained_trace"]
    evidence = sources["action_evidence"]
    rows = trace["rows"]
    actions = np.ascontiguousarray(np.asarray([row["applied_action"] for row in rows], dtype=np.float64))
    measured = np.ascontiguousarray(
        np.asarray([row["mapped_measured_joint_state"] for row in rows], dtype=np.float64)
    )
    timestamps = np.asarray([row["elapsed_seconds"] for row in rows], dtype=np.float64)
    evidence_actions = np.ascontiguousarray(
        np.asarray(evidence["observations"]["applied_action"]["values"], dtype=np.float64)
    )
    action_contract = config["action_contract"]
    _require(list(actions.shape) == action_contract["shape"], "retained trace action shape changed")
    _require(str(actions.dtype) == action_contract["dtype"], "retained trace action dtype changed")
    _require(actions.flags.c_contiguous, "retained trace action order changed")
    _require(_array_sha256(actions) == action_contract["sha256"], "retained trace action bytes changed")
    _require(np.array_equal(actions, evidence_actions), "evidence and retained trace actions differ")
    _require(trace["action_invariance"]["sha256"] == action_contract["sha256"], "retained trace action receipt changed")
    _require(trace["recording_id"] == action_contract["recording_id"], "retained recording changed")
    _require(measured.shape == actions.shape and len(timestamps) == len(actions), "retained trace rows misalign")
    _require(np.all(np.isfinite(actions)) and np.all(np.isfinite(measured)), "retained trace contains non-finite state")
    _require(np.all(np.diff(timestamps) > 0.0) and timestamps[0] == 0.0, "retained timestamps changed")
    return {
        "episode": {"recording_id": trace["recording_id"]},
        "timestamps": timestamps,
        "actions": actions,
        "measured": measured,
        "action_receipt": copy.deepcopy(trace["action_invariance"]),
    }


def _simulate_trial(
    *,
    mapped: Mapping[str, Any],
    workcell: WorkcellCandidate,
    protocol: Mapping[str, Any],
    trial: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    binding = build_workcell_model(workcell)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    dof_addresses = [int(model.jnt_dofadr[joint_id]) for joint_id in binding["joint_ids"]]
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    settle_steps = int(protocol["initial_settle_steps"])
    if settle_steps:
        mujoco.mj_step(model, data, nstep=settle_steps)

    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()
    times = mapped["timestamps"]
    actions = mapped["actions"]
    outputs = np.empty_like(mapped["measured"])
    timestep = float(model.opt.timestep)
    delay = float(protocol["application_delay_seconds"])
    stride = int(trial["command_update_stride"])
    coefficient = float(trial["elbow_load_bias_coefficient"])
    transitions: list[list[float | int]] = []
    last_source_index: int | None = None
    active_steps = 0
    applied_values: list[float] = []

    for row_index, timestamp in enumerate(times):
        outputs[row_index] = data.qpos[qpos_addresses]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        step_count = max(1, round(interval / timestep))
        for step in range(step_count):
            now = float(timestamp) + step * timestep
            available_index = max(0, int(np.searchsorted(times, now - delay, side="right") - 1))
            source_index = available_index - (available_index % stride)
            if source_index != last_source_index:
                transitions.append([now, source_index])
                last_source_index = source_index
            action = actions[source_index]
            data.ctrl[actuator_ids] = action
            data.qfrc_applied[dof_addresses] = 0.0
            for joint_name in ("shoulder_lift", "elbow_flex"):
                joint_index = BODY_JOINT_NAMES.index(joint_name)
                actuator_id = actuator_ids[joint_index]
                inactive = abs(float(action[joint_index] - data.qpos[qpos_addresses[joint_index]])) <= math.radians(
                    float(protocol["deadband_degrees"][joint_name])
                )
                scale = 0.0 if inactive else 1.0
                model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
                model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale
                if joint_name == "elbow_flex" and inactive and coefficient != 0.0:
                    value = coefficient * float(data.qfrc_bias[dof_addresses[joint_index]])
                    data.qfrc_applied[dof_addresses[joint_index]] = value
                    active_steps += 1
                    applied_values.append(value)
            mujoco.mj_step(model, data)

    schedule_unsigned = {
        "semantics": protocol["semantics"],
        "command_stride_semantics": protocol["command_stride_semantics"],
        "application_delay_seconds": delay,
        "command_update_stride": stride,
        "source_index_transitions": transitions,
    }
    schedule = {**schedule_unsigned, "schedule_digest": canonical_digest(schedule_unsigned)}
    torque = {
        "coefficient": coefficient,
        "active_physics_steps": active_steps,
        "mean_applied_torque": float(np.mean(applied_values)) if applied_values else 0.0,
        "mean_absolute_applied_torque": float(np.mean(np.abs(applied_values))) if applied_values else 0.0,
        "maximum_absolute_applied_torque": float(np.max(np.abs(applied_values))) if applied_values else 0.0,
    }
    return outputs, schedule, torque


def _subgroup_metrics(
    *,
    mapped: Mapping[str, Any],
    simulated: np.ndarray,
    config: Mapping[str, Any],
    workcell: WorkcellCandidate,
    schedule: Mapping[str, Any],
    torque: Mapping[str, Any],
) -> dict[str, Any]:
    base = _episode_metrics(
        dict(mapped),
        simulated,
        workcell,
        {"stall_probe": config["simulator_protocol"]["stall_probe"]},
    )
    error = np.degrees(simulated[:, :5] - mapped["measured"][:, :5])
    elbow_index = BODY_JOINT_NAMES.index("elbow_flex")
    stall = config["simulator_protocol"]["stall_probe"]
    measured_step = np.abs(np.diff(mapped["measured"][:, elbow_index]))
    command_gap = np.abs(mapped["actions"][:, elbow_index] - mapped["measured"][:, elbow_index])
    stationary = np.concatenate(
        (
            np.asarray([False]),
            (measured_step < np.radians(float(stall["real_stationary_maximum_step_degrees"])))
            & (command_gap[1:] > np.radians(float(stall["command_measurement_minimum_gap_degrees"]))),
        )
    )
    dt = np.diff(mapped["timestamps"])
    action_speed = np.max(np.abs(np.degrees(np.diff(mapped["actions"][:, :5], axis=0))) / dt[:, None], axis=1)
    dynamic = np.concatenate(
        (
            np.asarray([False]),
            action_speed >= float(config["simulator_protocol"]["dynamic_probe"]["minimum_action_speed_degrees_per_second"]),
        )
    )
    _require(bool(np.any(stationary)), "preregistered stationary subgroup is empty")
    _require(bool(np.any(dynamic)), "preregistered dynamic subgroup is empty")
    stall_fraction = {
        name: (
            float(base["stall_reproduced"][name]) / float(base["stall_rows"][name])
            if base["stall_rows"][name]
            else None
        )
        for name in BODY_JOINT_NAMES
    }
    public = {
        key: value
        for key, value in base.items()
        if key not in {"actual_points", "simulated_points", "simulated_states"}
    }
    public.update(
        {
            "per_joint_signed_mean_error_degrees": dict(
                zip(BODY_JOINT_NAMES, np.mean(error, axis=0).tolist(), strict=True)
            ),
            "stationary_row_count": int(np.sum(stationary)),
            "stationary_elbow_flex_rms_degrees": float(np.sqrt(np.mean(error[stationary, elbow_index] ** 2))),
            "stationary_elbow_flex_signed_mean_error_degrees": float(np.mean(error[stationary, elbow_index])),
            "stationary_elbow_flex_absolute_signed_mean_error_degrees": float(abs(np.mean(error[stationary, elbow_index]))),
            "dynamic_row_count": int(np.sum(dynamic)),
            "dynamic_elbow_flex_rms_degrees": float(np.sqrt(np.mean(error[dynamic, elbow_index] ** 2))),
            "dynamic_overall_joint_rms_degrees": float(np.sqrt(np.mean(error[dynamic] ** 2))),
            "stall_reproduction_fraction": stall_fraction,
            "command_transition_count": len(schedule["source_index_transitions"]),
            "load_torque_summary": copy.deepcopy(dict(torque)),
        }
    )
    return public


def _relative_change(candidate: float, reference: float) -> float:
    denominator = abs(reference)
    return float((candidate - reference) / denominator) if denominator > 1e-15 else 0.0


def _signature_evaluation(
    config: Mapping[str, Any], trial_metrics: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    baseline = trial_metrics["stride1_load0"]
    slow = trial_metrics["stride2_load0"]
    loaded = trial_metrics["stride1_loadm1500"]
    timing_values = {
        "timing-dynamic-rate-sensitivity": _relative_change(
            slow["dynamic_elbow_flex_rms_degrees"], baseline["dynamic_elbow_flex_rms_degrees"]
        ),
        "timing-common-dynamic-sensitivity": _relative_change(
            slow["dynamic_overall_joint_rms_degrees"], baseline["dynamic_overall_joint_rms_degrees"]
        ),
        "timing-load-nonspecific": _relative_change(
            loaded["stationary_elbow_flex_rms_degrees"], baseline["stationary_elbow_flex_rms_degrees"]
        ),
    }
    stationary_improvement = -_relative_change(
        loaded["stationary_elbow_flex_rms_degrees"], baseline["stationary_elbow_flex_rms_degrees"]
    )
    dynamic_improvement = -_relative_change(
        loaded["dynamic_elbow_flex_rms_degrees"], baseline["dynamic_elbow_flex_rms_degrees"]
    )
    load_values: dict[str, float | bool] = {
        "load-stationary-elbow-rms": -stationary_improvement,
        "load-stationary-elbow-bias": _relative_change(
            loaded["stationary_elbow_flex_absolute_signed_mean_error_degrees"],
            baseline["stationary_elbow_flex_absolute_signed_mean_error_degrees"],
        ),
        "load-locality": stationary_improvement > dynamic_improvement,
    }
    values: dict[str, Mapping[str, float | bool]] = {
        "timing_delay": timing_values,
        "load_compliance": load_values,
    }
    evaluated: dict[str, Any] = {}
    for mechanism_id, mechanism in config["mechanism_preregistration"].items():
        rows = []
        required_matches = []
        for signature in mechanism["predicted_signatures"]:
            observed = values[mechanism_id][signature["signature_id"]]
            direction = signature["direction"]
            threshold = float(signature["minimum_relative_magnitude"])
            if direction == "increase":
                matched: bool | None = bool(float(observed) >= threshold)
            elif direction == "decrease":
                matched = bool(float(observed) <= -threshold)
            elif direction == "true":
                matched = bool(observed)
            elif direction == "not_required_for_timing_support":
                matched = None
            else:  # pragma: no cover - load_config fixes the inventory
                raise ProspectiveSimulatorError(f"unsupported signature direction: {direction}")
            rows.append({**copy.deepcopy(signature), "observed": observed, "matched": matched})
            if matched is not None:
                required_matches.append(matched)
        score = float(sum(required_matches) / len(required_matches))
        evaluated[mechanism_id] = {
            "status_before_run": mechanism["status_before_run"],
            "signatures": rows,
            "matched_required_signatures": sum(required_matches),
            "required_signature_count": len(required_matches),
            "score": score,
            "status_after_run": "simulator_signature_supported" if score >= (2.0 / 3.0) else "simulator_signature_weak_or_contradicted",
            "physical_mechanism_identified": False,
        }
    return evaluated


def _compensating_fit(
    config: Mapping[str, Any], trial_metrics: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    rule = config["evaluator"]["compensating_fit_rejection"]
    candidate = trial_metrics[rule["candidate_trial_id"]]
    reference = trial_metrics[rule["reference_trial_id"]]
    aggregate_improvement = candidate["overall_joint_rms_degrees"] < reference["overall_joint_rms_degrees"]
    ee_regression = _relative_change(candidate["ee_rms_m"], reference["ee_rms_m"])
    per_joint_regressions = {
        name: _relative_change(candidate["per_joint_rms_degrees"][name], reference["per_joint_rms_degrees"][name])
        for name in BODY_JOINT_NAMES
    }
    dynamic_regression = _relative_change(
        candidate["dynamic_elbow_flex_rms_degrees"], reference["dynamic_elbow_flex_rms_degrees"]
    )
    guard_failures = []
    if ee_regression > float(rule["reject_on_ee_rms_relative_regression_over"]):
        guard_failures.append("ee_rms_relative_regression")
    if any(value > float(rule["reject_on_any_per_joint_rms_relative_regression_over"]) for value in per_joint_regressions.values()):
        guard_failures.append("per_joint_rms_relative_regression")
    if dynamic_regression > float(rule["reject_on_dynamic_elbow_rms_relative_regression_over"]):
        guard_failures.append("dynamic_elbow_rms_relative_regression")
    rejected = bool(aggregate_improvement and guard_failures)
    return {
        "candidate_trial_id": rule["candidate_trial_id"],
        "reference_trial_id": rule["reference_trial_id"],
        "aggregate_joint_rms_improved": aggregate_improvement,
        "ee_rms_relative_change": ee_regression,
        "per_joint_rms_relative_changes": per_joint_regressions,
        "dynamic_elbow_rms_relative_change": dynamic_regression,
        "guard_failures": guard_failures,
        "rejected_as_compensating_fit": rejected,
        "rule_changed_after_execution": False,
    }


def _posterior_and_next_probe(
    config: Mapping[str, Any], signatures: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    scores = {name: float(value["score"]) for name, value in signatures.items()}
    normalizer = sum(score + 0.25 for score in scores.values())
    weights = {name: float((score + 0.25) / normalizer) for name, score in scores.items()}
    best_score = max(scores.values())
    winners = sorted(name for name, score in scores.items() if abs(score - best_score) <= 1e-12)
    if len(winners) == 1:
        selected_mechanism = winners[0]
        next_probe = config["evaluator"]["next_probe_policy"][selected_mechanism]
        reason = "unique highest preregistered simulator signature score"
    else:
        selected_mechanism = None
        next_probe = config["evaluator"]["next_probe_policy"]["tie"]
        reason = "score tie retained both families; tie policy selects a rate discriminator"
    posterior = {
        "family_id": "prospective-load-timing-posterior-v1",
        "weights": weights,
        "scores": scores,
        "retained_mechanism_ids": sorted(scores),
        "selected_simulator_explanation": selected_mechanism,
        "physical_parameter_posterior": False,
        "normalization": "(signature_score + 0.25) normalized across preregistered families",
    }
    decision = {
        "selected_next_probe_id": next_probe,
        "reason": reason,
        "selected_mechanism_id": selected_mechanism,
        "decision_rule_changed_after_execution": False,
        "hardware_probe_selected_for_execution": False,
    }
    return posterior, decision


def _graph_delta(
    *,
    config: Mapping[str, Any],
    trial_rows: list[Mapping[str, Any]],
    signatures: Mapping[str, Any],
    posterior: Mapping[str, Any],
    next_probe: Mapping[str, Any],
    config_binding: Mapping[str, Any],
) -> dict[str, Any]:
    intervention_id = f"intervention:{config['acquisition_decision']['selected_probe_id']}"
    nodes: list[dict[str, Any]] = [
        {
            "id": intervention_id,
            "type": "intervention",
            "status": "executed_prospective_simulator",
            "source": copy.deepcopy(dict(config_binding)),
        }
    ]
    edges: list[dict[str, str]] = []
    for row in trial_rows:
        candidate_id = f"candidate:{row['trial_id']}"
        verdict_id = f"verdict:{row['trial_id']}"
        nodes.extend(
            [
                {"id": candidate_id, "type": "candidate", "status": row["retention_status"], "source": copy.deepcopy(dict(config_binding))},
                {"id": verdict_id, "type": "verdict", "status": row["retention_status"], "source": copy.deepcopy(dict(config_binding))},
            ]
        )
        edges.extend(
            [
                {"source": candidate_id, "type": "generated-from", "target": intervention_id},
                {"source": candidate_id, "type": "evaluated-on", "target": verdict_id},
            ]
        )
    posterior_id = "posterior:prospective-load-timing-v1"
    freeze_id = f"prediction-freeze:{config['phase2_prediction_freeze']['freeze_id']}"
    nodes.extend(
        [
            {"id": posterior_id, "type": "posterior", "status": "frozen_for_phase2", "data": copy.deepcopy(dict(posterior)), "source": copy.deepcopy(dict(config_binding))},
            {"id": freeze_id, "type": "prediction_freeze", "status": "frozen_before_physical_observation", "source": copy.deepcopy(dict(config_binding))},
        ]
    )
    edges.extend(
        [
            {"source": intervention_id, "type": "updates", "target": posterior_id},
            {"source": posterior_id, "type": "selects-next-probe", "target": f"intervention:{next_probe['selected_next_probe_id']}"},
            {"source": posterior_id, "type": "freezes", "target": freeze_id},
        ]
    )
    unsigned = {
        "schema_version": GRAPH_SCHEMA,
        "campaign_id": config["campaign_id"],
        "parent_graph": copy.deepcopy(config["source_bindings"]["parent_belief_graph"]),
        "nodes": nodes,
        "edges": edges,
        "mechanism_signature_evaluation": copy.deepcopy(dict(signatures)),
        "historical_graph_mutated": False,
        "graph_native": True,
    }
    return {**unsigned, "graph_delta_digest": canonical_digest(unsigned)}


def build_experiment(
    config: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, np.ndarray]]:
    mapped = _mapped_trace(config, sources)
    workcell = _workcell(sources["workcell_and_load_receipt"])
    initial_action_digest = _array_sha256(mapped["actions"])
    trials: list[dict[str, Any]] = []
    states_by_trial: dict[str, np.ndarray] = {}
    metrics_by_trial: dict[str, dict[str, Any]] = {}
    schedule_by_trial: dict[str, dict[str, Any]] = {}
    for declared in config["declared_trials"]:
        _require(_array_sha256(mapped["actions"]) == initial_action_digest, "action tensor changed before trial")
        simulated, schedule, torque = _simulate_trial(
            mapped=mapped,
            workcell=workcell,
            protocol=config["simulator_protocol"],
            trial=declared,
        )
        _require(_array_sha256(mapped["actions"]) == initial_action_digest, "action tensor changed during trial")
        metrics = _subgroup_metrics(
            mapped=mapped,
            simulated=simulated,
            config=config,
            workcell=workcell,
            schedule=schedule,
            torque=torque,
        )
        trial_id = declared["trial_id"]
        states_by_trial[trial_id] = simulated
        metrics_by_trial[trial_id] = metrics
        schedule_by_trial[trial_id] = schedule
        trials.append(
            {
                "trial_id": trial_id,
                "declared": copy.deepcopy(dict(declared)),
                "execution_status": "completed_declared_budget",
                "action_identity": {
                    "shape": list(mapped["actions"].shape),
                    "dtype": str(mapped["actions"].dtype),
                    "ordering": config["action_contract"]["ordering"],
                    "sha256": _array_sha256(mapped["actions"]),
                    "exact_evidence_trace_equality": True,
                    "array_mutated": False,
                },
                "schedule": schedule,
                "metrics": metrics,
                "missing_consequence_channels": copy.deepcopy(config["evaluator"]["missing_consequence_channels"]),
                "consequence_status": "not_evaluable_no_imputation",
            }
        )

    signatures = _signature_evaluation(config, metrics_by_trial)
    compensating = _compensating_fit(config, metrics_by_trial)
    baseline = metrics_by_trial["stride1_load0"]
    for row in trials:
        trial_id = row["trial_id"]
        if trial_id == "stride1_load0":
            status = "control_retained"
        elif trial_id == compensating["candidate_trial_id"] and compensating["rejected_as_compensating_fit"]:
            status = "rejected_compensating_fit_retained"
        elif (
            metrics_by_trial[trial_id]["overall_joint_rms_degrees"] > baseline["overall_joint_rms_degrees"]
            and metrics_by_trial[trial_id]["ee_rms_m"] > baseline["ee_rms_m"]
        ):
            status = "negative_result_retained"
        else:
            status = "diagnostic_result_retained"
        row["retention_status"] = status

    posterior, next_probe = _posterior_and_next_probe(config, signatures)
    eligible = [
        row
        for row in trials
        if row["retention_status"] != "rejected_compensating_fit_retained"
    ]
    selected_trial = min(
        eligible,
        key=lambda row: (
            row["metrics"]["overall_joint_rms_degrees"],
            row["metrics"]["ee_rms_m"],
            row["trial_id"],
        ),
    )
    experiment_unsigned = {
        "schema_version": EXPERIMENT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "proof_class": config["proof_class"],
        "claim_boundary": config["claim_boundary"],
        "preregistered_at": config["preregistered_at"],
        "source_bindings": copy.deepcopy(config["source_bindings"]),
        "acquisition_decision": copy.deepcopy(config["acquisition_decision"]),
        "mechanism_preregistration": copy.deepcopy(config["mechanism_preregistration"]),
        "declared_budget": copy.deepcopy(config["budget_and_stops"]),
        "action_invariance": {
            "expected": copy.deepcopy(config["action_contract"]),
            "observed_sha256": initial_action_digest,
            "all_trial_shape_dtype_order_values_hash_identical": all(
                row["action_identity"]["sha256"] == initial_action_digest for row in trials
            ),
            "full_tensor_retained_as_input_for_every_trial": True,
        },
        "trial_results": copy.deepcopy(trials),
        "predicted_versus_observed_signatures": signatures,
        "compensating_fit_evaluation": compensating,
        "loop_closure_next_probe": next_probe,
        "frozen_simulator_family": {
            "selected_trial_id_for_simulator_diagnostic": selected_trial["trial_id"],
            "selection_metric_order": ["overall_joint_rms_degrees", "ee_rms_m", "trial_id"],
            "retained_trial_ids": [row["trial_id"] for row in trials],
            "rejected_compensating_fit_trial_ids": [
                row["trial_id"] for row in trials if row["retention_status"] == "rejected_compensating_fit_retained"
            ],
            "simulator_composite_promoted": False,
            "physical_parameter_identified": False,
        },
        "frozen_posterior_family": posterior,
        "phase2_prediction_freeze": copy.deepcopy(config["phase2_prediction_freeze"]),
        "execution_accounting": {
            "episode_count": 1,
            "declared_trial_count": len(config["declared_trials"]),
            "executed_trial_count": len(trials),
            "retry_count": 0,
            "undeclared_trial_count": 0,
            "post_hoc_grid_expansion": False,
            "stopped_trial_count": 0,
            "all_results_retained": True,
        },
        "missing_channels": copy.deepcopy(config["evaluator"]["missing_consequence_channels"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    experiment = {**experiment_unsigned, "experiment_digest": canonical_digest(experiment_unsigned)}
    return experiment, trials, states_by_trial


def _trial_artifact(
    *,
    experiment: Mapping[str, Any],
    row: Mapping[str, Any],
    states: np.ndarray,
    mapped: Mapping[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": TRIAL_SCHEMA,
        "campaign_id": experiment["campaign_id"],
        "trial": copy.deepcopy(dict(row)),
        "trace": [
            {
                "sample_index": index,
                "elapsed_seconds": float(mapped["timestamps"][index]),
                "action_source_row": mapped["actions"][index].tolist(),
                "mapped_measured_joint_state": mapped["measured"][index].tolist(),
                "simulated_joint_state": states[index].tolist(),
            }
            for index in range(len(states))
        ],
        "physical_observation": False,
    }
    return {**unsigned, "trial_digest": canonical_digest(unsigned)}


def verify_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "unexpected prospective receipt schema")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "prospective receipt digest mismatch")
    _require(not any(normalized["authority"].values()), "prospective receipt authority widened")
    config_path = _repo_path(repo_root, normalized["config"]["path"], "receipt config")
    _require(sha256_file(config_path) == normalized["config"]["sha256"], "prospective config changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        _require(path.is_file() and sha256_file(path) == binding["sha256"], f"prospective output changed: {name}")
    _require(
        normalized["execution_accounting"]["executed_trial_count"]
        == normalized["execution_accounting"]["declared_trial_count"]
        == 4,
        "prospective trial accounting changed",
    )
    return {**normalized, "receipt_digest": observed}


def run_campaign(
    config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_config(resolved, repo_root=repo_root)
    sources = _load_sources(config, repo_root)
    experiment, trials, states_by_trial = build_experiment(config, sources)
    mapped = _mapped_trace(config, sources)
    output_root.mkdir(parents=True, exist_ok=True)
    trials_root = output_root / "trials"
    trials_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_root / "prospective_experiment.json", experiment)
    trial_bindings: dict[str, dict[str, str]] = {}
    for row in trials:
        path = trials_root / f"{row['trial_id']}.json"
        atomic_write_json(
            path,
            _trial_artifact(
                experiment=experiment,
                row=row,
                states=states_by_trial[row["trial_id"]],
                mapped=mapped,
            ),
        )
        trial_bindings[row["trial_id"]] = {
            "path": path.relative_to(output_root).as_posix(),
            "sha256": sha256_file(path),
        }
    config_binding = {
        "path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(),
        "sha256": sha256_file(resolved),
        "proof_class": config["proof_class"],
    }
    graph = _graph_delta(
        config=config,
        trial_rows=trials,
        signatures=experiment["predicted_versus_observed_signatures"],
        posterior=experiment["frozen_posterior_family"],
        next_probe=experiment["loop_closure_next_probe"],
        config_binding=config_binding,
    )
    freeze_unsigned = {
        "schema_version": FREEZE_SCHEMA,
        "campaign_id": config["campaign_id"],
        **copy.deepcopy(config["phase2_prediction_freeze"]),
        "posterior_family": copy.deepcopy(experiment["frozen_posterior_family"]),
        "simulator_family": copy.deepcopy(experiment["frozen_simulator_family"]),
        "loop_closure_next_probe": copy.deepcopy(experiment["loop_closure_next_probe"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    freeze = {**freeze_unsigned, "freeze_digest": canonical_digest(freeze_unsigned)}
    atomic_write_json(output_root / "prospective_graph_delta.json", graph)
    atomic_write_json(output_root / "phase2_prediction_freeze.json", freeze)
    outputs = {
        "experiment": {"path": "prospective_experiment.json", "sha256": sha256_file(output_root / "prospective_experiment.json")},
        "graph_delta": {"path": "prospective_graph_delta.json", "sha256": sha256_file(output_root / "prospective_graph_delta.json")},
        "phase2_prediction_freeze": {"path": "phase2_prediction_freeze.json", "sha256": sha256_file(output_root / "phase2_prediction_freeze.json")},
        **{f"trial:{name}": binding for name, binding in sorted(trial_bindings.items())},
    }
    receipt_unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "preregistered_at": config["preregistered_at"],
        "config": {"path": config_binding["path"], "sha256": config_binding["sha256"]},
        "compiler_sha256": sha256_file(Path(__file__).resolve()),
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "execution_accounting": copy.deepcopy(experiment["execution_accounting"]),
        "action_invariance": copy.deepcopy(experiment["action_invariance"]),
        "mechanism_scores": {
            name: row["score"] for name, row in experiment["predicted_versus_observed_signatures"].items()
        },
        "selected_next_probe_id": experiment["loop_closure_next_probe"]["selected_next_probe_id"],
        "selected_simulator_trial_id": experiment["frozen_simulator_family"]["selected_trial_id_for_simulator_diagnostic"],
        "phase2_prediction_freeze_digest": freeze["freeze_digest"],
        "physical_observations_consumed": 0,
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**receipt_unsigned, "receipt_digest": canonical_digest(receipt_unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_prospective_simulator_run_result.v1",
        "status": "completed_declared_budget",
        "trial_count": len(trials),
        "mechanism_scores": receipt["mechanism_scores"],
        "selected_next_probe_id": receipt["selected_next_probe_id"],
        "selected_simulator_trial_id": receipt["selected_simulator_trial_id"],
        "experiment_sha256": outputs["experiment"]["sha256"],
        "graph_delta_sha256": outputs["graph_delta"]["sha256"],
        "phase2_prediction_freeze_sha256": outputs["phase2_prediction_freeze"]["sha256"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "ProspectiveSimulatorError",
    "build_experiment",
    "load_config",
    "run_campaign",
    "verify_receipt",
]
