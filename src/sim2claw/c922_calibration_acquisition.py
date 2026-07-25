from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from PIL import Image

from .c922_exact_mode_calibration import (
    CONTRACT_SHA256,
    DEFAULT_CONTRACT_PATH,
    FRAME_RECEIPT_SCHEMA,
    INPUT_SCHEMA,
    REPO_ROOT,
    detect_corners,
    frame_geometry,
    load_inputs,
    load_contract,
    sha256_file,
)
from .native_dual_camera import NativeDualCameraRecorder


PLAN_SCHEMA = "sim2claw.c922_exact_mode_calibration_acquisition_plan.v1"
MEASUREMENT_SCHEMA = "sim2claw.printed_grid_measurement_receipt.v1"
REPORT_SCHEMA = "sim2claw.c922_calibration_acquisition_preflight.v1"
CORPUS_SCHEMA = "sim2claw.c922_calibration_acquisition_result.v1"
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


CaptureFunction = Callable[
    [Mapping[str, Any], Path, Mapping[str, Any], bool], Mapping[str, Any]
]
DetectorFunction = Callable[[Path, tuple[int, int], tuple[int, int]], np.ndarray | None]
PromptFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


def _relative(path: Path) -> str:
    resolved = path.resolve()
    root = REPO_ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("Calibration corpus must stay inside the repository.")
    return str(resolved.relative_to(root))


def _native_burst(
    slot: Mapping[str, Any],
    attempt: Path,
    camera: Mapping[str, Any],
    synthetic: bool,
) -> Mapping[str, Any]:
    del slot
    if synthetic:
        raise ValueError("Synthetic acquisition must use the fixture capture function.")
    recorder = NativeDualCameraRecorder(attempt)
    recorder.start()
    started = time.monotonic()
    try:
        time.sleep(1.25)
    finally:
        completed = recorder.finish(
            action_started_monotonic=started,
            action_stopped_monotonic=time.monotonic(),
            post_roll_seconds=0.0,
        )
    report = json.loads(recorder.report_path.read_text(encoding="utf-8"))
    stream = next(row for row in report["streams"] if row["role"] == "c922")
    active = next(
        row for row in report["stages"] if row["name"] == "after_start"
    )["c922"]
    exact = {
        "localized_name": active["localized_name"],
        "model_id": active["model_id"],
        "unique_id": active["unique_id"],
        "image_size_px": [active["width"], active["height"]],
        "media_subtype": active["subtype"],
        "format_index": active["format_index"],
    }
    if any(exact[key] != camera[key] for key in exact):
        raise ValueError("Native active-session C922 identity or exact mode changed.")
    image = attempt / "candidate.png"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required to extract a calibration frame.")
    try:
        extracted = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-sseof",
                "-0.2",
                "-i",
                str(recorder.overhead_browser_path),
                "-frames:v",
                "1",
                "-y",
                str(image),
            ],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"C922 frame extraction failed: {error}") from error
    if extracted.returncode != 0 or not image.is_file():
        raise ValueError(f"C922 frame extraction failed: {extracted.stderr.strip()}")
    return {
        "image_path": image,
        "camera": dict(camera),
        "source_pts_seconds": float(stream["last_pts_seconds"]),
        "captured_at": datetime.now(UTC).isoformat(),
        "capture_authority": "physical_camera_frame",
        "synthetic": False,
        "used_for_fit_or_selection": False,
        "native_report_path": _relative(recorder.report_path),
        "native_report_sha256": sha256_file(recorder.report_path),
        "native_common_session": completed["common_session"],
    }


def _synthetic_capture(
    slot: Mapping[str, Any],
    attempt: Path,
    camera: Mapping[str, Any],
    synthetic: bool,
) -> Mapping[str, Any]:
    if not synthetic:
        raise ValueError("Fixture capture is available only in dry-run mode.")
    image = attempt / "candidate.png"
    index = int(str(slot["frame_id"]).rsplit("-", 1)[-1])
    pattern = np.indices((7, 10)).sum(axis=0) % 2
    board = np.kron(pattern, np.ones((32, 32), dtype=np.uint8)) * 255
    pixels = np.full((480, 640), 190, dtype=np.uint8)
    pixels[128:352, 160:480] = board
    pixels[0, index] = index
    Image.fromarray(pixels).save(image)
    return {
        "image_path": image,
        "camera": dict(camera),
        "source_pts_seconds": float(int(str(slot["frame_id"]).rsplit("-", 1)[-1])),
        "captured_at": "2000-01-01T00:00:00+00:00",
        "capture_authority": "synthetic_fixture",
        "synthetic": True,
        "used_for_fit_or_selection": False,
    }


def acquire_corpus(
    plan_path: Path,
    output_root: Path,
    *,
    dry_run: bool = False,
    capture_fn: CaptureFunction | None = None,
    detector_fn: DetectorFunction = detect_corners,
    prompt_fn: PromptFunction = input,
    output_fn: OutputFunction = print,
    maximum_attempts: int = 3,
) -> dict[str, Any]:
    """Acquire the frozen slots sequentially without fitting a model."""

    contract = load_contract()
    plan = _load_json(plan_path)
    if plan is None:
        raise ValueError("Acquisition plan is unreadable.")
    preflight = preflight_acquisition(plan_path)
    if preflight["invalid_plan_reasons"]:
        raise ValueError(
            "Acquisition plan is invalid: "
            + ", ".join(preflight["invalid_plan_reasons"])
        )
    if not dry_run and not preflight["capture_ready"]:
        raise ValueError(
            "Physical inputs are incomplete: "
            + ", ".join(preflight["missing_physical_inputs"])
        )
    if output_root.exists():
        raise ValueError("Output corpus already exists; choose a fresh dataset path.")
    _relative(output_root)
    output_root.mkdir(parents=True)
    capture = capture_fn or (_synthetic_capture if dry_run else _native_burst)
    camera = dict(plan["camera"])
    focus = plan["focus"]
    focus_setting = (
        "synthetic_locked_fixture" if dry_run else focus["setting"]
    )
    declarations: list[dict[str, Any]] = []
    image_hashes: set[str] = set()
    inner = tuple(int(value) for value in contract["target"]["inner_corners"])
    size = tuple(int(value) for value in camera["image_size_px"])
    for slot_index, slot in enumerate(plan["frame_slots"]):
        accepted = False
        for attempt_index in range(1, maximum_attempts + 1):
            output_fn(
                json.dumps(
                    {
                        "view": slot_index + 1,
                        "total": len(plan["frame_slots"]),
                        **slot,
                    },
                    sort_keys=True,
                )
            )
            if not dry_run and prompt_fn("Type capture to acquire this view: ").strip() != "capture":
                raise ValueError(f"View {slot['frame_id']} was not acknowledged.")
            attempt = output_root / "_attempts" / str(slot["frame_id"]) / f"{attempt_index:02d}"
            attempt.mkdir(parents=True)
            candidate = dict(capture(slot, attempt, camera, dry_run))
            if candidate.get("camera") != camera:
                raise ValueError("Captured camera or exact mode does not match the plan.")
            expected_proof = ("synthetic_fixture", True) if dry_run else (
                "physical_camera_frame",
                False,
            )
            if (candidate.get("capture_authority"), candidate.get("synthetic")) != expected_proof:
                raise ValueError("Captured frame proof class does not match acquisition mode.")
            if candidate.get("used_for_fit_or_selection") is not False:
                raise ValueError("Acquisition frames cannot be used for fit or selection.")
            if not _positive(candidate.get("source_pts_seconds")) and candidate.get(
                "source_pts_seconds"
            ) != 0.0:
                raise ValueError("Captured frame source timestamp is invalid.")
            image_path = Path(candidate.get("image_path") or "")
            if not image_path.is_file():
                raise ValueError(f"Capture did not produce view {slot['frame_id']}.")
            image_hash = sha256_file(image_path)
            if image_hash in image_hashes:
                raise ValueError("Duplicate frame bytes are forbidden.")
            corners = detector_fn(image_path, inner, size)
            if corners is None:
                output_fn("checkerboard_not_detected")
                if attempt_index == maximum_attempts:
                    raise ValueError(f"View {slot['frame_id']} failed quality checks.")
                continue
            geometry = frame_geometry(
                corners,
                image_size=size,
                inner_corners=inner,
                contract=contract,
            )
            output_fn(json.dumps({"quality": geometry}, sort_keys=True))
            decision = "accept" if dry_run else prompt_fn("Type accept or retry: ").strip()
            if decision == "retry":
                continue
            if decision != "accept":
                raise ValueError(f"View {slot['frame_id']} was not accepted.")
            receipt = {
                "schema_version": FRAME_RECEIPT_SCHEMA,
                "frame_id": slot["frame_id"],
                "split": slot["split"],
                "camera": camera,
                "focus_setting": focus_setting,
                "focus_observation_method": (
                    "synthetic_fixture" if dry_run else focus["observation_method"]
                ),
                "image_path": _relative(image_path),
                "image_sha256": image_hash,
                "source_pts_seconds": candidate["source_pts_seconds"],
                "captured_at": candidate["captured_at"],
                "caller_supplied_corners": None,
                "capture_authority": candidate["capture_authority"],
                "synthetic": candidate["synthetic"],
                "used_for_fit_or_selection": False,
                "native_capture": {
                    key: candidate[key]
                    for key in (
                        "native_report_path",
                        "native_report_sha256",
                        "native_common_session",
                    )
                    if key in candidate
                },
            }
            receipt_path = output_root / "receipts" / f"{slot['frame_id']}.json"
            _write_json(receipt_path, receipt)
            declarations.append(
                {
                    "frame_id": slot["frame_id"],
                    "split": slot["split"],
                    "receipt_path": _relative(receipt_path),
                    "receipt_sha256": sha256_file(receipt_path),
                }
            )
            image_hashes.add(image_hash)
            accepted = True
            break
        if not accepted:
            raise ValueError(f"View {slot['frame_id']} is missing.")
    target = plan["target"]
    measurement = None
    if not dry_run:
        measurement_path = _repo_path(target["measurement_receipt_path"])
        assert measurement_path is not None
        measurement = _load_json(measurement_path)
    manifest = {
        "schema_version": INPUT_SCHEMA,
        "dataset_id": output_root.name,
        "camera": {**camera, "focus_setting": focus_setting},
        "target": {
            "asset_path": target["asset_path"],
            "asset_sha256": target["asset_sha256"],
            "printed_grid_measurement_receipt": (
                {
                    "path": target["measurement_receipt_path"],
                    "sha256": target["measurement_receipt_sha256"],
                    "physical_measurement": True,
                    "measurements": measurement,
                }
                if not dry_run
                else {
                    "physical_measurement": False,
                    "proof_class": "synthetic_fixture",
                }
            ),
        },
        "splits_frozen_before_fit": True,
        "held_out_sealed_from_fit_selection": True,
        "frames": declarations,
    }
    manifest_path = output_root / "inputs.json"
    _write_json(manifest_path, manifest)
    load_inputs(manifest_path, contract=contract)
    return {
        "schema_version": CORPUS_SCHEMA,
        "status": "synthetic_fixture_complete" if dry_run else "physical_corpus_complete",
        "proof_class": "synthetic_fixture" if dry_run else "physical_camera_frame",
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "frame_count": len(declarations),
        "split_counts": {
            split: sum(row["split"] == split for row in declarations)
            for split in ("fit", "validation", "held_out")
        },
        "evaluator_manifest_consumed": True,
        "fitting_performed": False,
        "physical_authority": False,
    }
