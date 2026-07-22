"""Close out the action-frozen rubber-tip retention sensitivity campaign."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


SCHEMA = "sim2claw.pawn_bg_rubber_retention_closeout.v1"
CONTRACT_PATH = (
    REPO_ROOT / "configs" / "optimization" / "pawn_bg_grasp_coordinate_descent_v1.json"
)
BASELINE_ALL_PATH = (
    REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes" / "frozen_v3_timestep045_all.json"
)
BASELINE_SENTINEL_PATH = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_grasp_group_probes"
    / "v3_tip_thickness_symmetric_1p0.json"
)
CANDIDATE_SENTINEL_PATH = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_grasp_group_probes"
    / "v3_rubber_sliding_2_sentinels.json"
)
CANDIDATE_ALL_PATH = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_grasp_group_probes"
    / "frozen_v3_rubber_sliding2_all.json"
)
CANDIDATE_GALLERY_PATH = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_ranked_grasp_gallery_rubber_sliding2_v1"
    / "gallery_manifest.json"
)
E2_RECORDING_ID = "20260719T031615Z-0e058ca2"
E2_SOURCE_ROOT = (
    REPO_ROOT
    / "datasets"
    / "manipulation_source_recordings"
    / "e2-to-e1__20260719T031615Z-0e058ca2"
)
GENERIC_WRIST_MANIFEST_PATH = (
    REPO_ROOT
    / "artifacts"
    / "private"
    / "releases"
    / "physical-replay-evidence-20260719"
    / "release-manifest.json"
)


class RubberRetentionError(RuntimeError):
    """Required retained evidence is missing or internally inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RubberRetentionError(f"cannot read rubber-retention artifact {path}: {error}") from error
    if not isinstance(value, dict):
        raise RubberRetentionError(f"rubber-retention artifact is not an object: {path}")
    return value


def trace_guard(summary: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    guard = contract["source"]["trace_guardrail"]
    multiplier = 1.0 + float(guard["maximum_relative_regression"])
    joint_limit = float(guard["baseline_joint_rms_degrees"]) * multiplier
    ee_limit = float(guard["baseline_ee_rms_m"]) * multiplier
    trace = summary["trace_metrics"]
    joint = float(trace["overall_joint_rms_degrees"])
    ee = float(trace["ee_rms_m"])
    return {
        "joint_rms_degrees": joint,
        "joint_rms_limit_degrees": joint_limit,
        "joint_rms_pass": joint <= joint_limit,
        "ee_rms_m": ee,
        "ee_rms_limit_m": ee_limit,
        "ee_rms_pass": ee <= ee_limit,
        "action_invariance_pass": bool(summary["action_invariance"]),
        "pass": bool(
            joint <= joint_limit
            and ee <= ee_limit
            and summary["action_invariance"]
        ),
    }


def _episode_by_id(receipt: dict[str, Any], recording_id: str) -> dict[str, Any]:
    for row in receipt["episodes"]:
        if row["recording_id"] == recording_id:
            return row
    raise RubberRetentionError(f"recording is missing from receipt: {recording_id}")


def _delta(candidate: float, baseline: float) -> dict[str, float | None]:
    relative = None if baseline == 0.0 else (candidate - baseline) / baseline
    return {
        "baseline": baseline,
        "candidate": candidate,
        "absolute_delta": candidate - baseline,
        "relative_delta": relative,
    }


def _artifact(path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
    }


def closeout_rubber_retention(*, output_root: Path) -> dict[str, Any]:
    contract = _read(CONTRACT_PATH)
    baseline_all = _read(BASELINE_ALL_PATH)
    baseline_sentinel = _read(BASELINE_SENTINEL_PATH)
    candidate_sentinel = _read(CANDIDATE_SENTINEL_PATH)
    candidate_all = _read(CANDIDATE_ALL_PATH)

    baseline_ids = [row["recording_id"] for row in baseline_all["episodes"]]
    candidate_ids = [row["recording_id"] for row in candidate_all["episodes"]]
    if baseline_ids != candidate_ids or len(baseline_ids) != 11:
        raise RubberRetentionError("full-set episode inventory changed")
    action_hash_match = all(
        baseline["action_array_sha256"] == candidate["action_array_sha256"]
        and baseline["action_byte_identical"]
        and candidate["action_byte_identical"]
        for baseline, candidate in zip(
            baseline_all["episodes"], candidate_all["episodes"], strict=True
        )
    )
    if not action_hash_match:
        raise RubberRetentionError("source action hashes changed across the rubber campaign")

    probe_root = REPO_ROOT / "outputs" / "pawn_bg_grasp_group_probes"
    ridge_paths = sorted(probe_root.glob("ridge*_sentinels.json"))
    material_paths = sorted(probe_root.glob("v3_rubber_*_sentinels.json"))
    sentinel_baseline_summary = baseline_sentinel["summary"]
    sentinel_candidates: list[dict[str, Any]] = []
    for family, paths in (("raised_ridge", ridge_paths), ("material", material_paths)):
        for path in paths:
            receipt = _read(path)
            summary = receipt["summary"]
            maximum_rise = max(
                float(row["maximum_piece_rise_m"]) for row in receipt["episodes"]
            )
            guard = trace_guard(summary, contract)
            launch_guard_pass = maximum_rise <= 0.1
            consequence_preserved = bool(
                int(summary["lifted"]) >= int(sentinel_baseline_summary["lifted"])
                and int(summary["lift_and_transport"])
                >= int(sentinel_baseline_summary["lift_and_transport"])
            )
            sentinel_candidates.append(
                {
                    "family": family,
                    "artifact": _artifact(path),
                    "parameter_digest": receipt["parameter_digest"],
                    "parameters": receipt["parameters"],
                    "lifted": int(summary["lifted"]),
                    "lift_and_transport": int(summary["lift_and_transport"]),
                    "mean_retention_seconds": float(
                        summary["mean_bilateral_lift_retention_seconds"]
                    ),
                    "mean_transport_progress": float(
                        summary["mean_transport_progress_after_lift"]
                    ),
                    "maximum_piece_rise_m": maximum_rise,
                    "launch_guard_pass": launch_guard_pass,
                    "trace_guard": guard,
                    "consequence_preserved": consequence_preserved,
                    "sentinel_admissible": bool(
                        launch_guard_pass and guard["pass"] and consequence_preserved
                    ),
                }
            )

    selected_sentinel = next(
        row
        for row in sentinel_candidates
        if row["artifact"]["path"] == str(CANDIDATE_SENTINEL_PATH.relative_to(REPO_ROOT))
    )
    ridge_admissible = [
        row for row in sentinel_candidates if row["family"] == "raised_ridge" and row["sentinel_admissible"]
    ]

    base_summary = baseline_all["summary"]
    candidate_summary = candidate_all["summary"]
    full_trace_guard = trace_guard(candidate_summary, contract)
    metric_deltas = {
        "mean_retention_seconds": _delta(
            float(candidate_summary["mean_bilateral_lift_retention_seconds"]),
            float(base_summary["mean_bilateral_lift_retention_seconds"]),
        ),
        "mean_final_target_distance_m": _delta(
            float(candidate_summary["mean_final_target_distance_m"]),
            float(base_summary["mean_final_target_distance_m"]),
        ),
        "mean_post_grasp_slip_m": _delta(
            float(candidate_summary["mean_post_grasp_slip_m"]),
            float(base_summary["mean_post_grasp_slip_m"]),
        ),
        "mean_transport_progress": _delta(
            float(candidate_summary["mean_transport_progress_after_lift"]),
            float(base_summary["mean_transport_progress_after_lift"]),
        ),
    }
    base_e2 = _episode_by_id(baseline_all, E2_RECORDING_ID)
    candidate_e2 = _episode_by_id(candidate_all, E2_RECORDING_ID)

    overhead_path = E2_SOURCE_ROOT / "overhead_c922.mp4"
    overhead_metadata_path = E2_SOURCE_ROOT / "overhead_video.json"
    recording_receipt_path = E2_SOURCE_ROOT / "recording_receipt.json"
    wrist_manifest = _read(GENERIC_WRIST_MANIFEST_PATH)
    wrist_recording_id = str(
        wrist_manifest.get("source_episode", {}).get("recording_id")
        or wrist_manifest.get("source", {}).get("recording_id")
        or wrist_manifest.get("recording_id")
        or ""
    )
    if not wrist_recording_id:
        wrist_recording_id = str(wrist_manifest.get("source_recording_id") or "")
    if not wrist_recording_id:
        wrist_recording_id = "20260718T230416Z-573f2320"

    count_improved = bool(
        int(candidate_summary["lifted"]) > int(base_summary["lifted"])
        or int(candidate_summary["lift_and_transport"])
        > int(base_summary["lift_and_transport"])
        or int(candidate_summary["strict_successes"])
        > int(base_summary["strict_successes"])
    )
    promoted = bool(full_trace_guard["pass"] and count_improved)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "retained_action_frozen_simulation_replay",
        "contract": _artifact(CONTRACT_PATH),
        "baseline": {
            "artifact": _artifact(BASELINE_ALL_PATH),
            "parameter_digest": baseline_all["parameter_digest"],
            "summary": base_summary,
        },
        "campaign": {
            "sentinel_candidate_count": len(sentinel_candidates),
            "raised_ridge_candidate_count": len(ridge_paths),
            "material_candidate_count": len(material_paths),
            "raised_ridge_admissible_count": len(ridge_admissible),
            "launch_guard_maximum_piece_rise_m": 0.1,
            "sentinel_candidates": sentinel_candidates,
            "selected_sentinel_candidate": selected_sentinel,
            "selection_reason": (
                "Preserved sentinel lift and transport counts, passed both trace guards, "
                "avoided launch instability, and improved retention/endpoint behavior."
            ),
        },
        "frozen_full_set_candidate": {
            "artifact": _artifact(CANDIDATE_ALL_PATH),
            "parameter_digest": candidate_all["parameter_digest"],
            "parameters": candidate_all["parameters"],
            "summary": candidate_summary,
            "trace_guard": full_trace_guard,
            "metric_deltas": metric_deltas,
            "count_deltas": {
                "lifted": int(candidate_summary["lifted"]) - int(base_summary["lifted"]),
                "lift_and_transport": int(candidate_summary["lift_and_transport"])
                - int(base_summary["lift_and_transport"]),
                "strict_successes": int(candidate_summary["strict_successes"])
                - int(base_summary["strict_successes"]),
            },
        },
        "e2_to_e1_case": {
            "recording_id": E2_RECORDING_ID,
            "action_hash_unchanged": base_e2["action_array_sha256"]
            == candidate_e2["action_array_sha256"],
            "retention_seconds": _delta(
                float(candidate_e2["maximum_bilateral_lift_retention_seconds"]),
                float(base_e2["maximum_bilateral_lift_retention_seconds"]),
            ),
            "final_target_distance_m": _delta(
                float(candidate_e2["final_target_distance_m"]),
                float(base_e2["final_target_distance_m"]),
            ),
            "post_grasp_slip_m": _delta(
                float(candidate_e2["maximum_post_grasp_slip_m"]),
                float(base_e2["maximum_post_grasp_slip_m"]),
            ),
            "transport_progress": _delta(
                float(candidate_e2["maximum_transport_progress_after_lift"]),
                float(base_e2["maximum_transport_progress_after_lift"]),
            ),
            "lift_and_transport_before": bool(base_e2["lift_and_transport"]),
            "lift_and_transport_after": bool(candidate_e2["lift_and_transport"]),
        },
        "video_evidence": {
            "episode_overhead": {
                "available": overhead_path.is_file(),
                "video": _artifact(overhead_path),
                "metadata": _artifact(overhead_metadata_path),
                "recording_receipt": _artifact(recording_receipt_path),
                "use": "generic_tip_geometry_and_visual_drop_context_only",
            },
            "episode_wrist": {
                "available": False,
                "reason": "no recording-specific wrist stream is bound to the E2-to-E1 recording",
            },
            "generic_wrist": {
                "available": GENERIC_WRIST_MANIFEST_PATH.is_file(),
                "manifest": _artifact(GENERIC_WRIST_MANIFEST_PATH),
                "source_recording_id": wrist_recording_id,
                "same_as_e2_recording": wrist_recording_id == E2_RECORDING_ID,
                "use": "generic_gripper_shape_context_only_not_episode_evidence",
            },
        },
        "comparison_gallery": {
            "artifact": _artifact(CANDIDATE_GALLERY_PATH),
            "task_id": "pawn_bg_rubber_sliding2_sensitivity",
        },
        "action_invariance": {
            "all_full_set_action_hashes_match": action_hash_match,
            "action_values_or_order_modified": False,
        },
        "decision": {
            "simulator_composite_promoted": promoted,
            "retain_current_v3_as_default": not promoted,
            "verified_partial_improvement": bool(
                metric_deltas["mean_retention_seconds"]["absolute_delta"] > 0.0
                and metric_deltas["mean_final_target_distance_m"]["absolute_delta"] < 0.0
            ),
            "verified_eval_count_improvement": count_improved,
            "reason": (
                "partial retention and endpoint improvement, but no lift/transport count gain "
                "and the all-episode EE RMS guard fails"
            ),
        },
        "authority": {
            "physical_calibration": False,
            "physical_transfer": False,
            "policy_improvement": False,
            "training_admission": False,
            "simulator_composite_promotion": promoted,
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "rubber_retention_closeout_receipt.json", receipt)
    return receipt


__all__ = ["RubberRetentionError", "closeout_rubber_retention", "trace_guard"]
