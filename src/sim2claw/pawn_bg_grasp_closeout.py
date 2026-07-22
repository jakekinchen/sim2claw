"""Publication-safe closeout for the action-frozen grasp campaign."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


SCHEMA = "sim2claw.pawn_bg_grasp_campaign_closeout.v1"
CONTRACT_PATH = REPO_ROOT / "configs" / "optimization" / "pawn_bg_grasp_coordinate_descent_v1.json"
CANDIDATE_PATHS = {
    "v2_clean": REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_v2_clean_all_event_aligned.json",
    "v3_timestep045": REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_v3_timestep045_all.json",
    "vertical_m15mm": REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_base_z_m15mm_all.json",
    "vertical_m20mm": REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_base_z_m20mm_all.json",
    "vertical_m15mm_armforce15": REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_v4_basez_m15_armforce15_all.json",
}
MEASURED_REPLAY_PATH = REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "v3_measured_state_upper_bound_sentinels.json"


class GraspCloseoutError(RuntimeError):
    """The campaign artifacts are incomplete or internally inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GraspCloseoutError(f"required campaign artifact is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GraspCloseoutError(f"campaign artifact is not an object: {path}")
    return payload


def paired_bootstrap(
    baseline: np.ndarray,
    candidate: np.ndarray,
    *,
    seed: int,
    replicates: int,
) -> dict[str, Any]:
    if baseline.shape != candidate.shape or baseline.ndim != 1:
        raise GraspCloseoutError("paired bootstrap vectors are incompatible")
    rng = np.random.default_rng(seed)
    differences = candidate.astype(float) - baseline.astype(float)
    draws = rng.integers(0, len(differences), size=(replicates, len(differences)))
    distribution = np.mean(differences[draws], axis=1)
    return {
        "episode_count": int(len(differences)),
        "point_mean_delta": float(np.mean(differences)),
        "confidence_interval_95": np.quantile(distribution, [0.025, 0.975]).astype(float).tolist(),
        "probability_delta_above_zero": float(np.mean(distribution > 0.0)),
        "seed": int(seed),
        "replicates": int(replicates),
        "unit": "whole_episode",
    }


def _metric_vector(receipt: dict[str, Any], key: str) -> np.ndarray:
    return np.asarray([bool(row[key]) for row in receipt["episodes"]], dtype=np.int8)


def _trace_guard(summary: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    guard = contract["source"]["trace_guardrail"]
    maximum = 1.0 + float(guard["maximum_relative_regression"])
    joint_limit = float(guard["baseline_joint_rms_degrees"]) * maximum
    ee_limit = float(guard["baseline_ee_rms_m"]) * maximum
    trace = summary["trace_metrics"]
    return {
        "joint_rms_limit_degrees": joint_limit,
        "ee_rms_limit_m": ee_limit,
        "joint_rms_pass": float(trace["overall_joint_rms_degrees"]) <= joint_limit,
        "ee_rms_pass": float(trace["ee_rms_m"]) <= ee_limit,
        "action_invariance_pass": bool(summary["action_invariance"]),
        "pass": bool(
            float(trace["overall_joint_rms_degrees"]) <= joint_limit
            and float(trace["ee_rms_m"]) <= ee_limit
            and summary["action_invariance"]
        ),
    }


def _figure(candidates: dict[str, dict[str, Any]], path: Path) -> None:
    names = ["v2_clean", "v3_timestep045", "vertical_m15mm", "vertical_m20mm"]
    labels = ["v2\nclean", "v3\n2.25 ms", "z -15\nmm", "z -20\nmm"]
    lifted = [candidates[name]["summary"]["lifted"] for name in names]
    transported = [candidates[name]["summary"]["lift_and_transport"] for name in names]
    joint_ratio = [
        candidates[name]["summary"]["trace_metrics"]["overall_joint_rms_degrees"]
        / candidates[name]["trace_guard"]["joint_rms_limit_degrees"]
        for name in names
    ]
    ee_ratio = [
        candidates[name]["summary"]["trace_metrics"]["ee_rms_m"]
        / candidates[name]["trace_guard"]["ee_rms_limit_m"]
        for name in names
    ]
    x = np.arange(len(names))
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    axes[0].bar(x - 0.18, lifted, 0.36, label="lifted")
    axes[0].bar(x + 0.18, transported, 0.36, label="lift + transport")
    axes[0].axhline(6, color="black", linestyle="--", linewidth=1, label="6/11 gate")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylim(0, 11)
    axes[0].set_ylabel("episodes (of 11)")
    axes[0].set_title("Action-frozen consequence")
    axes[0].legend(fontsize=8)
    axes[1].plot(x, joint_ratio, "o-", label="joint RMS / limit")
    axes[1].plot(x, ee_ratio, "s-", label="EE RMS / limit")
    axes[1].axhline(1.0, color="black", linestyle="--", linewidth=1, label="guardrail")
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("normalized error (lower is better)")
    axes[1].set_title("Trace guardrail")
    axes[1].legend(fontsize=8)
    fig.suptitle("B--G grasp fidelity: verified gains do not yet coincide")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def closeout_campaign(*, output_root: Path) -> dict[str, Any]:
    contract = _read(CONTRACT_PATH)
    raw = {name: _read(path) for name, path in CANDIDATE_PATHS.items()}
    episode_ids = [row["recording_id"] for row in raw["v2_clean"]["episodes"]]
    if len(episode_ids) != 11 or len(set(episode_ids)) != 11:
        raise GraspCloseoutError("baseline retained episode inventory changed")
    action_hashes: dict[str, set[str]] = {recording_id: set() for recording_id in episode_ids}
    candidates: dict[str, dict[str, Any]] = {}
    for name, receipt in raw.items():
        if [row["recording_id"] for row in receipt["episodes"]] != episode_ids:
            raise GraspCloseoutError(f"episode order changed for {name}")
        for row in receipt["episodes"]:
            if not row["action_byte_identical"]:
                raise GraspCloseoutError(f"action invariant failed for {name}")
            action_hashes[row["recording_id"]].add(str(row["action_array_sha256"]))
        candidates[name] = {
            "artifact_path": str(CANDIDATE_PATHS[name].relative_to(REPO_ROOT)),
            "artifact_sha256": sha256_file(CANDIDATE_PATHS[name]),
            "parameter_digest": receipt["parameter_digest"],
            "parameters": receipt["parameters"],
            "summary": receipt["summary"],
            "trace_guard": _trace_guard(receipt["summary"], contract),
            "lifted_recording_ids": [row["recording_id"] for row in receipt["episodes"] if row["piece_lifted"]],
            "lift_and_transport_recording_ids": [row["recording_id"] for row in receipt["episodes"] if row["lift_and_transport"]],
        }
    if any(len(hashes) != 1 for hashes in action_hashes.values()):
        raise GraspCloseoutError("a recording action hash differs across candidates")

    family_names = list(raw)
    union_lift = []
    union_transport = []
    for index, recording_id in enumerate(episode_ids):
        if any(raw[name]["episodes"][index]["piece_lifted"] for name in family_names):
            union_lift.append(recording_id)
        if any(raw[name]["episodes"][index]["lift_and_transport"] for name in family_names):
            union_transport.append(recording_id)

    v2 = raw["v2_clean"]
    v3 = raw["v3_timestep045"]
    vertical = raw["vertical_m15mm"]
    measured_replay = _read(MEASURED_REPLAY_PATH)
    lift_bootstrap = paired_bootstrap(
        _metric_vector(v2, "piece_lifted"),
        _metric_vector(v3, "piece_lifted"),
        seed=21072027,
        replicates=10000,
    )
    transport_bootstrap = paired_bootstrap(
        _metric_vector(v2, "lift_and_transport"),
        _metric_vector(vertical, "lift_and_transport"),
        seed=21072028,
        replicates=10000,
    )
    any_six_transports = any(
        int(receipt["summary"]["lift_and_transport"]) >= 6 for receipt in raw.values()
    )
    any_strict_success = any(
        int(receipt["summary"]["strict_successes"]) >= 1 for receipt in raw.values()
    )
    bootstrap_lower_bound_positive = bool(lift_bootstrap["confidence_interval_95"][0] > 0.0)
    promotion_eligible_candidates = [
        name
        for name, candidate in candidates.items()
        if candidate["trace_guard"]["pass"]
        and (
            int(candidate["summary"]["lift_and_transport"]) >= 6
            or int(candidate["summary"]["strict_successes"]) >= 1
        )
    ]
    figure_path = output_root / "grasp_campaign_closeout.png"
    _figure(candidates, figure_path)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "retained_action_frozen_simulation_replay",
        "contract": {
            "path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_file(CONTRACT_PATH),
        },
        "candidates": candidates,
        "action_invariance": {
            "all_candidate_episode_arrays_byte_identical": True,
            "distinct_recording_action_hash_count": len(action_hashes),
            "hashes_by_recording_id": {key: next(iter(value)) for key, value in action_hashes.items()},
            "action_values_or_order_modified": False,
        },
        "paired_bootstrap": {
            "v2_to_v3_lifted": lift_bootstrap,
            "v2_to_vertical_m15mm_lift_and_transport": transport_bootstrap,
        },
        "frozen_family_union": {
            "candidate_names": family_names,
            "lifted": len(union_lift),
            "lift_and_transport": len(union_transport),
            "lifted_recording_ids": union_lift,
            "lift_and_transport_recording_ids": union_transport,
            "interpretation": "posterior sensitivity coverage only; not a single simulator composite",
        },
        "measured_state_upper_bound_control": {
            "artifact_path": str(MEASURED_REPLAY_PATH.relative_to(REPO_ROOT)),
            "artifact_sha256": sha256_file(MEASURED_REPLAY_PATH),
            "summary": measured_replay["summary"],
            "simulator_candidate_promotion_allowed": False,
            "finding": "near_exact_retained_joint_replay_does_not_recover_grasp_consequence",
        },
        "verified_wins": {
            "v3_lifts_double_from_2_to_4_with_trace_guard_pass": bool(
                v2["summary"]["lifted"] == 2
                and v3["summary"]["lifted"] == 4
                and candidates["v3_timestep045"]["trace_guard"]["pass"]
            ),
            "vertical_family_transport_doubles_from_1_to_2": bool(
                v2["summary"]["lift_and_transport"] == 1
                and vertical["summary"]["lift_and_transport"] == 2
            ),
            "vertical_family_trace_guard_pass": candidates["vertical_m15mm"]["trace_guard"]["pass"],
            "posterior_union_reaches_6_lifts": len(union_lift) >= 6,
            "posterior_union_reaches_5_transports": len(union_transport) >= 5,
        },
        "promotion_gate": {
            "single_candidate_minimum_6_of_11_lift_and_transport": any_six_transports,
            "single_candidate_strict_success": any_strict_success,
            "paired_bootstrap_lower_bound_above_zero": bootstrap_lower_bound_positive,
            "promotion_eligible_candidates": promotion_eligible_candidates,
            "simulator_composite_promoted": bool(promotion_eligible_candidates),
            "decision": (
                "promoted_single_composite"
                if promotion_eligible_candidates
                else "terminal_negative_for_single_composite_positive_for_bounded_sensitivity_advancement"
            ),
        },
        "figure": {
            "path": str(figure_path.relative_to(REPO_ROOT)),
        },
        "authority": {
            "physical_calibration": False,
            "physical_transfer": False,
            "policy_improvement": False,
            "training_admission": False,
            "simulator_composite_promotion": bool(promotion_eligible_candidates),
        },
        "smallest_next_measurements": [
            "metric board-to-base vertical registration in the reconstructed scene",
            "measured pawn dimensions and mass",
            "jaw-tip rubber collision profile or calibrated close-range image",
            "per-episode initial pawn centers from a metric overhead calibration",
        ],
    }
    receipt["figure"]["sha256"] = sha256_file(figure_path)
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "grasp_campaign_closeout_receipt.json", receipt)
    return receipt


__all__ = ["GraspCloseoutError", "closeout_campaign", "paired_bootstrap"]
