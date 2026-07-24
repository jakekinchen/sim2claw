from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.hil_identifiability import (
    EVALUATION_SCHEMA,
    RAW_RECEIPT_SCHEMA,
    action_tensor_sha256,
    evaluate_hil_packet,
    load_hil_contract,
    materialize_packet_actions,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "current_100mm_hil_identifiability_v1.json"
)
CONTRACT_V2 = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "current_100mm_hil_multilevel_v2.json"
)
START = np.asarray([-4.0, -106.0, 100.0, -10.0, -95.0, 2.0])


def test_all_four_packets_are_deterministic_and_return_byte_exactly() -> None:
    contract = load_hil_contract(CONTRACT)
    hashes: set[str] = set()
    for packet in contract["packets"]:
        timestamps, actions = materialize_packet_actions(
            contract,
            packet["packet_id"],
            START,
        )
        repeated_timestamps, repeated_actions = materialize_packet_actions(
            contract,
            packet["packet_id"],
            START,
        )
        assert actions.dtype == np.dtype("<f8")
        assert actions.flags["C_CONTIGUOUS"]
        assert np.array_equal(timestamps, repeated_timestamps)
        assert np.array_equal(actions, repeated_actions)
        assert np.array_equal(actions[0], START)
        assert np.array_equal(actions[-1], START)
        assert np.all(np.diff(timestamps) > 0.0)
        hashes.add(action_tensor_sha256(actions))
    assert len(hashes) == 4


def test_v2_covers_all_six_joints_and_returns_byte_exactly() -> None:
    contract = load_hil_contract(CONTRACT_V2)
    assert [row["target_joint"] for row in contract["packets"]] == [
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    ]
    hashes: set[str] = set()
    for packet in contract["packets"]:
        timestamps, actions = materialize_packet_actions(
            contract,
            packet["packet_id"],
            START,
        )
        repeated_timestamps, repeated_actions = materialize_packet_actions(
            contract,
            packet["packet_id"],
            START,
        )
        joint_index = contract["action_materialization"]["joint_order"].index(
            packet["target_joint"]
        )
        assert np.array_equal(timestamps, repeated_timestamps)
        assert np.array_equal(actions, repeated_actions)
        assert np.array_equal(actions[0], START)
        assert np.array_equal(actions[-1], START)
        assert np.max(actions[:, joint_index]) - np.min(
            actions[:, joint_index]
        ) >= packet["required_position_span"]
        untouched = [index for index in range(6) if index != joint_index]
        assert np.array_equal(
            actions[:, untouched],
            np.repeat(START[None, untouched], actions.shape[0], axis=0),
        )
        hashes.add(action_tensor_sha256(actions))
    assert len(hashes) == 6


def _write_video_report(path: Path, *, fps: int, duration: float) -> None:
    frames = round(fps * duration)
    path.write_text(
        json.dumps(
            {
                "status": "completed",
                "observed_video": {
                    "streams": [{"nb_frames": str(frames)}],
                    "format": {"duration": str(duration)},
                    "container_timing": {
                        "schema_version": "sim2claw.video_container_timing.v1",
                        "status": "observed_container_timing",
                        "frame_count": frames,
                        "inferred_missing_frame_intervals": 0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _packet_fixture(
    root: Path,
    *,
    contract_path: Path = CONTRACT,
    packet_id: str = "HIL-GRIPPER-05",
) -> tuple[Path, Path]:
    contract = load_hil_contract(contract_path)
    timestamps, actions = materialize_packet_actions(contract, packet_id, START)
    session = root / packet_id
    source = session / "source"
    replay = session / "replay"
    source.mkdir(parents=True)
    replay.mkdir()
    np.save(source / "action_tensor.npy", actions, allow_pickle=False)
    rows = []
    for index, action in enumerate(actions):
        refresh_index = index // 4
        rows.append(
            {
                "schema_version": "sim2claw.physical_trace_replay_attempt.v1",
                "replay_phase": "source_trace",
                "requested_source_command_degrees": action.tolist(),
                "follower_command_degrees": action.tolist(),
                "follower_actual_position_degrees": action.tolist(),
                "available_motor_current_raw": {
                    "gripper": float(refresh_index % 7)
                },
                "current_telemetry_elapsed_seconds": refresh_index / 5.0,
                "current_telemetry_stale": False,
                "bus_read_retries_total": 0,
                "stalled": False,
            }
        )
    (replay / "replay_samples.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (replay / "replay_receipt.json").write_text(
        json.dumps({"status": "completed"}),
        encoding="utf-8",
    )
    duration = float(timestamps[-1])
    _write_video_report(session / "overhead_video.json", fps=30, duration=duration)
    _write_video_report(session / "wrist_video.json", fps=5, duration=duration)
    raw = {
        "schema_version": RAW_RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "packet_id": packet_id,
        "action_tensor_sha256": action_tensor_sha256(actions),
        "replay_receipt_path": str(replay / "replay_receipt.json"),
        "artifact_sha256": {},
    }
    raw_path = session / "raw_receipt.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    return raw_path, replay / "replay_samples.jsonl"


def test_evaluator_admits_only_raw_action_identical_dual_camera_packet(
    tmp_path: Path,
) -> None:
    raw_path, _ = _packet_fixture(tmp_path)
    evaluation = evaluate_hil_packet(raw_path, CONTRACT)
    assert evaluation["schema_version"] == EVALUATION_SCHEMA
    assert evaluation["verdict"] == "admit_unloaded_joint_measurement"
    assert evaluation["admitted"] is True
    assert evaluation["failures"] == []
    assert evaluation["authority"]["task_success"] is False
    assert evaluation["authority"]["training"] is False
    assert evaluation["authority"]["promotion"] is False


def test_evaluator_rejects_action_substitution_and_missing_wrist(
    tmp_path: Path,
) -> None:
    raw_path, samples_path = _packet_fixture(tmp_path)
    rows = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[10]["requested_source_command_degrees"][5] += 1.0
    samples_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (raw_path.parent / "wrist_video.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    evaluation = evaluate_hil_packet(raw_path, CONTRACT)
    assert evaluation["admitted"] is False
    assert "requested_action_bytes_changed" in evaluation["failures"]
    assert "wrist_video_not_completed" in evaluation["failures"]
    assert "wrist_frame_coverage_failed" in evaluation["failures"]


def test_evaluator_rejects_unverified_return_and_stale_current(
    tmp_path: Path,
) -> None:
    raw_path, samples_path = _packet_fixture(tmp_path)
    rows = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[-1]["follower_actual_position_degrees"][1] += 5.0
    for row in rows:
        row["current_telemetry_stale"] = True
    samples_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    evaluation = evaluate_hil_packet(raw_path, CONTRACT)
    assert evaluation["admitted"] is False
    assert "body_return_residual_exceeded" in evaluation["failures"]
    assert "current_refresh_coverage_failed" in evaluation["failures"]


def test_evaluator_rejects_replay_path_outside_packet(tmp_path: Path) -> None:
    raw_path, _ = _packet_fixture(tmp_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    raw["replay_receipt_path"] = str(outside)
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    try:
        evaluate_hil_packet(raw_path, CONTRACT)
    except Exception as error:
        assert "inside its packet directory" in str(error)
    else:
        raise AssertionError("outside replay path was not rejected")


def test_evaluator_uses_verified_wrist_derivative_frame_count(tmp_path: Path) -> None:
    raw_path, _ = _packet_fixture(tmp_path)
    wrist_path = raw_path.parent / "wrist_video.json"
    wrist = json.loads(wrist_path.read_text(encoding="utf-8"))
    wrist["observed_video"]["streams"][0].pop("nb_frames")
    wrist["browser_video_path"] = "wrist_d405.browser.mp4"
    wrist["browser_observed_video"] = {
        "streams": [{"nb_frames": "1000"}],
        "format": {"duration": "200.0"},
    }
    wrist_path.write_text(json.dumps(wrist), encoding="utf-8")
    evaluation = evaluate_hil_packet(raw_path, CONTRACT)
    assert evaluation["admitted"] is True
    assert evaluation["camera_metrics"]["wrist"]["frames"] == 1000


def test_v2_evaluator_fails_closed_without_wrist_container_timing(
    tmp_path: Path,
) -> None:
    raw_path, _ = _packet_fixture(
        tmp_path,
        contract_path=CONTRACT_V2,
        packet_id="HIL2-GRIPPER-MULTILEVEL",
    )
    wrist_path = raw_path.parent / "wrist_video.json"
    wrist = json.loads(wrist_path.read_text(encoding="utf-8"))
    wrist["observed_video"].pop("container_timing")
    wrist_path.write_text(json.dumps(wrist), encoding="utf-8")

    evaluation = evaluate_hil_packet(raw_path, CONTRACT_V2)

    assert evaluation["admitted"] is False
    assert "wrist_container_timing_unavailable" in evaluation["failures"]
    assert "wrist_container_timing_gap_fraction_failed" in evaluation["failures"]
    assert (
        evaluation["camera_metrics"]["wrist"][
            "inferred_missing_frame_interval_fraction"
        ]
        is None
    )
