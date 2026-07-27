from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.geometric_physical_gateway import (
    EXECUTION_SCHEMA,
    PACKET_SCHEMA,
    REVIEW_SCHEMA,
    GeometricPhysicalGatewayError,
    _excursion_audit,
    compile_geometric_physical_packet,
    execute_geometric_physical_packet,
    review_geometric_physical_packet,
)
from sim2claw.pawn_source_evaluator import (
    evaluator_path_for_scene,
    pawn_evaluator_sha256,
)
from sim2claw.physical_canary import EXCITATION_CONTROL_SOURCE, GATEWAY_SCHEMA
from sim2claw.recorded_replay import canonical_json_sha256
from sim2claw.scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
)
from sim2claw.source_episode import (
    ADMISSION_SCHEMA,
    CONTRACT_PATH_V3,
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    EPISODE_SCHEMA,
    RECEIPT_SCHEMA,
    SAMPLE_SCHEMA,
    admission_payload_sha256,
    sha256_file,
    source_contract_sha256,
    tree_manifest,
)


PORT = "/dev/follower-geometric-fixture"
CALIBRATION = "a" * 64


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _config() -> dict[str, object]:
    path = Path("configs/sysid/recorded_action_sysid_v1.json")
    config = json.loads(path.read_text(encoding="utf-8"))
    transform = config["physical_adapter"]["joint_transform"]
    transform["calibration_approved"] = True
    transform["review_status"] = "approved_physical_fixture"
    transform["review"] = {
        "reviewer": "fixture-metrology-reviewer",
        "reviewed_at": "2026-07-26T00:00:00Z",
        "decision_id": "fixture-transform-review",
        "evidence_sha256": "b" * 64,
    }
    config["physical_adapter"]["joint_transform_sha256"] = canonical_json_sha256(
        transform
    )
    return config


def _model_actions_from_physical(
    physical: np.ndarray, config: dict[str, object]
) -> np.ndarray:
    entries = config["physical_adapter"]["joint_transform"]["joints"]
    model = np.empty(physical.shape, dtype="<f4")
    for index, entry in enumerate(entries):
        model[:, index] = (
            physical[:, index] * float(entry["sign"]) * float(entry["scale"])
            + float(entry["zero_offset"])
        ).astype("<f4")
    return model


def _episode(
    root: Path, config: dict[str, object]
) -> tuple[Path, Path, np.ndarray]:
    directory = root / "episode"
    directory.mkdir()
    intended_physical = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 20.0],
            [0.5, -0.5, 0.25, -0.25, 0.5, 22.0],
            [1.0, -1.0, 0.5, -0.5, 1.0, 24.0],
        ],
        dtype=np.float64,
    )
    actions = _model_actions_from_physical(intended_physical, config)
    rows: list[dict[str, object]] = []
    privileged: list[dict[str, object]] = []
    for index, action in enumerate(actions):
        timestamp = index / 20.0
        row: dict[str, object] = {
            "schema_version": SAMPLE_SCHEMA,
            "episode_id": "geometric-fixture",
            "sample_index": index,
            "timestamp_monotonic_seconds": timestamp,
            "language_instruction": (
                "Pick up the tan pawn on c8 and place it upright on a6."
            ),
            "rgb": {},
            "robot": {
                "joint_position_rad": action.astype(float).tolist(),
                "joint_velocity_rad_s": [0.0] * 6,
                "end_effector_pose_world": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                "gripper_joint_position_rad": float(action[5]),
            },
            "goal": {
                "selected_piece_pose_world": [
                    0.0,
                    0.0,
                    0.8,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                ],
                "continuous_target_pose_world": [
                    0.0,
                    0.0,
                    0.8,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                ],
            },
            "action": {
                "representation": "absolute_joint_position_target",
                "joint_target_rad": action.astype(float).tolist(),
                "owner": "geometric_expert",
                "assistance": 0,
                "intervention": 0,
            },
            "events": {"contacts": [], "simulator_events": []},
            "evaluator_privileged_state": {
                "inline": False,
                "path": "evaluator_privileged_state.jsonl",
                "row_index": index,
            },
        }
        for stream in ("top", "wrist"):
            frame_path = directory / "rgb" / stream / f"{index:06d}.png"
            frame_path.parent.mkdir(parents=True, exist_ok=True)
            frame_path.write_bytes(f"{stream}-{index}".encode())
            row["rgb"][stream] = {
                "available": True,
                "path": frame_path.relative_to(directory).as_posix(),
                "timestamp_monotonic_seconds": timestamp,
                "sha256": sha256_file(frame_path),
            }
        rows.append(row)
        privileged.append(
            {
                "schema_version": "sim2claw.evaluator_privileged_state.v1",
                "episode_id": "geometric-fixture",
                "sample_index": index,
                "timestamp_monotonic_seconds": timestamp,
                "policy_adapter_access": False,
                "state": {"integration_state_float64": [0.0]},
            }
        )
    samples_path = directory / "samples.jsonl"
    samples_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    privileged_path = directory / "evaluator_privileged_state.jsonl"
    privileged_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in privileged),
        encoding="utf-8",
    )
    initial_path = directory / "initial_evaluator_privileged_state.json"
    _write(
        initial_path,
        {
            "schema_version": "sim2claw.evaluator_initial_privileged_state.v1",
            "episode_id": "geometric-fixture",
            "policy_adapter_access": False,
            "state": {"integration_state_float64": [0.0]},
        },
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "source_episode_schema": EPISODE_SCHEMA,
        "source_contract_sha256": source_contract_sha256(CONTRACT_PATH_V3),
        "task_id": "chess_pick_place_source_episode_v3",
        "recording_id": "geometric-fixture",
        "sample_count": len(rows),
        "sample_hz": 20,
        "piece_id": "tan_pawn_c8",
        "destination_square": "a6",
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
        "initial_layout_id": CURRENT_TASK_LAYOUT_ID,
        "samples_sha256": sha256_file(samples_path),
        "evaluator_privileged_state_path": privileged_path.name,
        "evaluator_privileged_state_sha256": sha256_file(privileged_path),
        "initial_evaluator_privileged_state_path": initial_path.name,
        "initial_evaluator_privileged_state_sha256": sha256_file(initial_path),
        "rgb_streams": tree_manifest(directory / "rgb"),
    }
    receipt_path = directory / "recording_receipt.json"
    _write(receipt_path, receipt)

    evaluator_path = evaluator_path_for_scene(
        CURRENT_SCENE_ID,
        source_contract_id="chess_pick_place_source_episode_v3",
    )
    from sim2claw.geometric_physical_gateway import _evaluator_identity

    verdict = {
        "schema_version": ADMISSION_SCHEMA,
        "evaluator_contract_sha256": pawn_evaluator_sha256(evaluator_path),
        "evaluator_identity": _evaluator_identity(),
        "source_recording_id": "geometric-fixture",
        "source_receipt_sha256": sha256_file(receipt_path),
        "source_samples_sha256": receipt["samples_sha256"],
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "selected_piece_id": "tan_pawn_c8",
        "strict_success": True,
        "terminal_outcome": "pawn_released_upright_on_target",
        "held_out_membership": False,
        "exact_float32_sample_hold_replay_passed": True,
        "physics_steps_per_action": 10,
        "assistance_frames": 0,
        "admission_class": "ordinary_strict_success",
        "all_source_actions_admitted": True,
    }
    verdict["canonical_payload_sha256"] = admission_payload_sha256(verdict)
    verdict_path = directory / "admission_verdict.json"
    _write(verdict_path, verdict)
    return directory, verdict_path, actions


def _manifest(
    path: Path,
    config: dict[str, object],
    *,
    approved: bool = True,
) -> Path:
    transform = config["physical_adapter"]["joint_transform"]
    transform["calibration_approved"] = approved
    if not approved:
        transform.pop("review", None)
        transform["review_status"] = "provisional_range_audit_blocked"
    config["physical_adapter"]["joint_transform_sha256"] = canonical_json_sha256(
        transform
    )
    _write(
        path,
        {
            "schema_version": "sim2claw.geometry_timing_twin_candidate.v1",
            "candidate_digest": "d" * 64,
            "candidate_config": config,
            "candidate_config_sha256": canonical_json_sha256(config),
            "identity": {
                "robot": {
                    "gateway_schema": GATEWAY_SCHEMA,
                    "follower_port": PORT,
                    "follower_calibration_sha256": CALIBRATION,
                }
            },
            "sources": {
                "p13_transform": {"sha256": "e" * 64},
                "p13_board_fit": {"sha256": "f" * 64},
            },
            "geometry_provenance": {
                "metric_geometry_available": True,
                "physical_promotion_requires_p13": False,
                "workcell_registration": {
                    "board_scene_id": CURRENT_SCENE_ID,
                    "board_pose_id": CURRENT_BOARD_POSE_ID,
                },
            },
        },
    )
    return path


def _inverse_first(
    source_actions: np.ndarray, config: dict[str, object]
) -> np.ndarray:
    result = np.empty(6, dtype=np.float64)
    for index, entry in enumerate(
        config["physical_adapter"]["joint_transform"]["joints"]
    ):
        result[index] = (
            float(source_actions[0, index]) - float(entry["zero_offset"])
        ) / (float(entry["sign"]) * float(entry["scale"]))
    return result


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
    raw = actions.astype("<f4", copy=False).tobytes(order="C")
    import hashlib

    return {
        "runtime": "fixture_mj_forward",
        "sample_count": len(actions),
        "exact_source_action_sha256": hashlib.sha256(raw).hexdigest(),
        "passed": True,
        "forbidden_robot_contact_count": 0,
    }


def _compiled(
    tmp_path: Path,
) -> tuple[Path, Path, np.ndarray, dict[str, object]]:
    config = _config()
    episode, verdict, source_actions = _episode(tmp_path, config)
    manifest = _manifest(tmp_path / "candidate.json", config)
    start = _inverse_first(source_actions, config)
    packet_path = tmp_path / "packet.json"
    packet = compile_geometric_physical_packet(
        episode,
        verdict,
        manifest,
        packet_path,
        preflight_fn=lambda: _preflight(start),
        preview_fn=_preview,
    )
    return packet_path, manifest, start, packet


def test_compile_freezes_exact_inverse_mapping_and_lineage(tmp_path: Path) -> None:
    packet_path, _, _, packet = _compiled(tmp_path)
    assert packet_path.is_file()
    assert packet["schema_version"] == PACKET_SCHEMA
    assert packet["source_episode"]["recording_id"] == "geometric-fixture"
    assert packet["physical_joint_transform"]["calibration_approved"] is True
    assert packet["rate_audit"]["all_rates_within_reviewed_gateway_limits"]
    assert packet["excursion_audit"][
        "all_excursions_within_reviewed_gateway_limits"
    ]
    source = np.frombuffer(
        __import__("base64").b64decode(packet["source_action_payload"]["base64"]),
        dtype="<f4",
    ).reshape(packet["source_action_payload"]["shape"])
    physical = np.frombuffer(
        __import__("base64").b64decode(
            packet["frozen_physical_action_payload"]["base64"]
        ),
        dtype="<f8",
    ).reshape(packet["frozen_physical_action_payload"]["shape"])
    assert source.shape == physical.shape == (3, 6)
    assert np.max(np.abs(physical[:, :5])) <= 1.00001
    assert np.allclose(physical[:, 5], [20.0, 22.0, 24.0], atol=1e-5)
    assert packet["physical_motion_commanded"] is False


def test_excursion_audit_rejects_body_motion_beyond_session_origin() -> None:
    actions = np.zeros((3, 6), dtype=np.float64)
    actions[1, 3] = 90.0
    actions[2, 3] = 90.0001
    with pytest.raises(
        GeometricPhysicalGatewayError, match="per-session excursion"
    ):
        _excursion_audit(actions)


def test_excursion_audit_uses_shortest_wrist_roll_delta() -> None:
    actions = np.zeros((2, 6), dtype=np.float64)
    actions[0, 4] = -179.0
    actions[1, 4] = 179.0
    audit = _excursion_audit(actions)
    assert audit["maximum_absolute_excursion_from_origin"][4] == pytest.approx(2.0)
    assert audit["wrist_roll_uses_shortest_angular_delta"] is True


def test_compile_rejects_unapproved_transform_before_hardware_read(
    tmp_path: Path,
) -> None:
    config = _config()
    episode, verdict, _ = _episode(tmp_path, config)
    manifest = _manifest(
        tmp_path / "candidate.json", config, approved=False
    )
    hardware_read = False

    def preflight() -> dict[str, object]:
        nonlocal hardware_read
        hardware_read = True
        raise AssertionError("must reject before hardware")

    with pytest.raises(
        GeometricPhysicalGatewayError, match="not calibration-approved"
    ):
        compile_geometric_physical_packet(
            episode,
            verdict,
            manifest,
            tmp_path / "packet.json",
            preflight_fn=preflight,
            preview_fn=_preview,
        )
    assert hardware_read is False


def test_compile_rejects_missing_metric_p13_before_hardware_read(
    tmp_path: Path,
) -> None:
    config = _config()
    episode, verdict, _ = _episode(tmp_path, config)
    manifest_path = _manifest(tmp_path / "candidate.json", config)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sources"] = {}
    manifest["geometry_provenance"] = {
        "metric_geometry_available": False,
        "physical_promotion_requires_p13": True,
    }
    _write(manifest_path, manifest)
    with pytest.raises(
        GeometricPhysicalGatewayError, match="metric P13"
    ):
        compile_geometric_physical_packet(
            episode,
            verdict,
            manifest_path,
            tmp_path / "packet.json",
            preflight_fn=lambda: pytest.fail("must reject before hardware"),
            preview_fn=_preview,
        )


def test_review_rejects_source_drift(tmp_path: Path) -> None:
    packet_path, _, _, _ = _compiled(tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    samples_path = Path(packet["source_episode"]["directory"]) / "samples.jsonl"
    samples_path.write_text(samples_path.read_text(encoding="utf-8") + "\n")
    with pytest.raises(
        (GeometricPhysicalGatewayError, ValueError),
        match="samples|drift",
    ):
        review_geometric_physical_packet(
            packet_path,
            tmp_path / "review.json",
            reviewer="independent-fixture",
            decision_id="fixture-drift",
            preview_fn=_preview,
        )


class _Gateway:
    def __init__(self, start: np.ndarray, *, stall: bool = False) -> None:
        self.start = start
        self.stall = stall
        self.closed = False
        self.samples: list[np.ndarray] = []

    def open(
        self, *, enable_motion: bool, paired_pose_confirmed: bool
    ) -> dict[str, object]:
        assert enable_motion and paired_pose_confirmed
        return {"follower_start_degrees": self.start.tolist()}

    def sample(
        self, timestamp: float, *, exact_requested_degrees: np.ndarray
    ) -> dict[str, object]:
        del timestamp
        self.samples.append(exact_requested_degrees.copy())
        values = exact_requested_degrees.tolist()
        stalled = self.stall and len(self.samples) == 1
        return {
            "follower_requested_degrees": values,
            "follower_command_degrees": values,
            "follower_actual_position_degrees": values,
            "tracking_error_limits": [10.0] * 6,
            "rate_limited": False,
            "safety_clamped": False,
            "stalled": stalled,
            "stalled_joints": ["shoulder_pan"] if stalled else [],
            "gripper_contact_hold": False,
        }

    def close(self) -> None:
        self.closed = True


class _Capture:
    def __init__(self) -> None:
        self.finished = False

    def start(self) -> dict[str, object]:
        return {
            "status": "recording",
            "overhead": {"status": "recording"},
            "wrist": {"status": "recording"},
        }

    def finish(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        self.finished = True
        return {
            "overhead": {"status": "completed", "container_frame_count": 3},
            "wrist": {"status": "completed", "container_frame_count": 2},
        }


def test_review_and_execute_use_exact_bytes_and_torque_off_postflight(
    tmp_path: Path,
) -> None:
    packet_path, _, start, packet = _compiled(tmp_path)
    review_path = tmp_path / "review.json"
    review = review_geometric_physical_packet(
        packet_path,
        review_path,
        reviewer="independent-fixture",
        decision_id="fixture-admit",
        preview_fn=_preview,
    )
    assert review["schema_version"] == REVIEW_SCHEMA
    gateway = _Gateway(start)
    capture = _Capture()
    result = execute_geometric_physical_packet(
        packet_path,
        review_path,
        tmp_path / "execution",
        operator_acknowledged=True,
        preflight_fn=lambda: _preflight(start),
        gateway_factory=lambda identity: gateway,
        capture_factory=lambda path: capture,
        clock_fn=lambda: 0.0,
        sleep_fn=lambda delay: None,
    )
    assert result["schema_version"] == EXECUTION_SCHEMA
    assert result["completed_samples"] == 3
    assert result["physical_action_sha256"] == packet[
        "frozen_physical_action_payload"
    ]["sha256"]
    assert result["physical_follower_torque_enabled"] is False
    assert result["physical_task_consequence_admitted"] is False
    assert gateway.closed and capture.finished


def test_execution_stall_fails_closed_and_finishes_capture(tmp_path: Path) -> None:
    packet_path, _, start, _ = _compiled(tmp_path)
    review_path = tmp_path / "review.json"
    review_geometric_physical_packet(
        packet_path,
        review_path,
        reviewer="independent-fixture",
        decision_id="fixture-stall",
        preview_fn=_preview,
    )
    gateway = _Gateway(start, stall=True)
    capture = _Capture()
    with pytest.raises(
        GeometricPhysicalGatewayError, match="stopped safely with torque off"
    ):
        execute_geometric_physical_packet(
            packet_path,
            review_path,
            tmp_path / "execution",
            operator_acknowledged=True,
            preflight_fn=lambda: _preflight(start),
            gateway_factory=lambda identity: gateway,
            capture_factory=lambda path: capture,
            clock_fn=lambda: 0.0,
            sleep_fn=lambda delay: None,
        )
    assert gateway.closed and capture.finished
    assert not (tmp_path / "execution" / "execution_receipt.json").exists()
