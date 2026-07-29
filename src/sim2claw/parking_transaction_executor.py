"""Fail-closed executor for the RP02 elbow parking transaction."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from .elbow_telemetry_probe import REGISTER_NAMES, _register_snapshot
from .parking_transaction_preview import ladder_request
from .paths import REPO_ROOT
from .physical_canary import _default_gateway, _default_preflight, _gateway_identity


class ParkingTransactionExecutionError(RuntimeError):
    """The RP02 packet, runtime, or safety state failed closed."""


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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParkingTransactionExecutionError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "RP02 binding escaped repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and _sha(path) == binding.get("sha256"),
        f"RP02 binding changed: {relative}",
    )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def load_packet(path: Path) -> dict[str, Any]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    _require(
        packet.get("schema_version")
        == "sim2claw.parking_transaction_execution_packet.v1"
        and packet.get("status")
        == "frozen_pending_independent_review_and_owner_authorization",
        "RP02 packet identity changed",
    )
    _require(
        packet.get("physical_authority") is False
        and packet.get("physical_task_attempt") is False
        and packet.get("pawn_contact") is False
        and packet.get("retry_without_new_preregistration") is False,
        "RP02 packet authority widened",
    )
    expected = {
        "target_degrees": 91.0,
        "maximum_request_step_degrees": 5.0,
        "maximum_iterations": 12,
        "wait_after_request_seconds": 2.0,
        "telemetry_hz": 5.0,
        "primary_success_maximum_degrees": 92.0,
        "marginal_success_maximum_degrees": 93.0,
        "stall_minimum_progress_degrees": 0.3,
        "stall_consecutive_iterations": 2,
        "held_joint_rebase_maximum_degrees": 0.5,
        "elbow_rebase_maximum_degrees": 1.0,
        "held_joint_drift_stop_degrees": 2.0,
        "hold_seconds": 15.0,
        "maximum_hold_drift_degrees": 0.5,
        "post_torque_off_read_seconds": 60.0,
    }
    _require(packet.get("runtime") == expected, "RP02 runtime constants changed")
    _require(
        packet.get("camera_stop_rule")
        == "camera_loss_or_writer_failure_safe_stop"
        and packet.get("dual_scene_safety_note")
        == (
            "registered scene clears 120 mm moving-chain gate; "
            "uncorrected canonical scene independently remains contact-free"
        ),
        "RP02 safety disclosure changed",
    )
    for binding in packet["inputs"].values():
        _bound(binding)
    closeout = _json(packet["inputs"]["rp01_closeout"])
    _require(
        closeout.get("status") == "pass_open_rp02_packet_freeze_only",
        "RP01 did not open RP02 packet freeze",
    )
    return packet


def load_authorization(
    path: Path,
    *,
    operation_id: str,
    packet_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    authorization = json.loads(path.read_text(encoding="utf-8"))
    _require(
        authorization.get("schema_version")
        == "sim2claw.owner_physical_authorization.v1"
        and authorization.get("status") == "active"
        and authorization.get("operation_id") == operation_id
        and authorization.get("packet_sha256") == packet_sha256
        and authorization.get("physical_parking_transaction") is True
        and authorization.get("physical_task_attempt") is False
        and authorization.get("maximum_executions") == 1,
        "RP02 owner authorization is missing or out of scope",
    )
    _require(
        bool(str(authorization.get("operator_name") or "").strip())
        and authorization.get("operator_present_full_transaction") is True
        and authorization.get(
            "power_down_supply_on_torque_cleanup_error"
        )
        is True,
        "RP02 authorization lacks supervised torque-alarm response",
    )
    issued = datetime.fromisoformat(str(authorization["issued_at"]))
    expires = datetime.fromisoformat(str(authorization["expires_at"]))
    _require(
        issued.tzinfo is not None and expires.tzinfo is not None,
        "RP02 authorization lacks timezone",
    )
    current = now or datetime.now(expires.tzinfo)
    _require(issued <= current < expires, "RP02 authorization is not active")
    return authorization


class C922PiParkingRecorder:
    """Own exact C922 callbacks plus one bounded Pi video."""

    def __init__(
        self,
        output_root: Path,
        *,
        c922_contract_path: Path,
        pi_contract_path: Path,
        session_token: str,
        fixed_mount_token: str,
    ) -> None:
        from .c922_terminal_hold_capture import NativeC922StillRecorder
        from .pi_motion_video import PiMotionVideoRecorder
        from .static_tricam_capture import load_contract

        self.c922 = NativeC922StillRecorder(
            output_root / "c922",
            contract=load_contract(c922_contract_path),
            camera_session_token=session_token,
            fixed_mount_token=fixed_mount_token,
        )
        self.pi = PiMotionVideoRecorder(
            output_root / "pi",
            contract_path=pi_contract_path,
        )
        self.c922_started = False
        self.pi_started = False

    def start(self) -> dict[str, Any]:
        try:
            c922 = self.c922.start()
            self.c922_started = True
            pi = self.pi.start()
            self.pi_started = True
            self.ensure_running()
            return {"c922": c922, "pi": pi}
        except Exception:
            if self.pi_started:
                self.pi._abort()
            if self.c922_started:
                self.c922.finish()
            raise

    def ensure_running(self) -> None:
        process = self.c922.process
        _require(
            process is not None and process.poll() is None,
            "C922 source owner exited",
        )
        self.pi.ensure_running()

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]:
        del post_roll_seconds
        errors: list[str] = []
        c922_result: dict[str, Any] | None = None
        pi_result: dict[str, Any] | None = None
        try:
            c922_result = self.c922.finish()
        except Exception as error:
            errors.append(f"C922: {error}")
        try:
            pi_result = self.pi.finish(
                action_started_monotonic=action_started_monotonic,
                action_stopped_monotonic=action_stopped_monotonic,
                post_roll_seconds=0.0,
            )
        except Exception as error:
            errors.append(f"Pi: {error}")
        _require(not errors, "; ".join(errors))
        return {"status": "completed", "c922": c922_result, "pi": pi_result}


def _registers_complete(snapshot: Mapping[str, Any]) -> bool:
    return all(
        name in snapshot
        and snapshot[name] is not None
        and not (
            isinstance(snapshot[name], Mapping)
            and snapshot[name].get("available") is False
        )
        for name in REGISTER_NAMES
    )


def _require_frozen_output_root(
    packet: Mapping[str, Any], output_root: Path
) -> None:
    expected = (REPO_ROOT / str(packet["output_directory"])).resolve()
    _require(
        output_root.resolve() == expected,
        "RP02 output must equal the packet-frozen one-execution path",
    )


def _sample(
    *,
    gateway: Any,
    camera: CameraEnclosure,
    request: np.ndarray,
    elapsed: float,
    anchor: np.ndarray,
    phase: str,
    iteration: int,
    telemetry: Any,
    clock: Callable[[], float],
) -> dict[str, Any]:
    camera.ensure_running()
    sample = gateway.sample(elapsed, exact_requested_degrees=request)
    _require(
        sample.get("precompiled_exact_action") is True
        and sample.get("rate_limited") is False
        and sample.get("safety_clamped") is False
        and sample.get("physical_follower_torque_enabled") is True,
        "gateway altered or rejected RP02 request",
    )
    actual = np.asarray(
        sample["follower_actual_position_degrees"], dtype=np.float64
    )
    held = np.abs(actual - anchor)
    _require(
        float(np.max(held[[0, 1, 3, 4, 5]])) <= 2.0,
        "held non-elbow joint drift exceeded 2 degrees",
    )
    registers = _register_snapshot(gateway)
    _require(_registers_complete(registers), "required servo telemetry unavailable")
    row = {
        "host_monotonic_seconds": clock(),
        "phase": phase,
        "iteration": iteration,
        "requested_degrees_percent": request.tolist(),
        "registers": registers,
        **sample,
    }
    telemetry.write(json.dumps(row, sort_keys=True) + "\n")
    telemetry.flush()
    return row


def run_ladder(
    *,
    gateway: Any,
    camera: CameraEnclosure,
    anchor: np.ndarray,
    packet: Mapping[str, Any],
    telemetry: Any,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    spec = packet["runtime"]
    period = 1.0 / float(spec["telemetry_hz"])
    started = clock()
    previous_read = float(anchor[2])
    stall_count = 0
    iterations: list[dict[str, Any]] = []
    final_row: dict[str, Any] | None = None
    outcome = "iteration_budget_exhausted"
    request = anchor.copy()

    for iteration in range(1, int(spec["maximum_iterations"]) + 1):
        requested_elbow = ladder_request(
            previous_read,
            target_degrees=float(spec["target_degrees"]),
            maximum_step_degrees=float(spec["maximum_request_step_degrees"]),
        )
        request = anchor.copy()
        request[2] = requested_elbow
        interval_start = clock()
        sample_index = 0
        while True:
            due = interval_start + sample_index * period
            delay = due - clock()
            if delay > 0:
                sleep(delay)
            final_row = _sample(
                gateway=gateway,
                camera=camera,
                request=request,
                elapsed=clock() - started,
                anchor=anchor,
                phase="ladder",
                iteration=iteration,
                telemetry=telemetry,
                clock=clock,
            )
            if clock() - interval_start >= float(
                spec["wait_after_request_seconds"]
            ):
                break
            sample_index += 1
        observed = float(final_row["follower_actual_position_degrees"][2])
        progress = previous_read - observed
        stall_count = stall_count + 1 if progress < float(
            spec["stall_minimum_progress_degrees"]
        ) else 0
        iterations.append(
            {
                "iteration": iteration,
                "previous_read_degrees": previous_read,
                "requested_degrees": requested_elbow,
                "observed_degrees": observed,
                "progress_degrees": progress,
                "consecutive_stall_count": stall_count,
            }
        )
        previous_read = observed
        if observed <= float(spec["primary_success_maximum_degrees"]):
            outcome = "primary_success"
            break
        if stall_count >= int(spec["stall_consecutive_iterations"]):
            outcome = "stall_safe_stop"
            break

    marginal = previous_read <= float(
        spec["marginal_success_maximum_degrees"]
    )
    if outcome == "stall_safe_stop" and marginal:
        outcome = "marginal_success_after_stall"
    elif outcome != "primary_success" and marginal:
        outcome = "marginal_success"

    hold: dict[str, Any] | None = None
    if outcome in {
        "primary_success",
        "marginal_success",
        "marginal_success_after_stall",
    }:
        hold_start = clock()
        hold_initial: float | None = None
        maximum_drift = 0.0
        sample_index = 0
        while clock() - hold_start < float(spec["hold_seconds"]):
            due = hold_start + sample_index * period
            delay = due - clock()
            if delay > 0:
                sleep(delay)
            final_row = _sample(
                gateway=gateway,
                camera=camera,
                request=request,
                elapsed=clock() - started,
                anchor=anchor,
                phase="hold",
                iteration=len(iterations),
                telemetry=telemetry,
                clock=clock,
            )
            elbow = float(final_row["follower_actual_position_degrees"][2])
            hold_initial = elbow if hold_initial is None else hold_initial
            maximum_drift = max(maximum_drift, abs(elbow - hold_initial))
            _require(
                maximum_drift
                <= float(spec["maximum_hold_drift_degrees"]),
                "RP02 elbow hold drift exceeded gate",
            )
            sample_index += 1
        hold = {
            "duration_seconds": clock() - hold_start,
            "initial_elbow_degrees": hold_initial,
            "maximum_elbow_drift_degrees": maximum_drift,
            "passed": True,
        }

    return {
        "outcome": outcome,
        "iterations": iterations,
        "final_elbow_degrees": previous_read,
        "hold": hold,
        "terminal_above_93_degrees": previous_read
        > float(spec["marginal_success_maximum_degrees"]),
    }


def execute(
    *,
    packet_path: Path,
    authorization_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = _default_preflight,
    gateway_factory: Callable[[Any], Any] = _default_gateway,
    camera_factory: Callable[[Path, Mapping[str, Any]], CameraEnclosure] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _require(operator_acknowledged, "RP02 execution requires --yes")
    packet_path = packet_path.resolve()
    authorization_path = authorization_path.resolve()
    output_root = output_root.resolve()
    packet = load_packet(packet_path)
    _require_frozen_output_root(packet, output_root)
    authorization = load_authorization(
        authorization_path,
        operation_id=str(packet["operation_id"]),
        packet_sha256=_sha(packet_path),
    )
    _require(not output_root.exists(), "refusing to overwrite RP02 output")

    preflight_start = clock()
    preflight = preflight_fn()
    preflight_end = clock()
    _require(
        preflight.get("passed") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "RP02 execution preflight failed",
    )
    expected = np.asarray(packet["expected_anchor_degrees_percent"], dtype=float)
    observed = np.asarray(preflight["follower_start_degrees"], dtype=float)
    delta = np.abs(observed - expected)
    _require(
        float(np.max(delta[[0, 1, 3, 4, 5]]))
        <= float(packet["runtime"]["held_joint_rebase_maximum_degrees"])
        and float(delta[2])
        <= float(packet["runtime"]["elbow_rebase_maximum_degrees"]),
        "RP02 execution preflight exceeded rebase gate",
    )
    _require(
        preflight["follower_port"] == packet["follower_port"]
        and preflight["follower_calibration_sha256"]
        == packet["follower_calibration_sha256"],
        "RP02 hardware identity changed",
    )

    output_root.mkdir(parents=True, exist_ok=False)
    telemetry_path = output_root / "telemetry.jsonl"
    if camera_factory is None:
        def camera_factory(
            root: Path, value: Mapping[str, Any]
        ) -> CameraEnclosure:
            return C922PiParkingRecorder(
                root,
                c922_contract_path=_bound(
                    value["inputs"]["c922_contract"]
                ),
                pi_contract_path=_bound(value["inputs"]["pi_contract"]),
                session_token=str(value["camera"]["session_token"]),
                fixed_mount_token=str(value["camera"]["fixed_mount_token"]),
            )

    camera = camera_factory(output_root / "cameras", packet)
    gateway: Any = None
    camera_start: dict[str, Any] | None = None
    camera_result: dict[str, Any] | None = None
    ladder: dict[str, Any] | None = None
    opened: dict[str, Any] | None = None
    postflight: dict[str, Any] | None = None
    failure: str | None = None
    cleanup_errors: list[str] = []
    action_started: float | None = None
    action_stopped: float | None = None
    try:
        camera_start = camera.start()
        gateway = gateway_factory(_gateway_identity(preflight))
        opened = gateway.open_live_anchored_setup()
        anchor = np.asarray(opened["setup_command_anchor_degrees"], dtype=float)
        live_delta = np.abs(anchor - observed)
        _require(
            float(np.max(live_delta[[0, 1, 3, 4, 5]])) <= 0.5
            and float(live_delta[2]) <= 1.0,
            "torque-on RP02 anchor exceeded rebase gate",
        )
        action_started = clock()
        with telemetry_path.open("x", encoding="utf-8") as telemetry:
            ladder = run_ladder(
                gateway=gateway,
                camera=camera,
                anchor=anchor,
                packet=packet,
                telemetry=telemetry,
                clock=clock,
                sleep=sleep,
            )
        action_stopped = clock()
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        action_stopped = clock()
    finally:
        if gateway is not None:
            try:
                gateway.close()
            except Exception as error:
                cleanup_errors.append(f"gateway: {error}")
        try:
            persistence_start = clock()
            while clock() - persistence_start < float(
                packet["runtime"]["post_torque_off_read_seconds"]
            ):
                camera.ensure_running()
                sleep(min(0.2, float(
                    packet["runtime"]["post_torque_off_read_seconds"]
                ) - (clock() - persistence_start)))
            postflight = preflight_fn()
            _require(
                postflight.get("physical_follower_torque_enabled") is False,
                "post-RP02 follower torque is not off",
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

    passed = bool(
        failure is None
        and not cleanup_errors
        and ladder is not None
        and ladder["outcome"]
        in {
            "primary_success",
            "marginal_success",
            "marginal_success_after_stall",
        }
        and postflight is not None
        and camera_result is not None
        and camera_result.get("status") == "completed"
    )
    receipt = {
        "schema_version": "sim2claw.parking_transaction_execution_receipt.v1",
        "status": (
            "parking_transaction_complete"
            if passed
            else "parking_transaction_stopped_safely"
        ),
        "proof_class": "physical_setup_recovery_not_task_evidence",
        "packet": {"path": str(packet_path), "sha256": _sha(packet_path)},
        "authorization": {
            "path": str(authorization_path),
            "sha256": _sha(authorization_path),
            "authorization_id": authorization["authorization_id"],
        },
        "execution_preflight": {
            **preflight,
            "host_monotonic_start": preflight_start,
            "host_monotonic_end": preflight_end,
        },
        "gateway_open": opened,
        "ladder": ladder,
        "camera_start": camera_start,
        "camera_result": camera_result,
        "postflight": postflight,
        "telemetry": (
            {
                "path": str(telemetry_path),
                "sha256": _sha(telemetry_path),
                "row_count": len(
                    telemetry_path.read_text(encoding="utf-8").splitlines()
                ),
            }
            if telemetry_path.is_file()
            else None
        ),
        "failure": failure,
        "cleanup_errors": cleanup_errors,
        "physical_task_attempts": 0,
        "pawn_contact": False,
        "retry_authorized": False,
        "passed": passed,
    }
    (output_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    receipt = execute(
        packet_path=args.packet,
        authorization_path=args.authorization,
        output_root=args.output,
        operator_acknowledged=args.yes,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
