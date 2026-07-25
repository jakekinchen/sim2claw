from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .c922_exact_mode_calibration import (
    CONTRACT_SHA256,
    DEFAULT_CONTRACT_PATH,
    REPO_ROOT,
    load_contract,
    sha256_file,
)


PLAN_SCHEMA = "sim2claw.c922_exact_mode_calibration_acquisition_plan.v1"
MEASUREMENT_SCHEMA = "sim2claw.printed_grid_measurement_receipt.v1"
REPORT_SCHEMA = "sim2claw.c922_calibration_acquisition_preflight.v1"
DEFAULT_PLAN_PATH = (
    REPO_ROOT / "configs/acquisition/c922_exact_mode_calibration.json"
)
CAMERA_KEYS = (
    "camera_id",
    "localized_name",
    "model_id",
    "unique_id",
    "image_size_px",
    "media_subtype",
    "format_index",
    "frame_rate_range_index",
    "frame_rate_fps",
    "orientation_filter",
)
SLOT_KEYS = {
    "frame_id",
    "split",
    "centroid_goal",
    "scale_goal",
    "pose_goal",
    "orientation_goal",
}


def _load_json(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = (REPO_ROOT / value).resolve()
    root = REPO_ROOT.resolve()
    if path == root or root not in path.parents:
        return None
    return path


def _positive(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(data, encoding="utf-8")
    temporary.replace(path)


def _measurement_ready(
    target: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    receipt_path = _repo_path(target.get("measurement_receipt_path"))
    declared_hash = target.get("measurement_receipt_sha256")
    if receipt_path is None or not receipt_path.is_file():
        return False, ["printed_grid_measurement_receipt"]
    if (
        not isinstance(declared_hash, str)
        or sha256_file(receipt_path) != declared_hash
    ):
        return False, ["printed_grid_measurement_receipt_hash"]
    receipt = _load_json(receipt_path)
    if receipt is None or receipt.get("schema_version") != MEASUREMENT_SCHEMA:
        return False, ["printed_grid_measurement_receipt_schema"]
    if (
        receipt.get("target_asset_sha256")
        != contract["target"]["asset_sha256"]
    ):
        missing.append("measured_target_asset_identity")
    for field in (
        "square_pitch_x_mm",
        "square_pitch_y_mm",
        "total_width_x_mm",
        "total_height_y_mm",
        "instrument_resolution_mm",
        "measurement_uncertainty_mm",
    ):
        if not _positive(receipt.get(field)):
            missing.append(field)
    for field in (
        "measurement_id",
        "instrument",
        "measurement_points_description",
        "measured_by",
        "measured_at",
    ):
        if not str(receipt.get(field) or "").strip():
            missing.append(field)
    if receipt.get("measurement_basis") != "physical_post_print_measurement":
        missing.append("physical_post_print_measurement_basis")
    if receipt.get("nominal_values_substituted") is not False:
        missing.append("nominal_values_must_not_be_substituted")
    return not missing, missing


def _frame_plan(
    slots: Any,
    *,
    contract: Mapping[str, Any],
) -> tuple[bool, dict[str, Any], list[str]]:
    reasons: list[str] = []
    if not isinstance(slots, list):
        return False, {}, ["frame_slots"]
    ids: list[str] = []
    split_counts = {"fit": 0, "validation": 0, "held_out": 0}
    centroid: set[str] = set()
    scale: set[str] = set()
    orientation: set[str] = set()
    pose_counts = {"tilted": 0, "near_frontal": 0}
    for index, slot in enumerate(slots):
        if not isinstance(slot, Mapping) or set(slot) != SLOT_KEYS:
            reasons.append(f"frame_slot_{index}_shape")
            continue
        frame_id = str(slot.get("frame_id") or "")
        split = str(slot.get("split") or "")
        if not frame_id:
            reasons.append(f"frame_slot_{index}_id")
        ids.append(frame_id)
        if split not in split_counts:
            reasons.append(f"frame_slot_{index}_split")
        else:
            split_counts[split] += 1
        centroid.add(str(slot.get("centroid_goal") or ""))
        scale.add(str(slot.get("scale_goal") or ""))
        orientation.add(str(slot.get("orientation_goal") or ""))
        pose = str(slot.get("pose_goal") or "")
        if pose in pose_counts:
            pose_counts[pose] += 1
        elif pose != "free":
            reasons.append(f"frame_slot_{index}_pose")
    if len(ids) != len(set(ids)):
        reasons.append("duplicate_frame_ids")
    dataset = contract["dataset"]
    if len(slots) != dataset["minimum_accepted_frames"]:
        reasons.append("frame_slot_count")
    if split_counts != dataset["required_split_counts"]:
        reasons.append("split_counts")
    if not set(dataset["required_centroid_bins"]).issubset(centroid):
        reasons.append("centroid_goal_coverage")
    if scale != {"small", "medium", "large"}:
        reasons.append("scale_goal_coverage")
    if orientation != {"negative", "center", "positive"}:
        reasons.append("orientation_goal_coverage")
    if pose_counts["tilted"] < dataset["minimum_tilted_views"]:
        reasons.append("tilted_goal_count")
    if pose_counts["near_frontal"] < dataset["minimum_near_frontal_views"]:
        reasons.append("near_frontal_goal_count")
    summary = {
        "slot_count": len(slots),
        "split_counts": split_counts,
        "centroid_goals": sorted(centroid),
        "scale_goals": sorted(scale),
        "orientation_goals": sorted(orientation),
        "tilted_goal_count": pose_counts["tilted"],
        "near_frontal_goal_count": pose_counts["near_frontal"],
        "actual_geometry_still_requires_evaluator_detection": True,
    }
    return not reasons, summary, reasons


def preflight_acquisition(
    plan_path: Path = DEFAULT_PLAN_PATH,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    plan = _load_json(plan_path)
    invalid: list[str] = []
    missing: list[str] = []
    if plan is None:
        invalid.append("acquisition_plan_unreadable")
        plan = {}
    if plan.get("schema_version") != PLAN_SCHEMA:
        invalid.append("acquisition_plan_schema")
    if (
        plan.get("contract_id") != contract["contract_id"]
        or plan.get("contract_sha256") != CONTRACT_SHA256
    ):
        invalid.append("calibration_contract_identity")
    camera = plan.get("camera")
    if not isinstance(camera, Mapping) or any(
        camera.get(key) != contract["camera"].get(key) for key in CAMERA_KEYS
    ):
        invalid.append("camera_exact_mode_identity")
    target = plan.get("target")
    if not isinstance(target, Mapping) or (
        target.get("asset_path") != contract["target"]["asset_path"]
        or target.get("asset_sha256") != contract["target"]["asset_sha256"]
    ):
        invalid.append("target_asset_identity")
        target = {}
    if target.get("printed_and_mounted_flat") is not True:
        missing.append("printed_target_mounted_flat")
    measurement_ready, measurement_missing = _measurement_ready(
        target,
        contract=contract,
    )
    if not measurement_ready:
        missing.extend(measurement_missing)

    focus = plan.get("focus")
    focus_ready = bool(
        isinstance(focus, Mapping)
        and focus.get("mode") == "manual_locked"
        and not isinstance(focus.get("setting"), bool)
        and isinstance(focus.get("setting"), (str, int, float))
        and focus.get("setting") != ""
        and str(focus.get("observation_method") or "").strip()
    )
    if not focus_ready:
        missing.append("fixed_observable_focus_setting")
    if plan.get("owner_capture_approved") is not True:
        missing.append("owner_approved_capture")

    frame_plan_valid, frame_plan, frame_reasons = _frame_plan(
        plan.get("frame_slots"),
        contract=contract,
    )
    invalid.extend(frame_reasons)
    motion = plan.get("motion_qualification")
    d405_repaired = bool(
        isinstance(motion, Mapping)
        and motion.get("d405_cable_connector_strain_relief_repaired") is True
    )
    if not (
        isinstance(motion, Mapping)
        and motion.get("required_for_stationary_c922_corpus") is False
        and motion.get("required_before_robot_motion") is True
    ):
        invalid.append("motion_qualification_boundary")
    authority = plan.get("authority")
    if not (
        isinstance(authority, Mapping)
        and authority.get("camera_capture_authorized") is False
        and authority.get("robot_motion_authorized") is False
        and authority.get("physical_authority") is False
    ):
        invalid.append("authority_boundary")

    capture_ready = not invalid and not missing
    return {
        "schema_version": REPORT_SCHEMA,
        "status": (
            "ready_for_owner_approved_stationary_capture"
            if capture_ready
            else "invalid_plan"
            if invalid
            else "blocked_physical_inputs"
        ),
        "capture_ready": capture_ready,
        "plan_path": str(plan_path),
        "plan_sha256": sha256_file(plan_path) if plan_path.is_file() else None,
        "contract_sha256": CONTRACT_SHA256,
        "camera_exact_mode": (
            {key: contract["camera"][key] for key in CAMERA_KEYS}
        ),
        "target_nominal_dimensions_are_metric_authority": False,
        "required_measurement_receipt_schema": MEASUREMENT_SCHEMA,
        "required_measured_dimensions": [
            "square_pitch_x_mm",
            "square_pitch_y_mm",
            "total_width_x_mm",
            "total_height_y_mm",
        ],
        "required_measurement_metadata": [
            "instrument",
            "instrument_resolution_mm",
            "measurement_uncertainty_mm",
            "measurement_points_description",
            "measured_by",
            "measured_at",
        ],
        "target_measurement_ready": measurement_ready,
        "focus_ready": focus_ready,
        "frame_plan_valid": frame_plan_valid,
        "frame_plan": frame_plan,
        "missing_physical_inputs": sorted(set(missing)),
        "invalid_plan_reasons": sorted(set(invalid)),
        "motion_qualification_blockers": (
            [] if d405_repaired else ["d405_cable_connector_strain_relief_repair"]
        ),
        "owner_actions": [
            "print_and_mount_target_flat",
            "measure_pitch_and_total_xy_dimensions_without_nominal_substitution",
            "record_instrument_resolution_uncertainty_and_measurement_points",
            "lock_c922_focus_and_record_the_observable_setting",
            "approve_one_stationary_18_view_capture",
            "repair_d405_cable_connector_and_strain_relief_before_robot_motion",
        ],
        "camera_opened": False,
        "camera_sessions_used": 0,
        "new_frames_captured": 0,
        "robot_motion_used": 0,
        "metric_fit_authorized": False,
        "evaluator_admission": False,
        "physical_authority": False,
    }


def preflight_and_write(
    plan_path: Path,
    output_path: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    report = preflight_acquisition(plan_path, contract_path=contract_path)
    _write_json(output_path, report)
    return report
