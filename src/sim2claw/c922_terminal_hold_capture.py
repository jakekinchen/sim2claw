"""Capture one exact-mode C922 still inside a frozen route's terminal hold."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np
from PIL import Image

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .live_anchored_camera_reposition import execute_live_anchored_camera_reposition
from .paths import REPO_ROOT
from .replay_eligibility import action_sha256

CONTRACT_PATH = REPO_ROOT / "configs/evaluations/c922_terminal_hold_still_capture_v1.json"
CONTRACT_SCHEMA = "sim2claw.c922_terminal_hold_still_capture_contract.v1"
RECEIPT_SCHEMA = "sim2claw.c922_terminal_hold_still_capture_receipt.v1"
POSE_RECEIPT_SCHEMA = "sim2claw.c922_terminal_hold_pose_receipt.v1"
SWIFT_SOURCE = REPO_ROOT / "tools/macos/C922TerminalHoldStillCapture.swift"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)


class C922TerminalHoldCaptureError(RuntimeError):
    """The exact camera mode, route binding, timing, or torque-off proof failed."""


class Recorder(Protocol):
    def start(self) -> dict[str, Any]: ...
    def finish(self) -> dict[str, Any]: ...


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise C922TerminalHoldCaptureError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise C922TerminalHoldCaptureError(f"cannot read JSON {path}: {error}") from error
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _json(path)
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "unexpected capture contract")
    _require(
        contract.get("status") == "preregistered_before_capture_or_motion",
        "capture contract status widened",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "capture contract authority must remain false",
    )
    return contract


class NativeC922StillRecorder:
    """Compile and own one C922-only AVFoundation source-callback process."""

    def __init__(
        self,
        output_root: Path,
        *,
        contract: Mapping[str, Any],
        camera_session_token: str,
        fixed_mount_token: str,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.output_root = output_root
        self.contract = contract
        self.camera_session_token = camera_session_token
        self.fixed_mount_token = fixed_mount_token
        self.clock_fn = clock_fn
        self.process: subprocess.Popen[str] | None = None
        self.stderr_handle: Any = None
        self.stop_path = output_root / "stop.request"

    def start(self) -> dict[str, Any]:
        _require(not self.output_root.exists(), "capture output already exists")
        self.output_root.mkdir(parents=True)
        runtime = self.output_root / "runtime"
        runtime.mkdir()
        compiler = shutil.which("swiftc")
        _require(compiler is not None, "swiftc is unavailable")
        binary = runtime / "c922-terminal-hold-still"
        compiled = subprocess.run(
            [compiler, str(SWIFT_SOURCE), "-o", str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        _require(compiled.returncode == 0, f"C922 capture compilation failed: {compiled.stderr}")
        camera = self.contract["camera"]
        command = [
            str(binary),
            "--camera-name", camera["localized_name"],
            "--camera-unique-id", camera["unique_id"],
            "--camera-model-id", camera["model_id"],
            "--format-index", str(camera["format_index"]),
            "--range-index", str(camera["frame_rate_range_index"]),
            "--width", str(camera["width"]),
            "--height", str(camera["height"]),
            "--subtype", camera["media_subtype_fourcc"],
            "--supported-fps", str(camera["supported_fps"]),
            "--maximum-frames", str(self.contract["selection"]["maximum_ring_frames"]),
            "--session-token", self.camera_session_token,
            "--mount-token", self.fixed_mount_token,
            "--output-directory", str(self.output_root),
            "--stop-path", str(self.stop_path),
        ]
        stderr_path = self.output_root / "capture.stderr.log"
        self.stderr_handle = stderr_path.open("w", encoding="utf-8")
        start_lower = self.clock_fn()
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=self.stderr_handle,
            text=True,
        )
        start_upper = self.clock_fn()
        ready_path = self.output_root / "ready.json"
        deadline = self.clock_fn() + 6.0
        while self.clock_fn() < deadline and self.process.poll() is None:
            if ready_path.is_file():
                break
            time.sleep(0.02)
        _require(ready_path.is_file(), "C922 did not deliver an exact-mode source frame")
        ready = _json(ready_path)
        _validate_camera_record(ready, self.contract, self.camera_session_token, self.fixed_mount_token)
        return {
            **ready,
            "process_start_monotonic_bounds": [start_lower, start_upper],
            "ready_observed_monotonic": self.clock_fn(),
            "source_path": str(SWIFT_SOURCE),
            "source_sha256": sha256_file(SWIFT_SOURCE),
            "binary_path": str(binary),
            "binary_sha256": sha256_file(binary),
            "command": command,
        }

    def finish(self) -> dict[str, Any]:
        _require(self.process is not None, "C922 recorder was not started")
        self.stop_path.write_text("stop\n", encoding="utf-8")
        try:
            return_code = self.process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            self.process.kill()
            self.process.wait()
            raise C922TerminalHoldCaptureError("C922 recorder did not stop") from error
        finally:
            if self.stderr_handle is not None:
                self.stderr_handle.close()
        _require(return_code == 0, "C922 recorder exited unsuccessfully")
        final_path = self.output_root / "final.json"
        ledger_path = self.output_root / "frames.jsonl"
        _require(final_path.is_file() and ledger_path.is_file(), "C922 final artifacts are missing")
        return {
            **_json(self.output_root / "ready.json"),
            **_json(final_path),
            "final_path": str(final_path),
            "final_sha256": sha256_file(final_path),
            "ledger_path": str(ledger_path),
            "ledger_sha256": sha256_file(ledger_path),
        }


def _validate_camera_record(
    value: Mapping[str, Any],
    contract: Mapping[str, Any],
    camera_session_token: str,
    fixed_mount_token: str,
) -> None:
    camera = contract["camera"]
    expected = {
        "cameraName": camera["localized_name"],
        "cameraUniqueID": camera["unique_id"],
        "cameraModelID": camera["model_id"],
        "width": camera["width"],
        "height": camera["height"],
        "mediaSubtype": camera["media_subtype_fourcc"],
        "pixelFormat": camera["media_subtype_fourcc"],
        "cameraSessionToken": camera_session_token,
        "fixedMountToken": fixed_mount_token,
    }
    _require(all(value.get(key) == expected_value for key, expected_value in expected.items()), "C922 mode, identity, or fixed token drifted")
    if "supportedFPS" in value:
        _require(
            math.isclose(
                float(value["supportedFPS"]),
                float(camera["supported_fps"]),
                rel_tol=0.0,
                abs_tol=1e-6,
            ),
            "C922 frame-rate selection drifted",
        )
    if "durationSeconds" in value:
        _require(
            math.isclose(
                float(value["durationSeconds"]),
                float(camera["frame_duration_seconds"]),
                rel_tol=0.0,
                abs_tol=1e-6,
            ),
            "C922 callback frame duration drifted",
        )


def _validate_route_receipt(
    receipt: Mapping[str, Any], contract: Mapping[str, Any]
) -> tuple[int, int, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    _require(
        receipt.get("status") == "completed_live_anchored_camera_reposition"
        and receipt.get("shutdown_torque_off_confirmed") is True
        and receipt.get("physical_follower_torque_enabled") is False,
        "route success or torque-off proof failed",
    )
    trajectory = receipt.get("trajectory")
    _require(isinstance(trajectory, dict), "route trajectory receipt is missing")
    planned = Path(str(trajectory.get("action_bytes_path", "")))
    executed = Path(str(trajectory.get("executed_action_bytes_path", "")))
    _require(planned.is_file() and executed.is_file(), "planned or executed action bytes are missing")
    planned_bytes, executed_bytes = planned.read_bytes(), executed.read_bytes()
    _require(
        sha256_file(planned) == trajectory.get("action_bytes_sha256")
        and sha256_file(executed) == trajectory.get("executed_action_bytes_sha256"),
        "planned or executed action byte hash drifted",
    )
    try:
        planned_actions = np.frombuffer(planned_bytes, dtype="<f8").reshape(-1, 6)
        executed_actions = np.frombuffer(executed_bytes, dtype="<f8").reshape(-1, 6)
    except ValueError as error:
        raise C922TerminalHoldCaptureError("route action bytes are malformed") from error
    _require(
        action_sha256(planned_actions) == trajectory.get("action_sha256")
        and action_sha256(executed_actions) == trajectory.get("executed_action_sha256"),
        "planned or executed semantic action hash drifted",
    )
    observed = receipt.get("observed_pose_termination") or {}
    if observed.get("configured") is True:
        stop = observed.get("stop") or {}
        stop_index = stop.get("planned_sample_index")
        hold_count = trajectory.get("target_hold_sample_count")
        _require(
            observed.get("reached") is True
            and observed.get("planned_full_path_was_cpu_previewed") is True
            and observed.get("executed_path_is_safe_prefix_plus_exact_terminal_hold") is True
            and isinstance(stop_index, int)
            and stop_index >= 0
            and isinstance(hold_count, int)
            and hold_count > 0,
            "observed-pose safe-prefix receipt is incomplete",
        )
        prefix = planned_actions[: stop_index + 1]
        expected_executed = np.concatenate(
            [prefix, np.repeat(prefix[-1][None, :], hold_count, axis=0)]
        ).astype("<f8", copy=False)
        _require(
            np.array_equal(executed_actions, expected_executed)
            and trajectory.get("executed_movement_prefix_sample_count") == len(prefix)
            and stop.get("planned_motion_prefix_sha256") == action_sha256(prefix)
            and stop.get("exact_command_sha256") == action_sha256(prefix[-1:])
            and (receipt.get("terminal_hold_monotonic_interval") or {}).get(
                "exact_terminal_command_sha256"
            )
            == action_sha256(prefix[-1:]),
            "executed safe prefix or exact terminal hold differs from planned bytes",
        )
        action_binding = {
            "mode": "cpu_previewed_planned_prefix_plus_exact_terminal_hold",
            "planned_full_action_sha256": trajectory["action_sha256"],
            "planned_prefix_action_sha256": action_sha256(prefix),
            "executed_action_sha256": action_sha256(executed_actions),
            "executed_movement_prefix_sample_count": len(prefix),
            "terminal_hold_sample_count": hold_count,
            "exact_terminal_command_sha256": action_sha256(prefix[-1:]),
            "unused_planned_suffix_executed": False,
        }
    else:
        _require(
            planned_bytes == executed_bytes,
            "non-observed route planned and executed bytes differ",
        )
        action_binding = {
            "mode": "complete_planned_path",
            "planned_full_action_sha256": trajectory["action_sha256"],
            "executed_action_sha256": trajectory["executed_action_sha256"],
            "unused_planned_suffix_executed": False,
        }
    hold = receipt.get("terminal_hold_monotonic_interval")
    _require(isinstance(hold, dict), "terminal hold receipt is missing")
    start, end = hold.get("start"), hold.get("end")
    _require(
        all(isinstance(item, (int, float)) and math.isfinite(float(item)) for item in (start, end))
        and float(end) - float(start) >= float(contract["selection"]["minimum_terminal_hold_seconds"]),
        "terminal hold interval is invalid or too short",
    )
    telemetry_path = Path(str((receipt.get("telemetry") or {}).get("path", "")))
    _require(
        telemetry_path.is_file()
        and sha256_file(telemetry_path) == (receipt.get("telemetry") or {}).get("sha256"),
        "route telemetry lineage drifted",
    )
    rows = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    hold_rows = [row for row in rows if row.get("setup_phase") == "target_hold"]
    poses = np.asarray([row.get("follower_actual_position_degrees") for row in hold_rows])
    _require(
        poses.ndim == 2
        and poses.shape[1] == 6
        and len(poses) > 0
        and np.all(np.isfinite(poses))
        and all(row.get("safety_clamped") is False for row in hold_rows),
        "terminal hold has no finite pose samples",
    )
    pose_summary = {
        "sample_count": len(poses),
        "mean_degrees": np.mean(poses, axis=0).tolist(),
        "range_degrees": np.ptp(poses, axis=0).tolist(),
        "telemetry_path": str(telemetry_path),
        "telemetry_sha256": sha256_file(telemetry_path),
        "exact_terminal_command_sha256": hold.get("exact_terminal_command_sha256"),
    }
    return (
        int(round(float(start) * 1e9)),
        int(round(float(end) * 1e9)),
        hold_rows,
        pose_summary,
        action_binding,
    )


def orchestrate_c922_terminal_hold_capture(
    *,
    output_root: Path,
    camera_session_token: str,
    fixed_mount_token: str,
    operator_acknowledged: bool,
    empty_gripper_confirmed: bool,
    route_path: Path | None = None,
    candidate_manifest_path: Path = DEFAULT_MANIFEST,
    contract_path: Path = CONTRACT_PATH,
    route_executor: Callable[..., dict[str, Any]] = execute_live_anchored_camera_reposition,
    recorder_factory: Callable[..., Recorder] = NativeC922StillRecorder,
) -> dict[str, Any]:
    """Start C922 first, execute one frozen setup route, then bind one hold still."""

    _require(operator_acknowledged, "physical setup orchestration requires --yes")
    _require(empty_gripper_confirmed, "empty gripper must be explicitly confirmed")
    _require(bool(camera_session_token.strip()), "camera session token is required")
    _require(bool(fixed_mount_token.strip()), "fixed mount token is required")
    output_root = output_root.resolve()
    _require(not output_root.exists(), "output root already exists")
    contract = load_contract(contract_path)
    frozen_route = (REPO_ROOT / contract["route"]["path"]).resolve()
    selected_route = (route_path or frozen_route).resolve()
    _require(
        selected_route == frozen_route
        and selected_route.is_file()
        and sha256_file(selected_route) == contract["route"]["sha256"],
        "selected frozen route drifted",
    )
    output_root.mkdir(parents=True)
    recorder = recorder_factory(
        output_root / "capture",
        contract=contract,
        camera_session_token=camera_session_token,
        fixed_mount_token=fixed_mount_token,
    )
    started: dict[str, Any] | None = None
    finished: dict[str, Any] | None = None
    route_receipt: dict[str, Any] | None = None
    try:
        started = recorder.start()
        route_receipt = route_executor(
            route_path=selected_route,
            candidate_manifest_path=candidate_manifest_path.resolve(),
            output_root=output_root / "route",
            operator_acknowledged=True,
        )
    finally:
        if started is not None:
            finished = recorder.finish()
    _require(route_receipt is not None and finished is not None, "capture or route did not finish")
    _validate_camera_record(started, contract, camera_session_token, fixed_mount_token)
    _validate_camera_record(finished, contract, camera_session_token, fixed_mount_token)
    _require(finished.get("status") == "completed", "C922 capture did not complete")
    hold_start_ns, hold_end_ns, hold_rows, pose_summary, action_binding = _validate_route_receipt(
        route_receipt, contract
    )
    ledger_path = Path(finished["ledger_path"])
    _require(
        ledger_path.is_file()
        and sha256_file(ledger_path) == finished.get("ledger_sha256"),
        "C922 callback ledger lineage drifted",
    )
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    candidates = [
        event
        for event in events
        if event.get("schemaVersion") == "sim2claw.c922_terminal_hold_frame_event.v1"
        and hold_start_ns <= int(event.get("hostContinuousNS", -1)) <= hold_end_ns
    ]
    _require(candidates, "no retained C922 callback frame falls inside terminal hold")
    midpoint = (hold_start_ns + hold_end_ns) // 2
    selected = min(candidates, key=lambda event: abs(int(event["hostContinuousNS"]) - midpoint))
    _validate_camera_record(selected, contract, camera_session_token, fixed_mount_token)
    source_png = output_root / "capture" / selected["pngPath"]
    _require(
        source_png.is_file() and sha256_file(source_png) == selected["pngSHA256"],
        "selected PNG hash drifted from callback evidence",
    )
    with Image.open(source_png) as image:
        _require(image.format == "PNG" and image.size == (640, 480), "selected still is not 640x480 PNG")
    selected_png = output_root / "selected.png"
    shutil.copyfile(source_png, selected_png)
    selected_sha = sha256_file(selected_png)
    route_receipt_path = output_root / "route/execution_receipt.json"
    pose_receipt = {
        "schema_version": POSE_RECEIPT_SCHEMA,
        "candidate_pose_id": contract["route"]["pose_id"],
        "frozen_candidate_pose_reached": contract["route"][
            "frozen_candidate_pose_reached"
        ],
        "settled_actual": pose_summary["mean_degrees"],
        "empty_gripper": True,
        "camera": {
            "role": "c922",
            "camera_fixed": True,
            "session_id": camera_session_token,
            "fixed_mount_token": fixed_mount_token,
            "intrinsics_sha256": None,
            "image_sha256": selected_sha,
            "exact_source_mode": "640x480_420v_30fps",
        },
        "gateway": {"admitted": True, "safety_clamped": False, "stalled": False},
        "diagnostic_only": True,
        "full_three_face_rank_eligible": False,
        "route_receipt": {
            "path": str(route_receipt_path),
            "sha256": sha256_file(route_receipt_path),
        },
        "terminal_hold": pose_summary,
        "authority": dict(contract["authority"]),
    }
    pose_path = output_root / "pose_receipt.json"
    atomic_write_json(pose_path, pose_receipt)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": "physical_c922_terminal_hold_still_diagnostic_only",
        "status": "completed",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "route": {
            "path": str(selected_route),
            "sha256": sha256_file(selected_route),
            "execution_receipt_path": str(route_receipt_path),
            "execution_receipt_sha256": sha256_file(route_receipt_path),
            "action_binding": action_binding,
            "shutdown_torque_off_confirmed": True,
        },
        "camera": {
            "session_token": camera_session_token,
            "fixed_mount_token": fixed_mount_token,
            "ready_before_route_executor": True,
            "start_report": started,
            "finish_report": finished,
        },
        "terminal_hold": {
            "start_host_continuous_ns": hold_start_ns,
            "end_host_continuous_ns": hold_end_ns,
            "joint_sample_count": len(hold_rows),
        },
        "selected_callback_event": selected,
        "selected_png": {"path": str(selected_png), "sha256": selected_sha},
        "pose_receipt": {"path": str(pose_path), "sha256": sha256_file(pose_path)},
        "annotation_performed": False,
        "fit_performed": False,
        "full_three_face_rank_eligible": False,
        "authority": dict(contract["authority"]),
    }
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camera-session-token", required=True)
    parser.add_argument("--fixed-mount-token", required=True)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--candidate-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--empty-gripper-confirmed", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    result = orchestrate_c922_terminal_hold_capture(
        output_root=args.output,
        camera_session_token=args.camera_session_token,
        fixed_mount_token=args.fixed_mount_token,
        operator_acknowledged=args.yes,
        empty_gripper_confirmed=args.empty_gripper_confirmed,
        route_path=args.route,
        candidate_manifest_path=args.candidate_manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
