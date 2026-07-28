"""Capture one rigid scene with C922, metric D405 RGB-D, and Pi IMX708.

The three camera owners are deliberately separate.  C922 uses its existing
single-camera AVFoundation recorder, D405 is opened only by ``rs-record``, and
each Pi still is produced by one completed SSH command.  This module constructs
no robot gateway and fits no calibration or transform.
"""

from __future__ import annotations

import json
import math
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from PIL import Image

from .c922_terminal_hold_capture import NativeC922StillRecorder
from .d405_pose_plane_capture import _NativeRsRecord, _native_camera_identity
from .d405_stationary_rgbd_capture import (
    _find_topic_id,
    _open_database_read_only,
    _pair_statistics,
    _semicolon_fields,
    _single_topic_string,
    _topic_inventory,
    _topic_timestamps,
)
from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "acquisition"
    / "current_static_tricam_capture_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.static_tricam_capture_contract.v1"
RECEIPT_SCHEMA = "sim2claw.static_tricam_capture_receipt.v1"


class StaticTricamCaptureError(RuntimeError):
    """The capture owner, timing, identity, or teardown failed closed."""


class CameraOwner(Protocol):
    def start(self) -> dict[str, Any]: ...

    def ensure_running(self) -> None: ...

    def finish(self) -> dict[str, Any]: ...


C922Factory = Callable[..., CameraOwner]
D405Factory = Callable[..., CameraOwner]
PiCapture = Callable[..., dict[str, Any]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StaticTricamCaptureError(message)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StaticTricamCaptureError(f"cannot read {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path, "static tricam contract")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "unexpected static tricam contract schema",
    )
    _require(
        contract.get("status") == "preregistered_before_capture",
        "static tricam contract status changed",
    )
    ownership = contract.get("ownership", {})
    _require(
        ownership.get("c922_owner") == "NativeC922StillRecorder"
        and ownership.get("d405_owner") == "rs-record"
        and ownership.get("pi_owner") == "ssh_rpicam-still"
        and ownership.get("forbid_avfoundation_d405") is True
        and ownership.get("forbid_native_dual_camera_recorder") is True
        and ownership.get("maximum_simultaneous_owner_per_device") == 1,
        "camera ownership contract changed",
    )
    c922 = contract.get("camera", {})
    _require(
        c922.get("localized_name") == "C922 Pro Stream Webcam"
        and c922.get("width") == 640
        and c922.get("height") == 480
        and c922.get("media_subtype_fourcc") == "420v",
        "C922 exact mode changed",
    )
    d405 = contract.get("d405", {})
    _require(
        d405.get("depth", {}).get("encoding") == "Z16"
        and d405.get("color", {}).get("encoding") == "RGB8"
        and d405.get("depth", {}).get("width") == 848
        and d405.get("depth", {}).get("height") == 480
        and d405.get("color", {}).get("width") == 848
        and d405.get("color", {}).get("height") == 480
        and d405.get("depth", {}).get("fps") == 30
        and d405.get("color", {}).get("fps") == 30,
        "D405 metric RGB-D mode changed",
    )
    pi = contract.get("pi", {})
    _require(
        pi.get("shot_count") == 3
        and pi.get("width") == 1536
        and pi.get("height") == 864
        and pi.get("horizontal_flip") is True
        and pi.get("vertical_flip") is True
        and pi.get("autofocus_mode") == "manual"
        and pi.get("remote_output") == "stdout",
        "Pi still contract changed",
    )
    rigidity = contract.get("rigidity", {})
    _require(
        rigidity.get("scene_and_arm_must_remain_rigid") is True
        and rigidity.get("operator_acknowledgement_required") is True
        and rigidity.get("component_must_not_construct_robot_gateway") is True
        and rigidity.get("component_robot_motion_commands_maximum") == 0
        and rigidity.get("external_reviewed_gateway_hold_permitted") is True
        and rigidity.get("external_hold_must_be_torque_on_and_receipt_bound")
        is True,
        "scene-rigidity or robot boundary changed",
    )
    authority = contract.get("authority", {})
    forbidden_authority = (
        "camera_transform",
        "camera_intrinsics",
        "board_registration",
        "simulator_parameter_promotion",
        "robot_gateway",
        "robot_motion",
        "policy",
        "task_success",
        "physical_task",
    )
    _require(
        authority.get("physical_static_camera_capture") is True
        and authority.get("metric_depth_capture") is True
        and all(authority.get(key) is False for key in forbidden_authority),
        "static tricam authority widened",
    )
    return contract


class _C922OnlyOwner:
    """Adapt the existing C922-only source recorder to this capture."""

    def __init__(
        self,
        output_root: Path,
        *,
        contract: Mapping[str, Any],
        camera_session_token: str,
        fixed_mount_token: str,
        clock_ns_fn: Callable[[], int],
    ) -> None:
        self.recorder = NativeC922StillRecorder(
            output_root,
            contract=contract,
            camera_session_token=camera_session_token,
            fixed_mount_token=fixed_mount_token,
            clock_fn=lambda: clock_ns_fn() / 1_000_000_000.0,
        )

    def start(self) -> dict[str, Any]:
        return self.recorder.start()

    def ensure_running(self) -> None:
        process = self.recorder.process
        _require(
            process is not None and process.poll() is None,
            "C922-only capture owner exited before teardown",
        )

    def finish(self) -> dict[str, Any]:
        return self.recorder.finish()


def _identity_matches(
    observed: Mapping[str, Any], expected: Mapping[str, Any]
) -> bool:
    keys = (
        "sdk_serial_number",
        "asic_serial_number",
        "firmware_update_id",
        "usb_product_id_hex",
        "physical_port",
    )
    return all(
        str(observed.get(key, "")).upper()
        == str(expected.get(key, "")).upper()
        for key in keys
    )


class _MetricD405Owner:
    """Own the D405 only through the existing native rs-record path."""

    def __init__(
        self,
        output_root: Path,
        *,
        contract: Mapping[str, Any],
        clock_ns_fn: Callable[[], int],
    ) -> None:
        self.output_root = output_root
        self.contract = contract
        self.clock_ns_fn = clock_ns_fn
        self.database_path = output_root / str(contract["d405"]["database_name"])
        self.recorder: _NativeRsRecord | None = None
        self.identity_before: dict[str, str] | None = None

    def start(self) -> dict[str, Any]:
        _require(not self.output_root.exists(), "D405 output already exists")
        self.output_root.mkdir(parents=True)
        self.identity_before = _native_camera_identity()
        _require(
            _identity_matches(
                self.identity_before, self.contract["d405"]["expected_device"]
            ),
            "live D405 identity differs from the frozen contract",
        )
        self.recorder = _NativeRsRecord(self.database_path)
        duration = float(
            self.contract["timing"]["capture_duration_seconds_maximum"]
        )
        self.recorder.command = [
            self.recorder.command[0],
            "-t",
            f"{duration:g}",
            "-f",
            str(self.database_path),
        ]
        try:
            report = self.recorder.start()
            deadline = (
                time.monotonic()
                + float(self.contract["timing"]["readiness_timeout_seconds"])
            )
            color_topic = self.contract["d405"]["color"]["topic"]
            while time.monotonic() < deadline:
                self.ensure_running()
                try:
                    with _open_database_read_only(
                        self.database_path
                    ) as connection:
                        inventory, _ids = _topic_inventory(connection)
                    color_ready = any(
                        row["name"] == color_topic
                        and row["message_count"] > 0
                        for row in inventory
                    )
                except Exception:
                    color_ready = False
                if color_ready:
                    break
                time.sleep(0.02)
            else:
                raise StaticTricamCaptureError(
                    "rs-record did not expose the RGB8 color topic"
                )
        except Exception:
            self._stop_after_start_failure()
            raise
        return {
            **report,
            "owner": "rs-record",
            "ready_observed_host_monotonic_ns": self.clock_ns_fn(),
            "identity_before": self.identity_before,
        }

    def _stop_after_start_failure(self) -> None:
        process = self.recorder.process if self.recorder is not None else None
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def ensure_running(self) -> None:
        process = self.recorder.process if self.recorder is not None else None
        _require(
            process is not None and process.poll() is None,
            "rs-record exited before D405 teardown",
        )

    def _inspect_database(self) -> dict[str, Any]:
        d405 = self.contract["d405"]
        with _open_database_read_only(self.database_path) as connection:
            _inventory, topic_ids = _topic_inventory(connection)
            depth_topic = str(d405["depth"]["topic"])
            color_topic = str(d405["color"]["topic"])
            _require(
                depth_topic in topic_ids and color_topic in topic_ids,
                "D405 RGB-D topics are incomplete",
            )
            depth_timestamps = _topic_timestamps(
                connection, topic_ids[depth_topic]
            )
            color_timestamps = _topic_timestamps(
                connection, topic_ids[color_topic]
            )
            pairing = _pair_statistics(depth_timestamps, color_timestamps)
            depth_info = _semicolon_fields(
                _single_topic_string(
                    connection, _find_topic_id(topic_ids, "Depth_0/info")
                )
            )
            color_info = _semicolon_fields(
                _single_topic_string(
                    connection, _find_topic_id(topic_ids, "Color_0/info")
                )
            )
            depth_camera = _semicolon_fields(
                _single_topic_string(
                    connection,
                    _find_topic_id(topic_ids, "Depth_0/camera_info"),
                )
            )
            color_camera = _semicolon_fields(
                _single_topic_string(
                    connection,
                    _find_topic_id(topic_ids, "Color_0/camera_info"),
                )
            )
            units = float(
                _single_topic_string(
                    connection,
                    _find_topic_id(topic_ids, "Depth_Units/value"),
                )
            )
        minimum = self.contract["minimum_frames"]
        maximum_pair_delta = float(
            self.contract["timing"]["maximum_rgb_depth_pair_delta_ms"]
        )
        checks = {
            "depth_encoding": depth_info.get("encoding")
            == d405["depth"]["encoding"],
            "color_encoding": color_info.get("encoding")
            == d405["color"]["encoding"],
            "depth_fps": int(depth_info.get("fps", 0))
            == int(d405["depth"]["fps"]),
            "color_fps": int(color_info.get("fps", 0))
            == int(d405["color"]["fps"]),
            "depth_width": int(depth_camera.get("width", 0))
            == int(d405["depth"]["width"]),
            "depth_height": int(depth_camera.get("height", 0))
            == int(d405["depth"]["height"]),
            "color_width": int(color_camera.get("width", 0))
            == int(d405["color"]["width"]),
            "color_height": int(color_camera.get("height", 0))
            == int(d405["color"]["height"]),
            "depth_frame_count": len(depth_timestamps)
            >= int(minimum["d405_depth"]),
            "color_frame_count": len(color_timestamps)
            >= int(minimum["d405_color"]),
            "rgb_depth_pair_delta": pairing["absolute_delta_ms"]["maximum"]
            <= maximum_pair_delta,
            "depth_units": math.isclose(
                units,
                float(d405["depth_units_m_per_z16_unit"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
        }
        _require(all(checks.values()), "D405 stream identity or frame gate failed")
        return {
            "checks": checks,
            "depth_frame_count": len(depth_timestamps),
            "color_frame_count": len(color_timestamps),
            "rgb_depth_pairing": pairing,
            "depth_units_m_per_z16_unit": units,
        }

    def finish(self) -> dict[str, Any]:
        _require(self.recorder is not None, "rs-record was not started")
        finish = self.recorder.finish()
        identity_after = _native_camera_identity()
        _require(
            self.identity_before is not None
            and identity_after == self.identity_before
            and _identity_matches(
                identity_after, self.contract["d405"]["expected_device"]
            ),
            "D405 identity changed across capture",
        )
        streams = self._inspect_database()
        return {
            "status": "completed",
            "owner": "rs-record",
            "finish": finish,
            "identity_before": self.identity_before,
            "identity_after": identity_after,
            "database_path": str(self.database_path),
            "database_sha256": sha256_file(self.database_path),
            **streams,
        }


def _capture_pi_over_ssh(
    specification: Mapping[str, Any],
    *,
    shot_index: int,
    output_path: Path,
    clock_ns_fn: Callable[[], int],
) -> dict[str, Any]:
    host = str(specification.get("ssh_host") or "")
    _require(
        host
        and all(character.isalnum() or character in "@._-" for character in host),
        "Pi SSH host is invalid",
    )
    _require(not output_path.exists(), "refusing to overwrite Pi still")
    ssh = shutil.which("ssh")
    _require(ssh is not None, "ssh is unavailable")
    remote_command = [
        "rpicam-still",
        "--nopreview",
        "--immediate",
        "--width",
        str(specification["width"]),
        "--height",
        str(specification["height"]),
        "--hflip",
        "--vflip",
        "--autofocus-mode",
        str(specification["autofocus_mode"]),
        "--lens-position",
        str(specification["lens_position_reciprocal_m"]),
        "--output",
        "-",
    ]
    command = [
        ssh,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        host,
        *remote_command,
    ]
    start_ns = clock_ns_fn()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=20.0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise StaticTricamCaptureError(
            f"Pi still {shot_index} failed: {error}"
        ) from error
    end_ns = clock_ns_fn()
    _require(
        completed.returncode == 0 and bool(completed.stdout),
        f"Pi still {shot_index} returned no JPEG",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(completed.stdout)
    try:
        with Image.open(output_path) as image:
            image.verify()
        with Image.open(output_path) as image:
            size = list(image.size)
    except OSError as error:
        raise StaticTricamCaptureError(
            f"Pi still {shot_index} is not a readable image"
        ) from error
    _require(
        size
        == [int(specification["width"]), int(specification["height"])],
        f"Pi still {shot_index} dimensions changed",
    )
    return {
        "schema_version": "sim2claw.static_tricam_pi_still.v1",
        "shot_index": shot_index,
        "status": "completed",
        "camera": specification["camera"],
        "ssh_host": host,
        "width": size[0],
        "height": size[1],
        "horizontal_flip": True,
        "vertical_flip": True,
        "autofocus_mode": specification["autofocus_mode"],
        "lens_position_reciprocal_m": specification[
            "lens_position_reciprocal_m"
        ],
        "host_monotonic_start_ns": start_ns,
        "host_monotonic_end_ns": end_ns,
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "process_completed": True,
    }


def _validate_c922(
    start: Mapping[str, Any],
    finish: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    common_start_ns: int,
    common_end_ns: int,
) -> dict[str, Any]:
    expected = contract["camera"]
    identity = {
        "cameraName": expected["localized_name"],
        "cameraUniqueID": expected["unique_id"],
        "cameraModelID": expected["model_id"],
        "width": expected["width"],
        "height": expected["height"],
        "mediaSubtype": expected["media_subtype_fourcc"],
        "pixelFormat": expected["media_subtype_fourcc"],
    }
    _require(
        all(start.get(key) == value for key, value in identity.items())
        and all(finish.get(key) == value for key, value in identity.items()),
        "C922 identity or exact mode changed",
    )
    _require(
        finish.get("status") == "completed"
        and finish.get("droppedCallbackCount") == 0,
        "C922 capture did not complete without dropped callbacks",
    )
    ledger_path = Path(str(finish.get("ledger_path", "")))
    _require(
        ledger_path.is_file()
        and sha256_file(ledger_path) == finish.get("ledger_sha256"),
        "C922 callback ledger is missing or changed",
    )
    events = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    inside = sorted(
        (
            item
            for item in events
            if common_start_ns
            <= int(item.get("hostContinuousNS", -1))
            <= common_end_ns
        ),
        key=lambda item: int(item["hostContinuousNS"]),
    )
    _require(
        len(inside)
        >= int(contract["minimum_frames"]["c922_inside_common_window"]),
        "C922 has too few frames inside the common window",
    )
    _require(
        all(
            all(item.get(key) == value for key, value in identity.items())
            for item in inside
        ),
        "C922 callback-event identity changed",
    )
    host_ns = [int(item["hostContinuousNS"]) for item in inside]
    intervals = [
        (right - left) / 1_000_000_000.0
        for left, right in zip(host_ns, host_ns[1:], strict=False)
    ]
    _require(
        all(value > 0.0 for value in intervals)
        and max(intervals, default=0.0)
        <= float(contract["timing"]["maximum_c922_interval_seconds"]),
        "C922 common-window timestamps are discontinuous",
    )
    return {
        "frame_count_inside_common_window": len(inside),
        "first_host_monotonic_ns": host_ns[0],
        "last_host_monotonic_ns": host_ns[-1],
        "maximum_interval_seconds": max(intervals, default=0.0),
        "ledger_path": str(ledger_path),
        "ledger_sha256": finish["ledger_sha256"],
    }


def _validate_pi_stills(
    stills: list[dict[str, Any]],
    *,
    contract: Mapping[str, Any],
    common_start_ns: int,
    common_end_ns: int,
) -> None:
    specification = contract["pi"]
    _require(
        len(stills) == int(specification["shot_count"]),
        "Pi still count changed",
    )
    for index, still in enumerate(stills):
        path = Path(str(still.get("path", "")))
        _require(
            still.get("shot_index") == index
            and still.get("status") == "completed"
            and still.get("process_completed") is True
            and still.get("width") == specification["width"]
            and still.get("height") == specification["height"]
            and still.get("horizontal_flip") is True
            and still.get("vertical_flip") is True
            and still.get("autofocus_mode")
            == specification["autofocus_mode"]
            and still.get("lens_position_reciprocal_m")
            == specification["lens_position_reciprocal_m"]
            and path.is_file()
            and sha256_file(path) == still.get("sha256"),
            f"Pi still {index} identity or hash failed",
        )
        start_ns = int(still.get("host_monotonic_start_ns", -1))
        end_ns = int(still.get("host_monotonic_end_ns", -1))
        _require(
            common_start_ns <= start_ns <= end_ns <= common_end_ns,
            f"Pi still {index} lies outside the common interior window",
        )


class StaticTricamCapture:
    """CameraCapture-compatible owner set for an externally held rigid pose."""

    def __init__(
        self,
        output_root: Path,
        *,
        operator_acknowledged: bool,
        camera_session_token: str,
        fixed_mount_token: str,
        contract_path: Path = CONTRACT_PATH,
        c922_factory: C922Factory = _C922OnlyOwner,
        d405_factory: D405Factory = _MetricD405Owner,
        pi_capture: PiCapture = _capture_pi_over_ssh,
        clock_ns_fn: Callable[[], int] = time.monotonic_ns,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        _require(
            operator_acknowledged, "static capture requires acknowledgement"
        )
        _require(
            bool(camera_session_token) and bool(fixed_mount_token),
            "camera-session and fixed-mount tokens are required",
        )
        self.output_root = output_root.resolve()
        self.contract_path = contract_path.resolve()
        _require(
            not self.output_root.exists(),
            f"refusing to overwrite {self.output_root}",
        )
        self.contract = load_contract(self.contract_path)
        self.clock_ns_fn = clock_ns_fn
        self.sleep_fn = sleep_fn
        self.pi_capture = pi_capture
        self.output_root.mkdir(parents=True)
        self.c922 = c922_factory(
            self.output_root / "c922",
            contract=self.contract,
            camera_session_token=camera_session_token,
            fixed_mount_token=fixed_mount_token,
            clock_ns_fn=clock_ns_fn,
        )
        self.d405 = d405_factory(
            self.output_root / "d405",
            contract=self.contract,
            clock_ns_fn=clock_ns_fn,
        )
        self.c922_attempted = False
        self.d405_attempted = False
        self.c922_finished = False
        self.d405_finished = False
        self.started = False
        self.finished = False
        self.c922_start: dict[str, Any] | None = None
        self.d405_start: dict[str, Any] | None = None
        self.pi_stills: list[dict[str, Any]] = []
        self.owner_common_start_ns: int | None = None

    def _finish_owners(
        self,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
        d405_finish: dict[str, Any] | None = None
        c922_finish: dict[str, Any] | None = None
        cleanup_errors: list[str] = []
        if self.d405_attempted and not self.d405_finished:
            try:
                d405_finish = self.d405.finish()
                self.d405_finished = True
            except Exception as error:
                cleanup_errors.append(f"D405 teardown: {error}")
        if self.c922_attempted and not self.c922_finished:
            try:
                c922_finish = self.c922.finish()
                self.c922_finished = True
            except Exception as error:
                cleanup_errors.append(f"C922 teardown: {error}")
        return d405_finish, c922_finish, cleanup_errors

    def start(self) -> dict[str, Any]:
        _require(not self.started and not self.finished, "capture already started")
        primary_error: Exception | None = None
        try:
            self.c922_attempted = True
            self.c922_start = self.c922.start()
            self.c922.ensure_running()
            self.d405_attempted = True
            self.d405_start = self.d405.start()
            self.d405.ensure_running()
            self.c922.ensure_running()
            self.owner_common_start_ns = self.clock_ns_fn()
            self.started = True
        except Exception as error:
            primary_error = error
        if primary_error is not None:
            _d405, _c922, cleanup_errors = self._finish_owners()
            detail = str(primary_error)
            if cleanup_errors:
                detail += "; " + "; ".join(cleanup_errors)
            self.finished = True
            raise StaticTricamCaptureError(detail) from primary_error
        return {
            "schema_version": "sim2claw.static_tricam_capture_started.v1",
            "status": "recording_static_tricam",
            "c922": self.c922_start,
            "d405": self.d405_start,
            "owner_common_start_host_monotonic_ns": self.owner_common_start_ns,
            "pi_shots_scheduled_during_external_hold": int(
                self.contract["pi"]["shot_count"]
            ),
            "component_robot_gateway_constructed": False,
            "component_robot_motion_commands": 0,
        }

    def ensure_running(self) -> None:
        _require(self.started and not self.finished, "capture is not running")
        self.c922.ensure_running()
        self.d405.ensure_running()
        if len(self.pi_stills) < int(self.contract["pi"]["shot_count"]):
            index = len(self.pi_stills)
            still = self.pi_capture(
                self.contract["pi"],
                shot_index=index,
                output_path=self.output_root / "pi" / f"imx708-{index}.jpg",
                clock_ns_fn=self.clock_ns_fn,
            )
            self.pi_stills.append(still)
        self.c922.ensure_running()
        self.d405.ensure_running()

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        _require(self.started and not self.finished, "capture is not running")
        _require(
            action_started_monotonic is not None
            and action_stopped_monotonic is not None
            and math.isfinite(action_started_monotonic)
            and math.isfinite(action_stopped_monotonic)
            and action_stopped_monotonic >= action_started_monotonic,
            "external rigid-hold monotonic bounds are required",
        )
        _require(
            post_roll_seconds >= 0.0 and math.isfinite(post_roll_seconds),
            "post-roll duration is invalid",
        )
        if post_roll_seconds:
            deadline_ns = self.clock_ns_fn() + int(
                post_roll_seconds * 1_000_000_000
            )
            while self.clock_ns_fn() < deadline_ns:
                self.c922.ensure_running()
                self.d405.ensure_running()
                remaining = (
                    deadline_ns - self.clock_ns_fn()
                ) / 1_000_000_000.0
                self.sleep_fn(min(0.05, max(0.0, remaining)))
        owner_common_end_ns = self.clock_ns_fn()
        d405_finish, c922_finish, cleanup_errors = self._finish_owners()
        self.finished = True
        if cleanup_errors:
            raise StaticTricamCaptureError("; ".join(cleanup_errors))
        _require(
            self.c922_start is not None
            and self.d405_start is not None
            and c922_finish is not None
            and d405_finish is not None
            and self.owner_common_start_ns is not None
            and self.c922_finished
            and self.d405_finished,
            "static tricam capture teardown is incomplete",
        )
        hold_start_ns = int(round(action_started_monotonic * 1_000_000_000))
        hold_end_ns = int(round(action_stopped_monotonic * 1_000_000_000))
        common_start_ns = max(self.owner_common_start_ns, hold_start_ns)
        common_end_ns = min(owner_common_end_ns, hold_end_ns)
        common_seconds = (
            common_end_ns - common_start_ns
        ) / 1_000_000_000.0
        _require(
            common_seconds
            >= float(self.contract["timing"]["minimum_common_interior_seconds"]),
            "receipt-bound rigid common interior window is too short",
        )
        _require(
            len(self.pi_stills) == int(self.contract["pi"]["shot_count"]),
            "all Pi shots must complete during the external rigid hold",
        )
        _require(
            d405_finish.get("status") == "completed"
            and d405_finish.get("owner") == "rs-record"
            and d405_finish.get("checks")
            and all(d405_finish["checks"].values()),
            "D405 capture proof is incomplete",
        )
        c922_validation = _validate_c922(
            self.c922_start,
            c922_finish,
            contract=self.contract,
            common_start_ns=common_start_ns,
            common_end_ns=common_end_ns,
        )
        _validate_pi_stills(
            self.pi_stills,
            contract=self.contract,
            common_start_ns=common_start_ns,
            common_end_ns=common_end_ns,
        )
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "proof_class": self.contract["proof_class"],
            "status": "completed_static_tricam_capture",
            "contract": {
                "path": str(self.contract_path),
                "sha256": sha256_file(self.contract_path),
                "contract_id": self.contract["contract_id"],
            },
            "ownership": {
                **self.contract["ownership"],
                "common_owner_count": 3,
                "owners_remaining_after_teardown": 0,
            },
            "external_rigid_hold": {
                "clock": "host_monotonic_seconds",
                "start": action_started_monotonic,
                "end": action_stopped_monotonic,
                "receipt_binding_required_from_caller": True,
                "component_asserts_external_torque_state": False,
            },
            "common_interior_window": {
                "clock": "host_monotonic_ns",
                "start_ns": common_start_ns,
                "end_ns": common_end_ns,
                "duration_seconds": common_seconds,
            },
            "c922": {
                "start": self.c922_start,
                "finish": c922_finish,
                "validation": c922_validation,
            },
            "d405": {
                "start": self.d405_start,
                "finish": d405_finish,
            },
            "pi_stills": self.pi_stills,
            "scene_rigidity": {
                "operator_acknowledged": True,
                "component_robot_gateway_constructed": False,
                "component_robot_motion_commands": 0,
                "external_reviewed_gateway_hold_permitted": True,
                "independently_measured_by_component": False,
            },
            "teardown": {
                "c922_owner_completed": self.c922_finished,
                "d405_owner_completed": self.d405_finished,
                "pi_processes_completed": len(self.pi_stills),
                "owners_remaining": 0,
            },
            "authority": self.contract["authority"],
            "claim_limits": self.contract["claim_limits"],
            "verdict": {
                "passed": True,
                "classification": "physical_static_tricam_capture_completed",
                "camera_transform_fitted": False,
                "metric_workcell_registration": False,
                "simulator_parameter_promoted": False,
                "component_robot_gateway_constructed": False,
            },
        }
        atomic_write_json(self.output_root / "capture_receipt.json", receipt)
        return receipt


def capture_static_tricam_bundle(
    *,
    output_root: Path,
    operator_acknowledged: bool,
    camera_session_token: str,
    fixed_mount_token: str,
    contract_path: Path = CONTRACT_PATH,
    c922_factory: C922Factory = _C922OnlyOwner,
    d405_factory: D405Factory = _MetricD405Owner,
    pi_capture: PiCapture = _capture_pi_over_ssh,
    clock_ns_fn: Callable[[], int] = time.monotonic_ns,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run the camera component under a local acknowledged rigid interval."""
    capture = StaticTricamCapture(
        output_root,
        operator_acknowledged=operator_acknowledged,
        camera_session_token=camera_session_token,
        fixed_mount_token=fixed_mount_token,
        contract_path=contract_path,
        c922_factory=c922_factory,
        d405_factory=d405_factory,
        pi_capture=pi_capture,
        clock_ns_fn=clock_ns_fn,
        sleep_fn=sleep_fn,
    )
    action_started: float | None = None
    started = False
    try:
        capture.start()
        started = True
        action_started = clock_ns_fn() / 1_000_000_000.0
        for _index in range(int(capture.contract["pi"]["shot_count"])):
            capture.ensure_running()
        deadline_ns = int(
            round(
                (
                    action_started
                    + float(
                        capture.contract["timing"][
                            "minimum_common_interior_seconds"
                        ]
                    )
                )
                * 1_000_000_000
            )
        )
        while clock_ns_fn() < deadline_ns:
            capture.c922.ensure_running()
            capture.d405.ensure_running()
            remaining = (
                deadline_ns - clock_ns_fn()
            ) / 1_000_000_000.0
            sleep_fn(min(0.05, max(0.0, remaining)))
        action_stopped = clock_ns_fn() / 1_000_000_000.0
        return capture.finish(
            action_started_monotonic=action_started,
            action_stopped_monotonic=action_stopped,
            post_roll_seconds=0.0,
        )
    except Exception:
        if started and not capture.finished:
            try:
                capture.finish(
                    action_started_monotonic=action_started,
                    action_stopped_monotonic=clock_ns_fn()
                    / 1_000_000_000.0,
                    post_roll_seconds=0.0,
                )
            except Exception:
                pass
        raise


__all__ = [
    "CONTRACT_PATH",
    "StaticTricamCapture",
    "StaticTricamCaptureError",
    "capture_static_tricam_bundle",
    "load_contract",
]
