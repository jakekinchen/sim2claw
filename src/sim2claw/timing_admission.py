"""Separate CPU/fp32 admission evaluator for a frozen P9 timing candidate."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .recorded_replay import (
    RecordedEpisode,
    float64_tensor_sha256,
    load_sysid_config,
    nominal_parameter_values,
    sha256_file,
    simulate_and_align,
    validate_parameter_values,
)
from .system_identification import (
    TIMING_ADMISSION_SCHEMA,
    TIMING_COHORT_SCHEMA,
    TIMING_RESULT_SCHEMA,
    SystemIdentificationError,
    _derive_timing_evidence_identity,
    _freeze_timing_cohort_split,
    _load_verified_physical_episode,
    _validated_timing_evidence_identity,
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemIdentificationError(
            f"refusing to overwrite existing timing admission receipt: {path}"
        )
    data = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _family_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {key: item for key, item in value.items() if key != "digest"},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _fp32_huber_mean(residual: np.ndarray, delta: float) -> float:
    values = np.asarray(residual, dtype=np.float32)
    bound = np.float32(delta)
    absolute = np.abs(values)
    loss = np.where(
        absolute <= bound,
        np.float32(0.5) * values * values,
        bound * (absolute - np.float32(0.5) * bound),
    ).astype(np.float32)
    return float(np.mean(loss, dtype=np.float32))


def _evaluate_fp32(
    episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
    parameters: Mapping[str, float],
    *,
    model_base_directory: Path,
) -> dict[str, Any]:
    losses: list[np.float32] = []
    by_episode: dict[str, Any] = {}
    delta = float(config["loss"]["huber_delta"]["joint_position"])
    for episode in episodes:
        before = float64_tensor_sha256(episode.commands)
        replay = simulate_and_align(
            episode,
            config,
            parameter_values=parameters,
            model_base_directory=model_base_directory,
        )
        consumed = replay["control_diagnostics"]["replay_input_action_sha256"]
        if consumed != before or float64_tensor_sha256(episode.commands) != before:
            raise SystemIdentificationError(
                "CPU/fp32 admission replay mutated or changed an action tensor"
            )
        measured = episode.measured_array("joint_position")
        simulated = replay["simulated"].get("joint_position")
        if measured is None or simulated is None:
            raise SystemIdentificationError(
                "CPU/fp32 timing admission requires measured joint position"
            )
        residual = np.asarray(simulated, dtype=np.float32) - np.asarray(
            measured, dtype=np.float32
        )
        loss = np.float32(_fp32_huber_mean(residual, delta))
        losses.append(loss)
        by_episode[episode.episode_id] = {
            "mean_huber_loss_fp32": float(loss),
            "replay_input_action_sha256": consumed,
        }
    if not losses:
        raise SystemIdentificationError("CPU/fp32 admission held-out group is empty")
    array = np.asarray(losses, dtype=np.float32)
    return {
        "episode_count": len(losses),
        "mean_loss_fp32": float(np.mean(array, dtype=np.float32)),
        "maximum_loss_fp32": float(np.max(array)),
        "by_episode": by_episode,
    }


def _fp32_gate(
    baseline_loss: float,
    candidate_loss: float,
    acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = np.float32(baseline_loss)
    candidate = np.float32(candidate_loss)
    absolute = np.float32(baseline - candidate)
    relative = np.float32(
        absolute / np.maximum(np.abs(baseline), np.float32(1e-15))
    )
    minimum_absolute = np.float32(acceptance["minimum_absolute_improvement"])
    minimum_relative = np.float32(acceptance["minimum_relative_improvement"])
    passed = bool(
        candidate < baseline
        and absolute >= minimum_absolute
        and relative >= minimum_relative
    )
    return {
        "baseline_loss_fp32": float(baseline),
        "candidate_loss_fp32": float(candidate),
        "absolute_improvement_fp32": float(absolute),
        "relative_improvement_fp32": float(relative),
        "minimum_absolute_improvement": float(minimum_absolute),
        "minimum_relative_improvement": float(minimum_relative),
        "passed": passed,
    }


def admit_physical_timing_actuation_fit(
    fit_path: Path,
    cohort_path: Path,
    *,
    config_path: Path,
    output_path: Path,
    synthetic_fixture_mode: bool = False,
) -> dict[str, Any]:
    """Re-evaluate a frozen selection without fitting, ranking, or family search."""

    fit_path = fit_path.resolve()
    cohort_path = cohort_path.resolve()
    config_path = config_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise SystemIdentificationError(
            f"refusing to overwrite existing timing admission receipt: {output_path}"
        )
    fit_result = json.loads(fit_path.read_text(encoding="utf-8"))
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    config = load_sysid_config(config_path)
    if (
        fit_result.get("schema_version") != TIMING_RESULT_SCHEMA
        or fit_result.get("status") != "diagnostic_fit_complete"
        or fit_result.get("parameters_promoted") is not False
        or fit_result.get("evaluator_admission") is not False
        or fit_result.get("evaluator_owned") is not False
        or fit_result.get("self_scored") is not True
    ):
        raise SystemIdentificationError(
            "timing admission requires a self-scored, non-promoting diagnostic P9 fit"
        )
    if cohort.get("schema_version") != TIMING_COHORT_SCHEMA:
        raise SystemIdentificationError("timing admission cohort schema changed")
    rows = cohort.get("episodes")
    if not isinstance(rows, list) or not rows:
        raise SystemIdentificationError("timing admission cohort is empty")
    base = cohort_path.parent
    explicit_identity = cohort.get("identity")
    if explicit_identity is not None:
        identity = _validated_timing_evidence_identity(explicit_identity)
    else:
        source_identities = [
            _derive_timing_evidence_identity(
                (base / str(row.get("recording") or "")).resolve(),
                (
                    base / str(row.get("exact_replay_manifest") or "")
                ).resolve(),
            )
            for row in rows
            if isinstance(row, Mapping)
        ]
        if len(source_identities) != len(rows) or not source_identities:
            raise SystemIdentificationError(
                "timing admission cohort identity sources are malformed"
            )
        identity = source_identities[0]
        if any(candidate != identity for candidate in source_identities[1:]):
            raise SystemIdentificationError(
                "timing admission source identities disagree"
            )
    if fit_result.get("identity") != identity:
        raise SystemIdentificationError("timing fit robot/workspace identity drifted")

    episodes: list[RecordedEpisode] = []
    bindings: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise SystemIdentificationError(
                f"timing admission cohort episode {index} is malformed"
            )
        recording = (base / str(row.get("recording") or "")).resolve()
        manifest = (base / str(row.get("exact_replay_manifest") or "")).resolve()
        episode, binding = _load_verified_physical_episode(
            recording,
            manifest,
            config=config,
            config_path=config_path,
            verification_directory=output_path.parent
            / "timing_admission_exact_replay"
            / f"episode-{index:02d}",
            expected_identity=identity,
            allow_implicit_identity=explicit_identity is None,
        )
        episodes.append(episode)
        bindings.append(binding)
    observed_synthetic = any(
        episode.proof_class_category in {"fixture", "synthetic"}
        for episode in episodes
    )
    if observed_synthetic is not bool(synthetic_fixture_mode):
        raise SystemIdentificationError(
            "timing admission proof class does not match synthetic fixture mode"
        )

    expected_split = _freeze_timing_cohort_split(episodes, config)
    if fit_result.get("frozen_split") != expected_split:
        raise SystemIdentificationError("timing frozen split digest or ordering drifted")
    expected_actions = {
        episode.episode_id: float64_tensor_sha256(episode.commands)
        for episode in episodes
    }
    action_identity = fit_result.get("action_identity")
    if (
        not isinstance(action_identity, Mapping)
        or action_identity.get("sha256_by_episode") != expected_actions
        or action_identity.get("unchanged_for_every_candidate") is not True
    ):
        raise SystemIdentificationError("timing fit action lineage drifted")

    family = fit_result.get("candidate_family")
    if not isinstance(family, Mapping) or family.get("digest") != _family_digest(family):
        raise SystemIdentificationError("timing candidate family digest drifted")
    timing_stage = [
        stage
        for stage in config["parameter_stages"]
        if stage["name"] == "timing_control"
    ][0]
    if family.get("parameters") != timing_stage["parameters"]:
        raise SystemIdentificationError("timing candidate family ordering drifted")
    selection = fit_result.get("candidate_selection")
    selected = (
        selection.get("selected_parameters")
        if isinstance(selection, Mapping)
        else None
    )
    expected_names = [parameter["name"] for parameter in timing_stage["parameters"]]
    if (
        not isinstance(selected, Mapping)
        or set(selected) != set(expected_names)
        or selection.get("held_out_used_for_selection") is not False
        or selection.get("selected_on") != ["train", "validation"]
    ):
        raise SystemIdentificationError(
            "timing selected family or train/validation boundary drifted"
        )
    selected_values = validate_parameter_values(config, selected)
    held_out = [
        episode
        for episode in episodes
        if expected_split["assignments"][episode.episode_id] == "held_out"
    ]
    baseline = _evaluate_fp32(
        held_out,
        config,
        nominal_parameter_values(config),
        model_base_directory=config_path.parent,
    )
    candidate = _evaluate_fp32(
        held_out,
        config,
        selected_values,
        model_base_directory=config_path.parent,
    )
    gate = _fp32_gate(
        baseline["mean_loss_fp32"],
        candidate["mean_loss_fp32"],
        config["held_out_acceptance"],
    )
    if not gate["passed"]:
        raise SystemIdentificationError(
            "separate CPU/fp32 timing held-out improvement gate did not pass"
        )

    evaluator_path = Path(__file__).resolve()
    receipt = {
        "schema_version": TIMING_ADMISSION_SCHEMA,
        "status": (
            "synthetic_fixture_admitted"
            if synthetic_fixture_mode
            else "admitted_configuration_input"
        ),
        "proof_class": "synthetic_fixture" if synthetic_fixture_mode else "replay_evaluator",
        "source_fit": {
            "sha256": sha256_file(fit_path),
            "schema_version": TIMING_RESULT_SCHEMA,
        },
        "source_cohort": {
            "sha256": sha256_file(cohort_path),
            "schema_version": TIMING_COHORT_SCHEMA,
        },
        "source_config": {
            "sha256": sha256_file(config_path),
            "config_id": config["config_id"],
        },
        "identity": identity,
        "candidate_family": copy.deepcopy(family),
        "selected_parameters": copy.deepcopy(dict(selected)),
        "frozen_split": copy.deepcopy(expected_split),
        "action_identity": {
            "sha256_by_episode": expected_actions,
            "byte_identical": True,
            "verified_source_bindings": bindings,
        },
        "held_out_replay": {
            "simulation_runtime": "cpu_mujoco_fp64",
            "evaluator_numeric_runtime": "cpu_numpy_fp32",
            "metric": "mean_joint_position_huber_loss_fp32",
            "fit_or_selection_performed": False,
            "baseline": baseline,
            "candidate": candidate,
            "improvement_gate": gate,
        },
        "evaluator_identity": {
            "name": "sim2claw-independent-timing-actuation-admission",
            "version": "1",
            "executable_path": str(evaluator_path),
            "executable_sha256": sha256_file(evaluator_path),
            "numeric_runtime": "cpu_numpy_fp32",
        },
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": bool(synthetic_fixture_mode),
        "evaluator_admission": not synthetic_fixture_mode,
        "parameters_promoted": False,
        "physical_authority": False,
        "claim_limits": [
            "timing and actuation configuration input only",
            "MuJoCo integration is fp64; the independent verdict metric is CPU/fp32",
            "no geometry, camera, contact, task, or physical execution authority",
        ],
    }
    _write_json(output_path, receipt)
    result = copy.deepcopy(receipt)
    result["receipt_path"] = str(output_path)
    result["receipt_sha256"] = sha256_file(output_path)
    return result
