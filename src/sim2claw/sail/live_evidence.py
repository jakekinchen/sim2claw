"""Fail-closed offline evidence admission for the SAIL decision control plane.

This module deliberately contains no simulator executor, physical gateway, camera,
serial, teleoperation, or force-device integration.  It verifies files produced by
an independently owned evaluator and maintains replay-safe generated campaign state.
"""

from __future__ import annotations

import copy
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .importers import load_json_object


SIMULATOR_RECEIPT_SCHEMA = "sim2claw.sail_simulator_evaluator_receipt.v2"
SIMULATOR_RESULT_SCHEMA = "sim2claw.sail_simulator_evaluated_result.v2"
MEASUREMENT_RECEIPT_SCHEMA = "sim2claw.sail_offline_measurement_evaluator_receipt.v1"
MEASUREMENT_RESULT_SCHEMA = "sim2claw.sail_offline_measurement_evaluated_result.v1"
MEASUREMENT_TRIALS_SCHEMA = "sim2claw.sail_offline_measurement_trials.v1"
CAMPAIGN_STATE_SCHEMA = "sim2claw.sail_live_campaign_state.v2"
ZERO_DIGEST = "0" * 64


class EvidenceAdmissionError(ValueError):
    """Evaluator evidence or persistent campaign state failed closed."""


def _all_false(mapping: Mapping[str, Any], *, label: str) -> None:
    if not isinstance(mapping, Mapping) or not mapping or any(
        value is not False for value in mapping.values()
    ):
        raise EvidenceAdmissionError(f"{label} widened authority")


def _nonempty_unique(values: Sequence[Any], *, label: str) -> list[str]:
    normalized = [str(value) for value in values]
    if not normalized or any(not value for value in normalized) or len(normalized) != len(
        set(normalized)
    ):
        raise EvidenceAdmissionError(f"{label} identities are empty or duplicated")
    return normalized


def _reject_supplied_promotion(consequence: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(consequence, Mapping):
        raise EvidenceAdmissionError(f"{label} consequence is missing")
    normalized = copy.deepcopy(dict(consequence))
    if any("promotion" in str(name) for name in normalized):
        raise EvidenceAdmissionError(f"{label} consequence may not supply promotion")
    for name in ("training_admitted", "physical_authority", "robot_motion"):
        if normalized.get(name) is True:
            raise EvidenceAdmissionError(f"{label} consequence widened authority")
    return normalized


def _verify_digest(payload: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise EvidenceAdmissionError(f"{label} digest mismatch")
    return {**normalized, "receipt_digest": str(observed)}


def _resolve_artifact(
    binding: Mapping[str, Any], *, base_dir: Path, label: str
) -> tuple[Path, dict[str, Any]]:
    if set(binding) != {"path", "sha256"}:
        raise EvidenceAdmissionError(f"{label} binding field set changed")
    raw_path = Path(str(binding["path"]))
    path = raw_path.resolve() if raw_path.is_absolute() else (base_dir / raw_path).resolve()
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise EvidenceAdmissionError(f"{label} artifact hash mismatch")
    return path, {"path": str(binding["path"]), "sha256": str(binding["sha256"])}


def evaluator_identity(
    *,
    evaluator: Mapping[str, Any],
    evaluator_digest: str,
    source_sha256: Mapping[str, str],
    config_sha256: str,
    config_digest: str,
    compiler_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Build the exact evaluator/code/config/source identity a receipt must bind."""

    return {
        "evaluator_id": str(evaluator["evaluator_id"]),
        "owner": str(evaluator["owner"]),
        "release_index": evaluator.get("release_index"),
        "evaluator_digest": evaluator_digest,
        "source_sha256": dict(sorted((str(k), str(v)) for k, v in source_sha256.items())),
        "campaign_config_sha256": config_sha256,
        "campaign_config_digest": config_digest,
        "compiler_sha256": dict(
            sorted((str(k), str(v)) for k, v in compiler_sha256.items())
        ),
    }


def verify_simulator_evaluator_receipt(
    receipt_path: Path,
    *,
    campaign_id: str,
    selected_intervention: Mapping[str, Any],
    intervention_set_digest: str,
    action_sha256: str,
    expected_evaluator_identity: Mapping[str, Any],
    remaining_anchor_replays: int,
) -> dict[str, Any]:
    """Verify a hash-bound simulator evaluator receipt and its result artifact."""

    receipt = _verify_digest(
        load_json_object(receipt_path, label="simulator evaluator receipt"),
        label="simulator evaluator receipt",
    )
    if receipt.get("schema_version") != SIMULATOR_RECEIPT_SCHEMA:
        raise EvidenceAdmissionError("unexpected simulator evaluator receipt schema")
    if receipt.get("campaign_id") != campaign_id:
        raise EvidenceAdmissionError("simulator receipt campaign identity changed")
    intervention_id = str(selected_intervention["intervention_id"])
    if receipt.get("selected_intervention") != intervention_id:
        raise EvidenceAdmissionError("simulator receipt does not bind the selected intervention")
    if receipt.get("frozen_intervention_set_digest") != intervention_set_digest:
        raise EvidenceAdmissionError("simulator receipt intervention set changed")
    if receipt.get("action_sha256") != action_sha256:
        raise EvidenceAdmissionError("simulator receipt action identity changed")
    if receipt.get("evaluator_identity") != expected_evaluator_identity:
        raise EvidenceAdmissionError("simulator receipt evaluator code/config/source identity changed")
    if "promotion" in receipt:
        raise EvidenceAdmissionError("simulator receipt may not self-describe promotion")
    _all_false(receipt.get("authority") or {}, label="simulator receipt")
    execution_id = str(receipt.get("execution_id", ""))
    if not execution_id:
        raise EvidenceAdmissionError("simulator receipt execution identity is missing")
    replay_ids = _nonempty_unique(
        receipt.get("anchor_replay_ids") or [], label="simulator anchor replay"
    )
    maximum_trials = int(selected_intervention["maximum_trials"])
    if len(replay_ids) > maximum_trials or len(replay_ids) > remaining_anchor_replays:
        raise EvidenceAdmissionError("simulator receipt escaped the anchor replay budget")
    actual_mutations = [str(value) for value in receipt.get("actual_mutations") or []]
    if len(actual_mutations) != len(set(actual_mutations)) or not set(
        actual_mutations
    ).issubset({str(value) for value in selected_intervention["allowed_mutations"]}):
        raise EvidenceAdmissionError("simulator receipt used an undeclared mutation")
    base_dir = receipt_path.resolve().parent
    raw_bindings = receipt.get("raw_artifacts") or []
    if not raw_bindings:
        raise EvidenceAdmissionError("simulator receipt has no raw evaluator artifacts")
    verified_raw = [
        _resolve_artifact(binding, base_dir=base_dir, label="simulator raw")[1]
        for binding in raw_bindings
    ]
    result_path, result_binding = _resolve_artifact(
        receipt.get("result_artifact") or {},
        base_dir=base_dir,
        label="simulator result",
    )
    result = load_json_object(result_path, label="simulator evaluated result")
    if result.get("schema_version") != SIMULATOR_RESULT_SCHEMA:
        raise EvidenceAdmissionError("unexpected simulator evaluated result schema")
    if "promotion" in result:
        raise EvidenceAdmissionError("simulator result may not self-describe promotion")
    if result.get("authority") != receipt.get("authority"):
        raise EvidenceAdmissionError("simulator result authority is not receipt-bound")
    consequence = _reject_supplied_promotion(
        receipt.get("consequence"), label="simulator receipt"
    )
    required_equal = {
        "campaign_id": campaign_id,
        "selected_intervention": intervention_id,
        "execution_id": execution_id,
        "anchor_replay_ids": replay_ids,
        "actual_mutations": actual_mutations,
        "consequence": consequence,
    }
    for name, expected in required_equal.items():
        if result.get(name) != expected:
            raise EvidenceAdmissionError(f"simulator result {name} is not receipt-bound")
    if not isinstance(result.get("hypothesis_likelihoods"), Mapping):
        raise EvidenceAdmissionError("simulator result likelihoods are missing")
    if not isinstance(result.get("factor_updates"), Mapping):
        raise EvidenceAdmissionError("simulator result factor updates are missing")
    return {
        "lane": "simulator_anchor_replay",
        "receipt": receipt,
        "receipt_sha256": sha256_file(receipt_path),
        "execution_id": execution_id,
        "anchor_replay_ids": replay_ids,
        "measurement_trial_ids": [],
        "actual_mutations": actual_mutations,
        "raw_artifacts": verified_raw,
        "result_artifact": result_binding,
        "result": result,
        "consequence": consequence,
    }


def _normalized(values: np.ndarray) -> np.ndarray:
    span = float(np.max(values) - np.min(values))
    if span <= 1e-12:
        return np.zeros_like(values)
    return (values - np.min(values)) / span


def _trial_features(trial: Mapping[str, Any]) -> dict[str, float]:
    arrays: dict[str, np.ndarray] = {}
    for name in ("jaw_force_n", "deformation_mm", "motor_current_a", "patch_area_mm2"):
        values = np.asarray(trial.get(name), dtype=np.float64)
        if values.ndim != 1 or values.size < 5 or not np.all(np.isfinite(values)):
            raise EvidenceAdmissionError(f"measurement trial {name} vector is invalid")
        arrays[name] = values
    sizes = {values.size for values in arrays.values()}
    phases = [str(value) for value in trial.get("phase_labels") or []]
    if len(sizes) != 1 or len(phases) != next(iter(sizes)):
        raise EvidenceAdmissionError("measurement trial vectors are not sample-aligned")
    force = arrays["jaw_force_n"]
    deformation = arrays["deformation_mm"]
    current = arrays["motor_current_a"]
    patch = arrays["patch_area_mm2"]
    if np.std(force) <= 1e-12 or np.std(deformation) <= 1e-12:
        coupling = 0.0
    else:
        coupling = float(np.corrcoef(force, deformation)[0, 1])
        if not np.isfinite(coupling):
            coupling = 0.0
        coupling = float(np.clip(coupling, 0.0, 1.0))
    force_n = _normalized(force)
    current_n = _normalized(current)
    loop_area = abs(
        float(
            np.sum(
                0.5
                * (current_n[:-1] + current_n[1:])
                * (force_n[1:] - force_n[:-1])
            )
        )
    )
    hysteresis = float(np.clip(loop_area, 0.0, 1.0))
    unloaded = np.asarray([phase == "unloaded close" for phase in phases])
    loaded = np.asarray([phase == "loaded hold" for phase in phases])
    if not np.any(unloaded) or not np.any(loaded):
        raise EvidenceAdmissionError("measurement trial lacks unloaded or loaded feature phase")
    baseline = float(np.mean(patch[unloaded]))
    loaded_mean = float(np.mean(patch[loaded]))
    patch_change = float(
        np.clip(abs(loaded_mean - baseline) / max(abs(baseline), abs(loaded_mean), 1e-12), 0.0, 1.0)
    )
    return {
        "force_deformation_coupling": coupling,
        "current_force_hysteresis": hysteresis,
        "loaded_patch_change": patch_change,
    }


def evaluate_offline_measurement_trials(
    artifacts: Sequence[Mapping[str, Any]],
    *,
    campaign_id: str,
    selected_intervention: str,
    packet: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate already-recorded synthetic measurement fixtures without device I/O."""

    allowed_proof_classes = {
        str(value) for value in evaluation_contract.get("allowed_proof_classes") or []
    }
    if allowed_proof_classes != {"synthetic_measurement_fixture"}:
        raise EvidenceAdmissionError("measurement lane is not restricted to synthetic fixtures")
    trials: list[dict[str, Any]] = []
    common_clock: str | None = None
    required_calibration = [str(value) for value in packet["calibration"]]
    required_phases = [str(value) for value in packet["required_phases"]]
    minimum_sampling_hz = float(packet["minimum_sampling_hz"])
    maximum_skew = int(packet["maximum_alignment_skew_samples"])
    for artifact in artifacts:
        if artifact.get("schema_version") != MEASUREMENT_TRIALS_SCHEMA:
            raise EvidenceAdmissionError("unexpected offline measurement trials schema")
        if artifact.get("campaign_id") != campaign_id:
            raise EvidenceAdmissionError("measurement trials campaign identity changed")
        if artifact.get("selected_intervention") != selected_intervention:
            raise EvidenceAdmissionError("measurement trials intervention identity changed")
        if str(artifact.get("proof_class", "")) not in allowed_proof_classes:
            raise EvidenceAdmissionError("measurement trials proof class is not admitted")
        _all_false(artifact.get("authority") or {}, label="measurement trials")
        for raw_trial in artifact.get("trials") or []:
            trial = copy.deepcopy(dict(raw_trial))
            trial_id = str(trial.get("trial_id", ""))
            clock_id = str(trial.get("clock_id", ""))
            if not trial_id or not clock_id:
                raise EvidenceAdmissionError("measurement trial identity or clock is missing")
            if common_clock is None:
                common_clock = clock_id
            elif clock_id != common_clock:
                raise EvidenceAdmissionError("measurement trials do not share one clock")
            if float(trial.get("sampling_hz", -1.0)) < minimum_sampling_hz:
                raise EvidenceAdmissionError("measurement trial sampling rate is below the packet")
            if int(trial.get("maximum_alignment_skew_samples", -1)) > maximum_skew:
                raise EvidenceAdmissionError("measurement trial alignment skew exceeds the packet")
            if [str(value) for value in trial.get("calibration_completed") or []] != required_calibration:
                raise EvidenceAdmissionError("measurement trial calibration does not match the packet")
            if [str(value) for value in trial.get("phases_completed") or []] != required_phases:
                raise EvidenceAdmissionError("measurement trial phases do not match the packet")
            trials.append({"trial_id": trial_id, "features": _trial_features(trial)})
    trial_ids = _nonempty_unique(
        [row["trial_id"] for row in trials], label="offline measurement trial"
    )
    names = (
        "force_deformation_coupling",
        "current_force_hysteresis",
        "loaded_patch_change",
    )
    feature_summary = {
        name: float(np.median([row["features"][name] for row in trials])) for name in names
    }
    thresholds = evaluation_contract["thresholds"]
    flexural = (
        feature_summary["force_deformation_coupling"]
        >= float(thresholds["flexural_min_force_deformation_coupling"])
        and feature_summary["current_force_hysteresis"]
        <= float(thresholds["flexural_max_current_force_hysteresis"])
        and feature_summary["loaded_patch_change"]
        >= float(thresholds["flexural_min_loaded_patch_change"])
    )
    actuator = (
        feature_summary["force_deformation_coupling"]
        <= float(thresholds["actuator_max_force_deformation_coupling"])
        and feature_summary["current_force_hysteresis"]
        >= float(thresholds["actuator_min_current_force_hysteresis"])
        and feature_summary["loaded_patch_change"]
        <= float(thresholds["actuator_max_loaded_patch_change"])
    )
    flexural_id = str(evaluation_contract["flexural_mechanism_id"])
    actuator_id = str(evaluation_contract["actuator_mechanism_id"])
    if flexural and actuator:
        raise EvidenceAdmissionError("measurement classification thresholds overlap")
    if flexural:
        classification = "flexural_dominant"
        likelihoods = {flexural_id: 0.9, actuator_id: 0.1}
    elif actuator:
        classification = "actuator_dominant"
        likelihoods = {flexural_id: 0.1, actuator_id: 0.9}
    else:
        classification = "ambiguous_abstention"
        likelihoods = {flexural_id: 1.0, actuator_id: 1.0}
    consequence = {
        "status": f"offline_measurement_{classification}",
        "evaluator_passed": False,
        "physical_mechanism_identified": False,
        "proof_class": "synthetic_measurement_fixture",
    }
    return {
        "measurement_trial_ids": trial_ids,
        "common_clock_id": common_clock,
        "feature_algorithms": copy.deepcopy(evaluation_contract["feature_algorithms"]),
        "trial_features": trials,
        "feature_summary": feature_summary,
        "classification": classification,
        "hypothesis_likelihoods": likelihoods,
        "factor_updates": {},
        "consequence": consequence,
    }


def verify_measurement_evaluator_receipt(
    receipt_path: Path,
    *,
    campaign_id: str,
    selected_intervention: Mapping[str, Any],
    intervention_set_digest: str,
    action_sha256: str,
    expected_evaluator_identity: Mapping[str, Any],
    expected_packet: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
    remaining_measurement_trials: int,
) -> dict[str, Any]:
    """Verify a packet-bound, synthetic-only offline measurement result receipt."""

    receipt = _verify_digest(
        load_json_object(receipt_path, label="offline measurement evaluator receipt"),
        label="offline measurement evaluator receipt",
    )
    if receipt.get("schema_version") != MEASUREMENT_RECEIPT_SCHEMA:
        raise EvidenceAdmissionError("unexpected offline measurement evaluator receipt schema")
    intervention_id = str(selected_intervention["intervention_id"])
    required = {
        "campaign_id": campaign_id,
        "selected_intervention": intervention_id,
        "frozen_intervention_set_digest": intervention_set_digest,
        "action_sha256": action_sha256,
        "evaluator_identity": expected_evaluator_identity,
    }
    for name, expected in required.items():
        if receipt.get(name) != expected:
            raise EvidenceAdmissionError(f"measurement receipt {name} changed")
    if "promotion" in receipt:
        raise EvidenceAdmissionError("measurement receipt may not self-describe promotion")
    _all_false(receipt.get("authority") or {}, label="measurement receipt")
    if receipt.get("actual_mutations") != []:
        raise EvidenceAdmissionError("measurement receipt declared a mutation")
    execution_id = str(receipt.get("execution_id", ""))
    if not execution_id:
        raise EvidenceAdmissionError("measurement receipt execution identity is missing")
    base_dir = receipt_path.resolve().parent
    packet_path, packet_binding = _resolve_artifact(
        receipt.get("acquisition_packet") or {}, base_dir=base_dir, label="acquisition packet"
    )
    packet = load_json_object(packet_path, label="sealed acquisition packet")
    if packet != expected_packet or packet.get("packet_digest") != expected_packet.get(
        "packet_digest"
    ):
        raise EvidenceAdmissionError("measurement receipt is not bound to the sealed packet")
    raw_payloads: list[dict[str, Any]] = []
    verified_raw: list[dict[str, Any]] = []
    for binding in receipt.get("raw_artifacts") or []:
        raw_path, verified_binding = _resolve_artifact(
            binding, base_dir=base_dir, label="measurement raw"
        )
        raw_payloads.append(load_json_object(raw_path, label="offline measurement raw artifact"))
        verified_raw.append(verified_binding)
    if not raw_payloads:
        raise EvidenceAdmissionError("measurement receipt has no raw artifacts")
    evaluated = evaluate_offline_measurement_trials(
        raw_payloads,
        campaign_id=campaign_id,
        selected_intervention=intervention_id,
        packet=packet,
        evaluation_contract=evaluation_contract,
    )
    receipt_trial_ids = _nonempty_unique(
        receipt.get("measurement_trial_ids") or [], label="measurement receipt trial"
    )
    if receipt_trial_ids != evaluated["measurement_trial_ids"]:
        raise EvidenceAdmissionError("measurement receipt trial identities changed")
    maximum_trials = int(selected_intervention["maximum_trials"])
    if len(receipt_trial_ids) > maximum_trials or len(receipt_trial_ids) > remaining_measurement_trials:
        raise EvidenceAdmissionError("measurement receipt escaped the measurement trial budget")
    result_path, result_binding = _resolve_artifact(
        receipt.get("result_artifact") or {}, base_dir=base_dir, label="measurement result"
    )
    result = load_json_object(result_path, label="offline measurement evaluated result")
    if result.get("schema_version") != MEASUREMENT_RESULT_SCHEMA or "promotion" in result:
        raise EvidenceAdmissionError("offline measurement result schema or promotion field is invalid")
    expected_result = {
        "schema_version": MEASUREMENT_RESULT_SCHEMA,
        "campaign_id": campaign_id,
        "selected_intervention": intervention_id,
        "execution_id": execution_id,
        "actual_mutations": [],
        "acquisition_packet_digest": packet["packet_digest"],
        **evaluated,
        "authority": copy.deepcopy(dict(receipt["authority"])),
    }
    if result != expected_result:
        raise EvidenceAdmissionError("offline measurement result does not match deterministic evaluation")
    if receipt.get("consequence") != evaluated["consequence"]:
        raise EvidenceAdmissionError("measurement receipt consequence is not evaluator-derived")
    return {
        "lane": "offline_measurement",
        "receipt": receipt,
        "receipt_sha256": sha256_file(receipt_path),
        "execution_id": execution_id,
        "anchor_replay_ids": [],
        "measurement_trial_ids": receipt_trial_ids,
        "actual_mutations": [],
        "acquisition_packet": packet_binding,
        "raw_artifacts": verified_raw,
        "result_artifact": result_binding,
        "result": result,
        "consequence": evaluated["consequence"],
    }


def _state_unsigned(state: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = copy.deepcopy(dict(state))
    unsigned.pop("state_digest", None)
    return unsigned


def _validate_budget(budget: Mapping[str, Any]) -> dict[str, int]:
    required = {
        "maximum_interventions",
        "maximum_anchor_replays",
        "maximum_measurement_trials",
        "used_interventions",
        "used_anchor_replays",
        "used_measurement_trials",
    }
    if set(budget) != required:
        raise EvidenceAdmissionError("persistent campaign budget field set changed")
    normalized = {name: int(budget[name]) for name in required}
    if (
        normalized["maximum_interventions"] <= 0
        or normalized["maximum_anchor_replays"] < 0
        or normalized["maximum_measurement_trials"] < 0
        or normalized["used_interventions"] < 0
        or normalized["used_anchor_replays"] < 0
        or normalized["used_measurement_trials"] < 0
        or normalized["used_interventions"] > normalized["maximum_interventions"]
        or normalized["used_anchor_replays"] > normalized["maximum_anchor_replays"]
        or normalized["used_measurement_trials"] > normalized["maximum_measurement_trials"]
    ):
        raise EvidenceAdmissionError("persistent campaign budget is invalid")
    return normalized


def _apply_delta(budget: Mapping[str, int], delta: Mapping[str, int]) -> dict[str, int]:
    after = dict(budget)
    after["used_interventions"] += int(delta["interventions"])
    after["used_anchor_replays"] += int(delta["anchor_replays"])
    after["used_measurement_trials"] += int(delta["measurement_trials"])
    return _validate_budget(after)


def _validate_state(
    state: Mapping[str, Any], *, campaign_id: str, config_digest: str, initial_budget: Mapping[str, Any]
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(state))
    if normalized.get("schema_version") != CAMPAIGN_STATE_SCHEMA:
        raise EvidenceAdmissionError("unexpected persistent campaign state schema")
    if normalized.get("campaign_id") != campaign_id or normalized.get("config_digest") != config_digest:
        raise EvidenceAdmissionError("persistent campaign state identity changed")
    expected_initial = _validate_budget(initial_budget)
    if normalized.get("initial_budget") != expected_initial:
        raise EvidenceAdmissionError("persistent campaign initial budget changed")
    if normalized.get("state_digest") != canonical_digest(_state_unsigned(normalized)):
        raise EvidenceAdmissionError("persistent campaign state digest mismatch")
    budget = dict(expected_initial)
    previous = ZERO_DIGEST
    execution_ids: set[str] = set()
    replay_ids: set[str] = set()
    trial_ids: set[str] = set()
    receipt_hashes: set[str] = set()
    result_hashes: set[str] = set()
    for sequence, raw_event in enumerate(normalized.get("events") or [], start=1):
        event = copy.deepcopy(dict(raw_event))
        observed_digest = event.pop("event_digest", None)
        if event.get("sequence") != sequence or event.get("previous_event_digest") != previous:
            raise EvidenceAdmissionError("persistent campaign receipt chain is discontinuous")
        if observed_digest != canonical_digest(event):
            raise EvidenceAdmissionError("persistent campaign event digest mismatch")
        execution_id = str(event.get("execution_id", ""))
        if not execution_id or execution_id in execution_ids:
            raise EvidenceAdmissionError("persistent campaign execution identity replayed")
        anchors = [str(value) for value in event.get("anchor_replay_ids") or []]
        trials = [str(value) for value in event.get("measurement_trial_ids") or []]
        if replay_ids.intersection(anchors) or trial_ids.intersection(trials):
            raise EvidenceAdmissionError("persistent campaign replay or trial identity replayed")
        receipt_sha = str(event.get("receipt_sha256", ""))
        result_sha = str(event.get("result_sha256", ""))
        if receipt_sha in receipt_hashes or result_sha in result_hashes:
            raise EvidenceAdmissionError("persistent campaign full result replayed")
        budget = _apply_delta(budget, event["budget_delta"])
        if event.get("budget_after") != budget:
            raise EvidenceAdmissionError("persistent campaign budget chain changed")
        execution_ids.add(execution_id)
        replay_ids.update(anchors)
        trial_ids.update(trials)
        receipt_hashes.add(receipt_sha)
        result_hashes.add(result_sha)
        previous = str(observed_digest)
    if normalized.get("budget") != budget or normalized.get("chain_head") != previous:
        raise EvidenceAdmissionError("persistent campaign state head or budget changed")
    return normalized


def _initial_state(
    *, campaign_id: str, config_digest: str, initial_budget: Mapping[str, Any]
) -> dict[str, Any]:
    unsigned = {
        "schema_version": CAMPAIGN_STATE_SCHEMA,
        "campaign_id": campaign_id,
        "config_digest": config_digest,
        "initial_budget": _validate_budget(initial_budget),
        "budget": _validate_budget(initial_budget),
        "events": [],
        "chain_head": ZERO_DIGEST,
    }
    return {**unsigned, "state_digest": canonical_digest(unsigned)}


@contextmanager
def locked_campaign_state(
    output_root: Path,
    *,
    campaign_id: str,
    config_digest: str,
    initial_budget: Mapping[str, Any],
) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Hold an exclusive file lock while validating/updating generated state."""

    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".campaign-state.lock"
    state_path = output_root / "campaign_state.json"
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        if state_path.exists():
            state = _validate_state(
                load_json_object(state_path, label="persistent SAIL campaign state"),
                campaign_id=campaign_id,
                config_digest=config_digest,
                initial_budget=initial_budget,
            )
        else:
            state = _initial_state(
                campaign_id=campaign_id,
                config_digest=config_digest,
                initial_budget=initial_budget,
            )
            atomic_write_json(state_path, state)
        yield state_path, state
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def append_admitted_result(state_path: Path, state: Mapping[str, Any], admission: Mapping[str, Any]) -> dict[str, Any]:
    """Atomically append one unique evaluator receipt to the validated chain."""

    events = copy.deepcopy(list(state["events"]))
    execution_ids = {str(event["execution_id"]) for event in events}
    replay_ids = {
        str(value) for event in events for value in event.get("anchor_replay_ids") or []
    }
    trial_ids = {
        str(value) for event in events for value in event.get("measurement_trial_ids") or []
    }
    receipt_hashes = {str(event["receipt_sha256"]) for event in events}
    result_hashes = {str(event["result_sha256"]) for event in events}
    execution_id = str(admission["execution_id"])
    anchors = [str(value) for value in admission["anchor_replay_ids"]]
    trials = [str(value) for value in admission["measurement_trial_ids"]]
    receipt_sha = str(admission["receipt_sha256"])
    result_sha = str(admission["result_artifact"]["sha256"])
    if (
        execution_id in execution_ids
        or replay_ids.intersection(anchors)
        or trial_ids.intersection(trials)
        or receipt_sha in receipt_hashes
        or result_sha in result_hashes
    ):
        raise EvidenceAdmissionError("evaluator result replay rejected by persistent campaign state")
    delta = {
        "interventions": 1,
        "anchor_replays": len(anchors),
        "measurement_trials": len(trials),
    }
    budget_after = _apply_delta(state["budget"], delta)
    event_unsigned = {
        "sequence": len(events) + 1,
        "previous_event_digest": str(state["chain_head"]),
        "lane": str(admission["lane"]),
        "execution_id": execution_id,
        "anchor_replay_ids": anchors,
        "measurement_trial_ids": trials,
        "receipt_sha256": receipt_sha,
        "receipt_digest": str(admission["receipt"]["receipt_digest"]),
        "result_sha256": result_sha,
        "budget_delta": delta,
        "budget_after": budget_after,
    }
    event = {**event_unsigned, "event_digest": canonical_digest(event_unsigned)}
    events.append(event)
    state_unsigned = {
        "schema_version": CAMPAIGN_STATE_SCHEMA,
        "campaign_id": state["campaign_id"],
        "config_digest": state["config_digest"],
        "initial_budget": copy.deepcopy(state["initial_budget"]),
        "budget": budget_after,
        "events": events,
        "chain_head": event["event_digest"],
    }
    updated = {**state_unsigned, "state_digest": canonical_digest(state_unsigned)}
    atomic_write_json(state_path, updated)
    return updated


__all__ = [
    "CAMPAIGN_STATE_SCHEMA",
    "EvidenceAdmissionError",
    "MEASUREMENT_RECEIPT_SCHEMA",
    "MEASUREMENT_RESULT_SCHEMA",
    "MEASUREMENT_TRIALS_SCHEMA",
    "SIMULATOR_RECEIPT_SCHEMA",
    "SIMULATOR_RESULT_SCHEMA",
    "append_admitted_result",
    "evaluate_offline_measurement_trials",
    "evaluator_identity",
    "locked_campaign_state",
    "verify_measurement_evaluator_receipt",
    "verify_simulator_evaluator_receipt",
]
