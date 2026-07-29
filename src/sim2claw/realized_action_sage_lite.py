"""Retrospective SAGE-lite analysis over frozen physical action episodes."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.realized_action_sage_lite_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_sage_lite_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "realized_action_sage_lite_v1.json"
)
OUTPUT_PATH = REPO_ROOT / "outputs" / "realized_action_sage_lite_v1" / "receipt.json"


@dataclass(frozen=True)
class EpisodeArrays:
    recording_id: str
    cohort_role: str
    joint_order: tuple[str, ...]
    requested: np.ndarray
    sent: np.ndarray
    measured: np.ndarray
    timestamps: np.ndarray
    currents: np.ndarray
    current_valid: np.ndarray
    rate_limited: np.ndarray
    safety_clamped: np.ndarray
    rate_limits: np.ndarray


def _require_hash(root: Path, entry: Mapping[str, Any], label: str) -> Path:
    path = root / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    return path


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="SAGE-lite contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported SAGE-lite contract")
    sources = contract.get("sources")
    if not isinstance(sources, dict):
        raise FactoryArtifactError("SAGE-lite sources are missing")
    for key in ("episode_twin_closeout", "episode_twin_receipt", "kinematic_manifest"):
        _require_hash(root, sources[key], key)
    for index, entry in enumerate(sources.get("runtime_surfaces", [])):
        _require_hash(root, entry, f"runtime surface {index}")
    if contract.get("cohorts", {}).get("sealed_use") != (
        "report_only_no_parameter_or_mechanism_selection"
    ):
        raise FactoryArtifactError("sealed SAGE-lite boundary widened")
    forbidden = contract.get("forbidden_claims")
    if not isinstance(forbidden, dict) or not forbidden or not all(forbidden.values()):
        raise FactoryArtifactError("SAGE-lite forbidden claim was enabled")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise FactoryArtifactError("SAGE-lite authority widened")
    shifts = contract.get("analysis", {}).get("alignment_sample_shifts")
    if shifts != list(range(-4, 5)):
        raise FactoryArtifactError("SAGE-lite alignment search changed")
    return contract


def _load_tensor(directory: Path, spec: Mapping[str, Any]) -> np.ndarray:
    path = directory / str(spec["file"])
    if not path.is_file() or sha256_file(path) != spec.get("file_sha256"):
        raise FactoryArtifactError(f"episode tensor hash rejected: {path}")
    shape = tuple(int(value) for value in spec["shape"])
    array = np.fromfile(path, dtype=np.dtype(str(spec["dtype"])))
    if array.size != math.prod(shape):
        raise FactoryArtifactError(f"episode tensor shape rejected: {path}")
    result = array.reshape(shape)
    if not np.all(np.isfinite(result)):
        raise FactoryArtifactError(f"episode tensor is non-finite: {path}")
    return result


def _raw_rows(root: Path, bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    spec = bundle["source"]["samples_asset"]
    path = root / str(spec["path"])
    if not path.is_file() or sha256_file(path) != spec.get("sha256"):
        raise FactoryArtifactError(f"episode raw samples hash rejected: {path}")
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot load episode raw rows: {error}") from error
    if len(rows) != int(bundle["source"]["sample_count"]):
        raise FactoryArtifactError("episode raw row count changed")
    return rows


def load_episodes(
    contract: Mapping[str, Any], *, root: Path = REPO_ROOT
) -> list[EpisodeArrays]:
    receipt_path = root / contract["sources"]["episode_twin_receipt"]["path"]
    receipt = load_json_object(receipt_path, label="episode twin receipt")
    if (
        receipt.get("artifact_sha256")
        != contract["sources"]["episode_twin_receipt"]["artifact_sha256"]
    ):
        raise FactoryArtifactError("episode twin artifact changed")
    expected_counts = contract["cohorts"]["expected_counts"]
    if receipt.get("cohort_counts") != expected_counts:
        raise FactoryArtifactError("episode cohort membership changed")
    if len(receipt.get("bundles", [])) != int(
        contract["cohorts"]["expected_episode_count"]
    ):
        raise FactoryArtifactError("episode count changed")
    joint_order = tuple(str(value) for value in contract["joint_order"])
    episodes: list[EpisodeArrays] = []
    for entry in receipt["bundles"]:
        bundle_path = root / str(entry["bundle_path"])
        if (
            not bundle_path.is_file()
            or sha256_file(bundle_path) != entry["bundle_file_sha256"]
        ):
            raise FactoryArtifactError(f"episode bundle hash rejected: {bundle_path}")
        bundle = load_json_object(bundle_path, label="episode bundle")
        unsigned = {key: value for key, value in bundle.items() if key != "artifact_sha256"}
        if (
            bundle.get("artifact_sha256") != entry["bundle_artifact_sha256"]
            or canonical_digest(unsigned) != entry["bundle_artifact_sha256"]
        ):
            raise FactoryArtifactError("episode bundle artifact changed")
        if tuple(bundle.get("joint_order", [])) != joint_order:
            raise FactoryArtifactError("episode joint order changed")
        tensors = bundle["tensors"]
        directory = bundle_path.parent
        requested = _load_tensor(directory, tensors["operator_requested"])
        sent = _load_tensor(directory, tensors["gateway_sent"])
        measured = _load_tensor(directory, tensors["measured_joints"])
        timestamps = _load_tensor(directory, tensors["source_timestamps"])
        if (
            requested.shape != sent.shape
            or requested.shape != measured.shape
            or requested.ndim != 2
            or requested.shape[1] != len(joint_order)
            or timestamps.shape != (requested.shape[0],)
            or np.any(np.diff(timestamps) <= 0.0)
        ):
            raise FactoryArtifactError("episode tensor alignment changed")
        rows = _raw_rows(root, bundle)
        currents = np.full(requested.shape, np.nan, dtype=np.float64)
        current_valid = np.zeros(requested.shape, dtype=bool)
        rate_limited = np.zeros(len(rows), dtype=bool)
        safety_clamped = np.zeros(len(rows), dtype=bool)
        rate_limits = np.empty(requested.shape, dtype=np.float64)
        for row_index, row in enumerate(rows):
            if int(row.get("sample_index", -1)) != row_index:
                raise FactoryArtifactError("episode raw sample order changed")
            rate_limited[row_index] = bool(row.get("rate_limited"))
            safety_clamped[row_index] = bool(row.get("safety_clamped"))
            limits = np.asarray(row.get("command_rate_limits_per_second"), dtype=np.float64)
            if limits.shape != (len(joint_order),) or not np.all(np.isfinite(limits)):
                raise FactoryArtifactError("episode gateway rate limit changed")
            rate_limits[row_index] = limits
            raw_current = row.get("available_motor_current_raw")
            stale = bool(row.get("current_telemetry_stale", True))
            if isinstance(raw_current, dict) and not stale:
                for joint_index, joint_name in enumerate(joint_order):
                    value = raw_current.get(joint_name)
                    if isinstance(value, (int, float)) and math.isfinite(float(value)):
                        currents[row_index, joint_index] = float(value)
                        current_valid[row_index, joint_index] = True
        episodes.append(
            EpisodeArrays(
                recording_id=str(bundle["recording_id"]),
                cohort_role=str(bundle["cohort_role"]),
                joint_order=joint_order,
                requested=np.asarray(requested, dtype=np.float64),
                sent=np.asarray(sent, dtype=np.float64),
                measured=np.asarray(measured, dtype=np.float64),
                timestamps=np.asarray(timestamps, dtype=np.float64),
                currents=currents,
                current_valid=current_valid,
                rate_limited=rate_limited,
                safety_clamped=safety_clamped,
                rate_limits=rate_limits,
            )
        )
    return episodes


def _rms(values: np.ndarray, axis: int | None = None) -> np.ndarray | float:
    return np.sqrt(np.mean(np.square(values), axis=axis))


def _correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 3 or np.std(left) <= 1e-12 or np.std(right) <= 1e-12:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _aligned_blocks(
    sent: np.ndarray, measured: np.ndarray, shift: int
) -> tuple[np.ndarray, np.ndarray]:
    if shift > 0:
        return sent[:-shift], measured[shift:]
    if shift < 0:
        return sent[-shift:], measured[:shift]
    return sent, measured


def sample_alignment(
    sent: np.ndarray, measured: np.ndarray, shifts: list[int]
) -> dict[str, Any]:
    rows = []
    for shift in shifts:
        left, right = _aligned_blocks(sent, measured, shift)
        per_joint = np.asarray(_rms(left - right, axis=0), dtype=np.float64)
        rows.append(
            {
                "shift_samples": int(shift),
                "sample_count": int(len(left)),
                "overall_rms_degrees": float(_rms(left - right)),
                "per_joint_rms_degrees": per_joint.tolist(),
            }
        )
    best_overall = min(rows, key=lambda row: row["overall_rms_degrees"])
    best_per_joint = []
    for joint_index in range(sent.shape[1]):
        selected = min(
            rows, key=lambda row: row["per_joint_rms_degrees"][joint_index]
        )
        best_per_joint.append(
            {
                "shift_samples": selected["shift_samples"],
                "rms_degrees": selected["per_joint_rms_degrees"][joint_index],
            }
        )
    return {
        "semantics": "positive_shift_means_measured_sample_after_sent_sample",
        "causal_latency_claim": False,
        "candidates": rows,
        "best_overall": best_overall,
        "best_per_joint": best_per_joint,
    }


class _Kinematics:
    def __init__(self, manifest: Mapping[str, Any]) -> None:
        config = manifest["candidate_config"]
        self.model, _ = _compile_model(config, base_directory=None)
        self.data = mujoco.MjData(self.model)
        bindings = config["bindings"]
        self.joint_ids = [
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, str(name))
            for name in bindings["joint_names"]
        ]
        self.qpos_addresses = [
            int(self.model.jnt_qposadr[joint_id]) for joint_id in self.joint_ids
        ]
        self.site_id = mujoco.mj_name2id(
            self.model,
            mujoco.mjtObj.mjOBJ_SITE,
            str(bindings["end_effector_site"]),
        )
        joints = config["physical_adapter"]["joint_transform"]["joints"]
        if (
            min(self.joint_ids + [self.site_id]) < 0
            or len(joints) != len(self.joint_ids)
        ):
            raise FactoryArtifactError("SAGE-lite kinematic binding is incomplete")
        self.scales = np.asarray(
            [float(row["scale"]) * float(row["sign"]) for row in joints],
            dtype=np.float64,
        )
        self.offsets = np.asarray(
            [float(row["zero_offset"]) for row in joints], dtype=np.float64
        )

    def positions(self, physical: np.ndarray) -> np.ndarray:
        mapped = physical * self.scales + self.offsets
        output = np.empty((len(mapped), 3), dtype=np.float64)
        for row_index, row in enumerate(mapped):
            self.data.qpos[self.qpos_addresses] = row
            self.data.qvel[:] = 0.0
            mujoco.mj_forward(self.model, self.data)
            output[row_index] = self.data.site_xpos[self.site_id]
        return output


def _episode_internal(
    episode: EpisodeArrays,
    contract: Mapping[str, Any],
    kinematics: _Kinematics,
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = contract["analysis"]
    dt = np.diff(episode.timestamps)
    sent_velocity = np.diff(episode.sent, axis=0) / dt[:, None]
    measured_velocity = np.diff(episode.measured, axis=0) / dt[:, None]
    sent_minus_requested = episode.sent - episode.requested
    sent_minus_measured = episode.sent - episode.measured
    direction_delta = np.diff(episode.sent, axis=0)
    direction_residual = sent_minus_measured[1:]
    hold_mask = np.abs(sent_velocity) <= float(
        analysis["hold_command_slew_max_degrees_per_second"]
    )
    direction_threshold = float(analysis["direction_command_delta_min_degrees"])
    near_limit = (
        np.abs(sent_velocity)
        >= episode.rate_limits[1:] * float(analysis["empirical_rate_margin_fraction"])
    )
    sent_ee = kinematics.positions(episode.sent)
    measured_ee = kinematics.positions(episode.measured)
    ee_error_mm = np.linalg.norm(sent_ee - measured_ee, axis=1) * 1000.0
    contributions = []
    contribution_series = []
    for joint_index, joint_name in enumerate(episode.joint_order):
        hybrid = episode.measured.copy()
        hybrid[:, joint_index] = episode.sent[:, joint_index]
        hybrid_ee = kinematics.positions(hybrid)
        series = np.linalg.norm(hybrid_ee - measured_ee, axis=1) * 1000.0
        contribution_series.append(series)
        contributions.append(
            {
                "joint": joint_name,
                "rms_mm": float(_rms(series)),
                "p95_mm": float(np.percentile(series, 95)),
            }
        )
    contributions.sort(key=lambda row: row["rms_mm"], reverse=True)
    direction_rows = []
    current_rows = []
    hold_rows = []
    for joint_index, joint_name in enumerate(episode.joint_order):
        positive = direction_delta[:, joint_index] >= direction_threshold
        negative = direction_delta[:, joint_index] <= -direction_threshold
        direction_rows.append(
            {
                "joint": joint_name,
                "positive_samples": int(np.sum(positive)),
                "positive_mean_sent_minus_measured_degrees": (
                    float(np.mean(direction_residual[positive, joint_index]))
                    if np.any(positive)
                    else None
                ),
                "negative_samples": int(np.sum(negative)),
                "negative_mean_sent_minus_measured_degrees": (
                    float(np.mean(direction_residual[negative, joint_index]))
                    if np.any(negative)
                    else None
                ),
            }
        )
        valid = episode.current_valid[:, joint_index]
        current = episode.currents[valid, joint_index]
        residual = sent_minus_measured[valid, joint_index]
        current_rows.append(
            {
                "joint": joint_name,
                "sample_count": int(np.sum(valid)),
                "signed_current_vs_signed_residual_correlation": _correlation(
                    current, residual
                ),
                "absolute_current_vs_absolute_residual_correlation": _correlation(
                    np.abs(current), np.abs(residual)
                ),
            }
        )
        selected = hold_mask[:, joint_index]
        hold_residual = sent_minus_measured[1:, joint_index][selected]
        hold_rows.append(
            {
                "joint": joint_name,
                "sample_count": int(len(hold_residual)),
                "mean_sent_minus_measured_degrees": (
                    float(np.mean(hold_residual)) if len(hold_residual) else None
                ),
                "rms_sent_minus_measured_degrees": (
                    float(_rms(hold_residual)) if len(hold_residual) else None
                ),
            }
        )
    body_return_sent_rms = float(
        _rms(episode.sent[-1, :5] - episode.sent[0, :5])
    )
    return_qualified = body_return_sent_rms <= float(
        analysis["return_sent_body_rms_max_degrees"]
    )
    result = {
        "recording_id": episode.recording_id,
        "cohort_role": episode.cohort_role,
        "sample_count": int(len(episode.timestamps)),
        "duration_seconds": float(episode.timestamps[-1] - episode.timestamps[0]),
        "requested_to_sent": {
            "changed_rows": int(np.sum(np.any(episode.requested != episode.sent, axis=1))),
            "rate_limited_rows": int(np.sum(episode.rate_limited)),
            "safety_clamped_rows": int(np.sum(episode.safety_clamped)),
            "overall_rms_degrees": float(_rms(sent_minus_requested)),
            "per_joint_rms_degrees": np.asarray(
                _rms(sent_minus_requested, axis=0)
            ).tolist(),
            "per_joint_maximum_absolute_degrees": np.max(
                np.abs(sent_minus_requested), axis=0
            ).tolist(),
        },
        "sent_to_measured": {
            "overall_rms_degrees": float(_rms(sent_minus_measured)),
            "per_joint_rms_degrees": np.asarray(
                _rms(sent_minus_measured, axis=0)
            ).tolist(),
            "per_joint_bias_degrees": np.mean(
                sent_minus_measured, axis=0
            ).tolist(),
            "per_joint_p95_absolute_degrees": np.percentile(
                np.abs(sent_minus_measured), 95, axis=0
            ).tolist(),
        },
        "velocity_and_rate": {
            "interval_count": int(len(dt)),
            "median_dt_seconds": float(np.median(dt)),
            "per_joint_sent_slew_p95_degrees_per_second": np.percentile(
                np.abs(sent_velocity), 95, axis=0
            ).tolist(),
            "per_joint_measured_velocity_p95_degrees_per_second": np.percentile(
                np.abs(measured_velocity), 95, axis=0
            ).tolist(),
            "per_joint_near_declared_rate_limit_intervals": np.sum(
                near_limit, axis=0
            ).astype(int).tolist(),
        },
        "steady_state_undertravel_proxy": hold_rows,
        "direction_conditioned_residual": direction_rows,
        "sample_domain_alignment": sample_alignment(
            episode.sent,
            episode.measured,
            list(analysis["alignment_sample_shifts"]),
        ),
        "current_register_association": {
            "semantics": "uncalibrated_association_proxy_not_torque_or_force",
            "per_joint": current_rows,
        },
        "return_residual": {
            "qualified": bool(return_qualified),
            "sent_body_endpoint_rms_degrees": body_return_sent_rms,
            "measured_final_minus_initial_degrees": (
                episode.measured[-1] - episode.measured[0]
            ).tolist(),
            "measured_body_return_rms_degrees": (
                float(_rms(episode.measured[-1, :5] - episode.measured[0, :5]))
                if return_qualified
                else None
            ),
        },
        "provisional_kinematic_ee_residual": {
            "mapping_globally_approved": False,
            "overall_rms_mm": float(_rms(ee_error_mm)),
            "p95_mm": float(np.percentile(ee_error_mm, 95)),
            "single_joint_substitution_ranking": contributions,
        },
    }
    internal = {
        "sent_minus_requested": sent_minus_requested,
        "sent_minus_measured": sent_minus_measured,
        "sent": episode.sent,
        "measured": episode.measured,
        "direction_delta": direction_delta,
        "direction_residual": direction_residual,
        "hold_mask": hold_mask,
        "currents": episode.currents,
        "current_valid": episode.current_valid,
        "ee_error_mm": ee_error_mm,
        "ee_contribution_series": contribution_series,
        "rate_limited": episode.rate_limited,
        "safety_clamped": episode.safety_clamped,
        "near_limit": near_limit,
        "return_qualified": return_qualified,
        "measured_return": episode.measured[-1] - episode.measured[0],
    }
    return result, internal


def _cohort_summary(
    role: str,
    episodes: list[EpisodeArrays],
    internals: list[dict[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    joint_order = episodes[0].joint_order
    sent_minus_requested = np.concatenate(
        [row["sent_minus_requested"] for row in internals]
    )
    sent_minus_measured = np.concatenate(
        [row["sent_minus_measured"] for row in internals]
    )
    direction_delta = np.concatenate([row["direction_delta"] for row in internals])
    direction_residual = np.concatenate(
        [row["direction_residual"] for row in internals]
    )
    hold_mask = np.concatenate([row["hold_mask"] for row in internals])
    current = np.concatenate([row["currents"] for row in internals])
    current_valid = np.concatenate([row["current_valid"] for row in internals])
    ee_error = np.concatenate([row["ee_error_mm"] for row in internals])
    threshold = float(contract["analysis"]["direction_command_delta_min_degrees"])
    direction_rows = []
    hold_rows = []
    current_rows = []
    for joint_index, joint_name in enumerate(joint_order):
        positive = direction_delta[:, joint_index] >= threshold
        negative = direction_delta[:, joint_index] <= -threshold
        direction_rows.append(
            {
                "joint": joint_name,
                "positive_samples": int(np.sum(positive)),
                "positive_mean_sent_minus_measured_degrees": (
                    float(np.mean(direction_residual[positive, joint_index]))
                    if np.any(positive)
                    else None
                ),
                "negative_samples": int(np.sum(negative)),
                "negative_mean_sent_minus_measured_degrees": (
                    float(np.mean(direction_residual[negative, joint_index]))
                    if np.any(negative)
                    else None
                ),
            }
        )
        residual = direction_residual[:, joint_index][hold_mask[:, joint_index]]
        hold_rows.append(
            {
                "joint": joint_name,
                "sample_count": int(len(residual)),
                "mean_sent_minus_measured_degrees": (
                    float(np.mean(residual)) if len(residual) else None
                ),
                "rms_sent_minus_measured_degrees": (
                    float(_rms(residual)) if len(residual) else None
                ),
            }
        )
        valid = current_valid[:, joint_index]
        current_rows.append(
            {
                "joint": joint_name,
                "sample_count": int(np.sum(valid)),
                "signed_current_vs_signed_residual_correlation": _correlation(
                    current[valid, joint_index],
                    sent_minus_measured[valid, joint_index],
                ),
                "absolute_current_vs_absolute_residual_correlation": _correlation(
                    np.abs(current[valid, joint_index]),
                    np.abs(sent_minus_measured[valid, joint_index]),
                ),
            }
        )
    contributions = []
    for joint_index, joint_name in enumerate(joint_order):
        series = np.concatenate(
            [row["ee_contribution_series"][joint_index] for row in internals]
        )
        contributions.append(
            {
                "joint": joint_name,
                "rms_mm": float(_rms(series)),
                "p95_mm": float(np.percentile(series, 95)),
            }
        )
    contributions.sort(key=lambda row: row["rms_mm"], reverse=True)
    alignment_candidates = []
    for shift in contract["analysis"]["alignment_sample_shifts"]:
        blocks = [
            _aligned_blocks(episode.sent, episode.measured, int(shift))
            for episode in episodes
        ]
        left = np.concatenate([block[0] for block in blocks])
        right = np.concatenate([block[1] for block in blocks])
        alignment_candidates.append(
            {
                "shift_samples": int(shift),
                "sample_count": int(len(left)),
                "overall_rms_degrees": float(_rms(left - right)),
                "per_joint_rms_degrees": np.asarray(
                    _rms(left - right, axis=0)
                ).tolist(),
            }
        )
    best = min(alignment_candidates, key=lambda row: row["overall_rms_degrees"])
    best_per_joint = []
    for joint_index, joint_name in enumerate(joint_order):
        selected = min(
            alignment_candidates,
            key=lambda row: row["per_joint_rms_degrees"][joint_index],
        )
        best_per_joint.append(
            {
                "joint": joint_name,
                "shift_samples": selected["shift_samples"],
                "rms_degrees": selected["per_joint_rms_degrees"][joint_index],
            }
        )
    return {
        "cohort_role": role,
        "episode_count": len(episodes),
        "sample_count": int(sum(len(episode.timestamps) for episode in episodes)),
        "requested_to_sent": {
            "changed_rows": int(
                sum(
                    np.sum(np.any(episode.requested != episode.sent, axis=1))
                    for episode in episodes
                )
            ),
            "rate_limited_rows": int(
                sum(np.sum(row["rate_limited"]) for row in internals)
            ),
            "safety_clamped_rows": int(
                sum(np.sum(row["safety_clamped"]) for row in internals)
            ),
            "overall_rms_degrees": float(_rms(sent_minus_requested)),
            "per_joint_rms_degrees": np.asarray(
                _rms(sent_minus_requested, axis=0)
            ).tolist(),
        },
        "sent_to_measured": {
            "overall_rms_degrees": float(_rms(sent_minus_measured)),
            "per_joint_rms_degrees": np.asarray(
                _rms(sent_minus_measured, axis=0)
            ).tolist(),
            "per_joint_bias_degrees": np.mean(
                sent_minus_measured, axis=0
            ).tolist(),
            "per_joint_p95_absolute_degrees": np.percentile(
                np.abs(sent_minus_measured), 95, axis=0
            ).tolist(),
        },
        "direction_conditioned_residual": direction_rows,
        "steady_state_undertravel_proxy": hold_rows,
        "sample_domain_alignment": {
            "semantics": "positive_shift_means_measured_sample_after_sent_sample",
            "causal_latency_claim": False,
            "best_overall": best,
            "best_per_joint": best_per_joint,
            "candidates": alignment_candidates,
        },
        "current_register_association": {
            "semantics": "uncalibrated_association_proxy_not_torque_or_force",
            "per_joint": current_rows,
        },
        "return_residual": {
            "qualified_episode_count": int(
                sum(bool(row["return_qualified"]) for row in internals)
            ),
            "measured_return_rms_degrees_by_qualified_episode": [
                float(_rms(row["measured_return"][:5]))
                for row in internals
                if row["return_qualified"]
            ],
        },
        "provisional_kinematic_ee_residual": {
            "mapping_globally_approved": False,
            "overall_rms_mm": float(_rms(ee_error)),
            "p95_mm": float(np.percentile(ee_error, 95)),
            "single_joint_substitution_ranking": contributions,
        },
    }


def analyze(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    episodes = load_episodes(contract, root=root)
    manifest = load_json_object(
        root / contract["sources"]["kinematic_manifest"]["path"],
        label="SAGE-lite kinematic manifest",
    )
    kinematics = _Kinematics(manifest)
    episode_results = []
    internal_by_role: dict[str, list[dict[str, Any]]] = {
        "fit": [],
        "validation": [],
        "sealed": [],
    }
    episodes_by_role: dict[str, list[EpisodeArrays]] = {
        "fit": [],
        "validation": [],
        "sealed": [],
    }
    for episode in episodes:
        result, internal = _episode_internal(episode, contract, kinematics)
        episode_results.append(result)
        episodes_by_role[episode.cohort_role].append(episode)
        internal_by_role[episode.cohort_role].append(internal)
    cohort_results = {
        role: _cohort_summary(
            role,
            episodes_by_role[role],
            internal_by_role[role],
            contract,
        )
        for role in ("fit", "validation", "sealed")
    }
    fit_ranking = cohort_results["fit"]["provisional_kinematic_ee_residual"][
        "single_joint_substitution_ranking"
    ]
    validation_ranking = cohort_results["validation"][
        "provisional_kinematic_ee_residual"
    ]["single_joint_substitution_ranking"]
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "source_episode_twin_artifact_sha256": contract["sources"][
            "episode_twin_receipt"
        ]["artifact_sha256"],
        "joint_order": list(episodes[0].joint_order),
        "episode_count": len(episodes),
        "cohort_results": cohort_results,
        "episode_results": episode_results,
        "cross_cohort_mechanism_ranking": {
            "fit_ee_joint_order": [row["joint"] for row in fit_ranking],
            "validation_ee_joint_order": [row["joint"] for row in validation_ranking],
            "sealed_used_for_selection": False,
        },
        "identifiability": {
            "sample_domain_alignment_only": True,
            "causal_command_latency_identified": False,
            "current_register_calibrated_as_torque_or_force": False,
            "actuator_application_timestamp_available": False,
            "global_physical_model_mapping_approved": False,
        },
        "claim_boundary": (
            "Retrospective requested, gateway-sent, measured-joint, rate, "
            "return, sample-alignment, and uncalibrated-current association "
            "analysis over frozen whole episodes. End-effector attribution uses "
            "the current provisional kinematics. No causal latency, torque, "
            "contact, parameter-promotion, outcome-transfer, or physical claim."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
