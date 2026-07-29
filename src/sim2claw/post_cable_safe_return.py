"""Static qualification and one-shot execution of the RP04H safe return."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from . import full_range_no_contact_execution as _execution
from . import full_range_no_contact_identification as _identification
from .coordinated_unloading_shadow_probe import _scene_audit
from .parking_transaction_executor import C922PiParkingRecorder
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .physical_trace_replay import (
    _mapped_leader_target,
    physical_replay_gateway,
)
from .teleop_recording import physical_gateway_preflight


class PostCableSafeReturnError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PostCableSafeReturnError(message)


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise PostCableSafeReturnError(
            "RP04H input escapes repository"
        ) from error
    _require(
        path.is_file() and _sha(path) == binding["sha256"],
        f"RP04H input changed: {path}",
    )
    return path


def _display(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT.resolve()))


def _interpolate(
    start: np.ndarray, target: np.ndarray, maximum_step: float
) -> np.ndarray:
    steps = max(
        1, int(math.ceil(float(np.max(np.abs(target - start))) / maximum_step))
    )
    return np.asarray(
        [
            start + (target - start) * (index / steps)
            for index in range(steps + 1)
        ],
        dtype="<f8",
        order="C",
    )


def compile_return(
    contract_path: Path, output_directory: Path
) -> dict[str, Any]:
    _require(
        not output_directory.exists(), "immutable RP04H output already exists"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.post_cable_safe_return_static.v1"
        and contract["authority"]
        == {
            "model_loading": True,
            "static_simulation": True,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "transfer_claim": False,
        },
        "RP04H static authority changed",
    )
    for entry in contract["inputs"].values():
        _bound(entry)
    manifest = json.loads(
        _bound(contract["inputs"]["candidate_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    rigid = json.loads(
        _bound(contract["inputs"]["registered_rigid_candidate"]).read_text(
            encoding="utf-8"
        )
    )
    start = np.asarray(contract["route"]["start_degrees"], dtype="<f8")
    stage = np.asarray(contract["route"]["stage_degrees"], dtype="<f8")
    target = np.asarray(contract["route"]["target_degrees"], dtype="<f8")
    maximum_step = float(contract["route"]["maximum_step_degrees"])
    first = _interpolate(start, stage, maximum_step)
    second = _interpolate(stage, target, maximum_step)
    physical = np.asarray(
        np.vstack((first, second[1:])), dtype="<f8", order="C"
    )
    boundary = len(first) - 1
    _require(
        list(physical.shape) == contract["route"]["expected_shape"]
        and boundary == contract["route"]["stage_boundary_row"]
        and np.array_equal(physical[0], start)
        and np.array_equal(physical[-1], target),
        "RP04H route denominator changed",
    )
    candidate = manifest["candidate_config"]
    model_actions = np.asarray(
        _physical_to_model_position(physical, candidate),
        dtype="<f8",
        order="C",
    )
    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model, candidate
    )
    selected_piece = str(contract["geometry"]["selected_piece_id"])
    registered_scene = _scene_audit(
        model_builder=model_builder,
        rigid=rigid,
        actions=model_actions,
        selected_piece_id=selected_piece,
    )
    uncorrected = {
        "robot_board_translation_xyz_m": [0.0, 0.0, 0.0],
        "robot_board_yaw_radians": 0.0,
    }
    uncorrected_scene = _scene_audit(
        model_builder=model_builder,
        rigid=uncorrected,
        actions=model_actions,
        selected_piece_id=selected_piece,
    )
    registered_clearance = _identification._clearance_audit(
        model_builder=model_builder, rigid=rigid, actions=model_actions
    )
    uncorrected_clearance = _identification._clearance_audit(
        model_builder=model_builder,
        rigid=uncorrected,
        actions=model_actions,
    )
    lower = np.asarray(contract["gateway"]["calibrated_minimum"], dtype=float)
    upper = np.asarray(contract["gateway"]["calibrated_maximum"], dtype=float)
    sample_hz = float(contract["route"]["sample_hz"])
    rates = np.max(np.abs(np.diff(physical, axis=0)) * sample_hz, axis=0)
    rate_limits = np.asarray(
        contract["gateway"]["maximum_rates_per_second"], dtype=float
    )
    clearance = float(contract["geometry"]["minimum_clearance_m"])
    checks = {
        "registered_scene_contact_free": registered_scene["passed"],
        "uncorrected_scene_contact_free": uncorrected_scene["passed"],
        "registered_scene_clearance": registered_clearance[
            "minimum_overall_clearance_m"
        ]
        >= clearance,
        "uncorrected_scene_clearance": uncorrected_clearance[
            "minimum_overall_clearance_m"
        ]
        >= clearance,
        "inside_calibrated_limits": bool(
            np.all(physical >= lower) and np.all(physical <= upper)
        ),
        "inside_gateway_rates": bool(np.all(rates <= rate_limits)),
        "row_zero_exact_postflight_pose": np.array_equal(physical[0], start),
        "terminal_exact_natural_anchor": np.array_equal(
            physical[-1], target
        ),
        "two_stage_route": boundary > 0 and boundary < len(physical) - 1,
    }
    passed = all(checks.values())
    output_directory.mkdir(parents=True)
    physical_path = output_directory / "physical_route.f64le"
    model_path = output_directory / "model_route.f64le"
    physical_path.write_bytes(physical.tobytes(order="C"))
    model_path.write_bytes(model_actions.tobytes(order="C"))
    receipt = {
        "schema_version": "sim2claw.post_cable_safe_return_static_receipt.v1",
        "status": (
            "post_cable_safe_return_static_pass"
            if passed
            else "post_cable_safe_return_static_reject"
        ),
        "passed": passed,
        "contract_path": _display(contract_path),
        "contract_sha256": _sha(contract_path),
        "physical_route": {
            "path": _display(physical_path),
            "sha256": _sha(physical_path),
            "shape": list(physical.shape),
            "dtype": "little_endian_float64",
        },
        "model_route": {
            "path": _display(model_path),
            "sha256": _sha(model_path),
            "shape": list(model_actions.shape),
            "dtype": "little_endian_float64",
        },
        "stage_boundary_row": boundary,
        "maximum_rates_per_second": rates.tolist(),
        "registered_scene": registered_scene,
        "uncorrected_scene": uncorrected_scene,
        "registered_clearance": registered_clearance,
        "uncorrected_clearance": uncorrected_clearance,
        "checks": checks,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "passed_claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def execute_return(
    *,
    packet_path: Path,
    authorization_path: Path,
    output_directory: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = physical_gateway_preflight,
    gateway_factory: Callable[[Any], Any] = physical_replay_gateway,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _require(operator_acknowledged, "explicit owner acknowledgement required")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    _require(
        packet.get("schema_version")
        == "sim2claw.post_cable_safe_return_packet.v1"
        and packet["maximum_executions"] == 1
        and packet["physical_task_attempt"] is False
        and packet["pawn_contact"] is False
        and packet["mapping_approval"] is False,
        "RP04H packet widened authority",
    )
    for entry in packet["inputs"].values():
        _bound(entry)
    static = json.loads(
        _bound(packet["inputs"]["static_receipt"]).read_text(encoding="utf-8")
    )
    _require(
        static["passed"] is True
        and static["status"] == "post_cable_safe_return_static_pass",
        "RP04H static route is not admitted",
    )
    route_entry = packet["physical_route"]
    route_path = _bound(route_entry)
    route = np.fromfile(route_path, dtype="<f8").reshape(route_entry["shape"])
    _require(
        route_entry["sha256"] == static["physical_route"]["sha256"]
        and route.shape[1] == 6,
        "RP04H route differs from static pass",
    )
    authorization = _execution._load_authorization(
        authorization_path.resolve(),
        packet=packet,
        packet_path=packet_path.resolve(),
    )
    expected_output = (REPO_ROOT / packet["output_directory"]).resolve()
    _require(
        output_directory.resolve() == expected_output
        and not expected_output.exists(),
        "RP04H output path changed or exists",
    )
    preflight = preflight_fn()
    _require(
        preflight.get("passed") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "fresh RP04H torque-off preflight failed",
    )
    _require(
        preflight["follower_port"] == packet["hardware"]["follower_port"]
        and preflight["follower_calibration_sha256"]
        == packet["hardware"]["follower_calibration_sha256"],
        "RP04H follower identity changed",
    )
    live = np.asarray(preflight["follower_start_degrees"], dtype=float)
    start_residual = _execution._residual(route[0], live)
    _require(
        float(np.max(np.abs(start_residual[:5])))
        <= packet["execution"]["maximum_start_body_delta_degrees"]
        and abs(float(start_residual[5]))
        <= packet["execution"]["maximum_start_gripper_delta"],
        "fresh RP04H pose is outside the start envelope",
    )
    expected_output.mkdir(parents=True)
    telemetry_path = expected_output / "telemetry.jsonl"
    camera = C922PiParkingRecorder(
        expected_output / "cameras",
        c922_contract_path=_bound(packet["inputs"]["c922_contract"]),
        pi_contract_path=_bound(packet["inputs"]["pi_contract"]),
        session_token=packet["camera"]["session_token"],
        fixed_mount_token=packet["camera"]["fixed_mount_token"],
    )
    gateway = None
    camera_start = None
    camera_result = None
    opened = None
    postflight = None
    failure = None
    cleanup_errors: list[str] = []
    samples: list[dict[str, Any]] = []
    action_started = None
    action_stopped = None
    try:
        camera_start = camera.start()
        identity = _execution._identity(preflight)
        gateway = gateway_factory(identity)
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        leader_origin = np.asarray(opened["leader_start_degrees"], dtype=float)
        follower_origin = np.asarray(
            opened["follower_start_degrees"], dtype=float
        )
        action_started = clock()
        boundary = int(packet["execution"]["stage_boundary_row"])
        with telemetry_path.open("x", encoding="utf-8") as handle:
            for index, target in enumerate(route):
                deadline = action_started + index / packet["execution"][
                    "sample_hz"
                ]
                delay = deadline - clock()
                if delay > 0:
                    sleep(delay)
                camera.ensure_running()
                gateway.leader.set_target(
                    _mapped_leader_target(
                        target, leader_origin, follower_origin
                    )
                )
                sample = gateway.sample(clock() - action_started)
                actual = np.asarray(
                    sample["follower_actual_position_degrees"], dtype=float
                )
                residual = _execution._residual(target, actual)
                row = {
                    **sample,
                    "schema_version":
                    "sim2claw.post_cable_safe_return_sample.v1",
                    "route_row": index,
                    "requested_degrees": target.tolist(),
                    "requested_minus_observed_degrees": residual.tolist(),
                    "sent_exact": bool(
                        np.all(
                            np.abs(
                                np.asarray(
                                    sample["follower_command_degrees"],
                                    dtype=float,
                                )
                                - target
                            )
                            <= 0.25
                        )
                    ),
                }
                handle.write(
                    json.dumps(row, separators=(",", ":"), sort_keys=True)
                    + "\n"
                )
                handle.flush()
                samples.append(row)
                if index == boundary:
                    sleep(packet["execution"]["stage_hold_seconds"])
            final_started = clock()
            final_actual = np.asarray(
                samples[-1]["follower_actual_position_degrees"], dtype=float
            )
            while (
                float(
                    np.max(
                        np.abs(
                            _execution._residual(route[-1], final_actual)[:5]
                        )
                    )
                )
                > packet["acceptance"]["maximum_final_body_residual_degrees"]
                and clock() - final_started
                <= packet["execution"]["final_hold_timeout_seconds"]
            ):
                camera.ensure_running()
                gateway.leader.set_target(
                    _mapped_leader_target(
                        route[-1], leader_origin, follower_origin
                    )
                )
                sample = gateway.sample(clock() - action_started)
                final_actual = np.asarray(
                    sample["follower_actual_position_degrees"], dtype=float
                )
                sleep(0.05)
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
            postflight = preflight_fn()
            _require(
                postflight.get("physical_follower_torque_enabled") is False,
                "RP04H postflight torque is not off",
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
    final_pose = np.asarray(
        (postflight or {}).get("follower_start_degrees", [math.nan] * 6),
        dtype=float,
    )
    final_residual = _execution._residual(route[-1], final_pose)
    passed = bool(
        failure is None
        and not cleanup_errors
        and len(samples) == len(route)
        and all(row["sent_exact"] for row in samples)
        and not any(row.get("safety_clamped") for row in samples)
        and float(np.max(np.abs(final_residual[:5])))
        <= packet["acceptance"]["maximum_final_body_residual_degrees"]
        and abs(float(final_residual[5]))
        <= packet["acceptance"]["maximum_final_gripper_residual"]
        and camera_result is not None
        and camera_result.get("status") == "completed"
        and postflight is not None
        and postflight.get("physical_follower_torque_enabled") is False
    )
    receipt = {
        "schema_version": "sim2claw.post_cable_safe_return_receipt.v1",
        "status": (
            "post_cable_safe_return_pass"
            if passed
            else "post_cable_safe_return_stopped_safely"
        ),
        "passed": passed,
        "packet": {"path": _display(packet_path), "sha256": _sha(packet_path)},
        "authorization": {
            "path": _display(authorization_path),
            "sha256": _sha(authorization_path),
            "authorization_id": authorization["authorization_id"],
        },
        "preflight": preflight,
        "gateway_open": opened,
        "camera_start": camera_start,
        "camera_result": camera_result,
        "failure": failure,
        "cleanup_errors": cleanup_errors,
        "route_sample_count": len(route),
        "executed_sample_count": len(samples),
        "postflight": postflight,
        "final_target_degrees": route[-1].tolist(),
        "final_residual_degrees": final_residual.tolist(),
        "telemetry": {
            "path": _display(telemetry_path),
            "sha256": _sha(telemetry_path) if telemetry_path.is_file() else None,
        },
        "physical_task_attempts": 0,
        "pawn_contact_claim": False,
        "mapping_approval": False,
    }
    (expected_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["PostCableSafeReturnError", "compile_return", "execute_return"]
