"""Fit and validate one bounded effective SO-101 plant."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .realized_action_sage_lite import (
    _Kinematics,
    EpisodeArrays,
    load_episodes,
)


SCHEMA = "sim2claw.realized_action_effective_plant_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_effective_plant_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_effective_plant_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "realized_action_effective_plant_v1"
)


def _hash_bytes(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes(order="C")).hexdigest()


def _bound(
    root: Path, entry: Mapping[str, Any], label: str
) -> tuple[Path, dict[str, Any]]:
    path = root / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    return path, load_json_object(path, label=label)


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="effective plant contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported effective plant contract")
    for key, entry in contract.get("sources", {}).items():
        _bound(root, entry, key)
    paths = contract.get("plant_paths")
    if (
        not isinstance(paths, list)
        or [row.get("path_id") for row in paths]
        != [
            "direct_target",
            "diagnostic_zoh_0p11s",
            "identified_effective_plant_v1",
        ]
        or paths[1].get("calibrated_physical_latency") is not False
        or paths[2].get("sample_hold") != 3
    ):
        raise FactoryArtifactError("effective plant paths changed")
    if not all(contract.get("rules", {}).values()):
        raise FactoryArtifactError("effective plant rule widened")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise FactoryArtifactError("effective plant authority widened")
    return contract


def _sample_hold(values: np.ndarray, samples: int) -> tuple[np.ndarray, np.ndarray]:
    indices = np.maximum(0, np.arange(len(values), dtype=np.int64) - int(samples))
    return np.asarray(values[indices], dtype=np.float64), indices


def _timestamp_zoh(
    values: np.ndarray, timestamps: np.ndarray, delay_seconds: float
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.searchsorted(
        timestamps, timestamps - float(delay_seconds), side="right"
    ) - 1
    indices = np.clip(indices, 0, len(values) - 1)
    return np.asarray(values[indices], dtype=np.float64), indices.astype(np.int64)


def _first_order(
    target: np.ndarray, initial: np.ndarray, alpha: np.ndarray
) -> np.ndarray:
    if (
        target.ndim != 2
        or initial.shape != (target.shape[1],)
        or alpha.shape != (target.shape[1],)
        or np.any(alpha <= 0.0)
        or np.any(alpha > 1.0)
    ):
        raise FactoryArtifactError("effective plant response input is invalid")
    output = np.empty_like(target, dtype=np.float64)
    output[0] = initial
    for index in range(1, len(target)):
        output[index] = output[index - 1] + alpha * (
            target[index] - output[index - 1]
        )
    return output


def _branches(target: np.ndarray, threshold: float) -> np.ndarray:
    delta = np.vstack((np.zeros((1, target.shape[1])), np.diff(target, axis=0)))
    result = np.zeros_like(delta, dtype=np.int8)
    result[delta >= float(threshold)] = 1
    result[delta <= -float(threshold)] = -1
    return result


def fit_model(
    episodes: list[EpisodeArrays], specification: Mapping[str, Any]
) -> dict[str, Any]:
    if not episodes or any(row.cohort_role != "fit" for row in episodes):
        raise FactoryArtifactError("effective plant fit requires fit episodes only")
    hold = int(specification["sample_hold"])
    alpha_grid = [float(value) for value in specification["alpha_grid"]]
    joint_count = episodes[0].sent.shape[1]
    alpha = np.empty(joint_count, dtype=np.float64)
    alpha_scores: list[dict[str, Any]] = []
    held_targets = [_sample_hold(row.sent, hold)[0] for row in episodes]
    for joint_index in range(joint_count):
        candidates = []
        for value in alpha_grid:
            squared = 0.0
            count = 0
            for episode, target in zip(episodes, held_targets, strict=True):
                predicted = _first_order(
                    target,
                    episode.measured[0],
                    np.full(joint_count, value, dtype=np.float64),
                )
                residual = predicted[:, joint_index] - episode.measured[:, joint_index]
                squared += float(np.sum(np.square(residual)))
                count += len(residual)
            candidates.append(
                {
                    "alpha": value,
                    "rms_degrees": float(np.sqrt(squared / count)),
                    "sample_count": count,
                }
            )
        selected = min(candidates, key=lambda row: (row["rms_degrees"], -row["alpha"]))
        alpha[joint_index] = selected["alpha"]
        alpha_scores.append({"joint_index": joint_index, "candidates": candidates, "selected": selected})
    base_predictions = [
        _first_order(target, episode.measured[0], alpha)
        for episode, target in zip(episodes, held_targets, strict=True)
    ]
    threshold = float(specification["direction_delta_min_degrees"])
    minimum = int(specification["minimum_branch_samples"])
    maximum = float(specification["maximum_absolute_direction_offset_degrees"])
    offsets = np.zeros((joint_count, 3), dtype=np.float64)
    branch_counts = np.zeros((joint_count, 3), dtype=np.int64)
    for joint_index in range(joint_count):
        for branch_index, branch_value in enumerate((-1, 0, 1)):
            residuals = []
            for episode, target, predicted in zip(
                episodes, held_targets, base_predictions, strict=True
            ):
                branch = _branches(target, threshold)[:, joint_index]
                selected = predicted[:, joint_index] - episode.measured[:, joint_index]
                residuals.append(selected[branch == branch_value])
            values = np.concatenate(residuals)
            branch_counts[joint_index, branch_index] = len(values)
            if len(values) >= minimum:
                offsets[joint_index, branch_index] = float(
                    np.clip(np.mean(values), -maximum, maximum)
                )
    return {
        "sample_hold": hold,
        "sample_hold_semantics": specification["sample_hold_semantics"],
        "alpha": alpha.tolist(),
        "alpha_search": alpha_scores,
        "direction_delta_min_degrees": threshold,
        "direction_offsets_degrees": offsets.tolist(),
        "direction_branch_order": [-1, 0, 1],
        "direction_branch_sample_counts": branch_counts.tolist(),
        "fit_episode_ids": [row.recording_id for row in episodes],
        "fit_sample_count": int(sum(len(row.sent) for row in episodes)),
        "causal_latency_claim": False,
    }


def apply_identified(
    episode: EpisodeArrays, model: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    target, indices = _sample_hold(episode.sent, int(model["sample_hold"]))
    predicted = _first_order(
        target,
        episode.measured[0],
        np.asarray(model["alpha"], dtype=np.float64),
    )
    branch = _branches(
        target, float(model["direction_delta_min_degrees"])
    )
    offsets = np.asarray(model["direction_offsets_degrees"], dtype=np.float64)
    for joint_index in range(predicted.shape[1]):
        predicted[:, joint_index] -= offsets[
            joint_index, branch[:, joint_index] + 1
        ]
    predicted[0] = episode.measured[0]
    return predicted, indices


def _metrics(
    prediction: np.ndarray,
    measured: np.ndarray,
    kinematics: _Kinematics,
) -> dict[str, Any]:
    residual = prediction - measured
    predicted_ee = kinematics.positions(prediction)
    measured_ee = kinematics.positions(measured)
    ee_mm = np.linalg.norm(predicted_ee - measured_ee, axis=1) * 1000.0
    return {
        "sample_count": int(len(prediction)),
        "overall_joint_rms_degrees": float(np.sqrt(np.mean(np.square(residual)))),
        "per_joint_rms_degrees": np.sqrt(
            np.mean(np.square(residual), axis=0)
        ).tolist(),
        "per_joint_bias_degrees": np.mean(residual, axis=0).tolist(),
        "provisional_ee_rms_mm": float(np.sqrt(np.mean(np.square(ee_mm)))),
        "provisional_ee_p95_mm": float(np.percentile(ee_mm, 95)),
        "global_mapping_approved": False,
    }


def _write_tensor(
    path: Path, values: np.ndarray, dtype: str
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    path.write_bytes(array.tobytes(order="C"))
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_file(path),
        "shape": list(array.shape),
        "dtype": dtype,
    }


def _cohort_metrics(
    episodes: list[EpisodeArrays],
    predictions: Mapping[str, Mapping[str, np.ndarray]],
    kinematics: _Kinematics,
) -> dict[str, Any]:
    result = {}
    for path_id in (
        "direct_target",
        "diagnostic_zoh_0p11s",
        "identified_effective_plant_v1",
    ):
        prediction = np.concatenate(
            [predictions[row.recording_id][path_id] for row in episodes]
        )
        measured = np.concatenate([row.measured for row in episodes])
        result[path_id] = _metrics(prediction, measured, kinematics)
    return result


def run(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    _, c3a = _bound(root, contract["sources"]["c3a_receipt"], "C3A receipt")
    if c3a.get("artifact_sha256") != contract["sources"]["c3a_receipt"][
        "artifact_sha256"
    ]:
        raise FactoryArtifactError("C3A artifact changed")
    c3_contract = load_json_object(
        root / "configs" / "evaluations" / "realized_action_sage_lite_v1.json",
        label="C3 contract",
    )
    episodes = load_episodes(c3_contract, root=root)
    by_role = {
        role: [row for row in episodes if row.cohort_role == role]
        for role in ("fit", "validation", "sealed")
    }
    identified_spec = contract["plant_paths"][2]
    model = fit_model(by_role["fit"], identified_spec)
    manifest = load_json_object(
        root / c3_contract["sources"]["kinematic_manifest"]["path"],
        label="effective plant kinematic manifest",
    )
    kinematics = _Kinematics(manifest)
    predictions: dict[str, dict[str, np.ndarray]] = {}
    trace_receipts = []
    for episode in episodes:
        direct = episode.sent.copy()
        diagnostic, diagnostic_indices = _timestamp_zoh(
            episode.sent,
            episode.timestamps,
            float(contract["plant_paths"][1]["delay_seconds"]),
        )
        identified, identified_indices = apply_identified(episode, model)
        predictions[episode.recording_id] = {
            "direct_target": direct,
            "diagnostic_zoh_0p11s": diagnostic,
            "identified_effective_plant_v1": identified,
        }
        directory = output_directory / "traces" / episode.recording_id
        requested_f4 = np.asarray(episode.requested, dtype="<f4")
        sent_f4 = np.asarray(episode.sent, dtype="<f4")
        source_identity = {
            "requested": _write_tensor(
                directory / "requested.f4le", requested_f4, "<f4"
            ),
            "sent": _write_tensor(directory / "sent.f4le", sent_f4, "<f4"),
            "measured": _write_tensor(
                directory / "measured.f8le", episode.measured, "<f8"
            ),
            "timestamps": _write_tensor(
                directory / "timestamps.f8le", episode.timestamps, "<f8"
            ),
        }
        paths = {}
        for path_id, values in predictions[episode.recording_id].items():
            paths[path_id] = {
                "applied": _write_tensor(
                    directory / f"{path_id}.applied.f8le", values, "<f8"
                ),
                "metrics": _metrics(values, episode.measured, kinematics),
            }
        paths["diagnostic_zoh_0p11s"]["source_indices"] = _write_tensor(
            directory / "diagnostic_zoh_0p11s.source_indices.i64le",
            diagnostic_indices,
            "<i8",
        )
        paths["identified_effective_plant_v1"]["source_indices"] = _write_tensor(
            directory / "identified_effective_plant_v1.source_indices.i64le",
            identified_indices,
            "<i8",
        )
        trace_receipts.append(
            {
                "recording_id": episode.recording_id,
                "cohort_role": episode.cohort_role,
                "source_identity": source_identity,
                "requested_raw_float32le_sha256": _hash_bytes(requested_f4),
                "sent_raw_float32le_sha256": _hash_bytes(sent_f4),
                "row_order_preserved": True,
                "timestamps_preserved": True,
                "paths": paths,
            }
        )
    cohorts = {
        role: _cohort_metrics(by_role[role], predictions, kinematics)
        for role in ("fit", "validation", "sealed")
    }
    validation = cohorts["validation"]
    direct = validation["direct_target"]
    identified = validation["identified_effective_plant_v1"]
    joint_improvement = (
        direct["overall_joint_rms_degrees"]
        - identified["overall_joint_rms_degrees"]
    ) / direct["overall_joint_rms_degrees"]
    ee_improvement = (
        direct["provisional_ee_rms_mm"] - identified["provisional_ee_rms_mm"]
    ) / direct["provisional_ee_rms_mm"]
    regressions = (
        np.asarray(identified["per_joint_rms_degrees"])
        - np.asarray(direct["per_joint_rms_degrees"])
    )
    gates = contract["validation_gates"]
    source_identity = all(
        row["source_identity"]["requested"]["sha256"]
        == row["requested_raw_float32le_sha256"]
        and row["source_identity"]["sent"]["sha256"]
        == row["sent_raw_float32le_sha256"]
        for row in trace_receipts
    )
    checks = {
        "requested_sent_source_hash_match": source_identity,
        "validation_episode_count": len(by_role["validation"])
        == int(gates["required_validation_episode_count"]),
        "pooled_joint_improvement": joint_improvement
        >= float(gates["minimum_pooled_joint_rms_improvement_fraction"]),
        "pooled_provisional_ee_improvement": ee_improvement
        >= float(
            gates["minimum_pooled_provisional_ee_rms_improvement_fraction"]
        ),
        "per_joint_no_material_regression": bool(
            np.all(
                regressions
                <= float(gates["maximum_per_joint_rms_regression_degrees"])
            )
        ),
    }
    passed = all(checks.values())
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "result": "PASS" if passed else "TERMINAL_IDENTIFIED_PLANT_NEGATIVE",
        "proof_class": "retrospective_fit_validation_effective_joint_plant",
        "model": model,
        "trace_receipts": trace_receipts,
        "cohort_metrics": cohorts,
        "validation": {
            "checks": checks,
            "joint_rms_improvement_fraction": float(joint_improvement),
            "provisional_ee_rms_improvement_fraction": float(ee_improvement),
            "per_joint_rms_regression_degrees": regressions.tolist(),
            "passed": passed,
        },
        "identifiability": {
            "sample_hold_is_causal_latency": False,
            "diagnostic_zoh_is_calibrated_plant": False,
            "sealed_used_for_selection": False,
            "source_action_modified": False,
            "global_mapping_approved": False,
        },
        "claim_boundary": (
            "Fit/validation effective joint-response plant over retained "
            "gateway-sent actions. The three-sample hold is a sample-domain "
            "association, the 0.11 second ZOH is diagnostic, and provisional "
            "kinematic EE metrics do not approve global mapping. No contact, "
            "task-outcome, physical, or causal-latency claim."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt
