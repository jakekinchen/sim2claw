"""Publication-safe closeout for the action-frozen B--G RMS advancement."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_servo_load_bias import (
    RECEIPT_SCHEMA as LOAD_BIAS_RECEIPT_SCHEMA,
    _baseline_candidate,
    _candidate_id,
    _replay,
    load_servo_load_bias_contract,
)
from .pawn_bg_timing_ablation import _episode_metrics, _mapped_episode, _pool, _strip_arrays


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_fidelity_advancement_v1.json"
)
SCHEMA = "sim2claw.pawn_bg_fidelity_advancement.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_fidelity_advancement_receipt.v1"
BODY_JOINT_COUNT = 5


class FidelityAdvancementError(RuntimeError):
    """The frozen fidelity-advancement closeout cannot be reproduced safely."""


def load_fidelity_advancement_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FidelityAdvancementError(f"cannot read advancement contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise FidelityAdvancementError("unexpected fidelity-advancement contract schema")
    if any(contract.get("authority", {}).values()):
        raise FidelityAdvancementError("fidelity-advancement authority widened")
    bootstrap = contract.get("bootstrap", {})
    if int(bootstrap.get("replicates", 0)) < 1000:
        raise FidelityAdvancementError("bootstrap replicate count is too small")
    if bootstrap.get("resampling_unit") != "whole_episode":
        raise FidelityAdvancementError("bootstrap must resample whole episodes")
    boundary = contract.get("boundary_disclosure", {})
    if not boundary.get("selection_at_grid_boundary"):
        raise FidelityAdvancementError("search-boundary disclosure was removed")
    if float(boundary.get("selected_value")) != float(boundary.get("frozen_grid_lower_bound")):
        raise FidelityAdvancementError("search-boundary disclosure is internally inconsistent")
    return contract


def _load_bound_receipt(
    repository_root: Path, contract: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    binding = contract["evidence"]["servo_load_bias_receipt"]
    path = repository_root / binding["path"]
    if sha256_file(path) != binding["sha256"]:
        raise FidelityAdvancementError("servo load-bias receipt hash drifted")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FidelityAdvancementError(f"cannot read servo load-bias receipt {path}: {error}") from error
    if receipt.get("schema_version") != binding["schema_version"]:
        raise FidelityAdvancementError("servo load-bias receipt schema drifted")
    if receipt.get("schema_version") != LOAD_BIAS_RECEIPT_SCHEMA:
        raise FidelityAdvancementError("unexpected installed load-bias receipt schema")
    payload = dict(receipt)
    recorded_digest = payload.pop("receipt_digest", None)
    if recorded_digest != canonical_digest(payload):
        raise FidelityAdvancementError("servo load-bias canonical receipt digest is invalid")
    return path, receipt


def _percentile_interval(values: np.ndarray, confidence: float) -> list[float]:
    alpha = (1.0 - confidence) / 2.0
    return [
        float(np.quantile(values, alpha)),
        float(np.quantile(values, 1.0 - alpha)),
    ]


def _bootstrap_paired_metrics(
    rows: list[dict[str, Any]], *, seed: int, replicates: int, confidence: float
) -> dict[str, Any]:
    episode_count = len(rows)
    if episode_count < 2:
        raise FidelityAdvancementError("paired bootstrap requires at least two episodes")
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, episode_count, size=(replicates, episode_count))
    sample_counts = np.asarray(
        [row["baseline_metrics"]["sample_count"] for row in rows], dtype=np.float64
    )
    candidate_counts = np.asarray(
        [row["candidate_metrics"]["sample_count"] for row in rows], dtype=np.float64
    )
    if not np.array_equal(sample_counts, candidate_counts):
        raise FidelityAdvancementError("paired candidate and baseline sample counts differ")
    baseline_joint_sse = np.asarray(
        [sum(row["baseline_metrics"]["joint_squared_error_degrees"]) for row in rows],
        dtype=np.float64,
    )
    candidate_joint_sse = np.asarray(
        [sum(row["candidate_metrics"]["joint_squared_error_degrees"]) for row in rows],
        dtype=np.float64,
    )
    baseline_ee_sse = np.asarray(
        [row["baseline_metrics"]["ee_squared_error_m2"] for row in rows], dtype=np.float64
    )
    candidate_ee_sse = np.asarray(
        [row["candidate_metrics"]["ee_squared_error_m2"] for row in rows], dtype=np.float64
    )
    denominator = sample_counts[samples].sum(axis=1)
    baseline_joint = np.sqrt(
        baseline_joint_sse[samples].sum(axis=1) / (denominator * BODY_JOINT_COUNT)
    )
    candidate_joint = np.sqrt(
        candidate_joint_sse[samples].sum(axis=1) / (denominator * BODY_JOINT_COUNT)
    )
    baseline_ee = np.sqrt(baseline_ee_sse[samples].sum(axis=1) / denominator)
    candidate_ee = np.sqrt(candidate_ee_sse[samples].sum(axis=1) / denominator)
    joint_improvement = (baseline_joint - candidate_joint) / baseline_joint
    ee_improvement = (baseline_ee - candidate_ee) / baseline_ee
    return {
        "seed": seed,
        "replicates": replicates,
        "confidence_level": confidence,
        "resampling_unit": "whole_episode",
        "dependence_boundary": (
            "Conditional retained-episode uncertainty only; the 11 episodes do not "
            "constitute independent physical acquisition sessions."
        ),
        "joint_rms_relative_improvement": {
            "confidence_interval": _percentile_interval(joint_improvement, confidence),
            "probability_greater_than_zero": float(np.mean(joint_improvement > 0.0)),
            "probability_at_least_five_percent": float(np.mean(joint_improvement >= 0.05)),
        },
        "ee_rms_relative_improvement": {
            "confidence_interval": _percentile_interval(ee_improvement, confidence),
            "probability_greater_than_zero": float(np.mean(ee_improvement > 0.0)),
        },
        "baseline_joint_rms_degrees": {
            "confidence_interval": _percentile_interval(baseline_joint, confidence)
        },
        "candidate_joint_rms_degrees": {
            "confidence_interval": _percentile_interval(candidate_joint, confidence)
        },
        "baseline_ee_rms_m": {
            "confidence_interval": _percentile_interval(baseline_ee, confidence)
        },
        "candidate_ee_rms_m": {
            "confidence_interval": _percentile_interval(candidate_ee, confidence)
        },
    }


def _plot_closeout(*, receipt: dict[str, Any], output_path: Path) -> None:
    rows = receipt["paired_validation_episodes"]
    baseline = [row["baseline_metrics"]["overall_joint_rms_degrees"] for row in rows]
    candidate = [row["candidate_metrics"]["overall_joint_rms_degrees"] for row in rows]
    consequences = receipt["target_piece_consequence_comparison"]
    before = consequences["current_baseline"]
    after = consequences["selected_load_bias"]

    figure, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    figure.suptitle(
        "Action-frozen B–G fidelity advancement and consequence boundary",
        fontsize=16,
        fontweight="bold",
    )

    ax = axes[0]
    for left, right in zip(baseline, candidate, strict=True):
        ax.plot([0, 1], [left, right], color="#7f8c8d", alpha=0.7, marker="o")
    ax.set(
        xticks=[0, 1],
        xticklabels=["current baseline", "fold-selected"],
        ylabel="episode joint RMS (degrees)",
        title=f"A. Paired validation episodes (n={len(rows)})",
    )

    ax = axes[1]
    pooled = receipt["pooled_cross_validated_metrics"]
    values = [
        pooled["baseline"]["overall_joint_rms_degrees"],
        pooled["candidate"]["overall_joint_rms_degrees"],
    ]
    ax.bar([0, 1], values, color=["#9d9d9d", "#4c78a8"])
    ax.set(
        xticks=[0, 1],
        xticklabels=["baseline", "candidate"],
        ylabel="joint RMS (degrees)",
        title=f"B. Pooled CV: {pooled['joint_rms_relative_improvement'] * 100:.2f}% lower",
    )
    ax.axhline(values[0] * 0.95, color="#333333", linestyle="--", linewidth=1, label="5% gate")
    ax.legend(fontsize=8)

    ax = axes[2]
    categories = ["contact", "lift", "inside target", "strict success"]
    before_values = [
        before["selected_piece_contact"],
        before["lifted"],
        before["whole_base_inside_destination"],
        before["task_consequence_successes"],
    ]
    after_values = [
        after["selected_piece_contact"],
        after["lifted"],
        after["whole_base_inside_destination"],
        after["task_consequence_successes"],
    ]
    x = np.arange(len(categories))
    ax.bar(x - 0.18, before_values, 0.36, color="#9d9d9d", label="baseline")
    ax.bar(x + 0.18, after_values, 0.36, color="#e45756", label="candidate")
    ax.set(
        xticks=x,
        xticklabels=categories,
        ylim=(0, 11.8),
        ylabel="episodes / 11",
        title="C. No grasp/task promotion",
    )
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_fidelity_advancement_closeout(
    *,
    source_repository_root: Path,
    output_root: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_fidelity_advancement_contract(contract_path)
    source_receipt_path, source_receipt = _load_bound_receipt(
        source_repository_root, contract
    )
    if not source_receipt["advancement_gates"]["verified_significant_rms_advancement"]:
        raise FidelityAdvancementError("source campaign did not pass its frozen RMS gate")
    if not source_receipt["action_arrays_byte_identical_across_variants"]:
        raise FidelityAdvancementError("source campaign action-invariance gate failed")

    servo_contract_path = Path(source_receipt["contract"]["path"])
    if sha256_file(servo_contract_path) != source_receipt["contract"]["sha256"]:
        raise FidelityAdvancementError("source servo contract hash drifted")
    servo_contract = load_servo_load_bias_contract(servo_contract_path)
    train_payloads, events = _load_partition(source_repository_root, "train")
    _parent, workcell, _parameters, _details = _reconstruct_stage_d(train_payloads, events)
    payload_by_id: dict[str, tuple[dict[str, Any], str, str, list[dict[str, Any]]]] = {}
    for payload in train_payloads:
        recording_id = str(payload[0]["recording_id"])
        payload_by_id[recording_id] = payload
    trace_by_id = {str(row["recording_id"]): row for row in source_receipt["traces"]}
    baseline_candidate = _baseline_candidate(servo_contract)

    paired_rows: list[dict[str, Any]] = []
    for fold in source_receipt["grouped_cross_validation"]["folds"]:
        candidate = {name: float(value) for name, value in fold["selected_candidate"].items()}
        if candidate["elbow_load_bias_coefficient"] != float(
            contract["boundary_disclosure"]["selected_value"]
        ):
            raise FidelityAdvancementError("fold-selected coefficient differs from frozen disclosure")
        for recording_id in fold["validation_episode_ids"]:
            mapped = _mapped_episode(payload_by_id[str(recording_id)], workcell)
            trace = trace_by_id[str(recording_id)]
            action_hash = _array_sha256(mapped["actions"])
            if action_hash != trace["action"]["sha256"]:
                raise FidelityAdvancementError(f"action hash drift for {recording_id}")
            candidate_states, schedule, torque = _replay(
                mapped, workcell, servo_contract, candidate
            )
            candidate_metrics = _episode_metrics(
                mapped, candidate_states, workcell, servo_contract
            )
            baseline_metrics = trace["metrics"]["current_baseline"]
            paired_rows.append(
                {
                    "recording_id": str(recording_id),
                    "fold_index": int(fold["fold_index"]),
                    "candidate_id": _candidate_id(candidate),
                    "candidate": candidate,
                    "action_sha256": action_hash,
                    "baseline_action_sha256": trace["action"]["sha256"],
                    "action_byte_identical": action_hash == trace["action"]["sha256"],
                    "baseline_metrics": baseline_metrics,
                    "candidate_metrics": _strip_arrays(candidate_metrics),
                    "candidate_schedule": schedule,
                    "candidate_load_bias_torque": torque,
                }
            )
    paired_rows.sort(key=lambda row: row["recording_id"])
    if len(paired_rows) != 11 or len({row["recording_id"] for row in paired_rows}) != 11:
        raise FidelityAdvancementError("paired validation inventory must contain 11 unique episodes")

    pooled_baseline = _pool(row["baseline_metrics"] for row in paired_rows)
    pooled_candidate = _pool(row["candidate_metrics"] for row in paired_rows)
    source_pooled = source_receipt["grouped_cross_validation"]
    for actual, expected, label in (
        (
            pooled_baseline["overall_joint_rms_degrees"],
            source_pooled["pooled_baseline"]["overall_joint_rms_degrees"],
            "pooled baseline joint RMS",
        ),
        (
            pooled_candidate["overall_joint_rms_degrees"],
            source_pooled["pooled_candidate"]["overall_joint_rms_degrees"],
            "pooled candidate joint RMS",
        ),
        (
            pooled_candidate["ee_rms_m"],
            source_pooled["pooled_candidate"]["ee_rms_m"],
            "pooled candidate EE RMS",
        ),
    ):
        if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12):
            raise FidelityAdvancementError(f"{label} does not reproduce source receipt")

    joint_improvement = float(
        (pooled_baseline["overall_joint_rms_degrees"] - pooled_candidate["overall_joint_rms_degrees"])
        / pooled_baseline["overall_joint_rms_degrees"]
    )
    ee_improvement = float(
        (pooled_baseline["ee_rms_m"] - pooled_candidate["ee_rms_m"])
        / pooled_baseline["ee_rms_m"]
    )
    bootstrap_contract = contract["bootstrap"]
    bootstrap = _bootstrap_paired_metrics(
        paired_rows,
        seed=int(bootstrap_contract["seed"]),
        replicates=int(bootstrap_contract["replicates"]),
        confidence=float(bootstrap_contract["confidence_level"]),
    )
    gates_contract = contract["gates"]
    gates = {
        "source_campaign_advancement_gate": bool(
            source_receipt["advancement_gates"]["verified_significant_rms_advancement"]
        ),
        "point_joint_rms_effect_size_gate": joint_improvement
        >= float(gates_contract["minimum_point_cross_validated_joint_rms_relative_improvement"]),
        "joint_rms_directional_bootstrap_gate": bootstrap["joint_rms_relative_improvement"]["confidence_interval"][0]
        > 0.0,
        "point_ee_non_regression_gate": pooled_candidate["ee_rms_m"]
        <= float(gates_contract["maximum_point_cross_validated_ee_rms_m"]),
        "all_validation_folds_improve_gate": all(
            float(fold["validation_joint_rms_relative_improvement"]) > 0.0
            for fold in source_receipt["grouped_cross_validation"]["folds"]
        ),
        "action_invariance_gate": all(row["action_byte_identical"] for row in paired_rows),
        "search_boundary_disclosed_gate": bool(
            contract["boundary_disclosure"]["selection_at_grid_boundary"]
        ),
    }
    verified = all(gates.values())

    consequence = source_receipt["action_frozen_consequence_replay"]
    before = consequence["current_baseline"]["summary"]
    after = consequence["selected_load_bias"]["summary"]
    consequence_comparison = {
        "current_baseline": before,
        "selected_load_bias": after,
        "delta": {
            "selected_piece_contact": int(after["selected_piece_contact"] - before["selected_piece_contact"]),
            "lifted": int(after["lifted"] - before["lifted"]),
            "whole_base_inside_destination": int(after["whole_base_inside_destination"] - before["whole_base_inside_destination"]),
            "task_consequence_successes": int(after["task_consequence_successes"] - before["task_consequence_successes"]),
            "mean_final_target_distance_m": float(after["mean_final_target_distance_m"] - before["mean_final_target_distance_m"]),
            "mean_final_target_distance_relative_improvement": float(
                (before["mean_final_target_distance_m"] - after["mean_final_target_distance_m"])
                / before["mean_final_target_distance_m"]
            ),
        },
        "verified_grasp_or_task_advancement": bool(
            source_receipt["advancement_gates"]["verified_significant_consequence_advancement"]
        ),
    }

    output_root = output_root.resolve()
    figure_path = output_root / "fidelity_advancement_summary.png"
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_trace_fidelity_advancement_closeout",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "source_servo_load_bias_receipt": {
            "path": str(source_receipt_path.resolve()),
            "sha256": sha256_file(source_receipt_path),
            "receipt_digest": source_receipt["receipt_digest"],
        },
        "paired_validation_episodes": paired_rows,
        "pooled_cross_validated_metrics": {
            "baseline": pooled_baseline,
            "candidate": pooled_candidate,
            "joint_rms_relative_improvement": joint_improvement,
            "ee_rms_relative_improvement": ee_improvement,
        },
        "episode_bootstrap": bootstrap,
        "advancement_gates": gates,
        "verified_significant_action_frozen_rms_advancement": verified,
        "target_piece_consequence_comparison": consequence_comparison,
        "already_opened_confirmation": source_receipt["already_opened_confirmation"],
        "selected_all_train_candidate": source_receipt["selected_candidate"],
        "selected_coefficient_is_frozen_search_boundary": True,
        "boundary_disclosure": contract["boundary_disclosure"],
        "figure": {"path": str(figure_path)},
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
        "goal_loop_stop_decision": (
            "stop_rms_lane_satisfied_do_not_claim_grasp_advancement"
            if verified
            else "continue_or_redirect_rms_lane_not_statistically_supported"
        ),
    }
    _plot_closeout(receipt=receipt, output_path=figure_path)
    receipt["figure"]["sha256"] = sha256_file(figure_path)
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "advancement_receipt.json", receipt)
    return receipt
