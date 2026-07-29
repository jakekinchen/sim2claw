"""Receipt-bound, no-contact elbow telemetry diagnostic.

This executor is setup/calibration evidence only. It uses the reviewed SO-101
gateway, compiles targets from the fresh torque-on anchor, records an identical
wrist-flex control, performs one torque off/on cycle, and never writes a servo
configuration register.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from .overhead_video import WristVideoRecorder
from .physical_canary import _default_gateway, _default_preflight, _gateway_identity
from .replay_eligibility import action_sha256
from .live_anchored_camera_reposition import _preflight_identity_and_limits
from .wrist_view_reposition import preview_wrist_view_actions


CONTRACT_SCHEMA = "sim2claw.elbow_telemetry_probe_contract.v3"
RECEIPT_SCHEMA = "sim2claw.elbow_telemetry_probe_receipt.v1"
SAMPLE_HZ = 20.0
REGISTER_HZ = 5.0
REGISTER_NAMES = (
    "Present_Current",
    "Present_Load",
    "Present_Temperature",
    "Status",
    "Goal_Position",
    "Torque_Enable",
)
JOINT_INDEX = {"elbow_flex": 2, "wrist_flex": 3}


class ElbowTelemetryProbeError(RuntimeError):
    """The diagnostic failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ElbowTelemetryProbeError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ElbowTelemetryProbeError(f"could not read {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def load_contract(path: Path) -> dict[str, Any]:
    contract = _read_json(path, "elbow telemetry contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "contract schema changed")
    _require(
        contract.get("status") == "preregistered_before_no_contact_probe"
        and contract.get("proof_class")
        == "prospective_no_contact_physical_elbow_telemetry_diagnostic",
        "contract identity changed",
    )
    _require(
        contract.get("elbow_offsets_degrees") == [-3.0, -5.0]
        and contract.get("wrist_control_offsets_degrees")
        == [3.0, -3.0, 5.0, -5.0]
        and contract.get("repeat_after_torque_cycle") == {
            "joint": "elbow_flex",
            "offset_degrees": -5.0,
        },
        "probe offsets changed",
    )
    _require(
        float(contract.get("sample_hz")) == SAMPLE_HZ
        and float(contract.get("register_hz")) == REGISTER_HZ
        and tuple(contract.get("registers") or ()) == REGISTER_NAMES,
        "probe observability changed",
    )
    _require(
        contract.get("physical_task_attempt") is False
        and contract.get("pawn_contact") is False
        and contract.get("gain_write") is False
        and contract.get("configuration_write") is False,
        "probe authority widened",
    )
    expires = datetime.fromisoformat(str(contract["authorization_expires_at"]))
    _require(expires.tzinfo is not None, "authorization expiry lacks timezone")
    return contract


def _trajectory(
    anchor: np.ndarray,
    *,
    joint: str,
    offsets: list[float],
    maximum_slew_degrees_s: float,
    hold_seconds: float,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    index = JOINT_INDEX[joint]
    rows: list[np.ndarray] = []
    phases: list[dict[str, Any]] = []
    current = anchor.copy()
    for offset in offsets:
        target = anchor.copy()
        target[index] += float(offset)
        for phase_name, destination in (
            ("outbound", target),
            ("return", anchor),
        ):
            delta = float(destination[index] - current[index])
            count = max(1, int(math.ceil(abs(delta) * SAMPLE_HZ / maximum_slew_degrees_s)))
            start_index = len(rows)
            for step in range(1, count + 1):
                row = current + (destination - current) * (step / count)
                rows.append(row.astype("<f8", copy=False))
            current = destination.copy()
            hold_count = int(math.ceil(hold_seconds * SAMPLE_HZ))
            for _ in range(hold_count):
                rows.append(current.astype("<f8", copy=True))
            phases.append(
                {
                    "joint": joint,
                    "offset_degrees": float(offset),
                    "phase": phase_name,
                    "start_index": start_index,
                    "end_index_exclusive": len(rows),
                    "target_degrees": current.tolist(),
                }
            )
    return np.asarray(rows, dtype="<f8"), phases


def _register_snapshot(gateway: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for register in REGISTER_NAMES:
        try:
            values[register] = gateway._read_optional(register)
        except (ConnectionError, OSError) as error:
            values[register] = {
                "available": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
    return values


def _run_session(
    *,
    gateway: Any,
    anchor: np.ndarray,
    actions: np.ndarray,
    phases: list[dict[str, Any]],
    candidate_manifest_path: Path,
    telemetry_handle: Any,
    session_id: str,
    clock_fn: Callable[[], float],
    sleep_fn: Callable[[float], None],
) -> dict[str, Any]:
    preview = preview_wrist_view_actions([actions], candidate_manifest_path)
    _require(
        preview.get("no_new_or_worsened_kinematic_contact") is True
        and not preview.get("external_contact_pairs"),
        f"{session_id} exact-action preview rejected",
    )
    _require(
        preview["stages"][0]["exact_physical_action_sha256"]
        == action_sha256(actions),
        f"{session_id} preview action hash changed",
    )
    started = clock_fn()
    completed = 0
    failure: str | None = None
    for sample_index, action in enumerate(actions):
        delay = started + sample_index / SAMPLE_HZ - clock_fn()
        if delay > 0:
            sleep_fn(delay)
        try:
            sample = gateway.sample(
                sample_index / SAMPLE_HZ,
                exact_requested_degrees=action,
                setup_elbow_tracking_error_limit_degrees=20.0,
            )
            _require(
                sample.get("precompiled_exact_action") is True
                and sample.get("rate_limited") is False
                and sample.get("safety_clamped") is False
                and sample.get("physical_follower_torque_enabled") is True,
                f"{session_id} gateway altered or rejected an exact target",
            )
            row = {
                "session_id": session_id,
                "sample_index": sample_index,
                "planned_action_sha256": action_sha256(actions),
                "register_snapshot": (
                    _register_snapshot(gateway)
                    if sample_index % int(SAMPLE_HZ / REGISTER_HZ) == 0
                    else None
                ),
                **sample,
            }
            telemetry_handle.write(json.dumps(row, sort_keys=True) + "\n")
            telemetry_handle.flush()
            completed += 1
        except Exception as error:
            failure = f"{type(error).__name__}: {error}"
            break
    return {
        "session_id": session_id,
        "action_sha256": action_sha256(actions),
        "planned_sample_count": int(actions.shape[0]),
        "completed_sample_count": completed,
        "phases": phases,
        "preview": preview,
        "failure": failure,
        "anchor_degrees": anchor.tolist(),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(str(row["session_id"]), []).append(row)
    summaries: dict[str, Any] = {}
    for session_id, session_rows in by_session.items():
        anchor = np.asarray(session_rows[0]["follower_actual_position_degrees"], dtype=float)
        maxima = np.max(
            np.abs(
                np.asarray(
                    [row["follower_actual_position_degrees"] for row in session_rows],
                    dtype=float,
                )
                - anchor[None, :]
            ),
            axis=0,
        )
        summaries[session_id] = {
            "sample_count": len(session_rows),
            "maximum_measured_excursion_degrees": maxima.tolist(),
            "current_register_rows": sum(
                row.get("register_snapshot") is not None for row in session_rows
            ),
        }
    return {
        "sessions": summaries,
        "diagnostic_class": "receipt_bound_response_measurement_no_automatic_repair_authority",
    }


def execute_probe(
    *,
    contract_path: Path,
    candidate_manifest_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = _default_preflight,
    gateway_factory: Callable[[Any], Any] = _default_gateway,
    recorder_factory: Callable[[Path], Any] = WristVideoRecorder,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    _require(operator_acknowledged, "physical probe requires --yes")
    contract_path = contract_path.resolve()
    candidate_manifest_path = candidate_manifest_path.resolve()
    output_root = output_root.resolve()
    contract = load_contract(contract_path)
    expires = datetime.fromisoformat(str(contract["authorization_expires_at"]))
    _require(datetime.now(expires.tzinfo) < expires, "physical authorization expired")
    _require(candidate_manifest_path.is_file(), "candidate manifest is missing")
    _require(not output_root.exists(), "refusing to overwrite probe output")
    preflight = preflight_fn()
    identity, preflight_lower, preflight_upper = _preflight_identity_and_limits(
        preflight
    )
    output_root.mkdir(parents=True)
    telemetry_path = output_root / "telemetry.jsonl"
    receipt_path = output_root / "receipt.json"
    recorder = recorder_factory(output_root / "wrist_d405.mkv")
    camera_started: dict[str, Any] | None = None
    camera_result: dict[str, Any] | None = None
    session_results: list[dict[str, Any]] = []
    shutdown_errors: list[str] = []
    failure: str | None = None
    action_artifacts: list[dict[str, Any]] = []
    action_started: float | None = None
    action_stopped: float | None = None
    try:
        camera_started = recorder.start()
        with telemetry_path.open("x", encoding="utf-8") as telemetry:
            plans = (
                (
                    "before_torque_cycle",
                    (
                        ("elbow_flex", list(contract["elbow_offsets_degrees"])),
                        (
                            "wrist_flex",
                            list(contract["wrist_control_offsets_degrees"]),
                        ),
                    ),
                ),
                (
                    "after_torque_cycle",
                    (
                        (
                            "elbow_flex",
                            [
                                float(
                                    contract["repeat_after_torque_cycle"][
                                        "offset_degrees"
                                    ]
                                )
                            ],
                        ),
                    ),
                ),
            )
            for session_id, joint_plans in plans:
                gateway = gateway_factory(_gateway_identity(identity))
                try:
                    opened = gateway.open_live_anchored_setup()
                    anchor = np.asarray(
                        opened["setup_command_anchor_degrees"], dtype=np.float64
                    )
                    actions_parts: list[np.ndarray] = []
                    phases: list[dict[str, Any]] = []
                    index_offset = 0
                    for joint, offsets in joint_plans:
                        actions, joint_phases = _trajectory(
                            anchor,
                            joint=joint,
                            offsets=offsets,
                            maximum_slew_degrees_s=float(
                                contract["maximum_slew_degrees_s"]
                            ),
                            hold_seconds=float(contract["hold_seconds"]),
                        )
                        for phase in joint_phases:
                            phase["start_index"] += index_offset
                            phase["end_index_exclusive"] += index_offset
                        actions_parts.append(actions)
                        phases.extend(joint_phases)
                        index_offset += int(actions.shape[0])
                    actions = np.concatenate(actions_parts).astype("<f8", copy=False)
                    lower = np.asarray(opened["follower_calibrated_minimum"], dtype=float)
                    upper = np.asarray(opened["follower_calibrated_maximum"], dtype=float)
                    _require(
                        np.array_equal(lower, preflight_lower)
                        and np.array_equal(upper, preflight_upper)
                        and
                        np.all(actions >= lower[None, :])
                        and np.all(actions <= upper[None, :]),
                        f"{session_id} exceeds fresh calibrated limits",
                    )
                    action_path = output_root / f"{session_id}.actions.float64le"
                    action_path.write_bytes(actions.tobytes(order="C"))
                    action_artifacts.append(
                        {
                            "session_id": session_id,
                            "path": str(action_path),
                            "sha256": _sha256(action_path),
                            "shape": list(actions.shape),
                        }
                    )
                    if action_started is None:
                        action_started = clock_fn()
                    result = _run_session(
                        gateway=gateway,
                        anchor=anchor,
                        actions=actions,
                        phases=phases,
                        candidate_manifest_path=candidate_manifest_path,
                        telemetry_handle=telemetry,
                        session_id=session_id,
                        clock_fn=clock_fn,
                        sleep_fn=sleep_fn,
                    )
                    session_results.append(result)
                    if result["failure"] is not None:
                        failure = str(result["failure"])
                        break
                finally:
                    try:
                        gateway.close()
                    except Exception as error:
                        shutdown_errors.append(f"{type(error).__name__}: {error}")
                sleep_fn(0.5)
        action_stopped = clock_fn()
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        action_stopped = clock_fn()
    finally:
        try:
            camera_result = recorder.finish(
                action_started_monotonic=action_started,
                action_stopped_monotonic=action_stopped,
                post_roll_seconds=0.0,
            )
        except Exception as error:
            shutdown_errors.append(f"camera: {type(error).__name__}: {error}")

    telemetry_rows = (
        [
            json.loads(line)
            for line in telemetry_path.read_text(encoding="utf-8").splitlines()
        ]
        if telemetry_path.is_file()
        else []
    )
    completed = (
        failure is None
        and not shutdown_errors
        and len(session_results) == 2
        and all(
            row["completed_sample_count"] == row["planned_sample_count"]
            for row in session_results
        )
        and camera_result is not None
        and camera_result.get("status") == "completed"
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": (
            "completed_no_contact_elbow_telemetry_probe"
            if completed
            else "stopped_safely_no_contact_elbow_telemetry_probe"
        ),
        "proof_class": "physical_no_contact_elbow_and_wrist_control_telemetry",
        "contract": {
            "path": str(contract_path),
            "sha256": _sha256(contract_path),
        },
        "candidate_manifest": {
            "path": str(candidate_manifest_path),
            "sha256": _sha256(candidate_manifest_path),
        },
        "preflight": preflight,
        "sessions": session_results,
        "action_artifacts": action_artifacts,
        "telemetry": (
            {
                "path": str(telemetry_path),
                "sha256": _sha256(telemetry_path),
                "row_count": len(telemetry_rows),
                "register_hz": REGISTER_HZ,
                "registers": list(REGISTER_NAMES),
            }
            if telemetry_path.is_file()
            else None
        ),
        "summary": _summarize(telemetry_rows) if telemetry_rows else None,
        "camera_start": camera_started,
        "camera_result": camera_result,
        "failure": failure,
        "shutdown_errors": shutdown_errors,
        "physical_task_attempts": 0,
        "pawn_contact": False,
        "gain_write": False,
        "configuration_write": False,
        "torque_cycle_count": 1 if len(session_results) == 2 else 0,
        "torque_off_cleanup_required": True,
        "passed": completed,
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    result = execute_probe(
        contract_path=args.contract,
        candidate_manifest_path=args.candidate_manifest,
        output_root=args.output,
        operator_acknowledged=args.yes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
