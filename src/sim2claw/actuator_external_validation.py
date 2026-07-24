"""Evaluator-owned external validation for the frozen actuator response model.

The selected model is not refit here. Five older recordings are a separate
evaluation cohort, and their joint/EE trace metrics cannot create task,
physical, contact, training, or promotion evidence.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT
from .pawn_bg_fidelity_advancement import _bootstrap_paired_metrics
from .pawn_bg_servo_load_bias import _replay, load_servo_load_bias_contract
from .pawn_bg_timing_ablation import _episode_metrics, _mapped_episode, _pool, _strip_arrays
from .pawn_bg_workcell_fit import WorkcellCandidate


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_actuator_external_validation_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.pawn_actuator_external_validation.v1"
RAW_SCHEMA = "sim2claw.pawn_actuator_external_validation_raw.v1"
EVALUATION_SCHEMA = "sim2claw.pawn_actuator_external_validation_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_actuator_external_validation_receipt.v1"
FORBIDDEN_RUNNER_FIELDS = frozenset(
    {
        "score",
        "passed",
        "verdict",
        "promoted",
        "task_success",
        "task_completion_score",
    }
)
RAW_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "validation_id",
        "contract_sha256",
        "proof_class",
        "candidate_runner_score_authority",
        "candidate_runner_promotion_authority",
        "inventory",
        "budget",
        "episodes",
    }
)
RAW_EPISODE_KEYS = frozenset(
    {
        "recording_id",
        "metadata_status",
        "samples_sha256",
        "historical_replay_receipt_sha256",
        "historical_state_trace_sha256",
        "variants",
    }
)
RAW_VARIANT_KEYS = frozenset(
    {
        "variant_id",
        "parameters",
        "action_sha256",
        "action_shape",
        "action_dtype",
        "clipped_action_rows",
        "schedule_sha256",
        "load_response",
        "metrics",
    }
)
METRIC_KEYS = frozenset(
    {
        "sample_count",
        "joint_squared_error_degrees",
        "per_joint_rms_degrees",
        "overall_joint_rms_degrees",
        "ee_squared_error_m2",
        "ee_rms_m",
        "ee_max_m",
        "stall_rows",
        "stall_reproduced",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ActuatorExternalValidationError(RuntimeError):
    """The external-validation proof boundary was violated."""


def _safe_repo_path(path_text: str, *, repo_root: Path) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ActuatorExternalValidationError(
            "external-validation paths must be safe repository-relative paths"
        )
    return repo_root / relative


def _variant_parameters(variant: Mapping[str, Any]) -> dict[str, float]:
    return {
        "shoulder_lift_deadband_degrees": float(
            variant["shoulder_lift_deadband_degrees"]
        ),
        "elbow_flex_deadband_degrees": float(
            variant["elbow_flex_deadband_degrees"]
        ),
        "elbow_load_bias_coefficient": float(
            variant["elbow_load_bias_coefficient"]
        ),
    }


def _require_sha256(value: Any, *, label: str) -> str:
    text = str(value)
    if SHA256_PATTERN.fullmatch(text) is None:
        raise ActuatorExternalValidationError(f"{label} is not a SHA-256 digest")
    return text


def _contains_forbidden_runner_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        if FORBIDDEN_RUNNER_FIELDS.intersection(value):
            return True
        return any(_contains_forbidden_runner_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_runner_field(item) for item in value)
    return False


def _replace_nonfinite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _replace_nonfinite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_nonfinite(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _validate_metrics(metrics: Any, *, sample_count: int, label: str) -> None:
    if not isinstance(metrics, Mapping) or set(metrics) != METRIC_KEYS:
        raise ActuatorExternalValidationError(f"{label} metric schema drifted")
    if int(metrics.get("sample_count", -1)) != sample_count or sample_count <= 0:
        raise ActuatorExternalValidationError(f"{label} metric sample count drifted")
    vector = np.asarray(metrics["joint_squared_error_degrees"], dtype=np.float64)
    if vector.shape != (5,) or not np.isfinite(vector).all() or np.any(vector < 0.0):
        raise ActuatorExternalValidationError(f"{label} joint SSE is invalid")
    for key in (
        "overall_joint_rms_degrees",
        "ee_squared_error_m2",
        "ee_rms_m",
        "ee_max_m",
    ):
        observed = float(metrics[key])
        if not np.isfinite(observed) or observed < 0.0:
            raise ActuatorExternalValidationError(f"{label} {key} is invalid")
    if float(metrics["overall_joint_rms_degrees"]) <= 0.0:
        raise ActuatorExternalValidationError(f"{label} joint RMS is zero")
    if float(metrics["ee_rms_m"]) <= 0.0:
        raise ActuatorExternalValidationError(f"{label} EE RMS is zero")
    expected_joint_rms = float(np.sqrt(vector.sum() / (sample_count * 5)))
    if not np.isclose(
        float(metrics["overall_joint_rms_degrees"]),
        expected_joint_rms,
        rtol=1e-12,
        atol=1e-12,
    ):
        raise ActuatorExternalValidationError(f"{label} joint RMS is inconsistent")
    expected_ee_rms = float(
        np.sqrt(float(metrics["ee_squared_error_m2"]) / sample_count)
    )
    if not np.isclose(
        float(metrics["ee_rms_m"]),
        expected_ee_rms,
        rtol=1e-12,
        atol=1e-12,
    ):
        raise ActuatorExternalValidationError(f"{label} EE RMS is inconsistent")
    for key in (
        "per_joint_rms_degrees",
        "stall_rows",
        "stall_reproduced",
    ):
        values = metrics[key]
        if not isinstance(values, Mapping) or len(values) != 5:
            raise ActuatorExternalValidationError(f"{label} {key} schema drifted")
        numeric = np.asarray(list(values.values()), dtype=np.float64)
        if not np.isfinite(numeric).all() or np.any(numeric < 0.0):
            raise ActuatorExternalValidationError(f"{label} {key} is invalid")
    per_joint = np.asarray(
        list(metrics["per_joint_rms_degrees"].values()), dtype=np.float64
    )
    if not np.allclose(
        per_joint,
        np.sqrt(vector / sample_count),
        rtol=1e-12,
        atol=1e-12,
    ):
        raise ActuatorExternalValidationError(
            f"{label} per-joint RMS is inconsistent"
        )


def validate_external_validation_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise ActuatorExternalValidationError(
            "unexpected actuator external-validation schema"
        )
    if contract.get("validation_id") != "pawn_actuator_external_validation_v1":
        raise ActuatorExternalValidationError(
            "unexpected actuator external-validation identity"
        )
    authority = contract.get("authority")
    if not isinstance(authority, Mapping) or not authority or any(authority.values()):
        raise ActuatorExternalValidationError(
            "external-validation authority widened"
        )
    proof = contract.get("proof_boundary") or {}
    if proof.get("candidate_runner_may_score_or_promote") is not False:
        raise ActuatorExternalValidationError("candidate runner gained score authority")
    if proof.get("external_trace_can_establish_task_success") is not False:
        raise ActuatorExternalValidationError(
            "external trace evidence gained task authority"
        )

    external = contract.get("external_evaluation") or {}
    if external.get("role") != "evaluation_only_never_selection_or_refit":
        raise ActuatorExternalValidationError("external cohort role drifted")
    if int(external.get("expected_episode_count", -1)) != 5:
        raise ActuatorExternalValidationError("external episode count widened")
    if int(external.get("expected_sample_count", -1)) != 2186:
        raise ActuatorExternalValidationError("external sample count drifted")
    manifest = external.get("expected_episode_manifest")
    if not isinstance(manifest, list) or len(manifest) != 5:
        raise ActuatorExternalValidationError("external manifest drifted")
    manifest_ids = [str(row.get("recording_id")) for row in manifest]
    if len(manifest_ids) != len(set(manifest_ids)):
        raise ActuatorExternalValidationError("external manifest duplicates an episode")
    if sum(int(row.get("sample_count", -1)) for row in manifest) != 2186:
        raise ActuatorExternalValidationError("external manifest sample count drifted")
    for row in manifest:
        for key in (
            "samples_sha256",
            "historical_replay_receipt_sha256",
            "historical_state_trace_sha256",
        ):
            _require_sha256(row.get(key), label=f"manifest {key}")

    variants = contract.get("variants") or {}
    if set(variants) != {
        "baseline",
        "candidate",
        "candidate_values_frozen_from_selection_receipt",
        "post_result_family_expansion_allowed",
    }:
        raise ActuatorExternalValidationError("variant family changed")
    if variants["candidate_values_frozen_from_selection_receipt"] is not True:
        raise ActuatorExternalValidationError("candidate is not frozen")
    if variants["post_result_family_expansion_allowed"] is not False:
        raise ActuatorExternalValidationError("post-result family expansion opened")
    baseline = variants["baseline"]
    candidate = variants["candidate"]
    if float(baseline["application_delay_seconds"]) != 0.11:
        raise ActuatorExternalValidationError("baseline delay drifted")
    if float(candidate["application_delay_seconds"]) != 0.11:
        raise ActuatorExternalValidationError("candidate delay drifted")
    if _variant_parameters(baseline) != {
        "shoulder_lift_deadband_degrees": 2.0,
        "elbow_flex_deadband_degrees": 2.0,
        "elbow_load_bias_coefficient": 0.0,
    }:
        raise ActuatorExternalValidationError("baseline candidate drifted")
    if _variant_parameters(candidate) != {
        "shoulder_lift_deadband_degrees": 1.5,
        "elbow_flex_deadband_degrees": 2.0,
        "elbow_load_bias_coefficient": -1.5,
    }:
        raise ActuatorExternalValidationError("selected candidate drifted")

    budget = contract.get("budget") or {}
    if budget != {
        "maximum_variants": 2,
        "maximum_episodes": 5,
        "maximum_simulator_replays": 10,
        "maximum_retries": 0,
        "maximum_provider_calls": 0,
    }:
        raise ActuatorExternalValidationError("external replay budget drifted")
    invariance = contract.get("action_invariance")
    if (
        not isinstance(invariance, Mapping)
        or not invariance
        or any(value is not True for value in invariance.values())
    ):
        raise ActuatorExternalValidationError("action invariance is not fail closed")

    evaluator = contract.get("evaluator") or {}
    if evaluator.get("owner") != "independent_cpu_fp32_external_trace_evaluator":
        raise ActuatorExternalValidationError("evaluator owner drifted")
    if float(evaluator.get("minimum_pooled_joint_rms_relative_improvement", -1)) != 0.02:
        raise ActuatorExternalValidationError("pooled RMS threshold drifted")
    if int(evaluator.get("minimum_improved_episode_count", -1)) != 4:
        raise ActuatorExternalValidationError("episode improvement threshold drifted")
    if int(evaluator.get("maximum_episode_count", -1)) != 5:
        raise ActuatorExternalValidationError("evaluator episode budget drifted")
    if float(evaluator.get("maximum_pooled_ee_rms_relative_to_baseline", -1)) != 1.0:
        raise ActuatorExternalValidationError("EE threshold drifted")
    bootstrap = evaluator.get("bootstrap") or {}
    if (
        int(bootstrap.get("replicates", 0)) != 10000
        or float(bootstrap.get("confidence_level", 0)) != 0.95
        or bootstrap.get("resampling_unit") != "whole_episode"
        or bootstrap.get(
            "require_joint_improvement_interval_lower_bound_above_zero"
        )
        is not True
    ):
        raise ActuatorExternalValidationError("bootstrap contract drifted")
    if evaluator.get("task_score_may_change_from_external_trace_only") is not False:
        raise ActuatorExternalValidationError(
            "external trace evidence gained task-score authority"
        )


def load_external_validation_contract(
    path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ActuatorExternalValidationError(
            f"cannot read external-validation contract {path}: {error}"
        ) from error
    validate_external_validation_contract(contract)
    return contract


def _load_hash_bound_json(
    binding: Mapping[str, Any],
    *,
    repo_root: Path,
    require_digest: bool = False,
) -> tuple[Path, dict[str, Any]]:
    path = _safe_repo_path(str(binding["path"]), repo_root=repo_root)
    if not path.is_file() or sha256_file(path) != binding["sha256"]:
        raise ActuatorExternalValidationError(
            f"hash-bound input drifted: {binding['path']}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ActuatorExternalValidationError(
            f"cannot read hash-bound input {path}: {error}"
        ) from error
    if require_digest:
        digest_payload = dict(payload)
        observed = digest_payload.pop("receipt_digest", None)
        if observed != binding.get("receipt_digest"):
            raise ActuatorExternalValidationError(
                f"receipt digest binding drifted: {binding['path']}"
            )
        if observed != canonical_digest(digest_payload):
            raise ActuatorExternalValidationError(
                f"receipt canonical digest is invalid: {binding['path']}"
            )
    return path, payload


def _workcell_candidate(source_receipt: Mapping[str, Any]) -> WorkcellCandidate:
    parameters = source_receipt["stage_d_parameters"]
    return WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            parameters["board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(value)
            for value in parameters["board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=tuple(
            float(value) for value in parameters["joint_zero_offsets_rad"]
        ),
        joint_range_envelope_rad=tuple(
            tuple(float(value) for value in pair)
            for pair in parameters["joint_range_envelope_rad"]
        ),
        base_z_offset_m=float(parameters.get("base_z_offset_m", 0.0)),
        base_roll_offset_degrees=float(
            parameters.get("base_roll_offset_degrees", 0.0)
        ),
        base_pitch_offset_degrees=float(
            parameters.get("base_pitch_offset_degrees", 0.0)
        ),
        board_side_m=(
            float(parameters["board_side_m"])
            if parameters.get("board_side_m") is not None
            else None
        ),
    )


def _load_source_experiment(
    source_receipt: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    declared = source_receipt["contract"]
    path = repo_root / "configs" / "sysid" / "pawn_bg_servo_load_bias_v1.json"
    if not path.is_file() or sha256_file(path) != declared["sha256"]:
        raise ActuatorExternalValidationError(
            "selected source experiment contract drifted"
        )
    experiment = load_servo_load_bias_contract(path)
    if source_receipt.get("selected_candidate") != {
        "shoulder_lift_deadband_degrees": 1.5,
        "elbow_flex_deadband_degrees": 2.0,
        "elbow_load_bias_coefficient": -1.5,
    }:
        raise ActuatorExternalValidationError(
            "selected source receipt candidate drifted"
        )
    return experiment


def _read_samples(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ActuatorExternalValidationError(
                f"{path}:{line_number} is invalid JSON"
            ) from error
        if not isinstance(row, dict):
            raise ActuatorExternalValidationError(
                f"{path}:{line_number} is not an object"
            )
        rows.append(row)
    return rows


def load_external_episode_payloads(
    contract: Mapping[str, Any],
    source_receipt: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[dict[str, Any]], WorkcellCandidate, dict[str, Any]]:
    external = contract["external_evaluation"]
    _, bridge = _load_hash_bound_json(
        external["bridge_contract"], repo_root=repo_root
    )
    ledger_path, ledger = _load_hash_bound_json(
        external["intake_ledger"], repo_root=repo_root
    )
    if bridge["physical_source_cohort"]["ledger_sha256"] != sha256_file(ledger_path):
        raise ActuatorExternalValidationError("bridge and intake ledger disagree")
    if bridge["physical_source_cohort"]["recorded_board_pose_id"] != external[
        "recorded_board_pose_id"
    ]:
        raise ActuatorExternalValidationError("external board-pose identity drifted")

    episodes = ledger.get("episodes") or []
    if len(episodes) != int(external["expected_episode_count"]):
        raise ActuatorExternalValidationError("external episode inventory drifted")
    workcell = _workcell_candidate(source_receipt)
    expected_manifest = {
        str(row["recording_id"]): row
        for row in external["expected_episode_manifest"]
    }
    payloads: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_rows = 0
    for entry in episodes:
        recording_id = str(entry["recording_id"])
        if recording_id in seen_ids:
            raise ActuatorExternalValidationError(
                f"duplicate external episode: {recording_id}"
            )
        seen_ids.add(recording_id)
        manifest_row = expected_manifest.get(recording_id)
        if manifest_row is None:
            raise ActuatorExternalValidationError(
                f"external episode is not preregistered: {recording_id}"
            )
        if manifest_row != {
            "recording_id": recording_id,
            "sample_count": int(entry["motion_trace"]["sample_count"]),
            "samples_sha256": entry["samples_sha256"],
            "historical_replay_receipt_sha256": entry["sim_replay"][
                "receipt_sha256"
            ],
            "historical_state_trace_sha256": entry["sim_replay"][
                "state_trace_sha256"
            ],
        }:
            raise ActuatorExternalValidationError(
                f"external manifest disagrees with ledger: {recording_id}"
            )
        directory = _safe_repo_path(str(entry["source_path"]), repo_root=repo_root)
        receipt_path = directory / "recording_receipt.json"
        samples_path = directory / "samples.jsonl"
        replay_path = _safe_repo_path(
            str(entry["sim_replay"]["receipt_path"]), repo_root=repo_root
        )
        state_trace_path = _safe_repo_path(
            str(entry["sim_replay"]["state_trace_path"]), repo_root=repo_root
        )
        expected = {
            receipt_path: entry["receipt_sha256"],
            samples_path: entry["samples_sha256"],
            replay_path: entry["sim_replay"]["receipt_sha256"],
            state_trace_path: entry["sim_replay"]["state_trace_sha256"],
        }
        for path, digest in expected.items():
            if not path.is_file() or sha256_file(path) != digest:
                raise ActuatorExternalValidationError(
                    f"external source payload drifted: {path}"
                )
        rows = _read_samples(samples_path)
        if len(rows) != int(entry["motion_trace"]["sample_count"]):
            raise ActuatorExternalValidationError(
                f"external sample count drifted: {recording_id}"
            )
        timestamps = np.asarray(
            [row.get("timestamp_monotonic_seconds") for row in rows],
            dtype=np.float64,
        )
        if (
            timestamps.ndim != 1
            or not np.isfinite(timestamps).all()
            or len(timestamps) < 2
            or np.any(np.diff(timestamps) <= 0.0)
        ):
            raise ActuatorExternalValidationError(
                f"external timestamps are invalid: {recording_id}"
            )
        mapped = _mapped_episode(
            (
                {
                    "recording_id": recording_id,
                    "folder_label": directory.name.rsplit("__", 1)[0],
                    "sample_hz": int(entry["motion_trace"]["sample_hz"]),
                },
                "unknown_legacy_source",
                "unknown_legacy_destination",
                rows,
            ),
            workcell,
        )
        if mapped["actions"].dtype != np.float64 or mapped["actions"].shape != (
            len(rows),
            6,
        ):
            raise ActuatorExternalValidationError(
                f"external action schema drifted: {recording_id}"
            )
        payloads.append(
            {
                "recording_id": recording_id,
                "metadata_status": entry["metadata_status"],
                "samples_sha256": entry["samples_sha256"],
                "historical_replay_receipt_sha256": entry["sim_replay"][
                    "receipt_sha256"
                ],
                "historical_state_trace_sha256": entry["sim_replay"][
                    "state_trace_sha256"
                ],
                "mapped": mapped,
            }
        )
        total_rows += len(rows)
    if total_rows != int(external["expected_sample_count"]):
        raise ActuatorExternalValidationError("external total sample count drifted")
    if seen_ids != set(expected_manifest):
        raise ActuatorExternalValidationError("external manifest inventory drifted")
    payloads.sort(key=lambda row: row["recording_id"])
    return payloads, workcell, {
        "episode_count": len(payloads),
        "sample_count": total_rows,
        "ledger_sha256": sha256_file(ledger_path),
    }


def execute_external_replays(
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
    source_receipt: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Execute raw variants without evaluator thresholds or verdict authority."""

    validate_external_validation_contract(contract)
    payloads, workcell, inventory = load_external_episode_payloads(
        contract, source_receipt, repo_root=repo_root
    )
    experiment = _load_source_experiment(source_receipt, repo_root=repo_root)
    variants = {
        name: _variant_parameters(contract["variants"][name])
        for name in ("baseline", "candidate")
    }
    rows: list[dict[str, Any]] = []
    replay_count = 0
    for payload in payloads:
        mapped = payload["mapped"]
        variant_results: dict[str, Any] = {}
        for name in ("baseline", "candidate"):
            simulated, schedule, torque = _replay(
                mapped, workcell, experiment, variants[name]
            )
            metrics = _strip_arrays(
                _episode_metrics(mapped, simulated, workcell, experiment)
            )
            variant_results[name] = {
                "variant_id": contract["variants"][name]["variant_id"],
                "parameters": variants[name],
                "action_sha256": mapped["action_receipt"]["sha256"],
                "action_shape": mapped["action_receipt"]["shape"],
                "action_dtype": mapped["action_receipt"]["dtype"],
                "clipped_action_rows": mapped["action_receipt"]["clipped_rows"],
                "schedule_sha256": schedule["sha256"],
                "load_response": torque,
                "metrics": metrics,
            }
            replay_count += 1
        rows.append(
            {
                "recording_id": payload["recording_id"],
                "metadata_status": payload["metadata_status"],
                "samples_sha256": payload["samples_sha256"],
                "historical_replay_receipt_sha256": payload[
                    "historical_replay_receipt_sha256"
                ],
                "historical_state_trace_sha256": payload[
                    "historical_state_trace_sha256"
                ],
                "variants": variant_results,
            }
        )
    if replay_count != int(contract["budget"]["maximum_simulator_replays"]):
        raise ActuatorExternalValidationError("external replay budget mismatch")
    return {
        "schema_version": RAW_SCHEMA,
        "validation_id": contract["validation_id"],
        "contract_sha256": contract_sha256,
        "proof_class": contract["proof_boundary"]["external_proof_class"],
        "candidate_runner_score_authority": False,
        "candidate_runner_promotion_authority": False,
        "inventory": inventory,
        "budget": {
            "simulator_replays_used": replay_count,
            "retries_used": 0,
            "provider_calls_used": 0,
        },
        "episodes": rows,
    }


def _validate_raw_result(
    raw: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
) -> None:
    if raw.get("schema_version") != RAW_SCHEMA:
        raise ActuatorExternalValidationError("unexpected raw result schema")
    if set(raw) != RAW_TOP_LEVEL_KEYS:
        raise ActuatorExternalValidationError("raw top-level schema drifted")
    if raw.get("validation_id") != contract["validation_id"]:
        raise ActuatorExternalValidationError("raw result identity drifted")
    if raw.get("contract_sha256") != contract_sha256:
        raise ActuatorExternalValidationError(
            "raw result is not bound to the evaluator contract"
        )
    if raw.get("proof_class") != contract["proof_boundary"]["external_proof_class"]:
        raise ActuatorExternalValidationError("raw proof class drifted")
    if _contains_forbidden_runner_field(raw):
        raise ActuatorExternalValidationError("candidate runner attempted to self-score")
    if raw.get("candidate_runner_score_authority") is not False:
        raise ActuatorExternalValidationError("candidate runner gained score authority")
    if raw.get("candidate_runner_promotion_authority") is not False:
        raise ActuatorExternalValidationError(
            "candidate runner gained promotion authority"
        )
    episodes = raw.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 5:
        raise ActuatorExternalValidationError("raw external episode count drifted")
    inventory = raw.get("inventory") or {}
    if inventory != {
        "episode_count": 5,
        "sample_count": 2186,
        "ledger_sha256": contract["external_evaluation"]["intake_ledger"]["sha256"],
    }:
        raise ActuatorExternalValidationError("raw source inventory drifted")
    ids = [str(row.get("recording_id")) for row in episodes]
    if len(ids) != len(set(ids)):
        raise ActuatorExternalValidationError("raw result replays an episode twice")
    expected_manifest = {
        str(row["recording_id"]): row
        for row in contract["external_evaluation"]["expected_episode_manifest"]
    }
    if set(ids) != set(expected_manifest):
        raise ActuatorExternalValidationError("raw episode substitution detected")
    budget = raw.get("budget") or {}
    if budget != {
        "simulator_replays_used": 10,
        "retries_used": 0,
        "provider_calls_used": 0,
    }:
        raise ActuatorExternalValidationError("raw execution budget drifted")
    observed_sample_count = 0
    for row in episodes:
        if not isinstance(row, Mapping) or set(row) != RAW_EPISODE_KEYS:
            raise ActuatorExternalValidationError("raw episode schema drifted")
        for key in (
            "samples_sha256",
            "historical_replay_receipt_sha256",
            "historical_state_trace_sha256",
        ):
            _require_sha256(row.get(key), label=f"{row.get('recording_id')} {key}")
        variants = row.get("variants") or {}
        if set(variants) != {"baseline", "candidate"}:
            raise ActuatorExternalValidationError("raw variant set drifted")
        baseline = variants["baseline"]
        candidate = variants["candidate"]
        for name, variant in variants.items():
            if not isinstance(variant, Mapping) or set(variant) != RAW_VARIANT_KEYS:
                raise ActuatorExternalValidationError(
                    f"raw {name} variant schema drifted"
                )
            if variant.get("variant_id") != contract["variants"][name]["variant_id"]:
                raise ActuatorExternalValidationError(
                    f"raw {name} variant identity drifted"
                )
            _require_sha256(
                variant.get("action_sha256"),
                label=f"{row.get('recording_id')} {name} action",
            )
            _require_sha256(
                variant.get("schedule_sha256"),
                label=f"{row.get('recording_id')} {name} schedule",
            )
        if baseline.get("action_sha256") != candidate.get("action_sha256"):
            raise ActuatorExternalValidationError(
                f"action substitution detected for {row.get('recording_id')}"
            )
        if (
            baseline.get("action_shape") != candidate.get("action_shape")
            or not isinstance(baseline.get("action_shape"), list)
            or len(baseline["action_shape"]) != 2
            or int(baseline["action_shape"][1]) != 6
            or int(baseline["action_shape"][0]) <= 0
        ):
            raise ActuatorExternalValidationError("action shape changed across variants")
        if (
            baseline.get("action_dtype") != "float64"
            or candidate.get("action_dtype") != "float64"
        ):
            raise ActuatorExternalValidationError("action dtype is not float64")
        manifest_row = expected_manifest[str(row["recording_id"])]
        if {
            "recording_id": str(row["recording_id"]),
            "sample_count": int(baseline["action_shape"][0]),
            "samples_sha256": row["samples_sha256"],
            "historical_replay_receipt_sha256": row[
                "historical_replay_receipt_sha256"
            ],
            "historical_state_trace_sha256": row[
                "historical_state_trace_sha256"
            ],
        } != manifest_row:
            raise ActuatorExternalValidationError("raw source manifest drifted")
        if int(baseline.get("clipped_action_rows", -1)) != 0 or int(
            candidate.get("clipped_action_rows", -1)
        ) != 0:
            raise ActuatorExternalValidationError("action clipping detected")
        if baseline.get("parameters") != _variant_parameters(
            contract["variants"]["baseline"]
        ):
            raise ActuatorExternalValidationError("raw baseline parameters drifted")
        if candidate.get("parameters") != _variant_parameters(
            contract["variants"]["candidate"]
        ):
            raise ActuatorExternalValidationError("raw candidate parameters drifted")
        row_sample_count = int(baseline["action_shape"][0])
        _validate_metrics(
            baseline.get("metrics"),
            sample_count=row_sample_count,
            label=f"{row.get('recording_id')} baseline",
        )
        _validate_metrics(
            candidate.get("metrics"),
            sample_count=row_sample_count,
            label=f"{row.get('recording_id')} candidate",
        )
        observed_sample_count += row_sample_count
    if observed_sample_count != int(
        contract["external_evaluation"]["expected_sample_count"]
    ):
        raise ActuatorExternalValidationError("raw action sample total drifted")


def _task_consequence_summary(
    task_receipt: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    if task_receipt.get("proof_class") != contract["proof_boundary"][
        "selection_proof_class"
    ]:
        raise ActuatorExternalValidationError("task receipt proof class drifted")
    comparison = task_receipt.get("target_piece_consequence_comparison") or {}
    before = comparison.get("current_baseline") or {}
    after = comparison.get("selected_load_bias") or {}
    expected_denominator = int(
        contract["evaluator"]["strict_task_score_denominator"]
    )
    if int(before.get("episode_count", -1)) != expected_denominator or int(
        after.get("episode_count", -1)
    ) != expected_denominator:
        raise ActuatorExternalValidationError("task consequence denominator drifted")
    expected_successes = int(
        contract["evaluator"]["expected_strict_task_successes_before"]
    )
    if int(before.get("task_consequence_successes", -1)) != expected_successes:
        raise ActuatorExternalValidationError("baseline task score drifted")
    if comparison.get("verified_grasp_or_task_advancement") is not False:
        raise ActuatorExternalValidationError(
            "task receipt unexpectedly claims consequence advancement"
        )
    after_successes = int(after.get("task_consequence_successes", -1))
    if after_successes < 0:
        raise ActuatorExternalValidationError("candidate task score is invalid")
    return {
        "denominator": expected_denominator,
        "strict_successes_before": expected_successes,
        "strict_successes_after": after_successes,
        "strict_task_score_changed": after_successes != expected_successes,
        "verified_grasp_or_task_advancement": False,
    }


def evaluate_external_replays(
    raw: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
    task_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate raw results with evaluator-owned frozen thresholds."""

    validate_external_validation_contract(contract)
    _validate_raw_result(raw, contract, contract_sha256=contract_sha256)
    paired: list[dict[str, Any]] = []
    improved = 0
    for row in raw["episodes"]:
        baseline = row["variants"]["baseline"]["metrics"]
        candidate = row["variants"]["candidate"]["metrics"]
        baseline_rms = float(baseline["overall_joint_rms_degrees"])
        candidate_rms = float(candidate["overall_joint_rms_degrees"])
        relative = (baseline_rms - candidate_rms) / baseline_rms
        improved += int(relative > 0.0)
        paired.append(
            {
                "recording_id": row["recording_id"],
                "action_sha256": row["variants"]["baseline"]["action_sha256"],
                "action_byte_identical": True,
                "baseline_metrics": baseline,
                "candidate_metrics": candidate,
                "joint_rms_relative_improvement": relative,
            }
        )
    pooled_baseline = _replace_nonfinite(
        _pool(row["baseline_metrics"] for row in paired)
    )
    pooled_candidate = _replace_nonfinite(
        _pool(row["candidate_metrics"] for row in paired)
    )
    joint_improvement = (
        float(pooled_baseline["overall_joint_rms_degrees"])
        - float(pooled_candidate["overall_joint_rms_degrees"])
    ) / float(pooled_baseline["overall_joint_rms_degrees"])
    ee_ratio = float(pooled_candidate["ee_rms_m"]) / float(
        pooled_baseline["ee_rms_m"]
    )
    bootstrap_contract = contract["evaluator"]["bootstrap"]
    bootstrap = _bootstrap_paired_metrics(
        paired,
        seed=int(bootstrap_contract["seed"]),
        replicates=int(bootstrap_contract["replicates"]),
        confidence=float(bootstrap_contract["confidence_level"]),
    )
    bootstrap["dependence_boundary"] = (
        "Conditional uncertainty over the five retained historical acquisition "
        "sessions only; it is not a physical task, calibration, or transfer claim."
    )
    task = _task_consequence_summary(task_receipt, contract)
    gates = {
        "action_invariance": all(row["action_byte_identical"] for row in paired),
        "pooled_joint_rms_effect": joint_improvement
        >= float(
            contract["evaluator"][
                "minimum_pooled_joint_rms_relative_improvement"
            ]
        ),
        "episode_improvement_count": improved
        >= int(contract["evaluator"]["minimum_improved_episode_count"]),
        "bootstrap_direction": bootstrap["joint_rms_relative_improvement"][
            "confidence_interval"
        ][0]
        > 0.0,
        "pooled_ee_non_regression": ee_ratio
        <= float(
            contract["evaluator"]["maximum_pooled_ee_rms_relative_to_baseline"]
        ),
        "task_receipt_preserves_score": task["strict_task_score_changed"] is False,
    }
    trace_passed = all(
        value for name, value in gates.items() if name != "task_receipt_preserves_score"
    )
    return {
        "schema_version": EVALUATION_SCHEMA,
        "validation_id": contract["validation_id"],
        "contract_sha256": contract_sha256,
        "evaluator_owner": contract["evaluator"]["owner"],
        "proof_class": contract["proof_boundary"]["external_proof_class"],
        "paired_episodes": paired,
        "pooled": {
            "baseline": pooled_baseline,
            "candidate": pooled_candidate,
            "joint_rms_relative_improvement": joint_improvement,
            "ee_rms_candidate_to_baseline_ratio": ee_ratio,
            "improved_episode_count": improved,
        },
        "bootstrap": bootstrap,
        "gates": gates,
        "external_trace_validation_passed": trace_passed,
        "task_consequence": task,
        "task_completion_score_changed": False,
        "parameters_promoted": False,
        "verdict": (
            "external_trace_validation_pass_task_completion_unchanged"
            if trace_passed
            else "external_trace_validation_reject_task_completion_unchanged"
        ),
        "isolation_guarantee": (
            "Trusted-code raw-runner/evaluator interface separation with "
            "content, action, config, budget, and receipt identity checks; "
            "not hostile-code process or cryptographic sandboxing."
        ),
    }


def run_actuator_external_validation(
    output_root: Path,
    *,
    contract_path: Path = CONTRACT_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Execute the preregistered family once and emit content-addressed evidence."""

    contract = load_external_validation_contract(contract_path)
    contract_sha256 = sha256_file(contract_path)
    selection = contract["selection_evidence"]
    source_path, source_receipt = _load_hash_bound_json(
        selection["servo_load_bias_receipt"],
        repo_root=repo_root,
        require_digest=True,
    )
    task_path, task_receipt = _load_hash_bound_json(
        selection["fidelity_advancement_receipt"],
        repo_root=repo_root,
        require_digest=True,
    )
    raw = execute_external_replays(
        contract,
        contract_sha256=contract_sha256,
        source_receipt=source_receipt,
        repo_root=repo_root,
    )
    evaluation = evaluate_external_replays(
        raw,
        contract,
        contract_sha256=contract_sha256,
        task_receipt=task_receipt,
    )
    output_root = output_root.resolve()
    raw_path = output_root / "raw_execution.json"
    evaluation_path = output_root / "evaluation.json"
    atomic_write_json(raw_path, raw)
    atomic_write_json(evaluation_path, evaluation)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "validation_id": contract["validation_id"],
        "proof_classes": {
            "selection": contract["proof_boundary"]["selection_proof_class"],
            "external": contract["proof_boundary"]["external_proof_class"],
            "task": contract["proof_boundary"]["task_proof_class"],
        },
        "contract": {
            "path": contract_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": contract_sha256,
        },
        "implementation": {
            "path": Path(__file__).resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(Path(__file__)),
        },
        "selection_receipt": {
            "path": source_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(source_path),
            "receipt_digest": source_receipt["receipt_digest"],
        },
        "task_evaluator_receipt": {
            "path": task_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(task_path),
            "receipt_digest": task_receipt["receipt_digest"],
        },
        "raw_execution": {
            "path": raw_path.name,
            "sha256": sha256_file(raw_path),
            "episode_count": raw["inventory"]["episode_count"],
            "sample_count": raw["inventory"]["sample_count"],
            **raw["budget"],
        },
        "evaluation": {
            "path": evaluation_path.name,
            "sha256": sha256_file(evaluation_path),
            "verdict": evaluation["verdict"],
            "external_trace_validation_passed": evaluation[
                "external_trace_validation_passed"
            ],
            "task_completion_score_changed": False,
        },
        "parameters_promoted": False,
        "authority": copy.deepcopy(contract["authority"]),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    result = copy.deepcopy(receipt)
    result["receipt_path"] = receipt_path.name
    result["receipt_sha256"] = sha256_file(receipt_path)
    return result
