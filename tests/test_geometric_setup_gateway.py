from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import sim2claw.geometric_setup_gateway as setup_gateway
from sim2claw.geometric_physical_gateway import GeometricPhysicalGatewayError
from sim2claw.geometric_setup_gateway import (
    SETUP_EXECUTION_SCHEMA,
    SETUP_PACKET_SCHEMA,
    SETUP_REVIEW_SCHEMA,
    compile_geometric_setup_phase_packet,
    execute_geometric_setup_phase_packet,
    review_geometric_setup_phase_packet,
)
from sim2claw.physical_canary import EXCITATION_CONTROL_SOURCE, GATEWAY_SCHEMA
from sim2claw.recorded_replay import canonical_json_sha256
from sim2claw.source_episode import sha256_file


PORT = "/dev/follower-setup-fixture"
CALIBRATION = "a" * 64


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _preflight(start: np.ndarray) -> dict[str, object]:
    return {
        "schema_version": GATEWAY_SCHEMA,
        "control_source": EXCITATION_CONTROL_SOURCE,
        "real_leader_opened": False,
        "follower_port": PORT,
        "follower_calibration_sha256": CALIBRATION,
        "follower_start_degrees": start.tolist(),
        "follower_calibrated_minimum": [-180.0] * 5 + [0.0],
        "follower_calibrated_maximum": [180.0] * 5 + [100.0],
        "physical_follower_torque_enabled": False,
        "device_configuration_rewritten": False,
    }


def _preview(
    actions: np.ndarray,
    episode: Path,
    receipt: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    del episode, receipt, config
    return {
        "runtime": "fixture_dynamic_setup_preview",
        "sample_count": len(actions),
        "exact_setup_sim_action_sha256": hashlib.sha256(
            actions.astype("<f8", copy=False).tobytes(order="C")
        ).hexdigest(),
        "forbidden_robot_contact_count": 0,
        "robot_pawn_contact_count": 0,
        "contact_gate_mode": "strict_zero_contact",
        "passed": True,
    }


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    unsafe_rate: bool = False,
) -> tuple[Path, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    episode = tmp_path / "episode"
    episode.mkdir()
    _write(episode / "recording_receipt.json", {"fixture": True})
    (episode / "samples.jsonl").write_text("{}\n", encoding="utf-8")
    _write(episode / "initial.json", {"state": {"integration_state_float64": []}})
    admission_path = episode / "admission.json"
    _write(admission_path, {"strict_success": True})

    transform = {
        "transform_id": "fixture_identity",
        "calibration_approved": True,
        "review": {"reviewer": "fixture"},
        "joints": [
            {
                "sign": 1.0,
                "scale": 1.0,
                "zero_offset": 0.0,
            }
            for _ in range(6)
        ],
    }
    transform_sha256 = canonical_json_sha256(transform)
    config: dict[str, Any] = {
        "physical_adapter": {
            "joint_transform": transform,
            "joint_transform_sha256": transform_sha256,
        }
    }
    manifest = {
        "candidate_digest": "d" * 64,
        "identity": {
            "robot": {
                "gateway_schema": GATEWAY_SCHEMA,
                "follower_port": PORT,
                "follower_calibration_sha256": CALIBRATION,
            }
        },
    }
    candidate_path = tmp_path / "candidate.json"
    _write(candidate_path, manifest)

    task_start = np.asarray(
        [3.0, -3.0, 2.0, 3.0, 6.0, 20.0],
        dtype="<f4",
    )
    source_actions = np.asarray(
        [
            task_start,
            task_start + np.asarray([0.1, 0.0, 0.0, 0.0, 0.0, 1.0]),
            task_start,
        ],
        dtype="<f4",
    )
    rows: list[dict[str, Any]] = []
    for index, action in enumerate(source_actions):
        rows.append(
            {
                "timestamp_monotonic_seconds": index / 20.0,
                "action": {"joint_target_rad": action.tolist()},
            }
        )
    receipt = {
        "recording_id": "setup-fixture",
        "initial_evaluator_privileged_state_path": "initial.json",
    }
    verdict = {"strict_success": True}
    monkeypatch.setattr(
        setup_gateway,
        "_validated_source",
        lambda episode_path, verdict_path: (
            receipt,
            rows,
            verdict,
            tmp_path / "evaluator.json",
        ),
    )
    monkeypatch.setattr(
        setup_gateway,
        "_validated_candidate",
        lambda candidate_path_arg, receipt_arg: (
            manifest,
            config,
            transform,
        ),
    )

    waypoints = [
        np.asarray([0.0, 0.0, 0.0, 0.0, 0.0, 5.0], dtype="<f8"),
        np.asarray([1.0, -1.0, 1.0, 1.0, 2.0, 10.0], dtype="<f8"),
        np.asarray([2.0, -2.0, 1.5, 2.0, 4.0, 15.0], dtype="<f8"),
        task_start.astype("<f8"),
    ]
    phases: list[np.ndarray] = []
    segments: list[dict[str, Any]] = []
    for index in range(3):
        phase = np.linspace(waypoints[index], waypoints[index + 1], 3)
        if unsafe_rate and index == 0:
            phase[1, 0] = 100.0
        start = index * 3
        phases.append(phase)
        segments.append(
            {
                "phase_index": index + 1,
                "combined_start_index": start,
                "combined_end_index_exclusive": start + 3,
                "sample_count": 3,
                "sample_hz": 20,
                "origin_physical_units": phase[0].tolist(),
                "target_physical_units": phase[-1].tolist(),
                "raw_float64_c_order_sha256": hashlib.sha256(
                    phase.astype("<f8", copy=False).tobytes(order="C")
                ).hexdigest(),
            }
        )
    physical = np.vstack(phases).astype("<f8")
    simulator = physical.copy()
    physical_path = tmp_path / "setup_physical.npy"
    simulator_path = tmp_path / "setup_simulator.npy"
    np.save(physical_path, physical, allow_pickle=False)
    np.save(simulator_path, simulator, allow_pickle=False)

    source_raw = source_actions.tobytes(order="C")
    compile_inputs: dict[str, Any] = {
        "schema_version": setup_gateway.TRANSFER_INPUT_SCHEMA,
        "physical_motion_performed": False,
        "physical_authority_created": False,
        "canonical_task_source": {
            "episode_directory": str(episode),
            "recording_receipt_sha256": sha256_file(
                episode / "recording_receipt.json"
            ),
            "samples_file_sha256": sha256_file(episode / "samples.jsonl"),
            "source_action_raw_sha256": hashlib.sha256(source_raw).hexdigest(),
            "task_actions_copied_into_bundle": False,
            "task_bytes_owner": "canonical source samples.jsonl",
        },
        "strict_admission": {
            "path": str(admission_path),
            "file_sha256": sha256_file(admission_path),
        },
        "candidate_manifest": {
            "path": str(candidate_path),
            "file_sha256": sha256_file(candidate_path),
            "candidate_digest": manifest["candidate_digest"],
            "joint_transform_sha256": transform_sha256,
        },
        "setup": {
            "combined_sample_count": len(physical),
            "sample_hz": 20,
            "segments": segments,
            "physical_array": {
                "path": str(physical_path),
                "shape": list(physical.shape),
                "dtype": "float64_little_endian",
                "raw_c_order_sha256": hashlib.sha256(
                    physical.tobytes(order="C")
                ).hexdigest(),
                "npy_sha256": sha256_file(physical_path),
            },
            "sim_array": {
                "path": str(simulator_path),
                "shape": list(simulator.shape),
                "dtype": "float64_little_endian",
                "raw_c_order_sha256": hashlib.sha256(
                    simulator.tobytes(order="C")
                ).hexdigest(),
                "npy_sha256": sha256_file(simulator_path),
            },
        },
    }
    compile_inputs["canonical_payload_sha256"] = canonical_json_sha256(
        compile_inputs
    )
    compile_inputs_path = tmp_path / "compile_inputs.json"
    _write(compile_inputs_path, compile_inputs)
    return compile_inputs_path, physical, source_actions, segments


class _Gateway:
    def __init__(self, start: np.ndarray, *, stall: bool = False) -> None:
        self.start = start.copy()
        self.stall = stall
        self.closed = False
        self.samples: list[np.ndarray] = []

    def open(
        self,
        *,
        enable_motion: bool,
        paired_pose_confirmed: bool,
    ) -> dict[str, object]:
        assert enable_motion and paired_pose_confirmed
        return {"follower_start_degrees": self.start.tolist()}

    def sample(
        self,
        timestamp: float,
        *,
        exact_requested_degrees: np.ndarray,
    ) -> dict[str, object]:
        del timestamp
        self.samples.append(exact_requested_degrees.copy())
        stalled = self.stall and len(self.samples) == 1
        return {
            "follower_requested_degrees": exact_requested_degrees.tolist(),
            "follower_command_degrees": exact_requested_degrees.tolist(),
            "follower_actual_position_degrees": (
                exact_requested_degrees.tolist()
            ),
            "tracking_error_limits": [10.0] * 6,
            "rate_limited": False,
            "safety_clamped": False,
            "stalled": stalled,
            "stalled_joints": ["shoulder_pan"] if stalled else [],
            "gripper_contact_hold": False,
        }

    def close(self) -> None:
        self.closed = True


def test_compile_binds_task_digest_without_task_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, physical, source_actions, _ = _fixture(
        tmp_path,
        monkeypatch,
    )
    preview_calls = 0
    preflight_calls = 0

    def preview(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal preview_calls
        preview_calls += 1
        return _preview(*args, **kwargs)

    def preflight() -> dict[str, object]:
        nonlocal preflight_calls
        preflight_calls += 1
        return _preflight(physical[0])

    packet = compile_geometric_setup_phase_packet(
        compile_inputs,
        1,
        tmp_path / "phase-1.json",
        preflight_fn=preflight,
        preview_fn=preview,
    )
    assert packet["schema_version"] == SETUP_PACKET_SCHEMA
    assert packet["task_binding"]["task_action_payload_present"] is False
    assert packet["task_binding"]["source_action_sha256"] == hashlib.sha256(
        source_actions.tobytes(order="C")
    ).hexdigest()
    assert "source_action_payload" not in packet
    assert packet["rate_audit"]["all_rates_within_reviewed_gateway_limits"]
    assert packet["excursion_audit"][
        "all_excursions_within_reviewed_gateway_limits"
    ]
    assert preview_calls == preflight_calls == 1


def test_unapproved_candidate_rejects_before_hardware_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, _, _, _ = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        setup_gateway,
        "_validated_candidate",
        lambda candidate, receipt: (_ for _ in ()).throw(
            GeometricPhysicalGatewayError(
                "candidate physical transform is not calibration-approved"
            )
        ),
    )
    hardware_read = False

    def preflight() -> dict[str, object]:
        nonlocal hardware_read
        hardware_read = True
        raise AssertionError("must reject before hardware")

    with pytest.raises(
        GeometricPhysicalGatewayError,
        match="not calibration-approved",
    ):
        compile_geometric_setup_phase_packet(
            compile_inputs,
            1,
            tmp_path / "phase-1.json",
            preflight_fn=preflight,
            preview_fn=_preview,
        )
    assert hardware_read is False


def test_contact_preview_rejects_before_hardware_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, _, _, _ = _fixture(tmp_path, monkeypatch)
    hardware_read = False

    def rejected_preview(
        actions: np.ndarray,
        *args: object,
    ) -> dict[str, object]:
        result = _preview(actions, *args)
        result["passed"] = False
        result["forbidden_robot_contact_count"] = 1
        return result

    def preflight() -> dict[str, object]:
        nonlocal hardware_read
        hardware_read = True
        raise AssertionError("must reject before hardware")

    with pytest.raises(
        GeometricPhysicalGatewayError,
        match="contact preview rejected",
    ):
        compile_geometric_setup_phase_packet(
            compile_inputs,
            1,
            tmp_path / "phase-1.json",
            preflight_fn=preflight,
            preview_fn=rejected_preview,
        )
    assert hardware_read is False


def _contact_snapshot(
    sample_index: int,
    physics_substep: int,
    *,
    distance_m: float | None,
    pair: tuple[str, str] = ("left_lower_arm", "left_shoulder"),
    both_robot: bool = True,
    touches_pawn: bool = False,
) -> dict[str, object]:
    contacts: list[dict[str, object]] = []
    if distance_m is not None:
        contacts.append(
            {
                "pair": list(pair),
                "distance_m": distance_m,
                "both_robot": both_robot,
                "touches_pawn": touches_pawn,
            }
        )
    return {
        "sample_index": sample_index,
        "physics_substep": physics_substep,
        "contacts": contacts,
    }


def test_tiny_preexisting_self_contact_must_resolve_without_worsening() -> None:
    result = setup_gateway._classify_contact_snapshots(
        [
            _contact_snapshot(0, -1, distance_m=-7.15e-5),
            _contact_snapshot(0, 0, distance_m=-7.15e-5),
            _contact_snapshot(1, 0, distance_m=-2.51e-5),
            _contact_snapshot(1, 1, distance_m=None),
            _contact_snapshot(1, 2, distance_m=None),
        ],
        first_changed_sample_index=1,
    )
    assert result["passed"] is True
    assert result["contact_gate_mode"] == (
        "resolving_preexisting_self_contact"
    )
    assert result["preexisting_contact_never_worsened"] is True
    assert result["preexisting_contact_resolved_during_egress"] is True
    assert result["forbidden_robot_contact_count"] == 0


@pytest.mark.parametrize(
    "bad_snapshot, expected_field",
    [
        (
            _contact_snapshot(
                1,
                0,
                distance_m=-2e-5,
                pair=("left_lower_arm", "tan_pawn_c8"),
                both_robot=False,
                touches_pawn=True,
            ),
            "new_contact_pair_count",
        ),
        (
            _contact_snapshot(1, 0, distance_m=-9e-5),
            "worsened_contact_pair_count",
        ),
    ],
)
def test_preexisting_contact_rule_rejects_new_or_worsened_contact(
    bad_snapshot: dict[str, object],
    expected_field: str,
) -> None:
    result = setup_gateway._classify_contact_snapshots(
        [
            _contact_snapshot(0, -1, distance_m=-7.15e-5),
            bad_snapshot,
            _contact_snapshot(1, 1, distance_m=None),
        ],
        first_changed_sample_index=1,
    )
    assert result["passed"] is False
    assert int(result[expected_field]) > 0
    assert int(result["forbidden_robot_contact_count"]) > 0


def test_preexisting_contact_rule_rejects_recurrence() -> None:
    result = setup_gateway._classify_contact_snapshots(
        [
            _contact_snapshot(0, -1, distance_m=-7.15e-5),
            _contact_snapshot(1, 0, distance_m=None),
            _contact_snapshot(1, 1, distance_m=-1e-6),
        ],
        first_changed_sample_index=1,
    )
    assert result["passed"] is False
    assert result["recurrent_contact_pair_count"] == 1


@pytest.mark.parametrize(
    "snapshots, first_changed",
    [
        (
            [
                _contact_snapshot(0, -1, distance_m=-1.01e-4),
                _contact_snapshot(1, 0, distance_m=None),
            ],
            1,
        ),
        (
            [
                _contact_snapshot(
                    0,
                    -1,
                    distance_m=-1e-6,
                    pair=("chess_board", "left_lower_arm"),
                    both_robot=False,
                ),
                _contact_snapshot(1, 0, distance_m=None),
            ],
            1,
        ),
        (
            [
                _contact_snapshot(0, -1, distance_m=-7.15e-5),
                _contact_snapshot(1, 3, distance_m=-1e-6),
                _contact_snapshot(1, 4, distance_m=None),
            ],
            1,
        ),
    ],
)
def test_preexisting_contact_rule_rejects_deep_external_or_late_resolution(
    snapshots: list[dict[str, object]],
    first_changed: int,
) -> None:
    result = setup_gateway._classify_contact_snapshots(
        snapshots,
        first_changed_sample_index=first_changed,
    )
    assert result["passed"] is False
    assert int(result["forbidden_robot_contact_count"]) > 0


def test_rate_gate_is_rechecked_per_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, physical, _, _ = _fixture(
        tmp_path,
        monkeypatch,
        unsafe_rate=True,
    )
    with pytest.raises(
        GeometricPhysicalGatewayError,
        match="rate limits",
    ):
        compile_geometric_setup_phase_packet(
            compile_inputs,
            1,
            tmp_path / "phase-1.json",
            preflight_fn=lambda: _preflight(physical[0]),
            preview_fn=_preview,
        )


def test_each_later_phase_requires_torque_off_previous_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, physical, _, segments = _fixture(tmp_path, monkeypatch)
    packet_1_path = tmp_path / "phase-1.json"
    packet_1 = compile_geometric_setup_phase_packet(
        compile_inputs,
        1,
        packet_1_path,
        preflight_fn=lambda: _preflight(physical[0]),
        preview_fn=_preview,
    )
    review_1_path = tmp_path / "phase-1-review.json"
    review_1 = review_geometric_setup_phase_packet(
        packet_1_path,
        review_1_path,
        reviewer="fixture-reviewer",
        decision_id="phase-1",
        preview_fn=_preview,
    )
    assert review_1["schema_version"] == SETUP_REVIEW_SCHEMA

    gateway = _Gateway(physical[0])
    preflights = iter(
        [
            _preflight(physical[0]),
            _preflight(physical[2]),
        ]
    )
    execution_1 = execute_geometric_setup_phase_packet(
        packet_1_path,
        review_1_path,
        tmp_path / "phase-1-execution",
        operator_acknowledged=True,
        preflight_fn=lambda: next(preflights),
        gateway_factory=lambda identity: gateway,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )
    assert execution_1["schema_version"] == SETUP_EXECUTION_SCHEMA
    assert execution_1["physical_follower_torque_enabled"] is False
    assert execution_1["stop_before_next_phase"] is True
    assert gateway.closed

    with pytest.raises(
        GeometricPhysicalGatewayError,
        match="requires phase 1 receipt",
    ):
        compile_geometric_setup_phase_packet(
            compile_inputs,
            2,
            tmp_path / "phase-2-without-receipt.json",
            preflight_fn=lambda: _preflight(physical[3]),
            preview_fn=_preview,
        )

    receipt_path = (
        tmp_path / "phase-1-execution" / "execution_receipt.json"
    )
    packet_2 = compile_geometric_setup_phase_packet(
        compile_inputs,
        2,
        tmp_path / "phase-2.json",
        previous_execution_path=receipt_path,
        preflight_fn=lambda: _preflight(physical[3]),
        preview_fn=_preview,
    )
    assert packet_2["phase_index"] == 2
    assert packet_2["previous_phase_execution"]["sha256"] == sha256_file(
        receipt_path
    )
    assert packet_2["phase_origin_physical_units"] == segments[1][
        "origin_physical_units"
    ]
    assert packet_1["task_binding"]["source_action_sha256"] == packet_2[
        "task_binding"
    ]["source_action_sha256"]


def test_execution_stall_closes_gateway_and_leaves_no_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_inputs, physical, _, _ = _fixture(tmp_path, monkeypatch)
    packet_path = tmp_path / "phase-1.json"
    compile_geometric_setup_phase_packet(
        compile_inputs,
        1,
        packet_path,
        preflight_fn=lambda: _preflight(physical[0]),
        preview_fn=_preview,
    )
    review_path = tmp_path / "review.json"
    review_geometric_setup_phase_packet(
        packet_path,
        review_path,
        reviewer="fixture-reviewer",
        decision_id="stall-test",
        preview_fn=_preview,
    )
    gateway = _Gateway(physical[0], stall=True)
    preflights = iter(
        [
            _preflight(physical[0]),
            _preflight(physical[0]),
        ]
    )
    output = tmp_path / "execution"
    with pytest.raises(
        GeometricPhysicalGatewayError,
        match="stopped safely with torque off",
    ):
        execute_geometric_setup_phase_packet(
            packet_path,
            review_path,
            output,
            operator_acknowledged=True,
            preflight_fn=lambda: next(preflights),
            gateway_factory=lambda identity: gateway,
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )
    assert gateway.closed
    assert not (output / "execution_receipt.json").exists()
