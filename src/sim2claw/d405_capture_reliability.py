"""Bounded camera-only qualification for the D405 capture transport.

The runner owns acquisition only. The evaluator re-probes the emitted videos
and derives the verdict from the frozen contract; recorder status fields are
inputs to validate, not self-scored claims.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .overhead_video import (
    OverheadVideoError,
    OverheadVideoRecorder,
    WristVideoRecorder,
)
from .video_timing import VideoTimingError, probe_video_container_timing


CONTRACT_SCHEMA = "sim2claw.d405_capture_reliability_contract.v1"
CAMPAIGN_SCHEMA = "sim2claw.d405_capture_reliability_campaign.v1"
EVALUATION_SCHEMA = "sim2claw.d405_capture_reliability_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.d405_capture_reliability_receipt.v1"


class D405ReliabilityError(RuntimeError):
    """The frozen qualification contract or raw campaign is invalid."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_d405_reliability_contract(path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D405ReliabilityError(f"Could not load D405 contract: {error}") from error
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise D405ReliabilityError("Unexpected D405 reliability contract schema.")
    if contract.get("status") != "frozen_before_recorder_reliability_implementation":
        raise D405ReliabilityError("D405 reliability contract is not frozen.")
    qualification = contract.get("qualification")
    if not isinstance(qualification, dict):
        raise D405ReliabilityError("D405 qualification declaration is missing.")
    expected = {
        "mode": "camera_only_no_robot_motion",
        "required_consecutive_trials": 6,
        "trial_duration_seconds": 40.0,
        "replacement_trials": 0,
        "simultaneous_c922_and_d405": True,
        "minimum_frame_coverage_fraction_per_stream": 0.95,
        "maximum_source_stalls": 0,
        "require_monotonic_container_pts": True,
        "require_zero_inferred_missing_frame_intervals": True,
        "metric_depth_claim": False,
        "motion_capture_reliability_claim": False,
    }
    for key, expected_value in expected.items():
        if qualification.get(key) != expected_value:
            raise D405ReliabilityError(
                f"Frozen qualification field {key!r} does not match {expected_value!r}."
            )
    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(bool(value) for value in authority.values()):
        raise D405ReliabilityError("D405 qualification authority must remain closed.")
    return contract


def verify_d405_runtime_identity(contract: dict[str, Any]) -> dict[str, str]:
    declared = contract.get("runtime_identity")
    if not isinstance(declared, dict):
        raise D405ReliabilityError("D405 runtime identity is missing.")
    observed: dict[str, str] = {}
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if executable is None:
            raise D405ReliabilityError(f"{name} is unavailable.")
        digest = _sha256_file(Path(executable))
        if digest != declared.get(f"{name}_executable_sha256"):
            raise D405ReliabilityError(f"{name} executable identity changed.")
        observed[f"{name}_path"] = executable
        observed[f"{name}_sha256"] = digest
    return observed


def run_d405_camera_only_qualification(
    *,
    contract_path: Path,
    output_root: Path,
    poll_interval_seconds: float = 0.25,
) -> dict[str, Any]:
    """Consume exactly six no-motion camera attempts with zero replacements."""

    contract = load_d405_reliability_contract(contract_path)
    if output_root.exists():
        raise D405ReliabilityError(
            "Qualification output already exists; retries and replacements are forbidden."
        )
    runtime_identity = verify_d405_runtime_identity(contract)
    output_root.mkdir(parents=True)
    qualification = contract["qualification"]
    trial_count = int(qualification["required_consecutive_trials"])
    duration_seconds = float(qualification["trial_duration_seconds"])
    events: list[dict[str, Any]] = []

    for index in range(1, trial_count + 1):
        trial_id = f"trial-{index:02d}"
        trial_root = output_root / trial_id
        trial_root.mkdir()
        overhead = OverheadVideoRecorder(trial_root / "overhead_c922.mp4")
        wrist = WristVideoRecorder(trial_root / "wrist_d405.mkv")
        started_at = _utc_now()
        interval_started: float | None = None
        interval_stopped: float | None = None
        start_reports: dict[str, Any] = {}
        capture_error: str | None = None

        try:
            start_reports["overhead"] = overhead.start()
            start_reports["wrist"] = wrist.start()
            interval_started = time.monotonic()
            deadline = interval_started + duration_seconds
            while time.monotonic() < deadline:
                overhead.ensure_running()
                wrist.ensure_running()
                time.sleep(
                    min(
                        max(0.01, poll_interval_seconds),
                        max(0.0, deadline - time.monotonic()),
                    )
                )
            overhead.ensure_running()
            wrist.ensure_running()
        except (OverheadVideoError, OSError) as error:
            capture_error = f"{type(error).__name__}: {error}"
        finally:
            interval_stopped = time.monotonic()
            reports: dict[str, Any] = {}
            for role, recorder in (("wrist", wrist), ("overhead", overhead)):
                try:
                    reports[role] = recorder.finish(
                        action_started_monotonic=interval_started,
                        action_stopped_monotonic=interval_stopped,
                        post_roll_seconds=0.0,
                    )
                except (OverheadVideoError, OSError) as error:
                    reports[role] = {
                        "status": "failed",
                        "failure_kind": "finalization_error",
                        "error": f"{type(error).__name__}: {error}",
                    }

        artifact_sha256: dict[str, str] = {}
        for path in sorted(trial_root.iterdir()):
            if path.is_file():
                artifact_sha256[path.name] = _sha256_file(path)
        event = {
            "trial_id": trial_id,
            "attempt_index": index,
            "replacement": False,
            "robot_motion": False,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "capture_error": capture_error,
            "start_reports": start_reports,
            "reports": reports,
            "artifact_sha256": artifact_sha256,
        }
        _write_json(trial_root / "capture_event.json", event)
        event["capture_event_sha256"] = _sha256_file(trial_root / "capture_event.json")
        events.append(event)

    campaign = {
        "schema_version": CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "runtime_identity": runtime_identity,
        "proof_class": "camera_only_stationary_dual_stream_transport_health",
        "budget": {
            "required_consecutive_trials": trial_count,
            "used_trials": len(events),
            "replacement_trials_allowed": 0,
            "replacement_trials_used": 0,
            "robot_motion_trials": 0,
            "provider_calls": 0,
        },
        "events": [
            {
                "trial_id": event["trial_id"],
                "attempt_index": event["attempt_index"],
                "capture_event_sha256": event["capture_event_sha256"],
            }
            for event in events
        ],
        "authority": {
            "metric_depth": False,
            "motion_capture_reliability": False,
            "robot_motion": False,
            "simulator_replay": False,
            "training": False,
            "promotion": False,
            "task_score_change": False,
        },
    }
    _write_json(output_root / "campaign.json", campaign)
    return campaign


def _probe_trial_video(
    *,
    path: Path,
    configured_fps: float,
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "video_missing"
    try:
        return (
            probe_video_container_timing(path, configured_fps=configured_fps),
            None,
        )
    except VideoTimingError as error:
        return None, f"timing_unavailable:{error}"


def evaluate_d405_camera_only_qualification(
    *,
    contract_path: Path,
    campaign_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independently re-probe six raw trials and issue a deterministic receipt."""

    contract = load_d405_reliability_contract(contract_path)
    try:
        campaign = json.loads(
            (campaign_root / "campaign.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise D405ReliabilityError(f"Could not load raw campaign: {error}") from error
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA:
        raise D405ReliabilityError("Unexpected D405 campaign schema.")
    if campaign.get("contract_id") != contract["contract_id"]:
        raise D405ReliabilityError("Raw campaign contract identity changed.")
    if (
        campaign.get("proof_class")
        != "camera_only_stationary_dual_stream_transport_health"
    ):
        raise D405ReliabilityError("Raw campaign proof class changed.")
    if campaign.get("contract_sha256") != _sha256_file(contract_path):
        raise D405ReliabilityError("Raw campaign contract hash does not match.")
    if campaign.get("runtime_identity") != verify_d405_runtime_identity(contract):
        raise D405ReliabilityError("Raw campaign runtime identity changed.")

    qualification = contract["qualification"]
    required_trials = int(qualification["required_consecutive_trials"])
    declared_events = campaign.get("events")
    if not isinstance(declared_events, list) or len(declared_events) != required_trials:
        raise D405ReliabilityError("Raw campaign does not contain exactly six events.")
    expected_ids = [f"trial-{index:02d}" for index in range(1, required_trials + 1)]
    if [event.get("trial_id") for event in declared_events] != expected_ids:
        raise D405ReliabilityError("Raw campaign trial order or identity changed.")
    observed_trial_ids = sorted(
        path.name
        for path in campaign_root.glob("trial-*")
        if path.is_dir()
    )
    if observed_trial_ids != expected_ids:
        raise D405ReliabilityError("Raw campaign contains missing or extra trials.")
    if campaign.get("budget") != {
        "required_consecutive_trials": required_trials,
        "used_trials": required_trials,
        "replacement_trials_allowed": 0,
        "replacement_trials_used": 0,
        "robot_motion_trials": 0,
        "provider_calls": 0,
    }:
        raise D405ReliabilityError("Raw campaign budget is not the frozen budget.")
    expected_authority = {
        "metric_depth": False,
        "motion_capture_reliability": False,
        "robot_motion": False,
        "simulator_replay": False,
        "training": False,
        "promotion": False,
        "task_score_change": False,
    }
    if campaign.get("authority") != expected_authority:
        raise D405ReliabilityError("Raw campaign authority is not closed.")

    duration = float(qualification["trial_duration_seconds"])
    minimum_coverage = float(
        qualification["minimum_frame_coverage_fraction_per_stream"]
    )
    evaluated_trials: list[dict[str, Any]] = []
    campaign_failures: list[str] = []
    raw_artifact_sha256: dict[str, str] = {}

    for trial_id in expected_ids:
        trial_root = campaign_root / trial_id
        event_path = trial_root / "capture_event.json"
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise D405ReliabilityError(
                f"Could not load {trial_id} capture event: {error}"
            ) from error
        declared = next(row for row in declared_events if row["trial_id"] == trial_id)
        if _sha256_file(event_path) != declared.get("capture_event_sha256"):
            raise D405ReliabilityError(f"{trial_id} capture-event hash changed.")
        if (
            event.get("trial_id") != trial_id
            or event.get("replacement") is not False
            or event.get("robot_motion") is not False
        ):
            raise D405ReliabilityError(f"{trial_id} identity or authority changed.")
        declared_artifacts = event.get("artifact_sha256")
        if not isinstance(declared_artifacts, dict):
            raise D405ReliabilityError(f"{trial_id} artifact manifest is missing.")
        for filename, declared_digest in sorted(declared_artifacts.items()):
            if Path(filename).name != filename:
                raise D405ReliabilityError(
                    f"{trial_id} artifact name is not a direct child."
                )
            artifact_path = trial_root / filename
            if (
                not artifact_path.is_file()
                or _sha256_file(artifact_path) != declared_digest
            ):
                raise D405ReliabilityError(
                    f"{trial_id} artifact {filename!r} changed."
                )
        for raw_path in sorted(trial_root.iterdir()):
            if raw_path.is_file():
                raw_artifact_sha256[
                    f"{trial_id}/{raw_path.name}"
                ] = _sha256_file(raw_path)

        trial_failures: list[str] = []
        role_results: dict[str, Any] = {}
        role_specs = {
            "overhead": ("overhead_c922.mp4", 30.0),
            "wrist": ("wrist_d405.mkv", 5.0),
        }
        for role, (filename, fps) in role_specs.items():
            video_path = trial_root / filename
            timing, probe_error = _probe_trial_video(
                path=video_path,
                configured_fps=fps,
            )
            relative = f"{trial_id}/{filename}"
            if video_path.is_file():
                raw_artifact_sha256[relative] = _sha256_file(video_path)
            report = event.get("reports", {}).get(role)
            if not isinstance(report, dict):
                report = {}
            if report.get("status") != "completed":
                trial_failures.append(f"{role}_recorder_not_completed")
            if role == "wrist" and (
                report.get("source_stall_detected") is not False
                or report.get("source_progress_status") != "progressing"
            ):
                trial_failures.append("wrist_source_progress_failed")
            if probe_error is not None or timing is None:
                trial_failures.append(f"{role}_{probe_error or 'timing_unavailable'}")
                role_results[role] = {
                    "status": "failed",
                    "probe_error": probe_error,
                }
                continue

            frame_count = int(timing["frame_count"])
            expected_frames = duration * fps
            coverage = min(1.0, frame_count / expected_frames)
            if coverage < minimum_coverage:
                trial_failures.append(f"{role}_frame_coverage_failed")
            if int(timing["non_monotonic_interval_count"]) != 0:
                trial_failures.append(f"{role}_non_monotonic_pts")
            if int(timing["inferred_missing_frame_intervals"]) != 0:
                trial_failures.append(f"{role}_inferred_missing_intervals")
            role_results[role] = {
                "status": "passed" if not any(
                    failure.startswith(f"{role}_") for failure in trial_failures
                ) else "failed",
                "configured_fps": fps,
                "expected_frames": expected_frames,
                "observed_frames": frame_count,
                "frame_coverage_fraction": coverage,
                "container_timing": timing,
            }

        if event.get("capture_error") is not None:
            trial_failures.append("runner_capture_error")
        trial_failures = sorted(set(trial_failures))
        if trial_failures:
            campaign_failures.extend(
                f"{trial_id}:{failure}" for failure in trial_failures
            )
        evaluated_trials.append(
            {
                "trial_id": trial_id,
                "status": "passed" if not trial_failures else "failed",
                "roles": role_results,
                "failures": trial_failures,
            }
        )

    passed_trials = sum(row["status"] == "passed" for row in evaluated_trials)
    verdict = (
        "pass_stationary_dual_camera_transport_health_only"
        if passed_trials == required_trials and not campaign_failures
        else "reject_stationary_capture_reliability"
    )
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "campaign_sha256": _sha256_file(campaign_root / "campaign.json"),
        "proof_class": "camera_only_stationary_dual_stream_transport_health",
        "trial_count": required_trials,
        "passed_trial_count": passed_trials,
        "failed_trial_count": required_trials - passed_trials,
        "source_stall_count": sum(
            "wrist_source_progress_failed" in trial["failures"]
            for trial in evaluated_trials
        ),
        "replacement_trial_count": 0,
        "robot_motion_trial_count": 0,
        "provider_call_count": 0,
        "trials": evaluated_trials,
        "failures": sorted(campaign_failures),
        "verdict": verdict,
        "claim_limits": {
            "stationary_camera_transport_health": verdict.startswith("pass_"),
            "motion_capture_reliability": False,
            "metric_depth": False,
            "camera_exposure_timestamps": False,
            "device_synchronized": False,
            "robot_behavior": False,
            "simulator_calibration": False,
            "task_success": False,
        },
    }
    receipt_payload = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": evaluation["contract_sha256"],
        "campaign_sha256": evaluation["campaign_sha256"],
        "evaluation_digest": _canonical_digest(evaluation),
        "raw_artifact_sha256": dict(sorted(raw_artifact_sha256.items())),
        "budget": campaign["budget"],
        "verdict": verdict,
        "proof_class": evaluation["proof_class"],
        "authority": campaign["authority"],
    }
    receipt = {
        **receipt_payload,
        "receipt_digest": _canonical_digest(receipt_payload),
    }
    _write_json(output_root / "evaluation.json", evaluation)
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
