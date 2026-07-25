from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sim2claw.physical_gateway import GATEWAY_SCHEMA
from sim2claw.teleop_recording import (
    PrecompiledExcitationBackend,
    RecorderError,
    _float64_sha256,
    compile_physical_excitation_packet,
    execute_physical_excitation_packet,
)


def _preflight(anchor: list[float] | None = None) -> dict[str, Any]:
    return {
        "schema_version": GATEWAY_SCHEMA,
        "passed": True,
        "paired_pose_registration_ready": True,
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
        "leader_port": "/dev/leader",
        "follower_port": "/dev/follower",
        "leader_calibration_sha256": "1" * 64,
        "follower_calibration_sha256": "2" * 64,
        "follower_start_degrees": anchor or [0.0, 0.0, 0.0, 0.0, 0.0, 50.0],
        "follower_calibrated_minimum": [-90.0] * 5 + [0.0],
        "follower_calibrated_maximum": [90.0] * 5 + [100.0],
    }


def _compile(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    packet_path = tmp_path / "packet.json"
    packet = compile_physical_excitation_packet(
        packet_path, preflight_fn=_preflight
    )
    return packet_path, packet


def _admit(packet_path: Path) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["physical_packet_execution_admitted"] = True
    packet["independent_review"] = {
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-07-25T00:00:00Z",
        "decision_id": "P10-fixture-admission",
        "bounded_excitation_reviewed": True,
        "collision_contact_free_workspace_confirmed": True,
    }
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    return packet


def _repo_with_authority(tmp_path: Path) -> Path:
    state = tmp_path / "docs/autonomous-workflow/project_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "twin_fidelity_closure_transaction": {
                    "authority": {
                        "owner_authorized_bounded_robot_motion": True,
                        "owner_workspace_clear_assertion": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_compile_is_deterministic_bounded_exciting_and_read_only(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def read_only() -> dict[str, Any]:
        report = _preflight()
        calls.append(report)
        return report

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = compile_physical_excitation_packet(first_path, preflight_fn=read_only)
    second = compile_physical_excitation_packet(second_path, preflight_fn=read_only)

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()
    assert len(calls) == 2
    assert all(call["physical_follower_torque_enabled"] is False for call in calls)
    plan = first["plan"]
    assert len(plan["episodes"]) == 5
    covered = set()
    for episode in plan["episodes"]:
        actions = np.asarray(episode["actions_degrees"], dtype=np.float64)
        timestamps = np.asarray(episode["timestamps_seconds"], dtype=np.float64)
        assert episode["gateway_action_degrees_sha256"] == _float64_sha256(
            actions
        )
        assert episode["canonical_action_radians_sha256"] == _float64_sha256(
            np.deg2rad(actions)
        )
        assert timestamps[-1] >= 1.0
        assert np.unique(actions, axis=0).shape[0] > 3
        assert np.all(actions[:, 5] == plan["anchor_degrees"][5])
        ranges = np.ptp(actions[:, :5], axis=0)
        covered.add(int(np.argmax(ranges)))
        assert np.max(ranges) >= 5.0
        slew = np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None])
        assert np.max(slew) <= 10.0 + 1e-12
    assert len(covered) >= 3


def test_pending_admission_rejects_before_hardware_open(tmp_path: Path) -> None:
    packet_path, _ = _compile(tmp_path)
    touched: list[str] = []

    with pytest.raises(RecorderError, match="pending independent admission"):
        execute_physical_excitation_packet(
            packet_path,
            tmp_path / "output",
            repo_root=tmp_path,
            operator_acknowledged=True,
            preflight_fn=lambda: touched.append("preflight"),
            manager_factory=lambda **kwargs: touched.append("manager"),
        )
    assert touched == []


class _FakeGateway:
    def __init__(self, anchor: list[float], *, mismatch: bool = False):
        self.anchor = np.asarray(anchor, dtype=np.float64)
        self.mismatch = mismatch
        self.closed = False
        self.targets: list[np.ndarray] = []

    def open(
        self, *, enable_motion: bool, paired_pose_confirmed: bool
    ) -> dict[str, Any]:
        current = self.anchor.copy()
        if self.mismatch:
            current[0] += 4.0
        return {
            "follower_registration_degrees": current.tolist(),
            "physical_follower_torque_enabled": True,
        }

    def sample(
        self, elapsed_seconds: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, Any]:
        target = exact_requested_degrees.copy()
        self.targets.append(target)
        return {
            "elapsed_seconds": elapsed_seconds,
            "follower_requested_degrees": target.tolist(),
            "follower_command_degrees": target.tolist(),
            "follower_actual_position_degrees": target.tolist(),
            "follower_actual_velocity_degrees_s": [0.0] * 6,
            "rate_limited": False,
            "safety_clamped": False,
        }

    def close(self) -> None:
        self.closed = True


def test_pose_anchor_mismatch_releases_torque(tmp_path: Path) -> None:
    _, packet = _compile(tmp_path)
    gateway = _FakeGateway(packet["plan"]["anchor_degrees"], mismatch=True)
    backend = PrecompiledExcitationBackend(
        {},
        {
            "devices": {
                "leader": {"port": "/dev/leader"},
                "follower": {"port": "/dev/follower"},
            },
            "calibrations": {
                "leader": {"sha256": "1" * 64},
                "follower": {"sha256": "2" * 64},
            },
        },
        plan=packet["plan"],
        episode=packet["plan"]["episodes"][0],
        gateway_factory=lambda _identity: gateway,
    )

    with pytest.raises(RecorderError, match="compiled anchor"):
        backend.open()
    assert gateway.closed is True


def test_backend_consumes_every_precompiled_action_byte_identically(
    tmp_path: Path,
) -> None:
    _, packet = _compile(tmp_path)
    episode = packet["plan"]["episodes"][0]
    gateway = _FakeGateway(packet["plan"]["anchor_degrees"])
    backend = PrecompiledExcitationBackend(
        {},
        {
            "devices": {
                "leader": {"port": "/dev/leader"},
                "follower": {"port": "/dev/follower"},
            },
            "calibrations": {
                "leader": {"sha256": "1" * 64},
                "follower": {"sha256": "2" * 64},
            },
        },
        plan=packet["plan"],
        episode=episode,
        gateway_factory=lambda _identity: gateway,
    )
    backend.open()
    while not backend.recording_complete:
        backend.sample(999.0)

    consumed = np.stack(gateway.targets)
    assert _float64_sha256(consumed) == episode[
        "gateway_action_degrees_sha256"
    ]


class _FakeManager:
    saved_count = 0

    def __init__(self, *, repo_root: Path, backend_factory: Any):
        self.repo_root = repo_root
        self.status = "idle"

    def start(self, request: dict[str, Any]) -> None:
        self.status = "awaiting_label"

    def snapshot(self) -> dict[str, Any]:
        return {"status": self.status}

    def finalize(self, labels: dict[str, Any]) -> dict[str, Any]:
        type(self).saved_count += 1
        relative = Path("datasets/manipulation_source_recordings") / (
            f"fixture-{type(self).saved_count}"
        )
        (self.repo_root / relative).mkdir(parents=True)
        self.status = "saved"
        return {"saved_path": relative.as_posix()}


def _execution_fakes(packet: dict[str, Any], *, fail_at: int | None = None):
    calls = 0

    def materialize(
        recording: Path, manifest: Path, report: Path
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if fail_at == calls:
            raise RecorderError("fixture P4 failure")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        report.write_text("{}", encoding="utf-8")
        return {
            "exact_replay_eligible": True,
            "applied_action_sha256": packet["plan"]["episodes"][calls - 1][
                "canonical_action_radians_sha256"
            ],
        }

    return materialize


def test_five_outputs_emit_p9_cohort_only_after_p4(tmp_path: Path) -> None:
    packet_path, _ = _compile(tmp_path)
    packet = _admit(packet_path)
    repo = _repo_with_authority(tmp_path / "repo")
    _FakeManager.saved_count = 0

    result = execute_physical_excitation_packet(
        packet_path,
        tmp_path / "output",
        repo_root=repo,
        operator_acknowledged=True,
        preflight_fn=_preflight,
        manager_factory=_FakeManager,
        materialize_fn=_execution_fakes(packet),
    )

    assert result["status"] == "five_recordings_finalized_and_p4_eligible"
    cohort = json.loads((tmp_path / "output/p9_cohort.json").read_text())
    assert len(cohort["episodes"]) == 5
    assert len(result["completed"]) == 5


def test_partial_run_fails_closed_without_cohort(tmp_path: Path) -> None:
    packet_path, _ = _compile(tmp_path)
    packet = _admit(packet_path)
    repo = _repo_with_authority(tmp_path / "repo")
    _FakeManager.saved_count = 0

    with pytest.raises(RecorderError, match="fixture P4 failure"):
        execute_physical_excitation_packet(
            packet_path,
            tmp_path / "output",
            repo_root=repo,
            operator_acknowledged=True,
            preflight_fn=_preflight,
            manager_factory=_FakeManager,
            materialize_fn=_execution_fakes(packet, fail_at=3),
        )

    assert not (tmp_path / "output/p9_cohort.json").exists()
    report = json.loads((tmp_path / "output/execution_report.json").read_text())
    assert report["status"] == "partial_failed_closed"
    assert len(report["completed"]) == 2
    assert report["cohort_emitted"] is False
