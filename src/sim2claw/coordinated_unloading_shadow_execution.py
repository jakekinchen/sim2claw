"""Execute one camera-enclosed coordinated-unloading shadow transaction."""

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


class CoordinatedUnloadingShadowExecutionError(RuntimeError):
    """The one-shot physical shadow transaction failed closed."""


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
        raise CoordinatedUnloadingShadowExecutionError(message)


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CoordinatedUnloadingShadowExecutionError(
            "shadow-execution input escapes repository"
        ) from error
    _require(path.is_file(), f"shadow-execution input is missing: {path}")
    _require(_sha(path) == binding["sha256"], f"shadow-execution input changed: {path}")
    return path


def _load_packet(packet_path: Path) -> tuple[dict[str, Any], np.ndarray]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    _require(
        packet.get("schema_version")
        == "sim2claw.coordinated_unloading_shadow_execution_packet.v1",
        "unexpected shadow-execution packet schema",
    )
    for binding in packet["inputs"].values():
        _bound(binding)
    static_receipt = json.loads(
        _bound(packet["inputs"]["static_receipt"]).read_text(encoding="utf-8")
    )
    _require(
        static_receipt["status"]
        == "coordinated_unloading_shadow_probe_static_pass"
        and static_receipt["passed"] is True
        and static_receipt["physical_task_attempts"] == 0,
        "static shadow-probe receipt is not an admitted pass",
    )
    action_path = _bound(packet["physical_prefix"])
    shape = tuple(int(value) for value in packet["physical_prefix"]["shape"])
    actions = np.fromfile(action_path, dtype="<f8")
    _require(actions.size == int(np.prod(shape)), "physical prefix shape changed")
    actions = np.ascontiguousarray(actions.reshape(shape), dtype="<f8")
    _require(shape == (491, 6), "physical prefix denominator changed")
    boundaries = [int(value) for value in packet["execution"]["segment_boundaries"]]
    _require(boundaries == [0, 433, 490], "segment boundaries changed")
    _require(
        np.array_equal(
            actions[0],
            np.asarray(packet["execution"]["expected_row_zero"], dtype="<f8"),
        ),
        "physical row zero changed",
    )
    _require(
        packet["physical_task_attempt"] is False
        and packet["pawn_contact"] is False
        and packet["maximum_executions"] == 1,
        "shadow packet widened physical authority",
    )
    return packet, actions


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
        "owner authorization does not bind this one execution",
    )
    _require(
        authorization["physical_no_contact_diagnostic"] is True
        and authorization["physical_task_attempt"] is False
        and authorization["pawn_contact"] is False,
        "owner authorization widened the shadow proof class",
    )
    _require(
        authorization["autonomous_agent_supervision"] is True
        and authorization["power_down_supply_on_torque_cleanup_error"] is True,
        "owner authorization lacks the fail-safe response",
    )
    issued = datetime.fromisoformat(str(authorization["issued_at"]))
    expires = datetime.fromisoformat(str(authorization["expires_at"]))
    _require(
        issued.tzinfo is not None and expires.tzinfo is not None,
        "owner authorization lacks timezone",
    )
    current = now or datetime.now(expires.tzinfo)
    _require(issued <= current < expires, "owner authorization is not active")
    return authorization


def _identity(preflight: Mapping[str, Any]) -> GatewayIdentity:
    return GatewayIdentity(
        leader_port=str(preflight["leader_port"]),
        follower_port=str(preflight["follower_port"]),
        leader_calibration_sha256=str(preflight["leader_calibration_sha256"]),
        follower_calibration_sha256=str(preflight["follower_calibration_sha256"]),
    )


def _residual(target: np.ndarray, actual: np.ndarray) -> np.ndarray:
    result = target - actual
    result[4] = shortest_delta_degrees(float(target[4]), float(actual[4]))
    return result


def execute(
    *,
    packet_path: Path,
    authorization_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = physical_gateway_preflight,
    gateway_factory: Callable[[GatewayIdentity], Any] = physical_replay_gateway,
    camera_factory: Callable[[Path, Mapping[str, Any]], CameraEnclosure] | None = None,
    clock: Clock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> dict[str, Any]:
    """Execute the exact prefix forward, return over exact reverse rows, stop torque."""

    _require(operator_acknowledged, "explicit owner acknowledgement is required")
    packet_path = packet_path.resolve()
    authorization_path = authorization_path.resolve()
    output_root = output_root.resolve()
    packet, actions = _load_packet(packet_path)
    authorization = _load_authorization(
        authorization_path, packet=packet, packet_path=packet_path
    )
    expected_output = (REPO_ROOT / str(packet["output_directory"])).resolve()
    _require(output_root == expected_output, "output path differs from frozen packet")
    _require(not output_root.exists(), "refusing to overwrite one-shot output")

    preflight = preflight_fn()
    _require(
        preflight.get("passed") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "fresh torque-off preflight failed",
    )
    _require(
        preflight["follower_port"] == packet["hardware"]["follower_port"]
        and preflight["follower_calibration_sha256"]
        == packet["hardware"]["follower_calibration_sha256"],
        "follower identity changed",
    )
    live = np.asarray(preflight["follower_start_degrees"], dtype=np.float64)
    start_delta = _residual(actions[0], live)
    _require(
        float(np.max(np.abs(start_delta[:5])))
        <= float(packet["execution"]["maximum_start_body_delta_degrees"])
        and abs(float(start_delta[5]))
        <= float(packet["execution"]["maximum_start_gripper_delta"]),
        "fresh follower pose is outside the frozen pre-roll envelope",
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
    source_metrics: list[dict[str, Any]] = []
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
        sent = np.asarray(sample["follower_command_degrees"], dtype=np.float64)
        actual = np.asarray(
            sample["follower_actual_position_degrees"], dtype=np.float64
        )
        residual = _residual(target, actual)
        exact_sent = bool(np.all(np.abs(sent - target) <= 0.25))
        row = {
            **sample,
            "schema_version": (
                "sim2claw.coordinated_unloading_shadow_execution_sample.v1"
            ),
            "phase": phase,
            "source_row_or_missing": source_row,
            "requested_source_command_degrees": target.tolist(),
            "source_requested_bytes_unchanged": True,
            "source_command_sent_within_0p25_degree": exact_sent,
            "requested_minus_observed_degrees": residual.tolist(),
            "host_monotonic": clock(),
        }
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
        handle.flush()
        if source_row is not None and phase == "forward_source":
            source_metrics.append(
                {
                    "source_row": source_row,
                    "elbow_error_degrees": abs(float(residual[2])),
                    "all_joint_residual_degrees": residual.tolist(),
                    "sent_exact": exact_sent,
                    "safety_clamped": bool(sample.get("safety_clamped")),
                }
            )
        return row

    def settle_boundary(
        handle: Any,
        *,
        target: np.ndarray,
        phase: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        assert gateway is not None
        assert leader_origin is not None and follower_origin is not None
        started = clock()
        last_row: dict[str, Any] | None = None
        while clock() - started <= timeout_seconds:
            camera.ensure_running()
            gateway.leader.set_target(
                _mapped_leader_target(target, leader_origin, follower_origin)
            )
            sample = gateway.sample(clock() - wall_started)  # type: ignore[arg-type]
            last_row = write_sample(
                handle,
                phase=phase,
                target=target,
                sample=sample,
                source_row=None,
            )
            actual = np.asarray(
                sample["follower_actual_position_degrees"], dtype=np.float64
            )
            residual = _residual(target, actual)
            if float(np.max(np.abs(residual[:5]))) <= 2.0 and abs(
                float(residual[5])
            ) <= 2.0:
                return {
                    "phase": phase,
                    "target_degrees": target.tolist(),
                    "actual_degrees": actual.tolist(),
                    "residual_degrees": residual.tolist(),
                    "passed": True,
                }
            sleep(0.05)
        raise CoordinatedUnloadingShadowExecutionError(
            f"{phase} did not reach the frozen 2 degree boundary gate"
        )

    def rebase(target: np.ndarray, phase: str) -> None:
        nonlocal leader_origin, follower_origin
        assert gateway is not None
        assert leader_origin is not None and follower_origin is not None
        next_leader = _mapped_leader_target(target, leader_origin, follower_origin)
        report = gateway.rebase_relative_origin(
            leader_origin=next_leader,
            follower_origin=target,
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
        started = clock()
        for offset, source_row in enumerate(rows):
            deadline = started + offset / 40.0
            delay = deadline - clock()
            if delay > 0:
                sleep(delay)
            camera.ensure_running()
            target = actions[source_row]
            gateway.leader.set_target(
                _mapped_leader_target(target, leader_origin, follower_origin)
            )
            sample = gateway.sample(clock() - wall_started)  # type: ignore[arg-type]
            write_sample(
                handle,
                phase=phase,
                target=target,
                sample=sample,
                source_row=source_row,
            )

    try:
        camera_start = camera.start()
        gateway = gateway_factory(_identity(preflight))
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        leader_origin = np.asarray(opened["leader_start_degrees"], dtype=np.float64)
        follower_origin = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
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
                if delay > 0:
                    sleep(delay)
                fraction = index / steps
                smooth = fraction * fraction * (3.0 - 2.0 * fraction)
                target = live + smooth * start_delta
                camera.ensure_running()
                gateway.leader.set_target(
                    _mapped_leader_target(target, leader_origin, follower_origin)
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
                settle_boundary(
                    telemetry,
                    target=actions[0],
                    phase="row_zero_settle",
                    timeout_seconds=2.0,
                )
            )
            rebase(actions[0], "row_zero")

            run_rows(telemetry, rows=list(range(0, 434)), phase="forward_source")
            boundary_reports.append(
                settle_boundary(
                    telemetry,
                    target=actions[433],
                    phase="forward_boundary_433",
                    timeout_seconds=2.0,
                )
            )
            rebase(actions[433], "forward_boundary_433")
            run_rows(telemetry, rows=list(range(434, 491)), phase="forward_source")
            boundary_reports.append(
                settle_boundary(
                    telemetry,
                    target=actions[490],
                    phase="forward_terminal_490",
                    timeout_seconds=2.0,
                )
            )
            rebase(actions[490], "forward_terminal_490")

            run_rows(
                telemetry,
                rows=list(range(490, 432, -1)),
                phase="reverse_source",
            )
            boundary_reports.append(
                settle_boundary(
                    telemetry,
                    target=actions[433],
                    phase="reverse_boundary_433",
                    timeout_seconds=2.0,
                )
            )
            rebase(actions[433], "reverse_boundary_433")
            run_rows(
                telemetry,
                rows=list(range(432, -1, -1)),
                phase="reverse_source",
            )
            boundary_reports.append(
                settle_boundary(
                    telemetry,
                    target=actions[0],
                    phase="return_row_zero",
                    timeout_seconds=3.0,
                )
            )
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
                    target=actions[0],
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
                "postflight torque is not off",
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

    elbow_errors = [
        float(row["elbow_error_degrees"]) for row in source_metrics
    ]
    maximum_elbow_error = max(elbow_errors, default=float("inf"))
    longest_over_three = 0
    active_over_three = 0
    for error in elbow_errors:
        active_over_three = active_over_three + 1 if error > 3.0 else 0
        longest_over_three = max(longest_over_three, active_over_three)
    telemetry_passed = bool(
        failure is None
        and not cleanup_errors
        and len(source_metrics) == 491
        and all(row["sent_exact"] for row in source_metrics)
        and not any(row["safety_clamped"] for row in source_metrics)
        and maximum_elbow_error
        <= float(packet["acceptance"]["maximum_elbow_error_degrees"])
        and longest_over_three
        < int(
            float(packet["acceptance"]["sustained_error_maximum_seconds"]) * 40.0
        )
        and len(boundary_reports) == 5
        and all(row["passed"] for row in boundary_reports)
        and postflight is not None
        and camera_result is not None
        and camera_result.get("status") == "completed"
    )
    receipt = {
        "schema_version": (
            "sim2claw.coordinated_unloading_shadow_execution_receipt.v1"
        ),
        "status": (
            "telemetry_pass_camera_review_pending"
            if telemetry_passed
            else "coordinated_unloading_shadow_stopped_safely"
        ),
        "proof_class": "physical_no_contact_coordinated_unloading_diagnostic",
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
            "sha256": _sha(telemetry_path) if telemetry_path.is_file() else None,
            "row_count": (
                len(telemetry_path.read_text(encoding="utf-8").splitlines())
                if telemetry_path.is_file()
                else 0
            ),
        },
        "forward_source_sample_count": len(source_metrics),
        "maximum_forward_elbow_requested_observed_error_degrees": maximum_elbow_error,
        "longest_forward_elbow_error_over_3deg_samples": longest_over_three,
        "longest_forward_elbow_error_over_3deg_seconds": (
            longest_over_three / 40.0
        ),
        "boundary_reports": boundary_reports,
        "origin_rebases": origin_rebases,
        "controlled_return_after_failure": controlled_return,
        "failure": failure,
        "cleanup_errors": cleanup_errors,
        "telemetry_acceptance_passed": telemetry_passed,
        "camera_contact_review_pending": telemetry_passed,
        "mapping_approval": False,
        "physical_task_attempts": 0,
        "pawn_contact_claim": "pending_camera_review" if telemetry_passed else False,
        "retry_authorized": False,
    }
    (output_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
