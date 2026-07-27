#!/usr/bin/env python3
"""Score one exact contact-free geometric hover against physical encoders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from sim2claw.grasp import _pinch_offset, _pinch_point
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.recorded_replay import _compile_model
from sim2claw.wrist_view_reposition import (
    _decode_capture_hold,
    _decode_stage,
    _physical_to_model_position,
)


SCHEMA = "sim2claw.geometric_hover_transfer_diagnostic.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_hover_transfer_diagnostic_receipt.v1"
JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)


class HoverTransferEvaluationError(RuntimeError):
    """A bound trace, exact action, or diagnostic boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HoverTransferEvaluationError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HoverTransferEvaluationError(f"cannot read JSON {path}: {error}") from error
    _require(isinstance(value, dict), f"expected an object in {path}")
    return value


def _bound(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "bound source escaped the repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and sha256_file(path) == binding.get("sha256"),
        f"bound source changed: {relative}",
    )
    return path


def _tricam(execution: Mapping[str, Any]) -> dict[str, bool]:
    finished = execution.get("camera_finished") or {}
    return {
        "c922_action_interval_enclosed": bool(
            (finished.get("overhead") or {}).get(
                "action_interval_enclosed_by_callback_frames"
            )
        ),
        "d405_action_interval_enclosed": bool(
            (finished.get("wrist") or {}).get(
                "action_interval_enclosed_by_callback_frames"
            )
        ),
        "pi_action_interval_enclosed": bool(
            (finished.get("pi") or {}).get("action_interval_enclosed")
        ),
    }


def _pinch_points(
    physical_degrees: np.ndarray,
    candidate_config: Mapping[str, Any],
) -> np.ndarray:
    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    joint_names = list((candidate_config.get("bindings") or {}).get("joint_names") or [])
    _require(len(joint_names) == 6, "candidate joint inventory changed")
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    _require(all(joint_id >= 0 for joint_id in joint_ids), "candidate joint is missing")
    qpos_addresses = np.asarray(
        [model.jnt_qposadr[joint_id] for joint_id in joint_ids],
        dtype=np.int32,
    )
    model_positions = _physical_to_model_position(
        physical_degrees,
        candidate_config,
    )
    data.qpos[qpos_addresses] = model_positions[0]
    mujoco.mj_forward(model, data)
    pinch_local = _pinch_offset(model, data, "left")
    points = []
    for row in model_positions:
        data.qpos[qpos_addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        points.append(_pinch_point(model, data, "left", pinch_local).copy())
    return np.asarray(points, dtype=np.float64)


def _phase_metrics(
    *,
    command: np.ndarray,
    actual: np.ndarray,
    command_points: np.ndarray,
    actual_points: np.ndarray,
    start: int,
    stop: int,
) -> dict[str, Any]:
    _require(0 <= start < stop <= len(command), "phase slice is invalid")
    joint_error = actual[start:stop] - command[start:stop]
    cartesian_error = actual_points[start:stop] - command_points[start:stop]
    distances = np.linalg.norm(cartesian_error, axis=1)
    return {
        "sample_count": int(stop - start),
        "per_joint_rms_degrees": {
            name: float(value)
            for name, value in zip(
                JOINT_NAMES,
                np.sqrt(np.mean(joint_error**2, axis=0)),
                strict=True,
            )
        },
        "per_joint_maximum_absolute_degrees": {
            name: float(value)
            for name, value in zip(
                JOINT_NAMES,
                np.max(np.abs(joint_error), axis=0),
                strict=True,
            )
        },
        "cartesian_rms_m": float(np.sqrt(np.mean(distances**2))),
        "cartesian_maximum_m": float(np.max(distances)),
        "cartesian_mean_actual_minus_command_xyz_m": np.mean(
            cartesian_error, axis=0
        ).tolist(),
    }


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = _json(contract_path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == "retrospective_after_trace_opened_no_parameter_selection",
        "diagnostic status changed",
    )
    _require(
        contract.get("authority")
        == {
            "diagnostic_analysis": True,
            "parameter_fitting": False,
            "simulator_parameter_promotion": False,
            "physical_motion": False,
            "pawn_contact": False,
            "task_success": False,
            "policy": False,
        },
        "diagnostic authority changed",
    )
    sources = contract["sources"]
    packet_path = _bound(sources["packet"])
    receipt_path = _bound(sources["execution_receipt"])
    samples_path = _bound(sources["joint_samples"])
    manifest_path = _bound(sources["candidate_manifest"])
    packet = _json(packet_path)
    execution = _json(receipt_path)
    manifest = _json(manifest_path)
    candidate_config = manifest.get("candidate_config")
    _require(isinstance(candidate_config, Mapping), "candidate config is missing")
    stage_index = int(contract["stage_index"])
    stage = packet["stages"][stage_index - 1]
    motion, _, _ = _decode_stage(stage)
    hold, _, _ = _decode_capture_hold(stage)
    exact = np.concatenate((motion, hold), axis=0)
    _require(
        packet.get("plan_sha256") == contract["expected"]["plan_sha256"]
        and stage.get("action_sha256") == contract["expected"]["action_sha256"]
        and stage.get("capture_hold_action_sha256")
        == contract["expected"]["capture_hold_action_sha256"],
        "frozen packet identity changed",
    )
    _require(
        execution.get("status") == "completed_wrist_view_reposition_stage"
        and execution.get("stage_index") == stage_index
        and execution.get("packet_sha256") == sha256_file(packet_path)
        and execution.get("action_sha256") == stage["action_sha256"]
        and execution.get("capture_hold_action_sha256")
        == stage["capture_hold_action_sha256"]
        and execution.get("joint_samples_sha256") == sha256_file(samples_path)
        and execution.get("completed_samples") == len(exact)
        and execution.get("physical_follower_torque_enabled") is False
        and execution.get("error") is None,
        "execution receipt is not exact, complete, and torque-off",
    )
    try:
        rows = [
            json.loads(line)
            for line in samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise HoverTransferEvaluationError(f"joint samples are invalid: {error}") from error
    _require(len(rows) == len(exact), "joint sample count changed")
    command = []
    actual = []
    for index, (row, action) in enumerate(zip(rows, exact, strict=True)):
        requested = np.asarray(row.get("requested_physical_units"), dtype="<f8")
        sent = np.asarray(row.get("follower_command_degrees"), dtype="<f8")
        observed = np.asarray(
            row.get("follower_actual_position_degrees"), dtype=np.float64
        )
        _require(
            row.get("sample_index") == index
            and requested.shape == (6,)
            and sent.shape == (6,)
            and observed.shape == (6,)
            and requested.tobytes() == action.astype("<f8").tobytes()
            and sent.tobytes() == action.astype("<f8").tobytes()
            and not bool(row.get("rate_limited"))
            and not bool(row.get("safety_clamped"))
            and not bool(row.get("stalled"))
            and not bool(row.get("assistance"))
            and not bool(row.get("intervention")),
            f"joint sample {index} changed or was assisted",
        )
        command.append(sent)
        actual.append(observed)
    command_array = np.asarray(command, dtype=np.float64)
    actual_array = np.asarray(actual, dtype=np.float64)
    command_points = _pinch_points(command_array, candidate_config)
    actual_points = _pinch_points(actual_array, candidate_config)
    phases = {
        str(spec["name"]): _phase_metrics(
            command=command_array,
            actual=actual_array,
            command_points=command_points,
            actual_points=actual_points,
            start=int(spec["start_index"]),
            stop=int(spec["end_index_exclusive"]),
        )
        for spec in contract["phase_slices"]
    }
    apex_index = int(contract["apex_index"])
    _require(0 <= apex_index < len(exact), "apex index is invalid")
    apex_delta = actual_points[apex_index] - command_points[apex_index]
    tricam = _tricam(execution)
    maximum_cartesian_error = max(
        phase["cartesian_maximum_m"] for phase in phases.values()
    )
    gates = {
        "exact_action_bytes_consumed_without_assistance": True,
        "all_three_camera_intervals_enclose_action": all(tricam.values()),
        "follower_torque_off_at_close": True,
        "no_gateway_rate_limit_clamp_or_stall": True,
        "retrospective_cartesian_screen_below_20mm": (
            maximum_cartesian_error
            <= float(contract["gates"]["maximum_cartesian_tracking_error_m"])
        ),
    }
    result = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "status": "completed_retrospective_contact_free_transfer_diagnostic",
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "sources": {
            name: {
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(path),
            }
            for name, path in (
                ("packet", packet_path),
                ("execution_receipt", receipt_path),
                ("joint_samples", samples_path),
                ("candidate_manifest", manifest_path),
            )
        },
        "action_identity": {
            "motion_shape": list(motion.shape),
            "motion_sha256": stage["action_sha256"],
            "hold_shape": list(hold.shape),
            "hold_sha256": stage["capture_hold_action_sha256"],
            "post_policy_transform": None,
            "ik_correction": None,
            "assistance": False,
        },
        "phases": phases,
        "apex": {
            "sample_index": apex_index,
            "command_pinch_xyz_m": command_points[apex_index].tolist(),
            "actual_pinch_xyz_m": actual_points[apex_index].tolist(),
            "actual_minus_command_xyz_m": apex_delta.tolist(),
            "cartesian_error_m": float(np.linalg.norm(apex_delta)),
            "command_degrees": command_array[apex_index].tolist(),
            "actual_degrees": actual_array[apex_index].tolist(),
        },
        "maximum_cartesian_tracking_error_m": maximum_cartesian_error,
        "final_residual_degrees": execution["final_residual_degrees"],
        "tricam_action_enclosure": tricam,
        "gates": gates,
        "screen_passed": all(gates.values()),
        "parameter_fitting_performed": False,
        "parameters_promoted": False,
        "pawn_contact_admitted": False,
        "task_success_claimed": False,
        "authority": contract["authority"],
    }
    result["receipt_digest"] = canonical_digest(result)
    atomic_write_json(output_path.resolve(), result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate(args.contract, args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
