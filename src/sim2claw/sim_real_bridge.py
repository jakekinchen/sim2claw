"""Fail-closed physical-source to current-simulation comparison boundary.

The five owner recordings predate the 100 mm workspace registration.  This
module permits their robot-response signals to inform diagnostic simulation
perturbations while preventing their pixels, labels, or free-text outcomes from
becoming 100 mm task evidence or imitation rows.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .paths import REPO_ROOT
from .scene import scene_summary
from .source_episode import sha256_file


BRIDGE_PATH = (
    REPO_ROOT / "configs" / "experiments" / "pawn_sim_real_bridge_v1.json"
)
BRIDGE_SCHEMA = "sim2claw.pawn_sim_real_bridge.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_sim_real_bridge_receipt.v1"
HISTORICAL_CHECKPOINT_ROOT = Path(
    "/Users/kelly/Documents/Codex/sim2claw-groot-n17-phase-progress-0718/"
    "checkpoint-1000"
)


def _relative_file(path_text: str, *, repo_root: Path) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("bridge paths must be safe repository-relative paths")
    return repo_root / relative


def load_bridge_contract(
    path: Path = BRIDGE_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != BRIDGE_SCHEMA:
        raise ValueError("unsupported sim-to-real bridge contract")
    if contract.get("experiment_id") != "pawn_sim_real_bridge_v1":
        raise ValueError("unexpected sim-to-real bridge identity")
    if contract.get("frozen_before_policy_comparison") is not True:
        raise ValueError("sim-to-real bridge must be frozen before comparison")

    simulation = contract["current_simulation"]
    for path_key, hash_key in (
        ("capture_config_path", "capture_config_sha256"),
        ("source_contract_path", "source_contract_sha256"),
        ("pawn_evaluator_path", "pawn_evaluator_sha256"),
    ):
        candidate = _relative_file(simulation[path_key], repo_root=repo_root)
        if not candidate.is_file() or sha256_file(candidate) != simulation[hash_key]:
            raise ValueError(f"current simulation identity drifted: {path_key}")
    summary = scene_summary(
        _relative_file(simulation["capture_config_path"], repo_root=repo_root),
        piece_layout="sparse_two_sided_pawns",
    )
    if (
        summary["board"]["scene_id"] != simulation["scene_id"]
        or summary["board"]["pose_id"] != simulation["board_pose_id"]
        or summary["board"]["center_in_table_frame_xy_m"]
        != simulation["board_center_in_table_frame_xy_m"]
        or summary["workspace_pose"]["pose_id"]
        != simulation["workspace_pose_id"]
    ):
        raise ValueError("runtime scene does not match the 100 mm bridge contract")

    cohort = contract["physical_source_cohort"]
    ledger_path = _relative_file(cohort["ledger_path"], repo_root=repo_root)
    if not ledger_path.is_file() or sha256_file(ledger_path) != cohort["ledger_sha256"]:
        raise ValueError("physical cohort ledger drifted")
    if int(cohort.get("expected_training_rows_admitted", -1)) != 0:
        raise ValueError("unqualified physical rows may not be pre-admitted")
    if int(contract["admission"].get("held_out_rows", -1)) != 0:
        raise ValueError("sim-to-real bridge must keep held-out rows at zero")
    if contract["admission"].get("failed_actions_may_enter_behavior_cloning") is not False:
        raise ValueError("failed physical actions may not enter behavior cloning")
    if contract["authority"].get("brev_may_start_before_local_preflight_passes") is not False:
        raise ValueError("paid compute must remain closed before local preflight")
    return contract


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} is not an object")
        rows.append(value)
    return rows


def _matrix(rows: list[dict[str, Any]], field: str) -> np.ndarray:
    values = np.asarray([row.get(field) for row in rows], dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 6 or not np.isfinite(values).all():
        raise ValueError(f"physical source field {field} must be finite Nx6")
    return values


def joint_response_metrics(
    rows: list[dict[str, Any]], *, sample_hz: int, maximum_lag_seconds: float
) -> dict[str, Any]:
    if not rows or sample_hz <= 0:
        raise ValueError("joint-response metrics require sampled physical rows")
    command = _matrix(rows, "follower_command_degrees")
    actual = _matrix(rows, "follower_actual_position_degrees")
    error = command - actual
    max_lag = min(len(rows) - 1, int(math.ceil(maximum_lag_seconds * sample_hz)))
    best_lags: list[int] = []
    lagged_rmse: list[float] = []
    for joint_index in range(6):
        candidates: list[tuple[float, int]] = []
        for lag in range(max_lag + 1):
            predicted = command[: len(rows) - lag, joint_index]
            observed = actual[lag:, joint_index]
            candidates.append((float(np.sqrt(np.mean((predicted - observed) ** 2))), lag))
        rmse, lag = min(candidates, key=lambda item: (item[0], item[1]))
        best_lags.append(lag)
        lagged_rmse.append(rmse)
    velocity = np.diff(actual, axis=0) * float(sample_hz)
    rate_limited = sum(bool(row.get("rate_limited")) for row in rows)
    return {
        "sample_count": len(rows),
        "sample_hz": sample_hz,
        "per_joint_rmse_native_units": np.sqrt(np.mean(error**2, axis=0)).tolist(),
        "per_joint_max_abs_error_native_units": np.max(np.abs(error), axis=0).tolist(),
        "best_lag_samples": best_lags,
        "best_lag_seconds": [lag / float(sample_hz) for lag in best_lags],
        "lag_aligned_rmse_native_units": lagged_rmse,
        "observed_abs_velocity_p95_native_units_per_second": (
            np.percentile(np.abs(velocity), 95, axis=0).tolist()
            if len(rows) > 1
            else [0.0] * 6
        ),
        "rate_limited_sample_count": rate_limited,
        "rate_limited_sample_fraction": rate_limited / len(rows),
    }


def inspect_sim_real_bridge(
    *,
    repo_root: Path = REPO_ROOT,
    contract_path: Path = BRIDGE_PATH,
    physical_root: Path | None = None,
    checkpoint_root: Path = HISTORICAL_CHECKPOINT_ROOT,
    output_path: Path | None = None,
) -> dict[str, Any]:
    contract = load_bridge_contract(contract_path, repo_root=repo_root)
    cohort_contract = contract["physical_source_cohort"]
    ledger_path = _relative_file(cohort_contract["ledger_path"], repo_root=repo_root)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("cohort_id") != cohort_contract["cohort_id"]:
        raise ValueError("physical cohort identity changed")
    if len(ledger.get("episodes") or []) != int(cohort_contract["expected_episode_count"]):
        raise ValueError("physical cohort episode count changed")
    if int(ledger["cohort_summary"]["saved_physical_sample_count"]) != int(
        cohort_contract["expected_sample_count"]
    ):
        raise ValueError("physical cohort sample count changed")

    raw_root = physical_root or _relative_file(
        cohort_contract["raw_root"], repo_root=repo_root
    )
    episode_reports: list[dict[str, Any]] = []
    total_verified_rows = 0
    all_raw_verified = True
    for episode in ledger["episodes"]:
        source_name = Path(str(episode["source_path"])).name
        directory = raw_root / source_name
        required = [directory / name for name in cohort_contract["required_raw_files"]]
        missing = [path.name for path in required if not path.is_file()]
        report: dict[str, Any] = {
            "recording_id": episode["recording_id"],
            "source_directory": str(directory),
            "raw_available": not missing,
            "missing_files": missing,
            "metadata_status": episode["metadata_status"],
            "training_admission": episode["training_admission"],
        }
        if missing:
            all_raw_verified = False
        else:
            expected_hashes = {
                "recording_receipt.json": episode["receipt_sha256"],
                "samples.jsonl": episode["samples_sha256"],
                "overhead_c922.mp4": episode["overhead_video_sha256"],
                "sim_replay_receipt.json": episode["sim_replay"]["receipt_sha256"],
                "sim_replay_state_trace.json": episode["sim_replay"]["state_trace_sha256"],
            }
            mismatches = [
                name
                for name, expected in expected_hashes.items()
                if sha256_file(directory / name) != expected
            ]
            if mismatches:
                all_raw_verified = False
                report["hash_mismatches"] = mismatches
            else:
                rows = _read_jsonl(directory / "samples.jsonl")
                metrics = joint_response_metrics(
                    rows,
                    sample_hz=int(episode["motion_trace"]["sample_hz"]),
                    maximum_lag_seconds=float(
                        contract["comparison"]["maximum_lag_search_seconds"]
                    ),
                )
                if metrics["sample_count"] != int(episode["motion_trace"]["sample_count"]):
                    raise ValueError("physical source sample count differs from its ledger")
                total_verified_rows += metrics["sample_count"]
                report["hashes_verified"] = True
                report["joint_response"] = metrics
        episode_reports.append(report)

    checkpoint = contract["policy_lineage"]["historical_groot_checkpoint"]
    checkpoint_available = checkpoint_root.is_dir()
    checkpoint_file_count = (
        len([path for path in checkpoint_root.rglob("*") if path.is_file()])
        if checkpoint_available
        else 0
    )
    current = contract["current_simulation"]
    spatial_pose_matches = (
        cohort_contract["recorded_scene_id"] == current["scene_id"]
        and cohort_contract["recorded_board_pose_id"] == current["board_pose_id"]
    )
    blockers: list[str] = []
    if not all_raw_verified:
        blockers.append("owner_local_raw_physical_artifacts_missing_or_hash_mismatched")
    if not spatial_pose_matches:
        blockers.append("physical_pixels_and_square_labels_bind_72mm_not_current_100mm")
    if int(ledger["cohort_summary"]["training_rows_admitted"]) != 0:
        raise ValueError("tracked physical ledger unexpectedly admits training rows")
    blockers.extend(
        [
            "physical_task_outcomes_and_piece_target_poses_not_evaluator_qualified",
            "historical_groot_checkpoint_has_zero_pawn_authority",
            "pawn_groot_dataset_receipt_and_loader_proof_not_frozen",
        ]
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "bridge_contract_sha256": sha256_file(contract_path),
        "bridge_module_sha256": sha256_file(Path(__file__)),
        "current_simulation": current,
        "physical_source": {
            "cohort_id": ledger["cohort_id"],
            "ledger_sha256": sha256_file(ledger_path),
            "recorded_scene_id": cohort_contract["recorded_scene_id"],
            "recorded_board_pose_id": cohort_contract["recorded_board_pose_id"],
            "raw_root": str(raw_root),
            "all_raw_payloads_verified": all_raw_verified,
            "verified_joint_response_rows": total_verified_rows,
            "training_rows_admitted": 0,
            "episodes": episode_reports,
        },
        "policy": {
            "physical_source_is_a_learned_policy": False,
            "physical_trained_checkpoint_present": False,
            "historical_checkpoint_available": checkpoint_available,
            "historical_checkpoint_file_count": checkpoint_file_count,
            "historical_checkpoint_manifest_sha256": checkpoint["manifest_sha256"],
            "historical_checkpoint_allowed_use": checkpoint["allowed_use"],
            "pawn_authority": False,
        },
        "comparison_readiness": {
            "joint_response_calibration_ready": all_raw_verified,
            "100mm_spatial_comparison_ready": all_raw_verified and spatial_pose_matches,
            "pawn_policy_training_ready": False,
            "pawn_policy_closed_loop_comparison_ready": False,
        },
        "blockers": blockers,
        "training_rows_authorized": 0,
        "held_out_rows_used": 0,
        "brev_authorized_to_start": False,
        "physical_authority_created": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt["receipt_path"] = str(output_path)
        receipt["receipt_sha256"] = sha256_file(output_path)
    return receipt
