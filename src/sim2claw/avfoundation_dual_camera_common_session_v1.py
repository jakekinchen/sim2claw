"""Runner and independent evaluator for one native dual-camera session."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)


CONTRACT_SHA256 = "c2ad7c333e06affae037998318976931da638c5eec2806e769f9c2971f817af1"
OBSERVATION_SCHEMA = (
    "sim2claw.avfoundation_dual_camera_common_session_observation.v1"
)
PRELAUNCH_SCHEMA = (
    "sim2claw.avfoundation_dual_camera_common_session_prelaunch.v1"
)
ATTEMPT_SCHEMA = "sim2claw.avfoundation_dual_camera_common_session_attempt.v1"
EVALUATION_SCHEMA = (
    "sim2claw.avfoundation_dual_camera_common_session_evaluation.v1"
)
RECEIPT_SCHEMA = "sim2claw.avfoundation_dual_camera_common_session_receipt.v1"
PROOF_CLASS = "stationary_native_dual_camera_common_session_callback_health"
CANONICAL_OBSERVATION_ROOT = Path(
    "outputs/avfoundation-dual-camera-common-session-v1/observed"
)
BINARY_RELATIVE = "runtime/avfoundation-dual-camera-common-session-v1"
USED_BUDGET = {
    "observation_attempts_used": 1,
    "common_capture_sessions_used": 1,
    "independent_camera_sessions_used": 0,
    "replacement_attempts_used": 0,
    "retries_used": 0,
    "robot_motion_trials_used": 0,
    "simulator_replays_used": 0,
    "provider_calls_used": 0,
}
RAW_KEYS = {
    "schema_version",
    "contract_sha256",
    "observer_role",
    "status",
    "failure_reason",
    "detected_device_names",
    "d405_match_count",
    "c922_match_count",
    "common_capture_sessions_used",
    "independent_camera_sessions_used",
    "robot_motion_trials_used",
    "simulator_replays_used",
    "provider_calls_used",
    "duration_seconds_requested",
    "maximum_callbacks",
    "d405_output_count",
    "d405_drop_count",
    "c922_output_count",
    "c922_drop_count",
    "stages",
    "events",
}
EVENT_KEYS = {
    "event_index",
    "role",
    "kind",
    "sequence",
    "host_continuous_ns",
    "pts_seconds",
    "duration_seconds",
    "width",
    "height",
    "subtype",
    "connection_enabled",
    "connection_active",
    "drop_reason",
}
STAGE_KEYS = {
    "name",
    "session_running",
    "d405_input_admitted",
    "c922_input_admitted",
    "d405_output_admitted",
    "c922_output_admitted",
    "d405",
    "c922",
}
FORMAT_KEYS = {
    "role",
    "localized_name",
    "unique_id",
    "model_id",
    "format_index",
    "range_index",
    "width",
    "height",
    "subtype",
    "minimum_duration_seconds",
    "maximum_duration_seconds",
}


def _error(message: str) -> AVFoundationFormatInventoryError:
    return AVFoundationFormatInventoryError(message)


def load_contract(path: Path) -> dict[str, Any]:
    if _sha256_file(path) != CONTRACT_SHA256:
        raise _error("Common-session contract identity changed.")
    contract = _load_json(path, label="common-session contract")
    if (
        contract.get("schema_version")
        != "sim2claw.avfoundation_dual_camera_common_session_contract.v1"
        or contract.get("status") != "preregistered_before_implementation"
    ):
        raise _error("Common-session contract state changed.")
    return contract


def compile_observer(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    binary_path: Path,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    runtime = contract["runtime_identity"]
    if Path(runtime["observer_source_path"]) != source_path:
        raise _error("Common-session source path changed.")
    if Path(runtime["evaluator_path"]) != evaluator_path:
        raise _error("Common-session evaluator path changed.")
    compiler = Path(runtime["compiler_path"])
    version = subprocess.run(
        [str(compiler), "--version"], capture_output=True, text=True, check=False
    )
    if (
        not compiler.is_file()
        or version.returncode != 0
        or not version.stdout.startswith(runtime["swift_version_prefix"])
    ):
        raise _error("Common-session compiler identity changed.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    built = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if built.returncode != 0:
        raise _error(f"Common-session Swift compilation failed: {built.stderr}")
    return {
        "contract_sha256": CONTRACT_SHA256,
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256_file(compiler),
        "swift_version": version.stdout.strip(),
        "binary_path": BINARY_RELATIVE,
        "binary_sha256": _sha256_file(binary_path),
    }


def run_observation(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    if output_root.resolve() != CANONICAL_OBSERVATION_ROOT.resolve():
        raise _error("Common-session observation root is not authorized.")
    if output_root.exists():
        raise _error("Common-session observation output exists; replay forbidden.")
    runtime = compile_observer(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=output_root / BINARY_RELATIVE,
    )
    raw = output_root / "raw/observation.json"
    stderr = output_root / "raw/observer.stderr.log"
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_observation_path": "raw/observation.json",
        "stderr_path": "raw/observer.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = output_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    args = [str(output_root / BINARY_RELATIVE)]
    for role in ("d405", "c922"):
        device = contract["devices"][role]
        prefix = f"--{role}"
        args += [
            f"{prefix}-name",
            device["exact_localized_name"],
            f"{prefix}-unique-id",
            device["exact_unique_id"],
            f"{prefix}-model-id",
            device["exact_model_id"],
            f"{prefix}-format-index",
            str(device["format_index"]),
            f"{prefix}-range-index",
            str(device["frame_rate_range_index"]),
            f"{prefix}-width",
            str(device["width"]),
            f"{prefix}-height",
            str(device["height"]),
            f"{prefix}-subtype",
            device["media_subtype_fourcc"],
            f"{prefix}-fps",
            str(device["supported_fps"]),
        ]
    args += [
        "--duration-seconds",
        str(contract["windowing"]["full_session_seconds"]),
        "--maximum-callbacks",
        str(contract["windowing"]["maximum_callbacks_total"]),
        "--contract-sha256",
        CONTRACT_SHA256,
        "--output",
        str(raw),
    ]
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=contract["windowing"]["full_session_seconds"] + 20.0,
        )
    except subprocess.TimeoutExpired as error:
        captured = error.stderr
        if isinstance(captured, bytes):
            captured = captured.decode("utf-8", errors="replace")
        completed = subprocess.CompletedProcess(
            args=args,
            returncode=-9,
            stdout="",
            stderr=(captured or "") + "observer_timeout\n",
        )
    stderr.parent.mkdir(parents=True, exist_ok=True)
    stderr.write_text(completed.stderr, encoding="utf-8")
    raw_available = raw.is_file()
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "status": (
            "observer_completed_with_raw"
            if raw_available
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": completed.returncode,
        "raw_observation_path": "raw/observation.json",
        "raw_observation_sha256": _sha256_file(raw) if raw_available else None,
        "stderr_path": "raw/observer.stderr.log",
        "stderr_sha256": _sha256_file(stderr),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write_json(output_root / "attempt.json", attempt)
    return attempt


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(f"{label} is not numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise _error(f"{label} is non-finite.")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _error(f"{label} is not an integer.")
    return value


def _verify_runtime(
    contract: dict[str, Any], root: Path, runtime: dict[str, Any]
) -> None:
    source = Path(contract["runtime_identity"]["observer_source_path"])
    evaluator = Path(contract["runtime_identity"]["evaluator_path"])
    compiler = Path(contract["runtime_identity"]["compiler_path"])
    binary = root / BINARY_RELATIVE
    if (
        runtime.get("contract_sha256") != CONTRACT_SHA256
        or runtime.get("binary_path") != BINARY_RELATIVE
        or _sha256_file(source) != runtime.get("source_sha256")
        or _sha256_file(evaluator) != runtime.get("evaluator_sha256")
        or runtime.get("compiler_path") != str(compiler)
        or _sha256_file(compiler) != runtime.get("compiler_sha256")
        or _sha256_file(binary) != runtime.get("binary_sha256")
    ):
        raise _error("Common-session runtime identity changed.")


def _validate_manifest(
    contract: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    prelaunch_path = root / "attempt-prelaunch.json"
    attempt_path = root / "attempt.json"
    prelaunch = _load_json(prelaunch_path, label="common-session prelaunch")
    attempt = _load_json(attempt_path, label="common-session attempt")
    if (
        prelaunch.get("schema_version") != PRELAUNCH_SCHEMA
        or prelaunch.get("status") != "prepared_before_observer_launch"
        or prelaunch.get("raw_observation_path") != "raw/observation.json"
        or prelaunch.get("stderr_path") != "raw/observer.stderr.log"
    ):
        raise _error("Common-session prelaunch state changed.")
    if attempt.get("schema_version") != ATTEMPT_SCHEMA:
        raise _error("Common-session attempt schema changed.")
    for payload in (prelaunch, attempt):
        if (
            payload.get("contract_id") != contract["contract_id"]
            or payload.get("contract_sha256") != CONTRACT_SHA256
            or payload.get("proof_class") != PROOF_CLASS
            or payload.get("budget") != USED_BUDGET
            or payload.get("authority") != contract["authority"]
        ):
            raise _error("Common-session manifest identity or budget changed.")
    if (
        attempt.get("prelaunch_manifest_path") != "attempt-prelaunch.json"
        or attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path)
        or attempt.get("runtime_identity") != prelaunch.get("runtime_identity")
    ):
        raise _error("Common-session prelaunch binding changed.")
    runtime = attempt.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise _error("Common-session runtime identity missing.")
    _verify_runtime(contract, root, runtime)
    stderr = root / "raw/observer.stderr.log"
    if (
        attempt.get("stderr_path") != "raw/observer.stderr.log"
        or _sha256_file(stderr) != attempt.get("stderr_sha256")
    ):
        raise _error("Common-session stderr identity changed.")
    raw = root / "raw/observation.json"
    available = raw.is_file()
    if (
        attempt.get("raw_observation_path") != "raw/observation.json"
        or attempt.get("status")
        != (
            "observer_completed_with_raw"
            if available
            else "observer_failed_without_raw"
        )
        or (available and _sha256_file(raw) != attempt.get("raw_observation_sha256"))
        or (not available and attempt.get("raw_observation_sha256") is not None)
    ):
        raise _error("Common-session raw identity changed.")
    _integer(attempt.get("return_code"), "observer return code")
    return prelaunch, attempt, raw, stderr


def _validate_stage(
    stage: object, contract: dict[str, Any], expected_name: str
) -> list[str]:
    if (
        not isinstance(stage, dict)
        or set(stage) != STAGE_KEYS
        or stage.get("name") != expected_name
    ):
        raise _error("Common-session stage order changed.")
    failures: list[str] = []
    expected_running = expected_name == "after_start"
    if stage.get("session_running") is not expected_running:
        failures.append(f"{expected_name}:session_running")
    for flag in (
        "d405_input_admitted",
        "c922_input_admitted",
        "d405_output_admitted",
        "c922_output_admitted",
    ):
        if stage.get(flag) is not True:
            failures.append(f"{expected_name}:{flag}")
    for role in ("d405", "c922"):
        row = stage.get(role)
        expected = contract["devices"][role]
        if not isinstance(row, dict) or set(row) != FORMAT_KEYS:
            failures.append(f"{expected_name}:{role}_format_missing")
            continue
        duration = expected["frame_duration_seconds"]
        checks = {
            "localized_name": expected["exact_localized_name"],
            "unique_id": expected["exact_unique_id"],
            "model_id": expected["exact_model_id"],
            "format_index": expected["format_index"],
            "range_index": expected["frame_rate_range_index"],
            "width": expected["width"],
            "height": expected["height"],
            "subtype": expected["media_subtype_fourcc"],
        }
        for key, value in checks.items():
            if row.get(key) != value:
                failures.append(f"{expected_name}:{role}_{key}")
        for key in ("minimum_duration_seconds", "maximum_duration_seconds"):
            if abs(_finite(row.get(key), f"{role} {key}") - duration) > 1e-9:
                failures.append(f"{expected_name}:{role}_{key}")
    return failures


def _stream_metrics(
    events: list[dict[str, Any]], role: str, contract: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    expected = contract["devices"][role]
    output = [row for row in events if row["role"] == role and row["kind"] == "output"]
    drops = [row for row in events if row["role"] == role and row["kind"] == "drop"]
    failures: list[str] = []
    pts = [_finite(row.get("pts_seconds"), f"{role} PTS") for row in output]
    if any(b <= a for a, b in zip(pts, pts[1:])):
        failures.append(f"{role}:pts_not_strictly_increasing")
    for row in output + drops:
        if (
            row.get("width") != expected["width"]
            or row.get("height") != expected["height"]
            or row.get("subtype") != expected["media_subtype_fourcc"]
            or row.get("connection_enabled") is not True
            or row.get("connection_active") is not True
        ):
            failures.append(f"{role}:callback_format_or_connection")
            break
    if drops:
        failures.append(f"{role}:drop_callbacks")
    warmup = contract["windowing"]["visible_source_pts_warmup_seconds_per_stream"]
    measurement = (
        [row for row, value in zip(output, pts) if pts and value >= pts[0] + warmup]
        if pts
        else []
    )
    measurement_pts = [
        _finite(row["pts_seconds"], f"{role} measurement PTS") for row in measurement
    ]
    intervals = [b - a for a, b in zip(measurement_pts, measurement_pts[1:])]
    maximum = max(intervals) if intervals else None
    gates = contract["evaluator"]
    minimum_count = gates[f"minimum_{role}_measurement_callbacks"]
    if len(measurement) < minimum_count:
        failures.append(f"{role}:measurement_callback_count")
    if maximum is None or maximum > gates[
        f"maximum_{role}_measurement_pts_interval_seconds"
    ]:
        failures.append(f"{role}:measurement_interval")
    return {
        "output_count": len(output),
        "drop_count": len(drops),
        "measurement_output_count": len(measurement),
        "measurement_pts_span_seconds": (
            measurement_pts[-1] - measurement_pts[0]
            if len(measurement_pts) >= 2
            else None
        ),
        "maximum_measurement_pts_interval_seconds": maximum,
        "measurement_first_host_ns": (
            measurement[0]["host_continuous_ns"] if measurement else None
        ),
        "measurement_last_host_ns": (
            measurement[-1]["host_continuous_ns"] if measurement else None
        ),
    }, failures


def evaluate(
    *, contract_path: Path, observation_root: Path, output_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_contract(contract_path)
    if output_root.exists():
        raise _error("Common-session evaluation output exists; replay forbidden.")
    prelaunch, attempt, raw_path, stderr = _validate_manifest(
        contract, observation_root
    )
    return_code = attempt["return_code"]
    raw_available = raw_path.is_file()
    failed_gates: list[str] = []
    metrics: dict[str, Any] = {}
    if not raw_available:
        if return_code == 0:
            raise _error("Successful common-session attempt lacks raw output.")
        verdict = "prerequisite_abstention"
    else:
        raw = _load_json(raw_path, label="common-session raw observation")
        if set(raw) != RAW_KEYS:
            raise _error("Common-session raw schema or self-score surface changed.")
        if (
            raw.get("schema_version") != OBSERVATION_SCHEMA
            or raw.get("contract_sha256") != CONTRACT_SHA256
            or raw.get("observer_role")
            != "dual_camera_common_session_callback_observer_only"
        ):
            raise _error("Common-session raw identity changed.")
        detected = raw.get("detected_device_names")
        if (
            not isinstance(detected, list)
            or detected != sorted(detected)
            or any(not isinstance(name, str) for name in detected)
        ):
            raise _error("Common-session detected-device inventory malformed.")
        for role in ("d405", "c922"):
            count = _integer(raw.get(f"{role}_match_count"), f"{role} match count")
            if detected.count(contract["devices"][role]["exact_localized_name"]) != count:
                raise _error(f"Common-session {role} match count contradicts inventory.")
        for key in (
            "common_capture_sessions_used",
            "independent_camera_sessions_used",
            "robot_motion_trials_used",
            "simulator_replays_used",
            "provider_calls_used",
            "d405_output_count",
            "d405_drop_count",
            "c922_output_count",
            "c922_drop_count",
        ):
            if _integer(raw.get(key), key) < 0:
                raise _error(f"Common-session {key} is negative.")
        if raw["independent_camera_sessions_used"] != 0:
            raise _error("Observer used an independent camera session.")
        if any(raw[key] != 0 for key in (
            "robot_motion_trials_used",
            "simulator_replays_used",
            "provider_calls_used",
        )):
            raise _error("Observer widened authority.")
        if raw.get("status") == "prerequisite_unavailable":
            if (
                return_code != 2
                or raw.get("failure_reason")
                != "c922_second_video_input_not_admitted"
                or raw["common_capture_sessions_used"] != 0
                or raw["stages"] != []
                or raw["events"] != []
                or any(raw[key] != 0 for key in (
                    "d405_output_count",
                    "d405_drop_count",
                    "c922_output_count",
                    "c922_drop_count",
                ))
            ):
                raise _error("Common-session abstention payload is malformed.")
            verdict = "prerequisite_abstention"
        elif raw.get("status") == "completed":
            if return_code != 0 or raw.get("failure_reason") is not None:
                raise _error("Common-session completed payload contradicts attempt.")
            if raw["common_capture_sessions_used"] != 1:
                raise _error("Common-session count changed.")
            if (
                _finite(
                    raw.get("duration_seconds_requested"),
                    "requested duration",
                )
                != contract["windowing"]["full_session_seconds"]
                or _integer(raw.get("maximum_callbacks"), "maximum callbacks")
                != contract["windowing"]["maximum_callbacks_total"]
            ):
                raise _error("Common-session requested window or budget changed.")
            events = raw.get("events")
            stages = raw.get("stages")
            if not isinstance(events, list) or not isinstance(stages, list):
                raise _error("Common-session events or stages malformed.")
            if len(stages) != 4:
                raise _error("Common-session stage count changed.")
            if len(events) > contract["windowing"]["maximum_callbacks_total"]:
                raise _error("Common-session callback budget exceeded.")
            sequences: dict[tuple[str, str], int] = {}
            previous_host = -1
            for index, row in enumerate(events):
                if (
                    not isinstance(row, dict)
                    or set(row) != EVENT_KEYS
                    or row.get("event_index") != index
                    or row.get("role") not in {"d405", "c922"}
                    or row.get("kind") not in {"output", "drop"}
                ):
                    raise _error("Common-session callback schema changed.")
                key = (row["role"], row["kind"])
                sequences[key] = sequences.get(key, 0) + 1
                if _integer(row.get("sequence"), "callback sequence") != sequences[key]:
                    raise _error("Common-session callback sequence changed.")
                host = _integer(row.get("host_continuous_ns"), "callback host time")
                if host < previous_host:
                    raise _error("Common-session callback host time regressed.")
                previous_host = host
                _finite(row.get("pts_seconds"), "callback PTS")
                _finite(row.get("duration_seconds"), "callback duration")
            for name, stage in zip(
                ("before_commit", "after_commit", "after_start", "after_stop"),
                stages,
                strict=True,
            ):
                failed_gates += _validate_stage(stage, contract, name)
            d405, d_fail = _stream_metrics(events, "d405", contract)
            c922, c_fail = _stream_metrics(events, "c922", contract)
            failed_gates += d_fail + c_fail
            metrics = {"d405": d405, "c922": c922}
            for role, result in metrics.items():
                if (
                    raw[f"{role}_output_count"] != result["output_count"]
                    or raw[f"{role}_drop_count"] != result["drop_count"]
                ):
                    raise _error(f"Common-session {role} callback accounting changed.")
            starts = [d405["measurement_first_host_ns"], c922["measurement_first_host_ns"]]
            stops = [d405["measurement_last_host_ns"], c922["measurement_last_host_ns"]]
            common_span = (
                (min(stops) - max(starts)) / 1e9
                if all(value is not None for value in starts + stops)
                else None
            )
            metrics["common_host_window_seconds"] = common_span
            if (
                common_span is None
                or common_span < contract["evaluator"]["minimum_common_host_window_seconds"]
            ):
                failed_gates.append("common_host_window")
            verdict = (
                "common_session_callback_delivery_verified"
                if not failed_gates
                else "common_session_callback_delivery_degraded"
            )
        else:
            raise _error("Common-session observer status changed.")
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "failed_gates": sorted(set(failed_gates)),
        "metrics": metrics,
        "observer_return_code": return_code,
        "raw_observation_sha256": _sha256_file(raw_path) if raw_available else None,
        "attempt_manifest_sha256": _sha256_file(observation_root / "attempt.json"),
        "prelaunch_manifest_sha256": _sha256_file(
            observation_root / "attempt-prelaunch.json"
        ),
        "budget": attempt["budget"],
        "claim_limits": contract["claim_limits"],
    }
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    runtime = attempt["runtime_identity"]
    receipt_base = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "source_sha256": runtime["source_sha256"],
        "evaluator_sha256": runtime["evaluator_sha256"],
        "compiler_sha256": runtime["compiler_sha256"],
        "binary_sha256": runtime["binary_sha256"],
        "prelaunch_manifest_sha256": _sha256_file(
            observation_root / "attempt-prelaunch.json"
        ),
        "attempt_manifest_sha256": _sha256_file(observation_root / "attempt.json"),
        "raw_observation_sha256": _sha256_file(raw_path) if raw_available else None,
        "stderr_sha256": _sha256_file(stderr),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "budget": attempt["budget"],
        "authority": contract["authority"],
    }
    receipt = {**receipt_base, "receipt_digest": _canonical_digest(receipt_base)}
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
