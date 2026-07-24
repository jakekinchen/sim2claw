"""Fail-closed current-workcell measurement acquisition.

The first stage is deliberately torque-off and read-only. It binds the live
SO-101 and camera identities to a preregistered contract, captures timestamped
joint/current observations plus diagnostic video, and emits a content-addressed
receipt. It has no motion method and grants no calibration or task authority.
"""

from __future__ import annotations

import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .overhead_video import OverheadVideoRecorder
from .paths import REPO_ROOT
from .physical_gateway import GatewayIdentity, SO101PhysicalGateway
from .teleop_recording import recorder_preflight


CONTRACT_SCHEMA = "sim2claw.current_100mm_measurement_acquisition.v1"
BASELINE_SCHEMA = "sim2claw.current_100mm_torque_off_baseline.v1"
RECEIPT_SCHEMA = "sim2claw.current_100mm_measurement_receipt.v1"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "current_100mm_measurement_acquisition_v1.json"
)


class CurrentWorkcellMeasurementError(RuntimeError):
    """A measurement identity, safety, or evidence boundary failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CurrentWorkcellMeasurementError(message)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_measurement_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentWorkcellMeasurementError(
            f"Could not load the current-workcell measurement contract: {error}"
        ) from error
    _require(isinstance(contract, dict), "Measurement contract must be an object.")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "Unsupported current-workcell measurement contract.",
    )
    _require(
        contract.get("status") == "preregistered_preflight_blocked_safe_start_pose",
        "Measurement contract status changed.",
    )
    budget = contract.get("measurement_budget")
    _require(isinstance(budget, dict), "Measurement budget is missing.")
    _require(
        int(budget.get("torque_off_baseline_sessions", -1)) == 1,
        "Torque-off baseline budget changed.",
    )
    authority = contract.get("authority")
    _require(isinstance(authority, dict), "Measurement authority is missing.")
    _require(
        authority.get("owner_authorized_camera_capture") is True,
        "Camera capture is not owner-authorized.",
    )
    _require(
        authority.get("gateway_motion_execution_admitted") is False,
        "Torque-off acquisition refuses a motion-admitted contract.",
    )
    _require(
        authority.get("physical_task_claim_admitted") is False
        and authority.get("training_admission") is False
        and authority.get("promotion_authority") is False,
        "Measurement contract widened downstream authority.",
    )
    return contract


def _identity_from_preflight(
    preflight: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> GatewayIdentity:
    hardware = contract["hardware_identity"]
    devices = preflight.get("devices")
    calibrations = preflight.get("calibrations")
    _require(
        isinstance(devices, Mapping) and isinstance(calibrations, Mapping),
        "Live hardware preflight is incomplete.",
    )
    observed = {
        "leader_port": devices["leader"].get("port"),
        "follower_port": devices["follower"].get("port"),
        "leader_calibration_sha256": calibrations["leader"].get("sha256"),
        "follower_calibration_sha256": calibrations["follower"].get("sha256"),
    }
    for field, value in observed.items():
        _require(value == hardware.get(field), f"Live hardware identity changed: {field}.")
    _require(
        preflight.get("modes", {}).get("physical_follower", {}).get("ready") is True,
        "Both preregistered calibrated SO-101 buses are required.",
    )
    return GatewayIdentity(**{field: str(value) for field, value in observed.items()})


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(path)


def capture_torque_off_baseline(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    sample_count: int = 30,
    sample_interval_seconds: float = 0.25,
    preflight_fn: Callable[[], dict[str, Any]] = recorder_preflight,
    gateway_factory: Callable[..., SO101PhysicalGateway] = SO101PhysicalGateway,
    video_factory: Callable[..., OverheadVideoRecorder] = OverheadVideoRecorder,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], str] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Capture one bounded torque-off baseline and return its verified receipt."""

    contract = load_measurement_contract(contract_path)
    budget = contract["measurement_budget"]
    _require(sample_count > 0, "Torque-off baseline requires at least one sample.")
    _require(
        sample_count <= int(budget["torque_off_samples_maximum"]),
        "Torque-off sample budget exceeded.",
    )
    _require(
        sample_interval_seconds >= 0.0,
        "Torque-off sample interval cannot be negative.",
    )
    planned_duration = max(0, sample_count - 1) * sample_interval_seconds
    _require(
        planned_duration <= float(budget["torque_off_video_seconds_maximum"]),
        "Torque-off video duration budget exceeded.",
    )
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "Measurement output root is not empty; replay/overwrite is refused.",
    )
    output_root.mkdir(parents=True, exist_ok=True)

    preflight = preflight_fn()
    identity = _identity_from_preflight(preflight, contract)
    hardware = contract["hardware_identity"]
    gateway = gateway_factory(identity, configure_devices=False)
    video = video_factory(
        output_root / "overhead_c922.mp4",
        width=640,
        height=480,
        fps=30,
    )
    gateway_opened = False
    video_started = False
    video_report: dict[str, Any] | None = None
    samples: list[dict[str, Any]] = []
    baseline_started: float | None = None
    baseline_stopped: float | None = None
    open_report: dict[str, Any] | None = None
    try:
        open_report = gateway.open(enable_motion=False)
        gateway_opened = True
        _require(
            open_report.get("physical_follower_torque_enabled") is False,
            "Gateway did not preserve torque-off state.",
        )
        video_report = video.start()
        video_started = True
        _require(
            video_report.get("status") == "recording",
            "Overhead camera did not enter recording state.",
        )
        baseline_started = clock()
        for index in range(sample_count):
            target = baseline_started + index * sample_interval_seconds
            delay = target - clock()
            if delay > 0.0:
                sleep(delay)
            video.ensure_running()
            started = clock()
            observed_at = wall_clock()
            sample = gateway.sample_read_only()
            completed = clock()
            _require(
                sample.get("physical_follower_torque_enabled") is False
                and sample.get("physical_motion_commanded") is False,
                "Torque or motion state changed during read-only acquisition.",
            )
            current = sample.get("available_motor_current_raw")
            samples.append(
                {
                    "schema_version": BASELINE_SCHEMA,
                    "sample_index": index,
                    "observed_at": observed_at,
                    "sample_started_monotonic_seconds": started,
                    "sample_completed_monotonic_seconds": completed,
                    "current_read_bracket_monotonic_seconds": [started, completed],
                    "current_fresh_for_this_sample": current is not None,
                    "observation": copy.deepcopy(sample),
                }
            )
        baseline_stopped = clock()
    finally:
        if video_started:
            video_report = video.finish(
                action_started_monotonic=baseline_started,
                action_stopped_monotonic=baseline_stopped or clock(),
                post_roll_seconds=0.0,
            )
        if gateway_opened:
            gateway.close()

    _require(video_report is not None, "Overhead video report is missing.")
    _require(video_report.get("status") == "completed", "Overhead video is incomplete.")
    _require(len(samples) == sample_count, "Torque-off sample count is incomplete.")
    _require(
        all(row["current_fresh_for_this_sample"] for row in samples),
        "Fresh current was unavailable for at least one torque-off sample.",
    )

    samples_path = output_root / "torque_off_samples.jsonl"
    _atomic_write_jsonl(samples_path, samples)
    video_path = output_root / str(video_report["video_path"])
    log_path = output_root / str(video_report["ffmpeg_log_path"])
    _require(video_path.is_file(), "Overhead video artifact is missing.")
    _require(log_path.is_file(), "Overhead camera log is missing.")
    artifacts = {
        "torque_off_samples.jsonl": sha256_file(samples_path),
        video_path.name: sha256_file(video_path),
        log_path.name: sha256_file(log_path),
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "proof_class": "physical_torque_off_read_only_baseline",
        "status": "complete_no_motion_no_task_claim",
        "captured_at": wall_clock(),
        "hardware_identity": copy.deepcopy(hardware),
        "sample_count": len(samples),
        "fresh_current_sample_count": sum(
            int(row["current_fresh_for_this_sample"]) for row in samples
        ),
        "gateway_open_report": copy.deepcopy(open_report),
        "video_report": copy.deepcopy(video_report),
        "artifact_sha256": artifacts,
        "unavailable_observables": [
            "metric_board_to_robot_registration",
            "metric_object_keypoints_or_pose",
            "contact_force",
            "load_or_deformation_sensor",
            "physical_task_consequence",
        ],
        "authority": {
            "physical_motion_commanded": False,
            "physical_task_claim_admitted": False,
            "training_admission": False,
            "promotion_authority": False,
        },
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "BASELINE_SCHEMA",
    "CONTRACT_SCHEMA",
    "CurrentWorkcellMeasurementError",
    "RECEIPT_SCHEMA",
    "capture_torque_off_baseline",
    "load_measurement_contract",
]
