from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
import sim2claw.observable_registration_d405_camera_capability as capability


def _clean_state() -> dict[str, object]:
    return {
        "head": "a" * 40,
        "remote_head": "a" * 40,
        "branch": "main",
        "worktree_clean": True,
    }


def test_contract_keeps_persistent_authority_false_and_scope_camera_only() -> None:
    contract = capability.load_d405_camera_capability_contract()
    assert not any(contract["persistent_campaign_authority_required"].values())
    assert contract["lease"]["maximum_invocations"] == 1
    assert contract["lease"]["adaptive_retry_allowed"] is False
    assert contract["lease"]["maximum_lease_seconds"] == 300
    assert contract["lease"]["sdk_serial_allowlist"] == ["130322273474"]
    assert contract["capability_scope"] == {
        "camera_device_enumeration": True,
        "camera_stream_start": True,
        "camera_frames": 30,
        "camera_stream_stop": True,
        "serial": False,
        "gateway": False,
        "torque": False,
        "robot_motion": False,
        "object_interaction": False,
        "physical_task_attempt": False,
        "simulator_replay": False,
        "transfer_claim": False,
    }


def test_lease_compiler_rejects_dirty_or_unsynchronized_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirty = _clean_state()
    dirty["worktree_clean"] = False
    monkeypatch.setattr(capability, "_repository_state", lambda root: dirty)
    with pytest.raises(FactoryArtifactError, match="worktree is not clean"):
        capability.compile_d405_camera_capability_lease(
            tmp_path / "lease.json", now_unix_ns=1_000_000_000
        )


def test_compiled_lease_binds_commit_binary_command_and_expiration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capability, "_repository_state", lambda root: _clean_state())
    lease = capability.compile_d405_camera_capability_lease(
        tmp_path / "lease.json", now_unix_ns=1_000_000_000
    )
    assert lease["repository"]["head"] == "a" * 40
    assert len(lease["recorder"]["binary_sha256"]) == 64
    assert lease["device"]["sdk_serial"] == "130322273474"
    assert lease["invocation"]["maximum_invocations"] == 1
    assert lease["invocation"]["adaptive_retry_allowed"] is False
    assert lease["expires_unix_ns"] - lease["issued_unix_ns"] == 300_000_000_000
    assert lease["arguments"][-2:] == ["--fps", "30"]


def test_execute_consumes_lease_once_and_never_grants_robot_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capability, "_repository_state", lambda root: _clean_state())
    lease_path = tmp_path / "lease.json"
    capability.compile_d405_camera_capability_lease(
        lease_path, now_unix_ns=1_000_000_000
    )
    calls: list[dict[str, object]] = []

    def fake_capture_runner(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "status": "PASS_D405_STATIC_METRIC_CAPTURE",
            "serial_opened": False,
            "torque_enabled": False,
            "robot_motion_performed": False,
            "physical_task_attempts": 0,
            "simulator_replays": 0,
            "transfer_claim": False,
        }

    receipt = capability.execute_d405_camera_capability_lease_once(
        lease_path,
        now_unix_ns=2_000_000_000,
        capture_runner=fake_capture_runner,
    )
    assert receipt["status"] == "PASS_CAMERA_CAPABILITY_CONSUMED"
    assert calls == [
        {
            "root": capability.REPO_ROOT,
            "camera_authority": True,
            "device_serial": "130322273474",
        }
    ]
    assert receipt["persistent_campaign_authority"] == {
        "camera_open": False,
        "gateway": False,
        "heldout_open": False,
        "paid_compute": False,
        "physical_motion": False,
        "serial": False,
        "simulator_promotion": False,
        "task_attempt": False,
        "training": False,
        "transfer_claim": False,
    }
    with pytest.raises(FactoryArtifactError, match="already consumed"):
        capability.execute_d405_camera_capability_lease_once(
            lease_path,
            now_unix_ns=3_000_000_000,
            capture_runner=fake_capture_runner,
        )
