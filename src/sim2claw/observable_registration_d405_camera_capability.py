"""Compile and consume the bounded OR45L camera-only capability lease."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path
from .observable_registration_d405_static_metric_capture import (
    run_d405_static_metric_capture_once,
)


SCHEMA = "sim2claw.observable_registration_d405_camera_capability_contract.v1"
LEASE_SCHEMA = "sim2claw.observable_registration_d405_camera_capability_lease.v1"
CONSUMPTION_SCHEMA = (
    "sim2claw.observable_registration_d405_camera_capability_consumption.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_d405_camera_capability_v1.json"
)
CAPABILITY_OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_d405_camera_capability_v1"
)
LEASE_PATH = CAPABILITY_OUTPUT_DIRECTORY / "lease.json"
GRAPH_PATH = REPO_ROOT / "configs/sail/observable_registration_current_graph_v1.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(result.returncode == 0, f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def _repository_state(root: Path) -> dict[str, object]:
    return {
        "head": _git(root, "rev-parse", "HEAD"),
        "remote_head": _git(root, "rev-parse", "origin/main"),
        "branch": _git(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git(root, "status", "--porcelain")),
    }


def _require_clean_synchronized_main(state: dict[str, object]) -> None:
    _require(state["branch"] == "main", "repository branch is not main")
    _require(state["worktree_clean"] is True, "repository worktree is not clean")
    _require(
        state["head"] == state["remote_head"],
        "repository HEAD is not synchronized with origin/main",
    )


def _persistent_graph(root: Path) -> dict[str, Any]:
    graph = load_json_object(
        root / "configs/sail/observable_registration_current_graph_v1.json",
        label="OR45L campaign graph",
    )
    _require(graph.get("active_card") == "OR45L", "OR45L is not active")
    authority = graph.get("authority")
    _require(isinstance(authority, dict), "campaign authority is missing")
    _require(not any(authority.values()), "persistent campaign authority widened")
    return graph


def load_d405_camera_capability_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR45L camera capability")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    lease = contract["lease"]
    _require(lease["sdk_serial_allowlist"] == ["130322273474"], "serial widened")
    _require(
        (lease["frame_count"], lease["width"], lease["height"], lease["fps"])
        == (30, 424, 240, 30),
        "OR45L capture geometry drifted",
    )
    _require(
        lease["stream"] == "depth" and lease["format"] == "Z16",
        "OR45L stream drifted",
    )
    _require(lease["maximum_invocations"] == 1, "invocation count widened")
    _require(
        lease["adaptive_retry_allowed"] is False,
        "adaptive retry boundary widened",
    )
    _require(lease["maximum_lease_seconds"] == 300, "lease duration widened")
    _require(
        not any(contract["persistent_campaign_authority_required"].values()),
        "persistent authority requirement widened",
    )
    scope = contract["capability_scope"]
    _require(
        scope["camera_device_enumeration"] is True
        and scope["camera_stream_start"] is True
        and scope["camera_frames"] == 30
        and scope["camera_stream_stop"] is True,
        "camera-only scope is incomplete",
    )
    forbidden = (
        "serial",
        "gateway",
        "torque",
        "robot_motion",
        "object_interaction",
        "physical_task_attempt",
        "simulator_replay",
        "transfer_claim",
    )
    _require(not any(scope[name] for name in forbidden), "non-camera scope widened")
    return contract


def _verified_recorder(root: Path, contract: dict[str, Any]) -> tuple[Path, str]:
    closeout_binding = contract["sources"]["or44_closeout"]
    closeout = load_json_object(
        root / closeout_binding["path"], label="OR44 closeout"
    )
    binary = (
        root
        / "outputs/observable_registration_d405_metric_sidecar_v1"
        / "RealSenseD405MetricRecorder"
    )
    _require(binary.is_file(), "OR44 recorder binary is missing")
    expected = closeout["result"]["binary_sha256"]
    _require(_sha256(binary) == expected, "OR44 recorder binary drifted")
    return binary, expected


def _device_identity(root: Path, contract: dict[str, Any]) -> dict[str, str]:
    binding = contract["sources"]["device_identity"]
    identity_contract = load_json_object(
        root / binding["path"], label="D405 device identity"
    )
    expected = identity_contract["d405"]["expected_device"]
    sdk_serial = str(expected["sdk_serial_number"])
    _require(
        sdk_serial in contract["lease"]["sdk_serial_allowlist"],
        "D405 SDK serial is outside the lease allowlist",
    )
    return {
        "name": str(expected["name"]),
        "sdk_serial": sdk_serial,
        "asic_serial": str(expected["asic_serial_number"]),
        "usb_product_id_hex": str(expected["usb_product_id_hex"]),
    }


def compile_d405_camera_capability_lease(
    lease_path: Path = LEASE_PATH,
    *,
    contract_path: Path = CONTRACT_PATH,
    root: Path = REPO_ROOT,
    now_unix_ns: int | None = None,
) -> dict[str, Any]:
    """Mint a five-minute lease without opening or enumerating a camera."""

    _require(not lease_path.exists(), "OR45L lease already exists")
    state = _repository_state(root)
    _require_clean_synchronized_main(state)
    graph = _persistent_graph(root)
    contract = load_d405_camera_capability_contract(contract_path, root=root)
    binary, binary_sha256 = _verified_recorder(root, contract)
    device = _device_identity(root, contract)
    output_directory = root / contract["lease"]["output_directory"]
    _require(not output_directory.exists(), "OR45 capture output already exists")
    issued = time.time_ns() if now_unix_ns is None else now_unix_ns
    expires = issued + contract["lease"]["maximum_lease_seconds"] * 1_000_000_000
    prefix = output_directory / "capture"
    arguments = [
        "--output-prefix",
        str(prefix),
        "--serial",
        device["sdk_serial"],
        "--frames",
        "30",
        "--width",
        "424",
        "--height",
        "240",
        "--fps",
        "30",
    ]
    lease = {
        "schema_version": LEASE_SCHEMA,
        "capability_id": contract["capability_id"],
        "proof_class": contract["proof_class"],
        "issued_unix_ns": issued,
        "expires_unix_ns": expires,
        "repository": state,
        "campaign": {
            "id": graph["campaign_id"],
            "active_card": graph["active_card"],
            "persistent_authority": graph["authority"],
        },
        "contract": {
            "path": str(contract_path.relative_to(root)),
            "sha256": _sha256(contract_path),
        },
        "recorder": {
            "path": str(binary.relative_to(root)),
            "binary_sha256": binary_sha256,
        },
        "device": device,
        "arguments": arguments,
        "output_directory": contract["lease"]["output_directory"],
        "invocation": {
            "maximum_invocations": 1,
            "adaptive_retry_allowed": False,
        },
        "capability_scope": contract["capability_scope"],
    }
    lease["artifact_sha256"] = canonical_digest(lease)
    atomic_write_json(lease_path, lease)
    return lease


CaptureRunner = Callable[..., dict[str, Any]]


def execute_d405_camera_capability_lease_once(
    lease_path: Path = LEASE_PATH,
    *,
    root: Path = REPO_ROOT,
    now_unix_ns: int | None = None,
    capture_runner: CaptureRunner = run_d405_static_metric_capture_once,
) -> dict[str, Any]:
    """Consume the lease exactly once and bind the OR45 terminal receipt."""

    consumed_path = lease_path.with_name("consumed.json")
    _require(not consumed_path.exists(), "OR45L lease already consumed")
    lease = load_json_object(lease_path, label="OR45L camera lease")
    _require(lease.get("schema_version") == LEASE_SCHEMA, "lease schema drifted")
    digest_candidate = dict(lease)
    expected_digest = digest_candidate.pop("artifact_sha256", None)
    _require(
        expected_digest == canonical_digest(digest_candidate),
        "lease digest drifted",
    )
    now = time.time_ns() if now_unix_ns is None else now_unix_ns
    _require(now >= lease["issued_unix_ns"], "lease is not active yet")
    _require(now <= lease["expires_unix_ns"], "lease expired")
    state = _repository_state(root)
    _require_clean_synchronized_main(state)
    _require(state == lease["repository"], "repository identity drifted after lease")
    graph = _persistent_graph(root)
    _require(
        graph["authority"] == lease["campaign"]["persistent_authority"],
        "persistent campaign authority drifted",
    )
    contract_path = root / lease["contract"]["path"]
    _require(_sha256(contract_path) == lease["contract"]["sha256"], "contract drifted")
    binary_path = root / lease["recorder"]["path"]
    _require(
        _sha256(binary_path) == lease["recorder"]["binary_sha256"],
        "recorder binary drifted after lease",
    )
    output_directory = root / lease["output_directory"]
    _require(not output_directory.exists(), "OR45 capture output already exists")

    try:
        capture_receipt = capture_runner(
            root=root,
            camera_authority=True,
            device_serial=lease["device"]["sdk_serial"],
        )
        forbidden_truth = {
            "serial_opened": capture_receipt.get("serial_opened"),
            "torque_enabled": capture_receipt.get("torque_enabled"),
            "robot_motion_performed": capture_receipt.get("robot_motion_performed"),
            "physical_task_attempts": capture_receipt.get("physical_task_attempts"),
            "simulator_replays": capture_receipt.get("simulator_replays"),
            "transfer_claim": capture_receipt.get("transfer_claim"),
        }
        _require(not any(forbidden_truth.values()), "capture widened non-camera scope")
        status = (
            "PASS_CAMERA_CAPABILITY_CONSUMED"
            if str(capture_receipt.get("status", "")).startswith("PASS_")
            else "TERMINAL_CAMERA_CAPABILITY_CONSUMED_CAPTURE_FAILED"
        )
        error = None
    except Exception as exception:  # the lease is consumed even on capture failure
        capture_receipt = None
        status = "TERMINAL_CAMERA_CAPABILITY_CONSUMED_EXCEPTION_NO_RETRY"
        error = f"{type(exception).__name__}: {exception}"

    receipt = {
        "schema_version": CONSUMPTION_SCHEMA,
        "capability_id": lease["capability_id"],
        "status": status,
        "lease_artifact_sha256": lease["artifact_sha256"],
        "consumed_unix_ns": now,
        "invocations_used": 1,
        "adaptive_retries": 0,
        "capture_receipt": capture_receipt,
        "error": error,
        "persistent_campaign_authority": graph["authority"],
        "serial_opened": False,
        "gateway_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "physical_task_attempts": 0,
        "simulator_replays": 0,
        "transfer_claim": False,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(consumed_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("compile", "execute"))
    arguments = parser.parse_args()
    if arguments.action == "compile":
        compile_d405_camera_capability_lease()
    else:
        execute_d405_camera_capability_lease_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
