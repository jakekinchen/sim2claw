"""Execute one camera-enclosed RP04C full-range no-contact route."""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from .parking_transaction_executor import C922PiParkingRecorder
from .paths import REPO_ROOT
from .physical_gateway import GatewayIdentity, shortest_delta_degrees
from .physical_trace_replay import (
    _controlled_return_to_source_start,
    _mapped_leader_target,
    physical_replay_gateway,
)
from .teleop_recording import physical_gateway_preflight


class FullRangeNoContactExecutionError(RuntimeError):
    """The one-shot RP04C physical transaction failed closed."""


class CameraEnclosure(Protocol):
    def start(self) -> dict[str, Any]: ...

    def ensure_running(self) -> None: ...

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]: ...


Clock = Callable[[], float]
Sleep = Callable[[float], None]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullRangeNoContactExecutionError(message)


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise FullRangeNoContactExecutionError(
            "RP04C execution input escapes repository"
        ) from error
    _require(path.is_file(), f"RP04C execution input is missing: {path}")
    _require(
        _sha(path) == entry["sha256"],
        f"RP04C execution input changed: {path}",
    )
    return path


def _load_packet(packet_path: Path) -> tuple[dict[str, Any], np.ndarray]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    _require(
        packet.get("schema_version")
        == "sim2claw.full_range_no_contact_execution_packet.v1",
        "unexpected RP04C packet schema",
    )
    for entry in packet["inputs"].values():
        _bound(entry)
    static = json.loads(
        _bound(packet["inputs"]["static_receipt"]).read_text(encoding="utf-8")
    )
    _require(
        static["status"]
        == "full_range_no_contact_identification_static_pass"
        and static["passed"] is True
        and static["physical_task_attempts"] == 0
        and static["mapping_approved"] is False,
        "RP04C static route is not an admitted pass",
    )
    route_entry = packet["physical_route"]
    shape = tuple(int(value) for value in route_entry["shape"])
    route = np.fromfile(_bound(route_entry), dtype="<f8")
    _require(route.size == int(np.prod(shape)), "RP04C route shape changed")
    route = np.asarray(route.reshape(shape), dtype="<f8", order="C")
    _require(shape == (1160, 6), "RP04C route denominator changed")
    _require(
        route_entry["sha256"] == static["physical_route"]["sha256"],
        "RP04C route differs from static pass",
    )
    boundaries = [
        int(value) for value in packet["execution"]["segment_boundaries"]
    ]
    _require(
        boundaries == [0, 61, 122, 555, 1159],
        "RP04C segment boundaries changed",
    )
    _require(
        np.array_equal(
            route[0],
            np.asarray(packet["execution"]["expected_row_zero"], dtype="<f8"),
        ),
        "RP04C row zero changed",
    )
    _require(
        packet["maximum_executions"] == 1
        and packet["physical_task_attempt"] is False
        and packet["pawn_contact"] is False
        and packet["mapping_approval"] is False,
        "RP04C packet widened authority",
    )
    return packet, route


def _load_authorization(
    authorization_path: Path,
    *,
    packet: Mapping[str, Any],
    packet_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    _require(
        authorization.get("schema_version")
        == "sim2claw.owner_physical_authorization.v1",
        "unexpected owner authorization schema",
    )
    _require(
        authorization["operation_id"] == packet["operation_id"]
        and authorization["packet_sha256"] == _sha(packet_path)
        and authorization["maximum_executions"] == 1,
        "authorization does not bind this RP04C execution",
    )
    _require(
        authorization["physical_no_contact_diagnostic"] is True
        and authorization["physical_task_attempt"] is False
        and authorization["pawn_contact"] is False
        and authorization["autonomous_agent_supervision"] is True
        and authorization["power_down_supply_on_torque_cleanup_error"] is True,
        "authorization widened RP04C or lacks fail-safe response",
    )
    issued = datetime.fromisoformat(str(authorization["issued_at"]))
    expires = datetime.fromisoformat(str(authorization["expires_at"]))
    _require(
        issued.tzinfo is not None and expires.tzinfo is not None,
        "authorization lacks timezone",
    )
    current = now or datetime.now(expires.tzinfo)
    _require(issued <= current < expires, "authorization is not active")
    return authorization


def _identity(preflight: Mapping[str, Any]) -> GatewayIdentity:
    return GatewayIdentity(
        leader_port=str(preflight["leader_port"]),
        follower_port=str(preflight["follower_port"]),
        leader_calibration_sha256=str(preflight["leader_calibration_sha256"]),
        follower_calibration_sha256=str(
            preflight["follower_calibration_sha256"]
        ),
    )


def _residual(target: np.ndarray, actual: np.ndarray) -> np.ndarray:
    result = target - actual
    result[4] = shortest_delta_degrees(
        float(target[4]), float(actual[4])
    )
    return result


def execute(
    *,
    packet_path: Path,
    authorization_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = physical_gateway_preflight,
    gateway_factory: Callable[[GatewayIdentity], Any] = physical_replay_gateway,
    camera_factory: Callable[
        [Path, Mapping[str, Any]], CameraEnclosure
    ]
    | None = None,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> dict[str, Any]:
    """Execute the exact route forward and reverse with boundary rebases."""

    _require(operator_acknowledged, "explicit owner acknowledgement required")
    packet_path = packet_path.resolve()
    authorization_path = authorization_path.resolve()
    output_root = output_root.resolve()
    packet, route = _load_packet(packet_path)
    authorization = _load_authorization(
        authorization_path, packet=packet, packet_path=packet_path
    )
    expected_output = (REPO_ROOT / packet["output_directory"]).resolve()
    _require(output_root == expected_output, "RP04C output path changed")
    _require(not output_root.exists(), "refusing to overwrite RP04C output")
    preflight = preflight_fn()
    _require(
        preflight.get("passed") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "fresh RP04C torque-off preflight failed",
    )
    _require(
        preflight["follower_port"] == packet["hardware"]["follower_port"]
        and preflight["follower_calibration_sha256"]
        == packet["hardware"]["follower_calibration_sha256"],
        "RP04C follower identity changed",
    )
    live = np.asarray(
        preflight["follower_start_degrees"], dtype=np.float64
    )
    start_delta = _residual(route[0], live)
    _require(
        float(np.max(np.abs(start_delta[:5])))
        <= float(packet["execution"]["maximum_start_body_delta_degrees"])
        and abs(float(start_delta[5]))
        <= float(packet["execution"]["maximum_start_gripper_delta"]),
        "fresh RP04C pose is outside the start envelope",
    )
    output_root.mkdir(parents=True, exist_ok=False)
    telemetry_path = output_root / "telemetry.jsonl"
    if camera_factory is None:

        def camera_factory(
            root: Path, value: Mapping[str, Any]
        ) -> CameraEnclosure:
            return C922PiParkingRecorder(
                root,
                c922_contract_path=_bound(value["inputs"]["c922_contract"]),
                pi_contract_path=_bound(value["inputs"]["pi_contract"]),
                session_token=str(value["camera"]["session_token"]),
                fixed_mount_token=str(value["camera"]["fixed_mount_token"]),
            )

    camera = camera_factory(output_root / "cameras", packet)
    gateway: Any | None = None
    camera_start: dict[str, Any] | None = None
    camera_result: dict[str, Any] | None = None
    opened: dict[str, Any] | None = None
    postflight: dict[str, Any] | None = None
    failure: str | None = None
    cleanup_errors: list[str] = []
    action_started: float | None = None
    action_stopped: float | None = None
    wall_started: float | None = None
    leader_origin: np.ndarray | None = None
    follower_origin: np.ndarray | None = None
    forward_metrics: list[dict[str, Any]] = []
    boundary_reports: list[dict[str, Any]] = []
    origin_rebases: list[dict[str, Any]] = []
    controlled_return: dict[str, Any] = {
        "requested": False,
        "completed": False,
        "sample_count": 0,
    }

    def write_sample(
        handle: Any,
        *,
        phase: str,
        target: np.ndarray,
        sample: Mapping[str, Any],
        source_row: int | None,
    ) -> dict[str, Any]:
        sent = np.asarray(
            sample["follower_command_degrees"], dtype=np.float64
        )
        actual = np.asarray(
            sample["follower_actual_position_degrees"], dtype=np.float64
        )
        residual = _residual(target, actual)
        sent_exact = bool(np.all(np.abs(sent - target) <= 0.25))
        row = {
            **sample,
            "schema_version":
            "sim2claw.full_range_no_contact_execution_sample.v1",
            "phase": phase,
            "source_row_or_missing": source_row,
            "requested_source_command_degrees": target.tolist(),
            "source_requested_bytes_unchanged": True,
            "source_command_sent_within_0p25_degree": sent_exact,
            "requested_minus_observed_degrees": residual.tolist(),
            "host_monotonic": clock(),
        }
        handle.write(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
        )
        handle.flush()
        if phase == "forward_source" and source_row is not None:
            forward_metrics.append(
                {
                    "source_row": source_row,
                    "elbow_requested_degrees": float(target[2]),
                    "elbow_observed_degrees": float(actual[2]),
                    "elbow_error_degrees": abs(float(residual[2])),
                    "all_joint_residual_degrees": residual.tolist(),
                    "sent_exact": sent_exact,
                    "safety_clamped": bool(sample.get("safety_clamped")),
                }
            )
        return row

    def settle(
        handle: Any,
        *,
        target: np.ndarray,
        phase: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        assert gateway is not None
        assert leader_origin is not None and follower_origin is not None
        assert wall_started is not None
        started = clock()
        limit = float(
            packet["acceptance"]["maximum_boundary_residual_degrees"]
        )
        while clock() - started <= timeout_seconds:
            camera.ensure_running()
            gateway.leader.set_target(
                _mapped_leader_target(
                    target, leader_origin, follower_origin
                )
            )
            sample = gateway.sample(clock() - wall_started)
            write_sample(
                handle,
                phase=phase,
                target=target,
                sample=sample,
                source_row=None,
            )
            actual = np.asarray(
                sample["follower_actual_position_degrees"],
                dtype=np.float64,
            )
            residual = _residual(target, actual)
            if float(np.max(np.abs(residual[:5]))) <= limit and abs(
                float(residual[5])
            ) <= limit:
                return {
                    "phase": phase,
                    "target_degrees": target.tolist(),
                    "actual_degrees": actual.tolist(),
                    "residual_degrees": residual.tolist(),
                    "passed": True,
                }
            sleep(0.05)
        raise FullRangeNoContactExecutionError(
            f"{phase} did not reach the frozen boundary gate"
        )

    def rebase(target: np.ndarray, phase: str) -> None:
        nonlocal leader_origin, follower_origin
        assert gateway is not None
        assert leader_origin is not None and follower_origin is not None
        next_leader = _mapped_leader_target(
            target, leader_origin, follower_origin
        )
        report = gateway.rebase_relative_origin(
            leader_origin=next_leader, follower_origin=target
        )
        report["phase"] = phase
        origin_rebases.append(report)
        leader_origin = next_leader
        follower_origin = target.copy()

    def run_rows(
        handle: Any,
        *,
        rows: list[int],
        phase: str,
    ) -> None:
        assert gateway is not None
        assert leader_origin is not None and follower_origin is not None
        assert wall_started is not None
        started = clock()
        for offset, source_row in enumerate(rows):
            deadline = started + offset / 40.0
            delay = deadline - clock()
            if delay > 0.0:
                sleep(delay)
            camera.ensure_running()
            target = route[source_row]
            gateway.leader.set_target(
                _mapped_leader_target(
                    target, leader_origin, follower_origin
                )
            )
            sample = gateway.sample(clock() - wall_started)
            write_sample(
                handle,
                phase=phase,
                target=target,
                sample=sample,
                source_row=source_row,
            )

    boundaries = [
        int(value) for value in packet["execution"]["segment_boundaries"]
    ]
    try:
        camera_start = camera.start()
        gateway = gateway_factory(_identity(preflight))
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        leader_origin = np.asarray(
            opened["leader_start_degrees"], dtype=np.float64
        )
        follower_origin = np.asarray(
            opened["follower_start_degrees"], dtype=np.float64
        )
        wall_started = clock()
        action_started = wall_started
        with telemetry_path.open("x", encoding="utf-8") as telemetry:
            travel_seconds = max(
                0.5,
                float(np.max(np.abs(start_delta[:4]))) / 10.0,
                abs(float(start_delta[4])) / 15.0,
                abs(float(start_delta[5])) / 20.0,
            )
            steps = max(1, math.ceil(travel_seconds * 20.0))
            for index in range(1, steps + 1):
                deadline = wall_started + index / 20.0
                delay = deadline - clock()
                if delay > 0.0:
                    sleep(delay)
                fraction = index / steps
                smooth = fraction * fraction * (3.0 - 2.0 * fraction)
                target = live + smooth * start_delta
                camera.ensure_running()
                gateway.leader.set_target(
                    _mapped_leader_target(
                        target, leader_origin, follower_origin
                    )
                )
                sample = gateway.sample(clock() - wall_started)
                write_sample(
                    telemetry,
                    phase="pre_roll",
                    target=target,
                    sample=sample,
                    source_row=None,
                )
            boundary_reports.append(
                settle(
                    telemetry,
                    target=route[0],
                    phase="row_zero_settle",
                    timeout_seconds=3.0,
                )
            )
            rebase(route[0], "row_zero")
            for segment_index, (start, stop) in enumerate(
                zip(boundaries[:-1], boundaries[1:], strict=True)
            ):
                first = start if segment_index == 0 else start + 1
                run_rows(
                    telemetry,
                    rows=list(range(first, stop + 1)),
                    phase="forward_source",
                )
                boundary_reports.append(
                    settle(
                        telemetry,
                        target=route[stop],
                        phase=f"forward_boundary_{stop}",
                        timeout_seconds=3.0,
                    )
                )
                rebase(route[stop], f"forward_boundary_{stop}")
            for reverse_index, (start, stop) in enumerate(
                reversed(list(zip(boundaries[:-1], boundaries[1:], strict=True)))
            ):
                first = stop if reverse_index == 0 else stop - 1
                run_rows(
                    telemetry,
                    rows=list(range(first, start - 1, -1)),
                    phase="reverse_source",
                )
                boundary_reports.append(
                    settle(
                        telemetry,
                        target=route[start],
                        phase=f"reverse_boundary_{start}",
                        timeout_seconds=3.0,
                    )
                )
                if start != 0:
                    rebase(route[start], f"reverse_boundary_{start}")
        action_stopped = clock()
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        action_stopped = clock()
    finally:
        if (
            failure is not None
            and gateway is not None
            and wall_started is not None
            and leader_origin is not None
            and follower_origin is not None
            and telemetry_path.is_file()
        ):
            try:
                controlled_return = _controlled_return_to_source_start(
                    gateway,
                    target=route[0],
                    leader_start=leader_origin,
                    follower_start=follower_origin,
                    wall_started=wall_started,
                    samples_path=telemetry_path,
                    clock=clock,
                    sleep=sleep,
                    hold_seconds=2.0,
                )
            except Exception as error:
                controlled_return = {
                    "requested": True,
                    "completed": False,
                    "failure": f"{type(error).__name__}: {error}",
                }
        if gateway is not None:
            try:
                gateway.close()
            except Exception as error:
                cleanup_errors.append(f"gateway: {error}")
        try:
            postflight = preflight_fn()
            _require(
                postflight.get("physical_follower_torque_enabled") is False,
                "RP04C postflight torque is not off",
            )
        except Exception as error:
            cleanup_errors.append(f"postflight: {error}")
        try:
            camera_result = camera.finish(
                action_started_monotonic=action_started,
                action_stopped_monotonic=action_stopped,
                post_roll_seconds=0.0,
            )
        except Exception as error:
            cleanup_errors.append(f"camera: {error}")
    errors = [row["elbow_error_degrees"] for row in forward_metrics]
    maximum_error = max(errors, default=float("inf"))
    threshold = float(
        packet["acceptance"]["sustained_error_threshold_degrees"]
    )
    longest = 0
    active = 0
    for error in errors:
        active = active + 1 if error > threshold else 0
        longest = max(longest, active)
    telemetry_passed = bool(
        failure is None
        and not cleanup_errors
        and len(forward_metrics) == len(route)
        and all(row["sent_exact"] for row in forward_metrics)
        and not any(row["safety_clamped"] for row in forward_metrics)
        and maximum_error
        <= float(packet["acceptance"]["maximum_elbow_error_degrees"])
        and longest
        < int(
            packet["acceptance"]["sustained_error_maximum_seconds"] * 40.0
        )
        and len(boundary_reports) == 9
        and all(row["passed"] for row in boundary_reports)
        and postflight is not None
        and camera_result is not None
        and camera_result.get("status") == "completed"
    )
    observed_elbow = [
        row["elbow_observed_degrees"] for row in forward_metrics
    ]
    receipt = {
        "schema_version":
        "sim2claw.full_range_no_contact_execution_receipt.v1",
        "status": (
            "telemetry_pass_camera_review_pending"
            if telemetry_passed
            else "full_range_no_contact_execution_stopped_safely"
        ),
        "proof_class": "physical_robot_only_no_contact_identification",
        "packet": {"path": str(packet_path), "sha256": _sha(packet_path)},
        "authorization": {
            "path": str(authorization_path),
            "sha256": _sha(authorization_path),
            "authorization_id": authorization["authorization_id"],
        },
        "preflight": preflight,
        "gateway_open": opened,
        "camera_start": camera_start,
        "camera_result": camera_result,
        "postflight": postflight,
        "telemetry": {
            "path": str(telemetry_path),
            "sha256": (
                _sha(telemetry_path) if telemetry_path.is_file() else None
            ),
            "row_count": (
                len(telemetry_path.read_text(encoding="utf-8").splitlines())
                if telemetry_path.is_file()
                else 0
            ),
        },
        "forward_source_sample_count": len(forward_metrics),
        "minimum_observed_elbow_degrees": (
            min(observed_elbow) if observed_elbow else None
        ),
        "maximum_forward_elbow_requested_observed_error_degrees":
        maximum_error,
        "longest_forward_elbow_error_over_threshold_samples": longest,
        "longest_forward_elbow_error_over_threshold_seconds": longest / 40.0,
        "boundary_reports": boundary_reports,
        "origin_rebases": origin_rebases,
        "controlled_return_after_failure": controlled_return,
        "failure": failure,
        "cleanup_errors": cleanup_errors,
        "telemetry_acceptance_passed": telemetry_passed,
        "camera_contact_review_pending": telemetry_passed,
        "mapping_approval": False,
        "physical_task_attempts": 0,
        "pawn_contact_claim": (
            "pending_camera_review" if telemetry_passed else False
        ),
        "retry_authorized": False,
    }
    (output_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "FullRangeNoContactExecutionError",
    "_load_packet",
    "execute",
]
