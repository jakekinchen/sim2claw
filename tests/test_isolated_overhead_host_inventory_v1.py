from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import sim2claw.isolated_overhead_host_inventory_v1 as inventory
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/isolated_overhead_host_inventory_v1.json"
)


def _profile(*, c922: int = 1, d405: int = 0) -> dict[str, object]:
    cameras: list[dict[str, object]] = []
    usb: list[dict[str, object]] = []
    for index in range(c922):
        cameras.append(
            {
                "_name": "C922 Pro Stream Webcam",
                "spcamera_unique-id": f"c922-{index}",
            }
        )
        usb.append(
            {
                "_name": "C922 Pro Stream Webcam",
                "vendor_id": "0x046d  (Logitech Inc.)",
                "product_id": "0x085c",
            }
        )
    for index in range(d405):
        cameras.append(
            {
                "_name": "Intel(R) RealSense(TM) Depth Camera 405  Depth",
                "spcamera_unique-id": f"d405-{index}",
            }
        )
        usb.append(
            {
                "_name": "Intel RealSense D405",
                "vendor_id": "0x8086  (Intel Corporation)",
                "product_id": "0x0b5b",
            }
        )
    return {
        "SPCameraDataType": cameras,
        "SPUSBDataType": [{"_name": "USB4 Bus", "_items": usb}],
    }


def _stdout(*, c922: int = 1, d405: int = 0) -> bytes:
    profile = json.dumps(_profile(c922=c922, d405=d405), sort_keys=True)
    return f"silicon\n15.5\n{profile}\n".encode()


def _completed(
    *,
    returncode: int = 0,
    stdout: bytes | None = None,
    stderr: bytes = b"",
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        inventory.SSH_ARGUMENTS,
        returncode,
        stdout=stdout if stdout is not None else _stdout(),
        stderr=stderr,
    )


def _materialize(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    completed: subprocess.CompletedProcess[bytes] | None = None,
) -> tuple[Path, Path]:
    observed = tmp_path / "observed"
    evaluated = tmp_path / "evaluated"
    monkeypatch.setattr(inventory, "DEFAULT_OBSERVED_ROOT", observed)
    monkeypatch.setattr(inventory, "DEFAULT_EVALUATED_ROOT", evaluated)

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args == (inventory.SSH_ARGUMENTS,)
        assert kwargs == {
            "check": False,
            "capture_output": True,
            "timeout": 15,
        }
        return completed or _completed()

    monkeypatch.setattr(inventory.subprocess, "run", runner)
    inventory.run_observation(
        contract_path=CONTRACT,
        output_root=observed,
    )
    return observed, evaluated


def test_contract_freezes_zero_session_single_connection_authority() -> None:
    contract = inventory.load_contract(CONTRACT)
    assert contract["operation_budget"] == {
        "remote_inventory_observations_maximum": 1,
        "ssh_connection_attempts_maximum": 1,
        "capture_sessions_maximum": 0,
        "camera_frames_maximum": 0,
        "remote_files_written_maximum": 0,
        "robot_motion_trials_maximum": 0,
        "simulator_replays_maximum": 0,
        "provider_calls_maximum": 0,
    }
    assert contract["authority"] == inventory.EXPECTED_AUTHORITY


def test_ssh_command_is_exact_noninteractive_read_only_allowlist() -> None:
    assert inventory.SSH_ARGUMENTS[:-1] == [
        "/usr/bin/ssh",
        "-F",
        "/dev/null",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        "-oConnectTimeout=5",
        "-oConnectionAttempts=1",
        "-oClearAllForwardings=yes",
        "-p22",
        "kelly@silicon.local",
    ]
    assert inventory.SSH_ARGUMENTS[-1] == inventory.REMOTE_COMMAND
    assert inventory.REMOTE_COMMAND.split(" && ") == [
        "/bin/hostname",
        "/usr/bin/sw_vers -productVersion",
        (
            "/usr/sbin/system_profiler SPCameraDataType "
            "SPUSBDataType -json -detailLevel mini"
        ),
    ]
    for forbidden in ("|", ">", "<", "$(", "`", "sudo", "scp", "rsync"):
        assert forbidden not in inventory.REMOTE_COMMAND
    assert inventory._runtime_identity()["ssh_identity_admitted"] is True


def test_ready_inventory_is_evaluated_byte_identically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed, evaluated = _materialize(monkeypatch, tmp_path)
    result = inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=evaluated,
    )
    assert result["verdict"] == "isolated_overhead_host_ready"
    first = (evaluated / "evaluation.json").read_bytes()
    first_receipt = (evaluated / "receipt.json").read_bytes()
    replay = tmp_path / "replay"
    monkeypatch.setattr(inventory, "DEFAULT_EVALUATED_ROOT", replay)
    inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=replay,
    )
    assert (replay / "evaluation.json").read_bytes() == first
    assert (replay / "receipt.json").read_bytes() == first_receipt


def test_absent_c922_returns_attachment_prerequisite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed, evaluated = _materialize(
        monkeypatch,
        tmp_path,
        completed=_completed(stdout=_stdout(c922=0)),
    )
    result = inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=evaluated,
    )
    assert result["verdict"] == "isolated_overhead_host_requires_c922_attachment"
    assert result["failed_gates"] == [
        "target_c922_camera_match_count",
        "target_c922_usb_match_count",
    ]


@pytest.mark.parametrize(
    ("c922", "d405", "failed_gate"),
    [
        (2, 0, "target_c922_camera_match_count"),
        (1, 1, "excluded_d405_camera_match_count"),
        (0, 1, "excluded_d405_camera_match_count"),
    ],
)
def test_substitution_or_excluded_device_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    c922: int,
    d405: int,
    failed_gate: str,
) -> None:
    observed, evaluated = _materialize(
        monkeypatch,
        tmp_path,
        completed=_completed(stdout=_stdout(c922=c922, d405=d405)),
    )
    result = inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=evaluated,
    )
    assert result["verdict"] == "prerequisite_abstention"
    assert failed_gate in result["failed_gates"]


@pytest.mark.parametrize(
    "completed",
    [
        _completed(returncode=255, stdout=b"", stderr=b"authentication failed"),
        _completed(stdout=b"silicon\n15.5\nnot-json\n"),
        _completed(stdout=b"silicon\n15.5\n{}\n"),
    ],
)
def test_access_or_malformed_metadata_seals_abstention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    completed: subprocess.CompletedProcess[bytes],
) -> None:
    observed, evaluated = _materialize(
        monkeypatch,
        tmp_path,
        completed=completed,
    )
    result = inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=evaluated,
    )
    assert result["verdict"] == "prerequisite_abstention"
    assert result["failed_gates"] == ["remote_metadata_available"]


def test_replayed_observation_root_is_rejected_before_ssh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed, _ = _materialize(monkeypatch, tmp_path)
    called = False

    def forbidden_runner(
        *_: object,
        **__: object,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal called
        called = True
        return _completed()

    monkeypatch.setattr(inventory.subprocess, "run", forbidden_runner)
    with pytest.raises(AVFoundationFormatInventoryError, match="replay"):
        inventory.run_observation(
            contract_path=CONTRACT,
            output_root=observed,
        )
    assert called is False


@pytest.mark.parametrize("failure", ["timeout", "launch", "identity", "missing"])
def test_timeout_or_ssh_launch_failure_is_sealed_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    observed = tmp_path / "observed"
    evaluated = tmp_path / "evaluated"
    monkeypatch.setattr(inventory, "DEFAULT_OBSERVED_ROOT", observed)
    monkeypatch.setattr(inventory, "DEFAULT_EVALUATED_ROOT", evaluated)
    if failure in {"identity", "missing"}:
        candidate = tmp_path / "unexpected-ssh"
        if failure == "identity":
            candidate.write_bytes(b"not the reviewed executable")
        monkeypatch.setattr(inventory, "SSH_PATH", candidate)
        monkeypatch.setattr(
            inventory,
            "SSH_ARGUMENTS",
            [str(candidate), *inventory.SSH_ARGUMENTS[1:]],
        )

    def failing_runner(*_: object, **__: object) -> subprocess.CompletedProcess[bytes]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                inventory.SSH_ARGUMENTS,
                15,
                output=b"partial",
            )
        raise FileNotFoundError("ssh")

    monkeypatch.setattr(inventory.subprocess, "run", failing_runner)
    result = inventory.run_observation(
        contract_path=CONTRACT,
        output_root=observed,
    )
    assert result["status"] == "prerequisite_unavailable"
    evaluated_result = inventory.evaluate(
        contract_path=CONTRACT,
        observed_root=observed,
        output_root=evaluated,
    )
    assert evaluated_result["verdict"] == "prerequisite_abstention"
    attempt = json.loads((observed / "attempt.json").read_text())
    assert attempt["return_code"] in {124, 126, 127}


@pytest.mark.parametrize(
    "mutation",
    [
        "ssh_args",
        "budget",
        "authority",
        "raw",
        "coordinated_raw_rehash",
        "observer_role",
        "contract_id",
        "return_code",
        "stream",
        "command",
    ],
)
def test_evaluator_rejects_manifest_or_evidence_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    observed, evaluated = _materialize(monkeypatch, tmp_path)
    if mutation in {"ssh_args", "budget", "authority"}:
        path = observed / "attempt.json"
        payload = json.loads(path.read_text())
        if mutation == "ssh_args":
            payload["ssh_arguments"][-1] += " && /usr/bin/id"
        elif mutation == "budget":
            payload["budget"]["ssh_connection_attempts_used"] = 2
        else:
            payload["authority"]["remote_file_write"] = True
        path.write_bytes(_canonical_bytes(payload))
    elif mutation in {
        "raw",
        "coordinated_raw_rehash",
        "observer_role",
    }:
        path = observed / "raw/observation.json"
        payload = json.loads(path.read_text())
        if mutation == "observer_role":
            payload["observer_role"] = "self_scoring_remote_observer"
        else:
            payload["remote_hostname"] = "substituted"
        path.write_bytes(_canonical_bytes(payload))
        if mutation in {"coordinated_raw_rehash", "observer_role"}:
            attempt = json.loads((observed / "attempt.json").read_text())
            attempt["raw_observation_sha256"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            (observed / "attempt.json").write_bytes(_canonical_bytes(attempt))
    elif mutation == "contract_id":
        prelaunch_path = observed / "attempt-prelaunch.json"
        prelaunch = json.loads(prelaunch_path.read_text())
        prelaunch["contract_id"] = "substituted-contract"
        prelaunch_path.write_bytes(_canonical_bytes(prelaunch))
        attempt_path = observed / "attempt.json"
        attempt = json.loads(attempt_path.read_text())
        attempt["contract_id"] = "substituted-contract"
        attempt["prelaunch_manifest_sha256"] = hashlib.sha256(
            prelaunch_path.read_bytes()
        ).hexdigest()
        attempt_path.write_bytes(_canonical_bytes(attempt))
    elif mutation == "return_code":
        path = observed / "attempt.json"
        payload = json.loads(path.read_text())
        payload["return_code"] = 255
        path.write_bytes(_canonical_bytes(payload))
    elif mutation == "stream":
        (observed / "raw/ssh.stdout").write_bytes(b"changed")
    else:
        path = observed / "raw/observation.json"
        payload = json.loads(path.read_text())
        payload["remote_command_sha256"] = "0" * 64
        path.write_bytes(_canonical_bytes(payload))
        attempt = json.loads((observed / "attempt.json").read_text())
        attempt["raw_observation_sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        (observed / "attempt.json").write_bytes(_canonical_bytes(attempt))
    with pytest.raises(AVFoundationFormatInventoryError):
        inventory.evaluate(
            contract_path=CONTRACT,
            observed_root=observed,
            output_root=evaluated,
        )


def test_malformed_profiler_data_type_shape_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    malformed = {
        "SPCameraDataType": {"_name": "C922 Pro Stream Webcam"},
        "SPUSBDataType": [],
    }
    stdout = f"silicon\n15.5\n{json.dumps(malformed)}\n".encode()
    observed, evaluated = _materialize(
        monkeypatch,
        tmp_path,
        completed=_completed(stdout=stdout),
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="malformed"):
        inventory.evaluate(
            contract_path=CONTRACT,
            observed_root=observed,
            output_root=evaluated,
        )


def test_contract_mutation_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(CONTRACT.read_text())
    payload["remote_endpoint"]["ssh_host"] = "other.local"
    path = tmp_path / "contract.json"
    path.write_bytes(_canonical_bytes(payload))
    with pytest.raises(AVFoundationFormatInventoryError, match="identity"):
        inventory.load_contract(path)
