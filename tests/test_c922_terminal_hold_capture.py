from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sim2claw.c922_terminal_hold_capture import (
    C922TerminalHoldCaptureError,
    CONTRACT_PATH,
    orchestrate_c922_terminal_hold_capture,
)
from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.replay_eligibility import action_sha256


SESSION = "fixture-session-unchanged"
MOUNT = "fixture-mount-untouched"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _camera_record(contract: dict[str, object]) -> dict[str, object]:
    camera = contract["camera"]
    return {
        "cameraName": camera["localized_name"],
        "cameraUniqueID": camera["unique_id"],
        "cameraModelID": camera["model_id"],
        "width": 640,
        "height": 480,
        "mediaSubtype": "420v",
        "pixelFormat": "420v",
        "cameraSessionToken": SESSION,
        "fixedMountToken": MOUNT,
    }


class _Recorder:
    started = False
    host_ns = 101_000_000_000

    def __init__(
        self,
        output_root: Path,
        *,
        contract: dict[str, object],
        camera_session_token: str,
        fixed_mount_token: str,
    ) -> None:
        assert camera_session_token == SESSION
        assert fixed_mount_token == MOUNT
        self.root = output_root
        self.contract = contract

    def start(self) -> dict[str, object]:
        self.root.mkdir(parents=True)
        (self.root / "frames").mkdir()
        type(self).started = True
        return {**_camera_record(self.contract), "status": "ready"}

    def finish(self) -> dict[str, object]:
        assert self.started
        image = self.root / "frames/frame-001.png"
        Image.new("RGB", (640, 480), (10, 20, 30)).save(image)
        event = {
            "schemaVersion": "sim2claw.c922_terminal_hold_frame_event.v1",
            "sequence": 1,
            "hostContinuousNS": type(self).host_ns,
            "ptsSeconds": 5.0,
            "durationSeconds": 1 / 30,
            "width": 640,
            "height": 480,
            "mediaSubtype": "420v",
            "pixelFormat": "420v",
            "cameraName": self.contract["camera"]["localized_name"],
            "cameraUniqueID": self.contract["camera"]["unique_id"],
            "cameraModelID": self.contract["camera"]["model_id"],
            "pngPath": "frames/frame-001.png",
            "pngSHA256": sha256_file(image),
            "cameraSessionToken": SESSION,
            "fixedMountToken": MOUNT,
        }
        ledger = self.root / "frames.jsonl"
        ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
        final = self.root / "final.json"
        _write(final, {"status": "completed"})
        return {
            **_camera_record(self.contract),
            "status": "completed",
            "ledger_path": str(ledger),
            "ledger_sha256": sha256_file(ledger),
            "final_path": str(final),
            "final_sha256": sha256_file(final),
        }


def _route_executor(
    *,
    mismatch: bool = False,
    torque_off: bool = True,
    observed_stop: bool = False,
    **kwargs: object,
) -> dict[str, object]:
    assert _Recorder.started
    output = Path(kwargs["output_root"])
    output.mkdir(parents=True)
    actions = (
        np.linspace(
            np.asarray([-18.0, -61.0, 100.0, 24.0, -75.0, 3.0]),
            np.asarray([-20.0, -63.0, 20.0, 88.0, -74.0, 3.0]),
            100,
            dtype=np.float64,
        ).astype("<f8")
        if observed_stop
        else np.repeat(
            np.asarray([[-20.0, -63.0, 35.0, 88.0, -74.0, 3.0]], dtype="<f8"),
            80,
            axis=0,
        )
    )
    stop_index = 49
    expected_executed = (
        np.concatenate(
            [
                actions[: stop_index + 1],
                np.repeat(actions[stop_index][None, :], 80, axis=0),
            ]
        ).astype("<f8")
        if observed_stop
        else actions
    )
    executed_actions = expected_executed + (1.0 if mismatch else 0.0)
    planned = output / "actions.float64le"
    executed = output / "executed_actions.float64le"
    planned.write_bytes(actions.tobytes())
    executed.write_bytes(
        executed_actions.astype("<f8").tobytes()
    )
    telemetry = output / "telemetry.jsonl"
    telemetry.write_text(
        "\n".join(
            json.dumps(
                {
                    "setup_phase": "target_hold",
                    "follower_actual_position_degrees": expected_executed[-1].tolist(),
                    "safety_clamped": False,
                }
            )
            for index in range(80)
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        "status": "completed_live_anchored_camera_reposition",
        "shutdown_torque_off_confirmed": torque_off,
        "physical_follower_torque_enabled": False if torque_off else True,
        "trajectory": {
            "action_sha256": action_sha256(actions),
            "executed_action_sha256": action_sha256(executed_actions),
            "action_bytes_path": str(planned),
            "action_bytes_sha256": sha256_file(planned),
            "executed_action_bytes_path": str(executed),
            "executed_action_bytes_sha256": sha256_file(executed),
            "target_hold_sample_count": 80,
            "executed_movement_prefix_sample_count": (
                stop_index + 1 if observed_stop else len(actions)
            ),
        },
        "observed_pose_termination": (
            {
                "configured": True,
                "reached": True,
                "planned_full_path_was_cpu_previewed": True,
                "executed_path_is_safe_prefix_plus_exact_terminal_hold": True,
                "stop": {
                    "planned_sample_index": stop_index,
                    "planned_motion_prefix_sha256": action_sha256(
                        actions[: stop_index + 1]
                    ),
                    "exact_command_sha256": action_sha256(
                        actions[stop_index : stop_index + 1]
                    ),
                },
            }
            if observed_stop
            else {"configured": False}
        ),
        "terminal_hold_monotonic_interval": {
            "start": 100.0,
            "end": 102.0,
            "exact_terminal_command_sha256": action_sha256(
                (
                    actions[stop_index : stop_index + 1]
                    if observed_stop
                    else actions[-1:]
                )
            ),
        },
        "telemetry": {"path": str(telemetry), "sha256": sha256_file(telemetry)},
    }
    _write(output / "execution_receipt.json", receipt)
    return receipt


def _run(tmp_path: Path, route_executor=_route_executor) -> dict[str, object]:
    _Recorder.started = False
    _Recorder.host_ns = 101_000_000_000
    return orchestrate_c922_terminal_hold_capture(
        output_root=tmp_path / "output",
        camera_session_token=SESSION,
        fixed_mount_token=MOUNT,
        operator_acknowledged=True,
        empty_gripper_confirmed=True,
        route_executor=route_executor,
        recorder_factory=_Recorder,
    )


def test_capture_starts_before_route_and_emits_hash_bound_pose_png(tmp_path: Path) -> None:
    receipt = _run(tmp_path)
    assert receipt["status"] == "completed"
    assert receipt["route"]["action_binding"]["mode"] == "complete_planned_path"
    assert receipt["route"]["shutdown_torque_off_confirmed"] is True
    assert receipt["selected_callback_event"]["hostContinuousNS"] == 101_000_000_000
    assert sha256_file(Path(receipt["selected_png"]["path"])) == receipt["selected_png"]["sha256"]
    pose = json.loads(Path(receipt["pose_receipt"]["path"]).read_text(encoding="utf-8"))
    assert pose["candidate_pose_id"] == "P0_v4_reached_observed_stop_diagnostic"
    assert pose["camera"]["image_sha256"] == receipt["selected_png"]["sha256"]
    assert pose["diagnostic_only"] is True
    assert pose["authority"] and not any(pose["authority"].values())
    assert receipt["annotation_performed"] is False
    assert receipt["fit_performed"] is False
    assert not any(receipt["authority"].values())


def test_observed_stop_accepts_only_planned_prefix_plus_exact_hold(
    tmp_path: Path,
) -> None:
    receipt = _run(
        tmp_path,
        route_executor=lambda **route: _route_executor(
            observed_stop=True, **route
        ),
    )
    binding = receipt["route"]["action_binding"]
    assert binding["mode"] == "cpu_previewed_planned_prefix_plus_exact_terminal_hold"
    assert binding["unused_planned_suffix_executed"] is False
    assert binding["executed_movement_prefix_sample_count"] == 50
    assert binding["terminal_hold_sample_count"] == 80
    assert binding["planned_full_action_sha256"] != binding["executed_action_sha256"]
    assert receipt["full_three_face_rank_eligible"] is False


@pytest.mark.parametrize("failure", ["bytes", "torque", "token", "empty"])
def test_capture_prerequisites_fail_closed(tmp_path: Path, failure: str) -> None:
    kwargs: dict[str, object] = {
        "output_root": tmp_path / "output",
        "camera_session_token": SESSION,
        "fixed_mount_token": MOUNT,
        "operator_acknowledged": True,
        "empty_gripper_confirmed": True,
        "recorder_factory": _Recorder,
    }
    if failure == "bytes":
        kwargs["route_executor"] = lambda **route: _route_executor(mismatch=True, **route)
        match = "planned and executed bytes differ"
    elif failure == "torque":
        kwargs["route_executor"] = lambda **route: _route_executor(torque_off=False, **route)
        match = "torque-off proof failed"
    elif failure == "token":
        kwargs["fixed_mount_token"] = ""
        match = "mount token is required"
    else:
        kwargs["empty_gripper_confirmed"] = False
        match = "empty gripper"
    _Recorder.started = False
    with pytest.raises(C922TerminalHoldCaptureError, match=match):
        orchestrate_c922_terminal_hold_capture(**kwargs)


def test_callback_outside_terminal_hold_fails_closed(tmp_path: Path) -> None:
    _Recorder.started = False
    _Recorder.host_ns = 103_000_000_000
    with pytest.raises(C922TerminalHoldCaptureError, match="inside terminal hold"):
        orchestrate_c922_terminal_hold_capture(
            output_root=tmp_path / "output",
            camera_session_token=SESSION,
            fixed_mount_token=MOUNT,
            operator_acknowledged=True,
            empty_gripper_confirmed=True,
            route_executor=_route_executor,
            recorder_factory=_Recorder,
        )


def test_contract_binds_one_frozen_route_and_all_authority_false() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    route = CONTRACT_PATH.parents[2] / contract["route"]["path"]
    assert sha256_file(route) == contract["route"]["sha256"]
    assert contract["camera"]["width"] == 640
    assert contract["camera"]["height"] == 480
    assert contract["camera"]["media_subtype_fourcc"] == "420v"
    assert contract["camera"]["supported_fps"] == pytest.approx(30.00003000003)
    assert not any(contract["authority"].values())
