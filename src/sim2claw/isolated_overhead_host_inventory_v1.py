"""One-shot, zero-session inventory for the isolated overhead-camera host."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)


CONTRACT_SHA256 = "10f4d01df62fc1f59b8efd46b61f4d19116966f17a18296c0e3ad5bb41623a7a"
PROOF_CLASS = "zero_session_isolated_overhead_host_and_device_inventory"
PRELAUNCH_SCHEMA = "sim2claw.isolated_overhead_host_inventory_prelaunch.v1"
ATTEMPT_SCHEMA = "sim2claw.isolated_overhead_host_inventory_attempt.v1"
RAW_SCHEMA = "sim2claw.isolated_overhead_host_inventory_observation.v1"
EVALUATION_SCHEMA = "sim2claw.isolated_overhead_host_inventory_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.isolated_overhead_host_inventory_receipt.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/isolated_overhead_host_inventory_v1.json"
)
DEFAULT_OBSERVED_ROOT = (
    REPO_ROOT / "outputs/isolated-overhead-host-inventory-v1/observed"
)
DEFAULT_EVALUATED_ROOT = (
    REPO_ROOT / "outputs/isolated-overhead-host-inventory-v1/evaluated"
)
SSH_PATH = Path("/usr/bin/ssh")
REMOTE_COMMAND = (
    "/bin/hostname && "
    "/usr/bin/sw_vers -productVersion && "
    "/usr/sbin/system_profiler "
    "SPCameraDataType SPUSBDataType -json -detailLevel mini"
)
SSH_ARGUMENTS = [
    str(SSH_PATH),
    "-oBatchMode=yes",
    "-oStrictHostKeyChecking=yes",
    "-oConnectTimeout=5",
    "-p22",
    "kelly@silicon.local",
    REMOTE_COMMAND,
]
USED_BUDGET = {
    "remote_inventory_observations_used": 1,
    "ssh_connection_attempts_used": 1,
    "capture_sessions_used": 0,
    "camera_frames_used": 0,
    "remote_files_written": 0,
    "retries_used": 0,
    "robot_motion_trials_used": 0,
    "simulator_replays_used": 0,
    "provider_calls_used": 0,
}
EXPECTED_AUTHORITY = {
    "remote_host_metadata_read": True,
    "remote_camera_metadata_read": True,
    "remote_file_write": False,
    "camera_session_start": False,
    "camera_frame_capture": False,
    "robot_gateway": False,
    "robot_motion": False,
    "metric_depth": False,
    "clock_synchronization": False,
    "cross_camera_exposure_synchronization": False,
    "simulator_replay": False,
    "simulator_parameter_promotion": False,
    "training": False,
    "provider_calls": False,
    "paid_compute": False,
    "task_score_change": False,
    "physical_task_authority": False,
}
RAW_KEYS = {
    "schema_version",
    "contract_sha256",
    "observer_role",
    "status",
    "failure_reason",
    "remote_endpoint",
    "remote_command_sha256",
    "ssh_return_code",
    "remote_hostname",
    "remote_macos_version",
    "system_profiler",
    "budget",
    "authority",
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AVFoundationFormatInventoryError(message)


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path, label="isolated-host inventory contract")
    _require(_sha256_file(path) == CONTRACT_SHA256, "Contract identity changed.")
    _require(
        contract.get("schema_version")
        == "sim2claw.isolated_overhead_host_inventory_contract.v1",
        "Contract schema changed.",
    )
    _require(
        contract.get("status")
        == "preregistered_before_implementation_or_remote_observation",
        "Contract status changed.",
    )
    endpoint = contract.get("remote_endpoint")
    _require(isinstance(endpoint, dict), "Remote endpoint is missing.")
    _require(
        endpoint
        == {
            "ssh_host": "silicon.local",
            "ssh_user": "kelly",
            "port": 22,
            "batch_mode": True,
            "strict_host_key_checking": True,
            "connect_timeout_seconds": 5,
            "connection_attempts_maximum": 1,
            "remote_shell_mutation_allowed": False,
            "remote_repo_access_required": False,
        },
        "Remote endpoint changed.",
    )
    observer = contract.get("observer")
    _require(isinstance(observer, dict), "Observer contract is missing.")
    _require(
        observer.get("allowed_programs")
        == ["/bin/hostname", "/usr/bin/sw_vers", "/usr/sbin/system_profiler"],
        "Remote program allowlist changed.",
    )
    _require(
        observer.get("system_profiler_data_types")
        == ["SPCameraDataType", "SPUSBDataType"],
        "System-profiler data types changed.",
    )
    _require(
        observer.get("capture_session_created") is False
        and observer.get("capture_session_started") is False
        and observer.get("camera_frames") == 0
        and observer.get("remote_files_written") == 0,
        "Zero-session observer contract changed.",
    )
    _require(
        contract.get("operation_budget")
        == {
            "remote_inventory_observations_maximum": 1,
            "ssh_connection_attempts_maximum": 1,
            "capture_sessions_maximum": 0,
            "camera_frames_maximum": 0,
            "remote_files_written_maximum": 0,
            "robot_motion_trials_maximum": 0,
            "simulator_replays_maximum": 0,
            "provider_calls_maximum": 0,
        },
        "Operation budget changed.",
    )
    _require(contract.get("authority") == EXPECTED_AUTHORITY, "Authority changed.")
    return contract


def _runtime_identity() -> dict[str, str]:
    module_path = Path(__file__).resolve()
    _require(SSH_PATH.is_file(), "SSH executable is unavailable.")
    return {
        "runner_evaluator_path": str(module_path),
        "runner_evaluator_sha256": _sha256_file(module_path),
        "ssh_path": str(SSH_PATH),
        "ssh_sha256": _sha256_file(SSH_PATH),
        "remote_command_sha256": _sha256_bytes(REMOTE_COMMAND.encode("utf-8")),
    }


def _parse_remote_stdout(stdout: bytes) -> tuple[str, str, dict[str, Any]]:
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AVFoundationFormatInventoryError(
            "Remote metadata is not UTF-8."
        ) from error
    lines = text.splitlines()
    _require(len(lines) >= 3, "Remote metadata is incomplete.")
    hostname = lines[0].strip()
    macos_version = lines[1].strip()
    _require(
        bool(hostname) and not any(char.isspace() for char in hostname),
        "Remote hostname is malformed.",
    )
    _require(
        re.fullmatch(r"\d+(?:\.\d+){1,2}", macos_version) is not None,
        "Remote macOS version is malformed.",
    )
    try:
        profiler = json.loads("\n".join(lines[2:]))
    except json.JSONDecodeError as error:
        raise AVFoundationFormatInventoryError(
            "System-profiler payload is malformed."
        ) from error
    _require(
        isinstance(profiler, dict),
        "System-profiler payload is not an object.",
    )
    _require(
        set(profiler) == {"SPCameraDataType", "SPUSBDataType"},
        "System-profiler data types changed.",
    )
    return hostname, macos_version, profiler


def run_observation(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_root: Path = DEFAULT_OBSERVED_ROOT,
) -> dict[str, Any]:
    """Perform the sole strict SSH metadata observation."""

    contract = load_contract(contract_path)
    _require(
        output_root.resolve() == DEFAULT_OBSERVED_ROOT.resolve(),
        "Observation requires the canonical output root.",
    )
    _require(
        not output_root.exists(),
        "Observation output already exists; replay is forbidden.",
    )
    raw_root = output_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=False)
    runtime = _runtime_identity()
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "status": "prepared_before_ssh_launch",
        "runtime_identity": runtime,
        "ssh_arguments": SSH_ARGUMENTS,
        "budget": USED_BUDGET,
        "authority": EXPECTED_AUTHORITY,
    }
    prelaunch_path = output_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    try:
        completed = subprocess.run(
            SSH_ARGUMENTS,
            check=False,
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, bytes) else b""
        stderr = error.stderr if isinstance(error.stderr, bytes) else b""
        completed = subprocess.CompletedProcess(
            SSH_ARGUMENTS,
            124,
            stdout=stdout,
            stderr=stderr + b"\nssh observation timed out\n",
        )
    except OSError as error:
        completed = subprocess.CompletedProcess(
            SSH_ARGUMENTS,
            127,
            stdout=b"",
            stderr=f"ssh launch failed: {type(error).__name__}\n".encode(),
        )
    _require(
        isinstance(completed.stdout, bytes) and isinstance(completed.stderr, bytes),
        "SSH runner did not return byte streams.",
    )
    stdout_path = raw_root / "ssh.stdout"
    stderr_path = raw_root / "ssh.stderr"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    status = "completed"
    failure_reason: str | None = None
    remote_hostname: str | None = None
    remote_macos_version: str | None = None
    system_profiler: dict[str, Any] | None = None
    if completed.returncode != 0:
        status = "prerequisite_unavailable"
        failure_reason = "ssh_command_failed"
    else:
        try:
            remote_hostname, remote_macos_version, system_profiler = (
                _parse_remote_stdout(completed.stdout)
            )
        except AVFoundationFormatInventoryError:
            status = "prerequisite_unavailable"
            failure_reason = "malformed_remote_metadata"
    raw = {
        "schema_version": RAW_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "observer_role": "remote_host_and_usb_camera_metadata_only",
        "status": status,
        "failure_reason": failure_reason,
        "remote_endpoint": "kelly@silicon.local:22",
        "remote_command_sha256": runtime["remote_command_sha256"],
        "ssh_return_code": completed.returncode,
        "remote_hostname": remote_hostname,
        "remote_macos_version": remote_macos_version,
        "system_profiler": system_profiler,
        "budget": USED_BUDGET,
        "authority": EXPECTED_AUTHORITY,
    }
    raw_path = raw_root / "observation.json"
    _write_json(raw_path, raw)
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "status": "ssh_observation_finished",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "ssh_arguments": SSH_ARGUMENTS,
        "return_code": completed.returncode,
        "stdout_sha256": _sha256_file(stdout_path),
        "stderr_sha256": _sha256_file(stderr_path),
        "raw_observation_sha256": _sha256_file(raw_path),
        "budget": USED_BUDGET,
        "authority": EXPECTED_AUTHORITY,
    }
    attempt_path = output_root / "attempt.json"
    _write_json(attempt_path, attempt)
    return {
        "prelaunch_path": str(prelaunch_path),
        "attempt_path": str(attempt_path),
        "raw_path": str(raw_path),
        "status": status,
    }


def _records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records(child)


def _normalize_hex_identifier(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    match = re.search(r"0x([0-9a-fA-F]+)", value)
    if match is not None:
        return int(match.group(1), 16)
    if value.strip().isdigit():
        return int(value.strip())
    return None


def _camera_name_match_count(payload: Any, name: str) -> int:
    return sum(
        1
        for record in _records(payload)
        if record.get("_name") == name
        or record.get("spcamera_model-id") == name
    )


def _usb_pair_match_count(payload: Any, vendor: int, product: int) -> int:
    count = 0
    for record in _records(payload):
        observed_vendor = _normalize_hex_identifier(
            record.get("vendor_id") or record.get("vendor-id")
        )
        observed_product = _normalize_hex_identifier(
            record.get("product_id") or record.get("product-id")
        )
        if observed_vendor == vendor and observed_product == product:
            count += 1
    return count


def _load_and_verify_manifests(
    observed_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    prelaunch_path = observed_root / "attempt-prelaunch.json"
    attempt_path = observed_root / "attempt.json"
    raw_path = observed_root / "raw/observation.json"
    prelaunch = _load_json(prelaunch_path, label="isolated-host prelaunch")
    attempt = _load_json(attempt_path, label="isolated-host attempt")
    raw = _load_json(raw_path, label="isolated-host raw observation")
    runtime = _runtime_identity()
    _require(prelaunch.get("schema_version") == PRELAUNCH_SCHEMA, "Prelaunch schema changed.")
    _require(attempt.get("schema_version") == ATTEMPT_SCHEMA, "Attempt schema changed.")
    _require(raw.get("schema_version") == RAW_SCHEMA, "Raw schema changed.")
    _require(set(raw) == RAW_KEYS, "Raw observation shape changed.")
    for payload, label in ((prelaunch, "Prelaunch"), (attempt, "Attempt"), (raw, "Raw")):
        _require(payload.get("contract_sha256") == CONTRACT_SHA256, f"{label} contract identity changed.")
        _require(payload.get("budget") == USED_BUDGET, f"{label} budget changed.")
        _require(payload.get("authority") == EXPECTED_AUTHORITY, f"{label} authority changed.")
    _require(prelaunch.get("runtime_identity") == runtime, "Prelaunch runtime identity changed.")
    _require(attempt.get("runtime_identity") == runtime, "Attempt runtime identity changed.")
    _require(prelaunch.get("ssh_arguments") == SSH_ARGUMENTS, "Prelaunch SSH command changed.")
    _require(attempt.get("ssh_arguments") == SSH_ARGUMENTS, "Attempt SSH command changed.")
    _require(
        attempt.get("prelaunch_manifest_sha256") == _sha256_file(prelaunch_path),
        "Prelaunch hash changed.",
    )
    _require(
        attempt.get("raw_observation_sha256") == _sha256_file(raw_path),
        "Raw observation hash changed.",
    )
    _require(
        attempt.get("stdout_sha256") == _sha256_file(observed_root / "raw/ssh.stdout")
        and attempt.get("stderr_sha256") == _sha256_file(observed_root / "raw/ssh.stderr"),
        "SSH stream hash changed.",
    )
    _require(
        raw.get("remote_command_sha256")
        == _sha256_bytes(REMOTE_COMMAND.encode("utf-8")),
        "Raw remote-command identity changed.",
    )
    return prelaunch, attempt, raw


def evaluate(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    observed_root: Path = DEFAULT_OBSERVED_ROOT,
    output_root: Path = DEFAULT_EVALUATED_ROOT,
) -> dict[str, Any]:
    """Independently evaluate the sole raw inventory."""

    contract = load_contract(contract_path)
    _require(
        observed_root.resolve() == DEFAULT_OBSERVED_ROOT.resolve(),
        "Evaluation requires the canonical observation root.",
    )
    _require(
        output_root.resolve() == DEFAULT_EVALUATED_ROOT.resolve(),
        "Evaluation requires the canonical output root.",
    )
    _require(
        not output_root.exists(),
        "Evaluation output already exists; replay is forbidden.",
    )
    _, attempt, raw = _load_and_verify_manifests(observed_root)
    failed_gates: list[str] = []
    target_camera_count = 0
    target_usb_count = 0
    excluded_camera_count = 0
    excluded_usb_count = 0
    if raw["status"] != "completed" or raw["ssh_return_code"] != 0:
        failed_gates.append("remote_metadata_available")
        verdict = "prerequisite_abstention"
    else:
        profiler = raw["system_profiler"]
        _require(isinstance(profiler, dict), "System-profiler payload is missing.")
        camera_payload = profiler["SPCameraDataType"]
        usb_payload = profiler["SPUSBDataType"]
        target = contract["target_device"]
        excluded = contract["excluded_device"]
        target_camera_count = _camera_name_match_count(
            camera_payload, target["exact_localized_name"]
        )
        target_usb_count = _usb_pair_match_count(
            usb_payload, target["usb_vendor_id"], target["usb_product_id"]
        )
        excluded_camera_count = _camera_name_match_count(
            camera_payload,
            "Intel(R) RealSense(TM) Depth Camera 405  Depth",
        )
        excluded_usb_count = _usb_pair_match_count(
            usb_payload, excluded["usb_vendor_id"], excluded["usb_product_id"]
        )
        if target_camera_count != 1:
            failed_gates.append("target_c922_camera_match_count")
        if target_usb_count != 1:
            failed_gates.append("target_c922_usb_match_count")
        if excluded_camera_count != 0:
            failed_gates.append("excluded_d405_camera_match_count")
        if excluded_usb_count != 0:
            failed_gates.append("excluded_d405_usb_match_count")
        if target_camera_count == 0 and target_usb_count == 0:
            verdict = "isolated_overhead_host_requires_c922_attachment"
        elif not failed_gates:
            verdict = "isolated_overhead_host_ready"
        else:
            verdict = "prerequisite_abstention"
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "failed_gates": failed_gates,
        "remote_hostname": raw["remote_hostname"],
        "remote_macos_version": raw["remote_macos_version"],
        "target_c922_camera_match_count": target_camera_count,
        "target_c922_usb_match_count": target_usb_count,
        "excluded_d405_camera_match_count": excluded_camera_count,
        "excluded_d405_usb_match_count": excluded_usb_count,
        "budget": USED_BUDGET,
        "authority": EXPECTED_AUTHORITY,
        "raw_observation_sha256": attempt["raw_observation_sha256"],
    }
    output_root.mkdir(parents=True, exist_ok=False)
    evaluation_path = output_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    evaluation_digest = _canonical_digest(evaluation)
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "failed_gates": failed_gates,
        "runner_evaluator_sha256": _runtime_identity()["runner_evaluator_sha256"],
        "ssh_sha256": _runtime_identity()["ssh_sha256"],
        "prelaunch_sha256": _sha256_file(observed_root / "attempt-prelaunch.json"),
        "attempt_sha256": _sha256_file(observed_root / "attempt.json"),
        "raw_observation_sha256": attempt["raw_observation_sha256"],
        "evaluation_sha256": _sha256_file(evaluation_path),
        "evaluation_digest": evaluation_digest,
        "budget": USED_BUDGET,
        "authority": EXPECTED_AUTHORITY,
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    receipt_path = output_root / "receipt.json"
    _write_json(receipt_path, receipt)
    return {
        "evaluation_path": str(evaluation_path),
        "receipt_path": str(receipt_path),
        "verdict": verdict,
        "failed_gates": failed_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    observe_parser.add_argument("--output-root", type=Path, default=DEFAULT_OBSERVED_ROOT)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    evaluate_parser.add_argument("--observed-root", type=Path, default=DEFAULT_OBSERVED_ROOT)
    evaluate_parser.add_argument("--output-root", type=Path, default=DEFAULT_EVALUATED_ROOT)
    args = parser.parse_args()
    if args.command == "observe":
        result = run_observation(
            contract_path=args.contract,
            output_root=args.output_root,
        )
    else:
        result = evaluate(
            contract_path=args.contract,
            observed_root=args.observed_root,
            output_root=args.output_root,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
