"""Evaluator-owned AVFoundation source-versus-container localization.

The native probe emits source observations only. This module owns compilation,
bounded no-motion orchestration, validation, and independent aggregation.
Neither source PTS nor host time is interpreted as a shared exposure clock.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .overhead_video import OverheadVideoError, WristVideoRecorder


CONTRACT_SCHEMA = "sim2claw.avfoundation_source_localization_contract.v1"
SOURCE_EVENT_SCHEMA = "sim2claw.avfoundation_source_event.v1"
ORCHESTRATION_EVENT_SCHEMA = "sim2claw.camera_lifecycle_orchestration_event.v1"
TRIAL_SCHEMA = "sim2claw.avfoundation_source_localization_trial.v1"
CAMPAIGN_SCHEMA = "sim2claw.avfoundation_source_localization_campaign.v1"
EVALUATION_SCHEMA = "sim2claw.avfoundation_source_localization_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.avfoundation_source_localization_receipt.v1"

ALLOWED_SOURCE_EVENT_TYPES = {
    "probe_started",
    "authorization_observed",
    "device_discovery_observed",
    "format_selected",
    "session_start_requested",
    "session_start_returned",
    "sample_output",
    "sample_dropped",
    "session_interrupted",
    "session_interruption_ended",
    "session_runtime_error",
    "device_connected",
    "device_disconnected",
    "session_stop_requested",
    "session_stop_returned",
    "probe_finished",
}

EXPECTED_TRIAL_ORDER = [
    "C01",
    "T01",
    "T02",
    "C02",
    "C03",
    "T03",
    "T04",
    "C04",
    "C05",
    "T05",
    "T06",
    "C06",
]


class AVFoundationLocalizationError(RuntimeError):
    """The frozen contract, source events, or campaign is invalid."""


class _MachTimebaseInfo(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


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


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(_canonical_bytes(value))
        handle.flush()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _host_continuous_stamp() -> dict[str, int]:
    """Read mach_continuous_time so Python and Swift lifecycle events align."""

    library = ctypes.CDLL(None)
    mach_continuous_time = library.mach_continuous_time
    mach_continuous_time.restype = ctypes.c_uint64
    mach_timebase_info = library.mach_timebase_info
    mach_timebase_info.argtypes = [ctypes.POINTER(_MachTimebaseInfo)]
    info = _MachTimebaseInfo()
    if mach_timebase_info(ctypes.byref(info)) != 0 or info.denom == 0:
        raise AVFoundationLocalizationError("Could not read Mach timebase.")
    ticks = int(mach_continuous_time())
    nanoseconds = int((ticks * int(info.numer)) // int(info.denom))
    return {
        "host_continuous_ticks": ticks,
        "host_continuous_ns": nanoseconds,
        "mach_timebase_numer": int(info.numer),
        "mach_timebase_denom": int(info.denom),
    }


def load_source_localization_contract(path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationLocalizationError(
            f"Could not load source-localization contract: {error}"
        ) from error
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise AVFoundationLocalizationError(
            "Unexpected source-localization contract schema."
        )
    if contract.get("status") != "frozen_before_source_probe_implementation":
        raise AVFoundationLocalizationError("Source-localization contract is not frozen.")

    campaign = contract.get("campaign")
    if not isinstance(campaign, dict):
        raise AVFoundationLocalizationError("Campaign declaration is missing.")
    expected_campaign = {
        "mode": "camera_only_no_robot_motion",
        "fixed_trial_order": EXPECTED_TRIAL_ORDER,
        "trials_per_cell": 6,
        "total_trials": 12,
        "replacement_trials": 0,
        "source_probe_duration_seconds": 30.0,
        "source_warmup_seconds": 5.0,
        "lifecycle_start_offset_seconds": 5.0,
        "lifecycle_stop_offset_seconds": 25.0,
        "source_probe_stop_offset_seconds": 30.0,
        "poll_interval_seconds": 0.05,
        "robot_motion": False,
        "provider_calls": 0,
    }
    for key, expected in expected_campaign.items():
        if campaign.get(key) != expected:
            raise AVFoundationLocalizationError(
                f"Frozen campaign field {key!r} does not match {expected!r}."
            )

    evaluator = contract.get("evaluator")
    if not isinstance(evaluator, dict):
        raise AVFoundationLocalizationError("Evaluator declaration is missing.")
    expected_evaluator = {
        "nominal_source_interval_seconds": 1.0 / 30.0,
        "large_source_interval_multiplier": 1.5,
        "boundary_window_seconds": 1.5,
        "maximum_non_monotonic_source_intervals": 0,
        "maximum_duplicate_source_pts": 0,
        "maximum_d405_source_stalls": 0,
        "require_all_trials_complete": True,
        "require_all_raw_artifacts_hash_bound": True,
        "source_attribution_requires_treatment_replication_count": 6,
        "source_continuity_does_not_prove_physical_exposure_continuity": True,
        "source_continuity_does_not_reclassify_sealed_container_result": True,
    }
    for key, expected in expected_evaluator.items():
        observed = evaluator.get(key)
        if isinstance(expected, float):
            if not isinstance(observed, (int, float)) or not math.isclose(
                float(observed), expected, rel_tol=0.0, abs_tol=1e-15
            ):
                raise AVFoundationLocalizationError(
                    f"Frozen evaluator field {key!r} changed."
                )
        elif observed != expected:
            raise AVFoundationLocalizationError(
                f"Frozen evaluator field {key!r} changed."
            )

    authority = contract.get("authority")
    if not isinstance(authority, dict) or any(bool(value) for value in authority.values()):
        raise AVFoundationLocalizationError(
            "Source-localization authority must remain closed."
        )
    return contract


def _runtime_identity(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    source_path: Path,
    runner_path: Path,
) -> dict[str, str]:
    declared = contract["runtime_identity"]
    swiftc = shutil.which("swiftc")
    if swiftc is None:
        raise AVFoundationLocalizationError("swiftc is unavailable.")
    if source_path.as_posix().endswith(declared["swift_source_path"]) is False:
        raise AVFoundationLocalizationError("Swift source path changed.")
    if runner_path.as_posix().endswith(declared["python_runner_path"]) is False:
        raise AVFoundationLocalizationError("Python runner path changed.")
    try:
        swift_version = subprocess.run(
            [swiftc, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10.0,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise AVFoundationLocalizationError(f"Could not identify swiftc: {error}") from error
    if declared["swift_version_prefix"] not in swift_version:
        raise AVFoundationLocalizationError("Swift compiler version changed.")

    observed: dict[str, str] = {
        "contract_sha256": _sha256_file(contract_path),
        "swift_source_sha256": _sha256_file(source_path),
        "python_runner_sha256": _sha256_file(runner_path),
        "swiftc_path": swiftc,
        "swiftc_sha256": _sha256_file(Path(swiftc)),
        "swift_version": swift_version,
    }
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if executable is None:
            raise AVFoundationLocalizationError(f"{name} is unavailable.")
        digest = _sha256_file(Path(executable))
        if digest != declared[f"{name}_executable_sha256"]:
            raise AVFoundationLocalizationError(f"{name} executable identity changed.")
        observed[f"{name}_path"] = executable
        observed[f"{name}_sha256"] = digest
    return observed


def compile_source_probe(
    *,
    contract_path: Path,
    source_path: Path,
    runner_path: Path,
    binary_path: Path,
) -> dict[str, str]:
    contract = load_source_localization_contract(contract_path)
    identity = _runtime_identity(
        contract=contract,
        contract_path=contract_path,
        source_path=source_path,
        runner_path=runner_path,
    )
    if binary_path.exists():
        raise AVFoundationLocalizationError(
            "Source-probe binary already exists; build substitution is forbidden."
        )
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        identity["swiftc_path"],
        "-O",
        str(source_path),
        "-o",
        str(binary_path),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AVFoundationLocalizationError(
            f"Could not compile source probe: {error}"
        ) from error
    if result.returncode != 0 or not binary_path.is_file():
        detail = (result.stderr or result.stdout).strip()
        raise AVFoundationLocalizationError(
            f"Source-probe compilation failed: {detail}"
        )
    identity["source_probe_binary_sha256"] = _sha256_file(binary_path)
    return identity


def parse_source_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AVFoundationLocalizationError(
            f"Could not read source events: {error}"
        ) from error
    if not lines:
        raise AVFoundationLocalizationError("Source event log is empty.")
    events: list[dict[str, Any]] = []
    prior_host_ns: int | None = None
    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise AVFoundationLocalizationError(
                f"Malformed source event at line {index + 1}: {error}"
            ) from error
        if event.get("schema_version") != SOURCE_EVENT_SCHEMA:
            raise AVFoundationLocalizationError("Source event schema changed.")
        if event.get("event_index") != index:
            raise AVFoundationLocalizationError("Source event index is not contiguous.")
        event_type = event.get("event_type")
        if event_type not in ALLOWED_SOURCE_EVENT_TYPES:
            raise AVFoundationLocalizationError(
                f"Unexpected source event type {event_type!r}."
            )
        host_ns = event.get("host_continuous_ns")
        if not isinstance(host_ns, int) or host_ns < 0:
            raise AVFoundationLocalizationError("Source host time is invalid.")
        if prior_host_ns is not None and host_ns < prior_host_ns:
            raise AVFoundationLocalizationError("Source host time is non-monotonic.")
        prior_host_ns = host_ns
        events.append(event)
    return events


def parse_orchestration_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AVFoundationLocalizationError(
            f"Could not read orchestration events: {error}"
        ) from error
    events: list[dict[str, Any]] = []
    prior_host_ns: int | None = None
    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise AVFoundationLocalizationError(
                f"Malformed orchestration event at line {index + 1}: {error}"
            ) from error
        if event.get("schema_version") != ORCHESTRATION_EVENT_SCHEMA:
            raise AVFoundationLocalizationError("Orchestration event schema changed.")
        if event.get("event_index") != index:
            raise AVFoundationLocalizationError(
                "Orchestration event index is not contiguous."
            )
        host_ns = event.get("host_continuous_ns")
        if not isinstance(host_ns, int) or host_ns < 0:
            raise AVFoundationLocalizationError("Orchestration host time is invalid.")
        if prior_host_ns is not None and host_ns < prior_host_ns:
            raise AVFoundationLocalizationError(
                "Orchestration host time is non-monotonic."
            )
        prior_host_ns = host_ns
        events.append(event)
    if not events:
        raise AVFoundationLocalizationError("Orchestration event log is empty.")
    return events


def _single_event(
    events: list[dict[str, Any]],
    event_type: str,
) -> dict[str, Any]:
    matches = [event for event in events if event.get("event_type") == event_type]
    if len(matches) != 1:
        raise AVFoundationLocalizationError(
            f"Expected exactly one {event_type!r} event; observed {len(matches)}."
        )
    return matches[0]


def summarize_source_events(
    *,
    source_events: list[dict[str, Any]],
    orchestration_events: list[dict[str, Any]],
    nominal_interval_seconds: float,
    large_interval_multiplier: float,
    boundary_window_seconds: float,
) -> dict[str, Any]:
    if source_events[0].get("event_type") != "probe_started":
        raise AVFoundationLocalizationError("Source log does not start with probe_started.")
    if source_events[-1].get("event_type") != "probe_finished":
        raise AVFoundationLocalizationError("Source log does not end with probe_finished.")
    _single_event(source_events, "session_start_returned")
    _single_event(source_events, "session_stop_returned")
    finished = _single_event(source_events, "probe_finished")
    samples = [
        event for event in source_events if event.get("event_type") == "sample_output"
    ]
    dropped = [
        event for event in source_events if event.get("event_type") == "sample_dropped"
    ]
    if not samples:
        raise AVFoundationLocalizationError("Source log contains no sample_output events.")
    if finished.get("sample_output_count") != len(samples):
        raise AVFoundationLocalizationError("Source sample count does not match footer.")
    if finished.get("sample_dropped_count") != len(dropped):
        raise AVFoundationLocalizationError("Dropped sample count does not match footer.")
    if finished.get("write_failure") is not None:
        raise AVFoundationLocalizationError("Source probe reported an output write failure.")

    pts: list[float] = []
    for event in samples:
        if event.get("sample_pts_valid") is not True:
            raise AVFoundationLocalizationError("Source sample PTS is invalid.")
        value = event.get("sample_pts_seconds")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise AVFoundationLocalizationError("Source sample PTS is non-finite.")
        pts.append(float(value))
    intervals = [current - prior for prior, current in zip(pts, pts[1:], strict=False)]
    non_monotonic = sum(interval < 0.0 for interval in intervals)
    duplicates = sum(interval == 0.0 for interval in intervals)
    threshold = nominal_interval_seconds * large_interval_multiplier

    start_marker = _single_event(orchestration_events, "lifecycle_start_requested")
    stop_marker = _single_event(orchestration_events, "lifecycle_stop_requested")
    boundary_ns = {
        "lifecycle_start_requested": int(start_marker["host_continuous_ns"]),
        "lifecycle_stop_requested": int(stop_marker["host_continuous_ns"]),
    }
    large_intervals: list[dict[str, Any]] = []
    for index, interval in enumerate(intervals, start=1):
        if interval <= threshold:
            continue
        prior_event = samples[index - 1]
        event = samples[index]
        midpoint_ns = (
            int(prior_event["host_continuous_ns"])
            + int(event["host_continuous_ns"])
        ) // 2
        nearest_name, nearest_ns = min(
            boundary_ns.items(),
            key=lambda item: abs(midpoint_ns - item[1]),
        )
        delta_seconds = (midpoint_ns - nearest_ns) / 1_000_000_000.0
        large_intervals.append(
            {
                "prior_sample_pts_seconds": pts[index - 1],
                "sample_pts_seconds": pts[index],
                "interval_seconds": interval,
                "nearest_boundary": nearest_name,
                "boundary_delta_seconds": delta_seconds,
                "within_boundary_window": abs(delta_seconds) <= boundary_window_seconds,
            }
        )

    dropped_rows: list[dict[str, Any]] = []
    for event in dropped:
        host_ns = int(event["host_continuous_ns"])
        nearest_name, nearest_ns = min(
            boundary_ns.items(),
            key=lambda item: abs(host_ns - item[1]),
        )
        delta_seconds = (host_ns - nearest_ns) / 1_000_000_000.0
        dropped_rows.append(
            {
                "drop_reason": event.get("drop_reason"),
                "drop_reason_info": event.get("drop_reason_info"),
                "nearest_boundary": nearest_name,
                "boundary_delta_seconds": delta_seconds,
                "within_boundary_window": abs(delta_seconds) <= boundary_window_seconds,
            }
        )

    device_disconnects = [
        event
        for event in source_events
        if event.get("event_type") == "device_disconnected"
    ]
    runtime_errors = [
        event
        for event in source_events
        if event.get("event_type") == "session_runtime_error"
    ]
    interruptions = [
        event
        for event in source_events
        if event.get("event_type") == "session_interrupted"
    ]
    interval_summary = {
        "minimum": min(intervals) if intervals else None,
        "median": statistics.median(intervals) if intervals else None,
        "maximum": max(intervals) if intervals else None,
    }
    return {
        "sample_output_count": len(samples),
        "sample_dropped_count": len(dropped),
        "first_source_pts_seconds": pts[0],
        "last_source_pts_seconds": pts[-1],
        "source_interval_seconds": interval_summary,
        "non_monotonic_source_interval_count": non_monotonic,
        "duplicate_source_pts_count": duplicates,
        "large_source_interval_count": len(large_intervals),
        "large_source_intervals": large_intervals,
        "boundary_aligned_large_source_interval_count": sum(
            row["within_boundary_window"] for row in large_intervals
        ),
        "dropped_samples": dropped_rows,
        "boundary_aligned_dropped_sample_count": sum(
            row["within_boundary_window"] for row in dropped_rows
        ),
        "device_disconnect_count": len(device_disconnects),
        "session_runtime_error_count": len(runtime_errors),
        "session_interruption_count": len(interruptions),
        "semantics": {
            "source_pts_is_cross_camera_exposure_clock": False,
            "host_time_is_cross_camera_exposure_clock": False,
            "source_continuity_proves_physical_exposure_continuity": False,
            "container_result_reclassified": False,
        },
    }


def _wait_until_ns(target_ns: int, *, process: subprocess.Popen[bytes]) -> None:
    while True:
        if process.poll() is not None:
            raise AVFoundationLocalizationError(
                "Source probe exited before a frozen lifecycle boundary."
            )
        remaining_ns = target_ns - _host_continuous_stamp()["host_continuous_ns"]
        if remaining_ns <= 0:
            return
        time.sleep(min(0.05, remaining_ns / 1_000_000_000.0))


def _wait_for_source_start(
    *,
    path: Path,
    process: subprocess.Popen[bytes],
    timeout_seconds: float = 8.0,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AVFoundationLocalizationError(
                "Source probe exited before session startup completed."
            )
        if path.is_file():
            try:
                events = parse_source_events(path)
            except AVFoundationLocalizationError:
                events = []
            starts = [
                event
                for event in events
                if event.get("event_type") == "session_start_returned"
            ]
            samples = [
                event for event in events if event.get("event_type") == "sample_output"
            ]
            if len(starts) == 1 and samples:
                return int(starts[0]["host_continuous_ns"])
        time.sleep(0.05)
    raise AVFoundationLocalizationError(
        "Source probe did not produce a running session and first sample in time."
    )


def _emit_orchestration(
    path: Path,
    events: list[dict[str, Any]],
    event_type: str,
    *,
    fields: dict[str, Any] | None = None,
) -> None:
    event = {
        "schema_version": ORCHESTRATION_EVENT_SCHEMA,
        "event_index": len(events),
        "event_type": event_type,
        "wall_time_utc": _utc_now(),
        **_host_continuous_stamp(),
        **(fields or {}),
    }
    _append_jsonl(path, event)
    events.append(event)


def run_source_localization_campaign(
    *,
    contract_path: Path,
    source_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Consume the fixed 12-trial no-motion source-localization campaign."""

    contract = load_source_localization_contract(contract_path)
    if output_root.exists():
        raise AVFoundationLocalizationError(
            "Campaign output already exists; retries and replacements are forbidden."
        )
    output_root.mkdir(parents=True)
    runner_path = Path(__file__).resolve()
    binary_path = output_root / "runtime" / "avfoundation-source-probe"
    runtime_identity = compile_source_probe(
        contract_path=contract_path,
        source_path=source_path,
        runner_path=runner_path,
        binary_path=binary_path,
    )
    runtime_identity["source_probe_binary_path"] = binary_path.relative_to(
        output_root
    ).as_posix()

    campaign_config = contract["campaign"]
    cameras = contract["cameras"]
    source_camera = cameras["source_probe"]
    duration_seconds = float(campaign_config["source_probe_duration_seconds"])
    start_offset_seconds = float(campaign_config["lifecycle_start_offset_seconds"])
    stop_offset_seconds = float(campaign_config["lifecycle_stop_offset_seconds"])
    entries: list[dict[str, Any]] = []

    for attempt_index, trial_id in enumerate(EXPECTED_TRIAL_ORDER, start=1):
        cell = "T" if trial_id.startswith("T") else "C"
        trial_root = output_root / "trials" / trial_id
        trial_root.mkdir(parents=True)
        source_event_path = trial_root / "c922_source_events.jsonl"
        orchestration_path = trial_root / "orchestration_events.jsonl"
        stderr_path = trial_root / "source_probe.stderr.log"
        command = [
            str(binary_path),
            "--camera-name",
            str(source_camera["name"]),
            "--width",
            str(source_camera["width"]),
            "--height",
            str(source_camera["height"]),
            "--fps",
            str(source_camera["fps"]),
            "--duration-seconds",
            str(duration_seconds),
            "--output",
            str(source_event_path),
        ]
        orchestration_events: list[dict[str, Any]] = []
        _emit_orchestration(
            orchestration_path,
            orchestration_events,
            "trial_started",
            fields={
                "trial_id": trial_id,
                "cell": cell,
                "robot_motion": False,
                "replacement": False,
            },
        )
        with stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                start_new_session=True,
            )

            d405_report: dict[str, Any] | None = None
            trial_error: str | None = None
            wrist: WristVideoRecorder | None = None
            try:
                session_started_ns = _wait_for_source_start(
                    path=source_event_path,
                    process=process,
                )
                lifecycle_start_ns = session_started_ns + int(
                    start_offset_seconds * 1_000_000_000
                )
                lifecycle_stop_ns = session_started_ns + int(
                    stop_offset_seconds * 1_000_000_000
                )
                _wait_until_ns(lifecycle_start_ns, process=process)
                _emit_orchestration(
                    orchestration_path,
                    orchestration_events,
                    "lifecycle_start_requested",
                    fields={"cell": cell, "intervention": "d405" if cell == "T" else "none"},
                )
                if cell == "T":
                    wrist = WristVideoRecorder(trial_root / "wrist_d405.mkv")
                    wrist.start()
                _emit_orchestration(
                    orchestration_path,
                    orchestration_events,
                    "lifecycle_start_returned",
                    fields={"cell": cell, "intervention": "d405" if cell == "T" else "none"},
                )
                _wait_until_ns(lifecycle_stop_ns, process=process)
                _emit_orchestration(
                    orchestration_path,
                    orchestration_events,
                    "lifecycle_stop_requested",
                    fields={"cell": cell, "intervention": "d405" if cell == "T" else "none"},
                )
                if wrist is not None:
                    d405_report = wrist.finish(
                        action_started_monotonic=None,
                        action_stopped_monotonic=None,
                        post_roll_seconds=0.0,
                    )
                    wrist = None
                _emit_orchestration(
                    orchestration_path,
                    orchestration_events,
                    "lifecycle_stop_returned",
                    fields={"cell": cell, "intervention": "d405" if cell == "T" else "none"},
                )
                process.wait(timeout=duration_seconds + 10.0)
                if process.returncode != 0:
                    raise AVFoundationLocalizationError(
                        f"Source probe returned {process.returncode}."
                    )
            except (
                AVFoundationLocalizationError,
                OverheadVideoError,
                OSError,
                subprocess.SubprocessError,
            ) as error:
                trial_error = f"{type(error).__name__}: {error}"
            finally:
                if wrist is not None:
                    try:
                        d405_report = wrist.finish(
                            action_started_monotonic=None,
                            action_stopped_monotonic=None,
                            post_roll_seconds=0.0,
                        )
                    except (OverheadVideoError, OSError) as error:
                        trial_error = trial_error or f"{type(error).__name__}: {error}"
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2.0)
                _emit_orchestration(
                    orchestration_path,
                    orchestration_events,
                    "trial_finished",
                    fields={
                        "trial_id": trial_id,
                        "cell": cell,
                        "source_probe_return_code": process.returncode,
                        "trial_error": trial_error,
                    },
                )

        d405_report_path: Path | None = None
        if d405_report is not None:
            d405_report_path = trial_root / "d405_report.json"
            _write_json(d405_report_path, d405_report)
        artifact_sha256: dict[str, str] = {}
        for path in sorted(trial_root.iterdir()):
            if path.is_file():
                artifact_sha256[path.name] = _sha256_file(path)
        trial = {
            "schema_version": TRIAL_SCHEMA,
            "trial_id": trial_id,
            "attempt_index": attempt_index,
            "cell": cell,
            "replacement": False,
            "robot_motion": False,
            "trial_error": trial_error,
            "source_probe_return_code": process.returncode,
            "source_event_path": source_event_path.name,
            "orchestration_event_path": orchestration_path.name,
            "d405_report_path": d405_report_path.name if d405_report_path else None,
            "artifact_sha256": artifact_sha256,
        }
        trial_path = trial_root / "trial.json"
        _write_json(trial_path, trial)
        entries.append(
            {
                "trial_id": trial_id,
                "attempt_index": attempt_index,
                "cell": cell,
                "trial_sha256": _sha256_file(trial_path),
            }
        )

    campaign = {
        "schema_version": CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "proof_class": "camera_source_lifecycle_localization",
        "runtime_identity": runtime_identity,
        "budget": {
            "required_trials": 12,
            "used_trials": len(entries),
            "control_trials": sum(row["cell"] == "C" for row in entries),
            "treatment_trials": sum(row["cell"] == "T" for row in entries),
            "replacement_trials_allowed": 0,
            "replacement_trials_used": 0,
            "robot_motion_trials": 0,
            "provider_calls": 0,
        },
        "trials": entries,
        "authority": contract["authority"],
    }
    _write_json(output_root / "campaign.json", campaign)
    return campaign


def _load_trial(campaign_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    trial_id = entry.get("trial_id")
    if not isinstance(trial_id, str) or "/" in trial_id or ".." in trial_id:
        raise AVFoundationLocalizationError("Unsafe or invalid trial ID.")
    trial_path = campaign_root / "trials" / trial_id / "trial.json"
    if not trial_path.is_file() or _sha256_file(trial_path) != entry.get("trial_sha256"):
        raise AVFoundationLocalizationError(f"Trial receipt mismatch for {trial_id}.")
    try:
        trial = json.loads(trial_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationLocalizationError(f"Could not load trial {trial_id}: {error}") from error
    if trial.get("schema_version") != TRIAL_SCHEMA or trial.get("trial_id") != trial_id:
        raise AVFoundationLocalizationError(f"Trial schema or identity changed for {trial_id}.")
    if trial.get("attempt_index") != entry.get("attempt_index"):
        raise AVFoundationLocalizationError(f"Trial order changed for {trial_id}.")
    if trial.get("cell") != entry.get("cell"):
        raise AVFoundationLocalizationError(f"Trial cell changed for {trial_id}.")
    if trial.get("replacement") is not False or trial.get("robot_motion") is not False:
        raise AVFoundationLocalizationError(f"Trial authority changed for {trial_id}.")
    root = trial_path.parent
    artifacts = trial.get("artifact_sha256")
    if not isinstance(artifacts, dict):
        raise AVFoundationLocalizationError(f"Trial artifacts missing for {trial_id}.")
    for name, digest in artifacts.items():
        path = root / name
        if not path.is_file() or _sha256_file(path) != digest:
            raise AVFoundationLocalizationError(
                f"Trial artifact mismatch for {trial_id}/{name}."
            )
    return trial


def evaluate_source_localization_campaign(
    *,
    contract_path: Path,
    campaign_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_source_localization_contract(contract_path)
    if output_root.exists():
        raise AVFoundationLocalizationError(
            "Evaluation output already exists; replay/substitution is forbidden."
        )
    campaign_path = campaign_root / "campaign.json"
    try:
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationLocalizationError(f"Could not load campaign: {error}") from error
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA:
        raise AVFoundationLocalizationError("Campaign schema changed.")
    contract_sha256 = _sha256_file(contract_path)
    if campaign.get("contract_sha256") != contract_sha256:
        raise AVFoundationLocalizationError("Campaign contract identity changed.")
    if campaign.get("authority") != contract["authority"]:
        raise AVFoundationLocalizationError("Campaign authority changed.")
    budget = campaign.get("budget")
    expected_budget = {
        "required_trials": 12,
        "used_trials": 12,
        "control_trials": 6,
        "treatment_trials": 6,
        "replacement_trials_allowed": 0,
        "replacement_trials_used": 0,
        "robot_motion_trials": 0,
        "provider_calls": 0,
    }
    if budget != expected_budget:
        raise AVFoundationLocalizationError("Campaign budget changed.")
    entries = campaign.get("trials")
    if not isinstance(entries, list) or len(entries) != 12:
        raise AVFoundationLocalizationError("Campaign must contain exactly 12 trials.")
    observed_ids = [entry.get("trial_id") for entry in entries]
    if observed_ids != EXPECTED_TRIAL_ORDER or len(set(observed_ids)) != 12:
        raise AVFoundationLocalizationError("Campaign trial order or uniqueness changed.")

    runtime = campaign.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise AVFoundationLocalizationError("Campaign runtime identity is missing.")
    binary_relative = runtime.get("source_probe_binary_path")
    if not isinstance(binary_relative, str) or binary_relative.startswith("/") or ".." in binary_relative:
        raise AVFoundationLocalizationError("Unsafe source-probe binary path.")
    binary_path = campaign_root / binary_relative
    if (
        not binary_path.is_file()
        or _sha256_file(binary_path) != runtime.get("source_probe_binary_sha256")
    ):
        raise AVFoundationLocalizationError("Source-probe binary identity changed.")
    source_path = Path(contract["runtime_identity"]["swift_source_path"])
    runner_path = Path(contract["runtime_identity"]["python_runner_path"])
    if (
        not source_path.is_file()
        or _sha256_file(source_path) != runtime.get("swift_source_sha256")
        or not runner_path.is_file()
        or _sha256_file(runner_path) != runtime.get("python_runner_sha256")
    ):
        raise AVFoundationLocalizationError("Source or runner identity changed.")

    evaluator = contract["evaluator"]
    rows: list[dict[str, Any]] = []
    incomplete_count = 0
    d405_stall_count = 0
    for entry in entries:
        trial = _load_trial(campaign_root, entry)
        trial_root = campaign_root / "trials" / trial["trial_id"]
        source_path_trial = trial_root / trial["source_event_path"]
        orchestration_path = trial_root / trial["orchestration_event_path"]
        source_events = parse_source_events(source_path_trial)
        orchestration_events = parse_orchestration_events(orchestration_path)
        summary = summarize_source_events(
            source_events=source_events,
            orchestration_events=orchestration_events,
            nominal_interval_seconds=float(
                evaluator["nominal_source_interval_seconds"]
            ),
            large_interval_multiplier=float(
                evaluator["large_source_interval_multiplier"]
            ),
            boundary_window_seconds=float(evaluator["boundary_window_seconds"]),
        )
        complete = (
            trial.get("trial_error") is None
            and trial.get("source_probe_return_code") == 0
        )
        if trial["cell"] == "T":
            report_name = trial.get("d405_report_path")
            if not isinstance(report_name, str):
                complete = False
            else:
                report = json.loads(
                    (trial_root / report_name).read_text(encoding="utf-8")
                )
                if report.get("source_stall_detected") is True:
                    d405_stall_count += 1
                if report.get("status") != "completed":
                    complete = False
        if not complete:
            incomplete_count += 1
        rows.append(
            {
                "trial_id": trial["trial_id"],
                "cell": trial["cell"],
                "complete": complete,
                "source": summary,
            }
        )

    control_rows = [row for row in rows if row["cell"] == "C"]
    treatment_rows = [row for row in rows if row["cell"] == "T"]
    treatment_source_discontinuity_count = sum(
        (
            row["source"]["boundary_aligned_large_source_interval_count"] > 0
            or any(
                "Discontinuity" in str(drop.get("drop_reason"))
                for drop in row["source"]["dropped_samples"]
                if drop["within_boundary_window"]
            )
        )
        for row in treatment_rows
    )
    treatment_late_or_buffer_count = sum(
        any(
            (
                "FrameWasLate" in str(drop.get("drop_reason"))
                or "OutOfBuffers" in str(drop.get("drop_reason"))
            )
            for drop in row["source"]["dropped_samples"]
            if drop["within_boundary_window"]
        )
        for row in treatment_rows
    )
    control_boundary_event_count = sum(
        (
            row["source"]["boundary_aligned_large_source_interval_count"]
            + row["source"]["boundary_aligned_dropped_sample_count"]
        )
        for row in control_rows
    )
    treatment_boundary_event_count = sum(
        (
            row["source"]["boundary_aligned_large_source_interval_count"]
            + row["source"]["boundary_aligned_dropped_sample_count"]
        )
        for row in treatment_rows
    )
    disconnect_count = sum(
        row["source"]["device_disconnect_count"] for row in rows
    )
    replication = int(evaluator["source_attribution_requires_treatment_replication_count"])
    if (
        incomplete_count > 0
        or d405_stall_count > int(evaluator["maximum_d405_source_stalls"])
        or disconnect_count > 0
    ):
        verdict = "prerequisite_abstention"
    elif (
        treatment_source_discontinuity_count == replication
        and control_boundary_event_count == 0
    ):
        verdict = "source_discontinuity_replicated"
    elif (
        treatment_late_or_buffer_count == replication
        and control_boundary_event_count == 0
    ):
        verdict = "client_lateness_or_buffer_pressure_replicated"
    elif treatment_boundary_event_count == 0 and control_boundary_event_count == 0:
        verdict = "source_continuous_under_d405_lifecycle"
    else:
        verdict = "inconclusive_or_mixed"

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha256,
        "campaign_sha256": _sha256_file(campaign_path),
        "proof_class": "camera_source_lifecycle_localization",
        "verdict": verdict,
        "trial_count": len(rows),
        "control_trial_count": len(control_rows),
        "treatment_trial_count": len(treatment_rows),
        "incomplete_trial_count": incomplete_count,
        "d405_source_stall_count": d405_stall_count,
        "device_disconnect_count": disconnect_count,
        "control_boundary_event_count": control_boundary_event_count,
        "treatment_boundary_event_count": treatment_boundary_event_count,
        "treatment_source_discontinuity_trial_count": treatment_source_discontinuity_count,
        "treatment_late_or_buffer_trial_count": treatment_late_or_buffer_count,
        "trials": rows,
        "claim_limits": {
            "physical_exposure_continuity": False,
            "cross_camera_exposure_synchronization": False,
            "metric_depth": False,
            "motion_capture_reliability": False,
            "simulator_calibration": False,
            "task_success": False,
            "sealed_container_result_reclassified": False,
        },
    }
    output_root.mkdir(parents=True)
    evaluation_path = output_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)

    raw_artifacts: dict[str, str] = {}
    for path in sorted(campaign_root.rglob("*")):
        if path.is_file():
            raw_artifacts[path.relative_to(campaign_root).as_posix()] = _sha256_file(
                path
            )
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": contract_sha256,
        "campaign_sha256": _sha256_file(campaign_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": "camera_source_lifecycle_localization",
        "verdict": verdict,
        "budget": expected_budget,
        "raw_artifact_sha256": raw_artifacts,
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
