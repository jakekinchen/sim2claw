"""One-shot evaluator-owned qualification of nested dual-camera lifecycle.

The runner acquires raw media and lifecycle anchors. The evaluator re-probes
the media and owns every threshold and verdict. Container PTS are not exposure
timestamps and this module cannot establish cross-camera synchronization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .overhead_video import (
    OverheadVideoError,
    OverheadVideoRecorder,
    WristVideoRecorder,
    list_avfoundation_cameras,
)
from .video_timing import VideoTimingError, probe_video_container_timing


CONTRACT_SCHEMA = "sim2claw.dual_camera_lifecycle_qualification_contract.v1"
CAMPAIGN_SCHEMA = "sim2claw.dual_camera_lifecycle_campaign.v1"
EVENT_SCHEMA = "sim2claw.dual_camera_lifecycle_event.v1"
EVALUATION_SCHEMA = "sim2claw.dual_camera_lifecycle_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.dual_camera_lifecycle_receipt.v1"
PROOF_CLASS = "stationary_nested_dual_camera_lifecycle_container_health"
IMPLEMENTATION_PATHS = (
    "src/sim2claw/dual_camera_lifecycle.py",
    "src/sim2claw/overhead_video.py",
    "src/sim2claw/teleop_recording.py",
    "src/sim2claw/hil_identifiability.py",
)


class DualCameraLifecycleError(RuntimeError):
    """The frozen contract, runtime, raw evidence, or output root is invalid."""


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


def load_contract(path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DualCameraLifecycleError(f"Could not load lifecycle contract: {error}") from error
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise DualCameraLifecycleError("Unexpected dual-camera contract schema.")
    if contract.get("status") != "preregistered_before_implementation_and_observation":
        raise DualCameraLifecycleError("Dual-camera contract is not preregistered.")
    lifecycle = contract.get("lifecycle")
    if lifecycle != {
        "start_order": ["d405_wrist", "c922_overhead"],
        "stop_order": ["c922_overhead", "d405_wrist"],
        "d405_start_completion_before_c922_open_required": True,
        "c922_finalization_before_d405_stop_required": True,
        "both_live_during_common_window_required": True,
    }:
        raise DualCameraLifecycleError("Frozen nested lifecycle changed.")
    qualification = contract.get("qualification")
    expected_qualification = {
        "mode": "stationary_camera_only_no_robot",
        "common_window_duration_seconds": 10.0,
        "attempts_maximum": 1,
        "replacement_attempts": 0,
        "retries": 0,
        "minimum_frame_coverage_fraction_per_stream": 0.95,
        "maximum_source_stalls": 0,
        "require_completed_recorders": True,
        "require_numeric_monotonic_container_pts": True,
        "require_zero_inferred_missing_frame_intervals": True,
        "metric_depth_claim": False,
        "motion_capture_reliability_claim": False,
        "exposure_synchronization_claim": False,
    }
    if qualification != expected_qualification:
        raise DualCameraLifecycleError("Frozen lifecycle qualification changed.")
    budget = contract.get("operation_budget")
    if budget != {
        "attempts_maximum": 1,
        "d405_capture_sessions_maximum": 1,
        "c922_capture_sessions_maximum": 1,
        "common_window_seconds_maximum": 10.0,
        "replacement_attempts_maximum": 0,
        "retries_maximum": 0,
        "robot_motion_trials_maximum": 0,
        "simulator_replays_maximum": 0,
        "provider_calls_maximum": 0,
    }:
        raise DualCameraLifecycleError("Frozen lifecycle budget changed.")
    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise DualCameraLifecycleError("Lifecycle authority is missing.")
    if authority.get("c922_capture_session") is not True:
        raise DualCameraLifecycleError("C922 session authority is missing.")
    if authority.get("d405_capture_session") is not True:
        raise DualCameraLifecycleError("D405 session authority is missing.")
    closed = {
        key: value
        for key, value in authority.items()
        if key not in {"c922_capture_session", "d405_capture_session"}
    }
    if any(bool(value) for value in closed.values()):
        raise DualCameraLifecycleError("Lifecycle authority widened.")
    return contract


def verify_runtime_identity(contract: dict[str, Any]) -> dict[str, str]:
    declared = contract.get("runtime_identity")
    if not isinstance(declared, dict):
        raise DualCameraLifecycleError("Runtime identity is missing.")
    observed: dict[str, str] = {}
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if executable is None:
            raise DualCameraLifecycleError(f"{name} is unavailable.")
        digest = _sha256_file(Path(executable))
        if digest != declared.get(f"{name}_executable_sha256"):
            raise DualCameraLifecycleError(f"{name} executable identity changed.")
        observed[f"{name}_path"] = executable
        observed[f"{name}_sha256"] = digest
    return observed


def implementation_identity() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    return {
        relative: _sha256_file(repo_root / relative)
        for relative in IMPLEMENTATION_PATHS
    }


def repository_identity() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]

    def git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DualCameraLifecycleError(
                f"Could not inspect repository identity: {error}"
            ) from error
        if result.returncode != 0:
            detail = result.stderr.strip() or f"git exited {result.returncode}"
            raise DualCameraLifecycleError(
                f"Could not inspect repository identity: {detail}"
            )
        return result.stdout.strip()

    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise DualCameraLifecycleError(
            "Lifecycle qualification requires a clean exact implementation commit."
        )
    return {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "worktree_clean": True,
    }


def _walk_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(_walk_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_objects(child))
    return found


def inspect_camera_identity(contract: dict[str, Any]) -> dict[str, Any]:
    """Read device identity without opening a capture session."""

    discovery = list_avfoundation_cameras()
    names = [
        str(row.get("name"))
        for row in discovery.get("cameras", [])
        if isinstance(row, dict)
    ]
    declared = contract["device_identity"]
    expected_names = {
        "d405_wrist": str(declared["d405_exact_name"]),
        "c922_overhead": str(declared["c922_exact_name"]),
    }
    for role, name in expected_names.items():
        if names.count(name) != int(declared["exact_avfoundation_name_match_count"]):
            raise DualCameraLifecycleError(
                f"{role} exact AVFoundation device match count changed."
            )

    profiler = Path("/usr/sbin/system_profiler")
    if not profiler.is_file():
        raise DualCameraLifecycleError("system_profiler is unavailable.")
    try:
        result = subprocess.run(
            [str(profiler), "SPCameraDataType", "-json"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DualCameraLifecycleError(f"Could not inspect camera identity: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"system_profiler exited {result.returncode}"
        raise DualCameraLifecycleError(f"Could not inspect camera identity: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DualCameraLifecycleError("Camera identity output is malformed.") from error

    identity: dict[str, Any] = {"avfoundation_names": names}
    for role, name in expected_names.items():
        matches = [
            row
            for row in _walk_objects(payload)
            if row.get("_name") == name
        ]
        if len(matches) != 1:
            raise DualCameraLifecycleError(f"{role} camera profiler identity is ambiguous.")
        row = matches[0]
        prefix = "d405" if role == "d405_wrist" else "c922"
        unique_id = row.get("spcamera_unique-id")
        model_id = row.get("spcamera_model-id")
        if unique_id != declared[f"{prefix}_camera_unique_id"]:
            raise DualCameraLifecycleError(f"{role} unique identity changed.")
        if model_id != declared[f"{prefix}_model_id"]:
            raise DualCameraLifecycleError(f"{role} model identity changed.")
        identity[role] = {
            "name": name,
            "unique_id": unique_id,
            "model_id": model_id,
        }
    return identity


def run_qualification(
    *,
    contract_path: Path,
    output_root: Path,
    poll_interval_seconds: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    overhead_factory: Callable[[Path], Any] = OverheadVideoRecorder,
    wrist_factory: Callable[[Path], Any] = WristVideoRecorder,
) -> dict[str, Any]:
    """Consume the sole stationary session and emit raw evidence without scoring."""

    contract = load_contract(contract_path)
    if output_root.exists():
        raise DualCameraLifecycleError(
            "Lifecycle qualification output already exists; retry is forbidden."
        )
    runtime_identity = verify_runtime_identity(contract)
    camera_identity = inspect_camera_identity(contract)
    code_identity = implementation_identity()
    repo_identity = repository_identity()
    output_root.mkdir(parents=True)
    trial_root = output_root / "trial-01"
    trial_root.mkdir()

    wrist = wrist_factory(trial_root / "wrist_d405.mkv")
    overhead = overhead_factory(trial_root / "overhead_c922.mp4")
    anchors: dict[str, float] = {}
    start_reports: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    capture_error: str | None = None
    wrist_started = False
    overhead_started = False
    wrist_start_invoked = False
    overhead_start_invoked = False
    started_at = _utc_now()

    try:
        anchors["d405_start_requested"] = clock()
        wrist_start_invoked = True
        start_reports["d405_wrist"] = wrist.start()
        wrist_started = True
        anchors["d405_started"] = clock()

        anchors["c922_start_requested"] = clock()
        overhead_start_invoked = True
        start_reports["c922_overhead"] = overhead.start()
        overhead_started = True
        anchors["c922_started"] = clock()

        anchors["common_window_started"] = clock()
        deadline = (
            anchors["common_window_started"]
            + float(contract["qualification"]["common_window_duration_seconds"])
        )
        while clock() < deadline:
            wrist.ensure_running()
            overhead.ensure_running()
            sleep(
                min(
                    max(0.01, float(poll_interval_seconds)),
                    max(0.0, deadline - clock()),
                )
            )
        wrist.ensure_running()
        overhead.ensure_running()
        anchors["common_window_stopped"] = clock()
    except (DualCameraLifecycleError, OverheadVideoError, OSError) as error:
        capture_error = f"{type(error).__name__}: {error}"
        anchors.setdefault("common_window_stopped", clock())
    finally:
        common_start = anchors.get("common_window_started")
        common_stop = anchors.get("common_window_stopped")
        if overhead_started:
            anchors["c922_stop_requested"] = clock()
            try:
                reports["c922_overhead"] = overhead.finish(
                    action_started_monotonic=common_start,
                    action_stopped_monotonic=common_stop,
                    post_roll_seconds=0.0,
                )
            except (OverheadVideoError, OSError) as error:
                reports["c922_overhead"] = {
                    "status": "failed",
                    "failure_kind": "finalization_error",
                    "error": f"{type(error).__name__}: {error}",
                }
            anchors["c922_stopped"] = clock()
        if wrist_started:
            anchors["d405_stop_requested"] = clock()
            try:
                reports["d405_wrist"] = wrist.finish(
                    action_started_monotonic=common_start,
                    action_stopped_monotonic=common_stop,
                    post_roll_seconds=0.0,
                )
            except (OverheadVideoError, OSError) as error:
                reports["d405_wrist"] = {
                    "status": "failed",
                    "failure_kind": "finalization_error",
                    "error": f"{type(error).__name__}: {error}",
                }
            anchors["d405_stopped"] = clock()

    artifact_sha256 = {
        path.name: _sha256_file(path)
        for path in sorted(trial_root.iterdir())
        if path.is_file()
    }
    event = {
        "schema_version": EVENT_SCHEMA,
        "contract_id": contract["contract_id"],
        "attempt_index": 1,
        "replacement": False,
        "retry": False,
        "proof_class": PROOF_CLASS,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "runtime_identity": runtime_identity,
        "implementation_identity": code_identity,
        "repository_identity": repo_identity,
        "camera_identity": camera_identity,
        "lifecycle_anchors_monotonic_seconds": anchors,
        "capture_error": capture_error,
        "start_reports": start_reports,
        "reports": reports,
        "artifact_sha256": artifact_sha256,
        "authority": {
            "robot_gateway": False,
            "robot_motion": False,
            "simulator_replay": False,
            "provider_calls": 0,
            "training": False,
            "promotion": False,
            "task_score_change": False,
        },
    }
    event_path = trial_root / "capture_event.json"
    _write_json(event_path, event)
    campaign = {
        "schema_version": CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "proof_class": PROOF_CLASS,
        "runtime_identity": runtime_identity,
        "implementation_identity": code_identity,
        "repository_identity": repo_identity,
        "event": {
            "attempt_index": 1,
            "path": "trial-01/capture_event.json",
            "sha256": _sha256_file(event_path),
        },
        "budget": {
            "attempts_used": 1,
            "attempts_maximum": 1,
            "replacement_attempts_used": 0,
            "retries_used": 0,
            "d405_capture_sessions_used": int(wrist_start_invoked),
            "c922_capture_sessions_used": int(overhead_start_invoked),
            "robot_motion_trials_used": 0,
            "simulator_replays_used": 0,
            "provider_calls_used": 0,
        },
        "authority": {
            "motion_capture_reliability": False,
            "metric_depth": False,
            "exposure_synchronization": False,
            "robot_behavior": False,
            "simulator_calibration": False,
            "task_success": False,
        },
    }
    _write_json(output_root / "campaign.json", campaign)
    return campaign


def _probe_stream(path: Path, *, ffprobe_path: str) -> dict[str, Any]:
    if not path.is_file():
        raise DualCameraLifecycleError(f"Raw video is missing: {path.name}")
    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,pix_fmt",
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DualCameraLifecycleError(f"Could not probe {path.name}: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"ffprobe exited {result.returncode}"
        raise DualCameraLifecycleError(f"Could not probe {path.name}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DualCameraLifecycleError(f"{path.name} stream metadata is malformed.") from error
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise DualCameraLifecycleError(f"{path.name} must contain exactly one video stream.")
    return streams[0]


def _anchors_are_nested(anchors: Any) -> bool:
    keys = [
        "d405_start_requested",
        "d405_started",
        "c922_start_requested",
        "c922_started",
        "common_window_started",
        "common_window_stopped",
        "c922_stop_requested",
        "c922_stopped",
        "d405_stop_requested",
        "d405_stopped",
    ]
    if not isinstance(anchors, dict) or set(anchors) != set(keys):
        return False
    values: list[float] = []
    for key in keys:
        value = anchors.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        parsed = float(value)
        if not math.isfinite(parsed):
            return False
        values.append(parsed)
    return all(right >= left for left, right in zip(values, values[1:]))


def evaluate_qualification(
    *,
    contract_path: Path,
    campaign_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independently validate, re-probe, score, and seal the one raw event."""

    contract = load_contract(contract_path)
    if output_root.exists():
        raise DualCameraLifecycleError("Evaluation output already exists.")
    runtime_identity = verify_runtime_identity(contract)
    campaign_path = campaign_root / "campaign.json"
    try:
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DualCameraLifecycleError(f"Could not load raw campaign: {error}") from error
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA:
        raise DualCameraLifecycleError("Unexpected raw campaign schema.")
    if campaign.get("contract_id") != contract["contract_id"]:
        raise DualCameraLifecycleError("Raw campaign contract identity changed.")
    if campaign.get("contract_sha256") != _sha256_file(contract_path):
        raise DualCameraLifecycleError("Raw campaign contract hash changed.")
    if campaign.get("proof_class") != PROOF_CLASS:
        raise DualCameraLifecycleError("Raw campaign proof class changed.")
    if campaign.get("runtime_identity") != runtime_identity:
        raise DualCameraLifecycleError("Raw campaign runtime identity changed.")
    code_identity = implementation_identity()
    if campaign.get("implementation_identity") != code_identity:
        raise DualCameraLifecycleError("Raw campaign implementation identity changed.")
    repo_identity = campaign.get("repository_identity")
    if (
        not isinstance(repo_identity, dict)
        or not isinstance(repo_identity.get("head"), str)
        or len(repo_identity["head"]) != 40
        or not isinstance(repo_identity.get("tree"), str)
        or len(repo_identity["tree"]) != 40
        or repo_identity.get("worktree_clean") is not True
    ):
        raise DualCameraLifecycleError("Raw repository identity is invalid.")
    observed_budget = campaign.get("budget")
    if not isinstance(observed_budget, dict):
        raise DualCameraLifecycleError("Raw campaign budget is missing.")
    expected_static_budget = {
        "attempts_used": 1,
        "attempts_maximum": 1,
        "replacement_attempts_used": 0,
        "retries_used": 0,
        "robot_motion_trials_used": 0,
        "simulator_replays_used": 0,
        "provider_calls_used": 0,
    }
    if any(
        observed_budget.get(key) != value
        for key, value in expected_static_budget.items()
    ):
        raise DualCameraLifecycleError("Raw campaign budget is not the frozen budget.")
    if observed_budget.get("d405_capture_sessions_used") != 1:
        raise DualCameraLifecycleError("Raw campaign D405 session accounting changed.")
    if observed_budget.get("c922_capture_sessions_used") not in {0, 1}:
        raise DualCameraLifecycleError("Raw campaign C922 session accounting changed.")
    if set(observed_budget) != {
        *expected_static_budget,
        "d405_capture_sessions_used",
        "c922_capture_sessions_used",
    }:
        raise DualCameraLifecycleError("Raw campaign budget contains extra fields.")
    expected_campaign_authority = {
        "motion_capture_reliability": False,
        "metric_depth": False,
        "exposure_synchronization": False,
        "robot_behavior": False,
        "simulator_calibration": False,
        "task_success": False,
    }
    if campaign.get("authority") != expected_campaign_authority:
        raise DualCameraLifecycleError("Raw campaign authority widened.")
    event_ref = campaign.get("event")
    if event_ref != {
        "attempt_index": 1,
        "path": "trial-01/capture_event.json",
        "sha256": event_ref.get("sha256") if isinstance(event_ref, dict) else None,
    }:
        raise DualCameraLifecycleError("Raw campaign event identity changed.")
    trial_dirs = sorted(path.name for path in campaign_root.glob("trial-*") if path.is_dir())
    if trial_dirs != ["trial-01"]:
        raise DualCameraLifecycleError("Raw campaign contains missing or extra trials.")
    root_files = sorted(path.name for path in campaign_root.iterdir() if path.is_file())
    if root_files != ["campaign.json"]:
        raise DualCameraLifecycleError("Raw campaign contains extra root artifacts.")
    event_path = campaign_root / "trial-01" / "capture_event.json"
    if not isinstance(event_ref, dict) or _sha256_file(event_path) != event_ref.get("sha256"):
        raise DualCameraLifecycleError("Raw lifecycle event hash changed.")
    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DualCameraLifecycleError(f"Could not load raw lifecycle event: {error}") from error
    if (
        event.get("schema_version") != EVENT_SCHEMA
        or event.get("contract_id") != contract["contract_id"]
        or event.get("attempt_index") != 1
        or event.get("replacement") is not False
        or event.get("retry") is not False
        or event.get("proof_class") != PROOF_CLASS
    ):
        raise DualCameraLifecycleError("Raw lifecycle event identity changed.")
    if event.get("runtime_identity") != runtime_identity:
        raise DualCameraLifecycleError("Raw event runtime identity changed.")
    if event.get("implementation_identity") != code_identity:
        raise DualCameraLifecycleError("Raw event implementation identity changed.")
    if event.get("repository_identity") != repo_identity:
        raise DualCameraLifecycleError("Raw event repository identity changed.")
    captured_camera_identity = event.get("camera_identity")
    declared_camera_identity = contract["device_identity"]
    expected_cameras = {
        "d405_wrist": {
            "name": declared_camera_identity["d405_exact_name"],
            "unique_id": declared_camera_identity["d405_camera_unique_id"],
            "model_id": declared_camera_identity["d405_model_id"],
        },
        "c922_overhead": {
            "name": declared_camera_identity["c922_exact_name"],
            "unique_id": declared_camera_identity["c922_camera_unique_id"],
            "model_id": declared_camera_identity["c922_model_id"],
        },
    }
    if not isinstance(captured_camera_identity, dict):
        raise DualCameraLifecycleError("Raw camera identity is missing.")
    captured_names = captured_camera_identity.get("avfoundation_names")
    if not isinstance(captured_names, list):
        raise DualCameraLifecycleError("Raw AVFoundation device names are missing.")
    for role, expected in expected_cameras.items():
        if captured_camera_identity.get(role) != expected:
            raise DualCameraLifecycleError(f"Raw {role} identity changed.")
        if captured_names.count(expected["name"]) != int(
            declared_camera_identity["exact_avfoundation_name_match_count"]
        ):
            raise DualCameraLifecycleError(f"Raw {role} match count changed.")
    if event.get("authority") != {
        "robot_gateway": False,
        "robot_motion": False,
        "simulator_replay": False,
        "provider_calls": 0,
        "training": False,
        "promotion": False,
        "task_score_change": False,
    }:
        raise DualCameraLifecycleError("Raw event authority widened.")

    trial_root = campaign_root / "trial-01"
    declared_artifacts = event.get("artifact_sha256")
    if not isinstance(declared_artifacts, dict):
        raise DualCameraLifecycleError("Raw artifact manifest is missing.")
    observed_artifact_names = {
        path.name
        for path in trial_root.iterdir()
        if path.is_file() and path.name != "capture_event.json"
    }
    if set(declared_artifacts) != observed_artifact_names:
        raise DualCameraLifecycleError(
            "Raw artifact manifest does not cover the exact trial files."
        )
    raw_artifact_sha256: dict[str, str] = {
        "campaign.json": _sha256_file(campaign_path),
        "trial-01/capture_event.json": _sha256_file(event_path),
    }
    for filename, declared_digest in sorted(declared_artifacts.items()):
        if Path(filename).name != filename:
            raise DualCameraLifecycleError("Raw artifact path is not a direct child.")
        path = trial_root / filename
        if not path.is_file() or _sha256_file(path) != declared_digest:
            raise DualCameraLifecycleError(f"Raw artifact changed: {filename}")
        raw_artifact_sha256[f"trial-01/{filename}"] = declared_digest

    failures: list[str] = []
    anchors = event.get("lifecycle_anchors_monotonic_seconds")
    if not _anchors_are_nested(anchors):
        failures.append("nested_lifecycle_order_failed")
        common_duration = None
    else:
        common_duration = (
            float(anchors["common_window_stopped"])
            - float(anchors["common_window_started"])
        )
        if common_duration < float(
            contract["qualification"]["common_window_duration_seconds"]
        ):
            failures.append("common_window_duration_failed")
    if event.get("capture_error") is not None:
        failures.append("runner_capture_error")

    roles: dict[str, Any] = {}
    role_specs = {
        "d405_wrist": {
            "filename": "wrist_d405.mkv",
            "fps": 5.0,
            "width": 424,
            "height": 240,
            "codec_name": "ffv1",
            "minimum_frames": 48,
        },
        "c922_overhead": {
            "filename": "overhead_c922.mp4",
            "fps": 30.0,
            "width": 640,
            "height": 480,
            "codec_name": "h264",
            "minimum_frames": 285,
        },
    }
    ffprobe_path = runtime_identity["ffprobe_path"]
    for role, spec in role_specs.items():
        role_failures: list[str] = []
        start_report = event.get("start_reports", {}).get(role)
        expected_camera_name = expected_cameras[role]["name"]
        if not isinstance(start_report, dict) or start_report.get("status") != "recording":
            role_failures.append("recorder_not_started")
        elif (
            start_report.get("camera_name") != expected_camera_name
            or start_report.get("configured_width") != spec["width"]
            or start_report.get("configured_height") != spec["height"]
            or start_report.get("configured_fps") != spec["fps"]
        ):
            role_failures.append("start_configuration_changed")
        report = event.get("reports", {}).get(role)
        if not isinstance(report, dict) or report.get("status") != "completed":
            role_failures.append("recorder_not_completed")
        if role == "d405_wrist" and (
            not isinstance(report, dict)
            or report.get("source_stall_detected") is not False
            or report.get("source_progress_status") != "progressing"
        ):
            role_failures.append("source_progress_failed")
        path = trial_root / str(spec["filename"])
        try:
            stream = _probe_stream(path, ffprobe_path=ffprobe_path)
            timing = probe_video_container_timing(
                path,
                configured_fps=float(spec["fps"]),
                ffprobe_path=ffprobe_path,
            )
        except (DualCameraLifecycleError, VideoTimingError) as error:
            role_failures.append("media_probe_failed")
            stream = {"error": str(error)}
            timing = None
        if timing is not None:
            if int(timing["frame_count"]) < int(spec["minimum_frames"]):
                role_failures.append("frame_coverage_failed")
            if (
                int(timing["duplicate_pts_count"]) != 0
                or int(timing["non_monotonic_interval_count"]) != 0
            ):
                role_failures.append("container_pts_not_strictly_monotonic")
            if int(timing["inferred_missing_frame_intervals"]) != 0:
                role_failures.append("inferred_missing_intervals")
        if stream.get("width") != spec["width"] or stream.get("height") != spec["height"]:
            role_failures.append("dimensions_changed")
        if stream.get("codec_name") != spec["codec_name"]:
            role_failures.append("codec_changed")
        role_failures = sorted(set(role_failures))
        failures.extend(f"{role}:{failure}" for failure in role_failures)
        roles[role] = {
            "status": "passed" if not role_failures else "failed",
            "configured_fps": spec["fps"],
            "minimum_common_window_frames": spec["minimum_frames"],
            "stream": stream,
            "container_timing": timing,
            "failures": role_failures,
        }

    failures = sorted(set(failures))
    verdict = (
        "pass_stationary_nested_dual_camera_lifecycle_health_only"
        if not failures
        else "reject_stationary_nested_dual_camera_lifecycle"
    )
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "campaign_sha256": _sha256_file(campaign_path),
        "event_sha256": _sha256_file(event_path),
        "proof_class": PROOF_CLASS,
        "attempt_count": 1,
        "replacement_attempt_count": 0,
        "retry_count": 0,
        "d405_capture_session_count": observed_budget[
            "d405_capture_sessions_used"
        ],
        "c922_capture_session_count": observed_budget[
            "c922_capture_sessions_used"
        ],
        "robot_motion_trial_count": 0,
        "simulator_replay_count": 0,
        "provider_call_count": 0,
        "lifecycle_anchors_monotonic_seconds": anchors,
        "common_window_duration_seconds": common_duration,
        "roles": roles,
        "failures": failures,
        "verdict": verdict,
        "claim_limits": {
            "stationary_nested_camera_lifecycle_health": verdict.startswith("pass_"),
            "motion_capture_reliability": False,
            "metric_depth": False,
            "camera_exposure_timestamps": False,
            "cross_camera_synchronization": False,
            "robot_behavior": False,
            "simulator_calibration": False,
            "task_success": False,
        },
    }
    evaluation["evaluation_digest"] = _canonical_digest(evaluation)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "campaign_sha256": _sha256_file(campaign_path),
        "event_sha256": _sha256_file(event_path),
        "evaluation_digest": evaluation["evaluation_digest"],
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "operation_budget": observed_budget,
        "raw_artifact_sha256": raw_artifact_sha256,
        "claim_limits": evaluation["claim_limits"],
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--contract", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--contract", type=Path, required=True)
    evaluate.add_argument("--campaign-root", type=Path, required=True)
    evaluate.add_argument("--output-root", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "run":
        result = run_qualification(
            contract_path=args.contract,
            output_root=args.output_root,
        )
    else:
        result, _ = evaluate_qualification(
            contract_path=args.contract,
            campaign_root=args.campaign_root,
            output_root=args.output_root,
        )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
