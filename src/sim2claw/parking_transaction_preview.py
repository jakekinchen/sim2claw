"""Motion-free RP01 elbow-parking transaction safety preview."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class ParkingTransactionPreviewError(RuntimeError):
    """The frozen transaction or its motion-free preview failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParkingTransactionPreviewError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "RP01 bound path escaped repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and _sha(path) == binding.get("sha256"),
        f"RP01 bound source changed: {relative}",
    )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def ladder_request(
    observed_elbow_degrees: float,
    *,
    target_degrees: float = 91.0,
    maximum_step_degrees: float = 5.0,
) -> float:
    """Return the frozen read-conditioned next elbow request."""

    return max(
        float(target_degrees),
        float(observed_elbow_degrees) - float(maximum_step_degrees),
    )


def _collision_geoms(
    model: mujoco.MjModel,
    body_ids: set[int],
) -> list[int]:
    return [
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) in body_ids
        and (
            int(model.geom_contype[geom_id]) != 0
            or int(model.geom_conaffinity[geom_id]) != 0
        )
    ]


def _environment_geoms(
    model: mujoco.MjModel,
) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {
        "table": [],
        "board": [],
        "pawns": [],
    }
    for geom_id in range(model.ngeom):
        if not (
            int(model.geom_contype[geom_id]) != 0
            or int(model.geom_conaffinity[geom_id]) != 0
        ):
            continue
        body_name = _static._body_name(
            model, int(model.geom_bodyid[geom_id])
        )
        if body_name == "measured_table":
            result["table"].append(geom_id)
        elif body_name == "chess_board":
            result["board"].append(geom_id)
        elif "pawn_" in body_name:
            result["pawns"].append(geom_id)
    return result


def _geom_name(model: mujoco.MjModel, geom_id: int) -> str:
    return (
        mujoco.mj_id2name(
            model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id)
        )
        or f"geom-{geom_id}"
    )


def _witness_distance(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    first: int,
    second: int,
    *,
    limit_m: float,
) -> tuple[float, float, float]:
    """Resolve MuJoCo's box-box zero return using its separated witnesses.

    MuJoCo 3.10 can return zero for a separated box-box pair while still
    returning distinct closest-point witnesses. Contacts are audited
    independently, so the conservative separation is the larger of the raw
    return and witness norm.
    """

    witness = np.zeros(6, dtype=np.float64)
    raw = float(
        mujoco.mj_geomDistance(
            model, data, first, second, float(limit_m), witness
        )
    )
    witness_norm = float(np.linalg.norm(witness[:3] - witness[3:]))
    return max(raw, witness_norm), raw, witness_norm


def _validate_contract(contract: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "inputs",
        "fresh_anchor",
        "setup",
        "parking_control_law",
        "telemetry",
        "cameras",
        "cleanup",
        "static_preview",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    expected_authority = {
        "model_loading": True,
        "static_simulation": True,
        "camera": False,
        "gateway": False,
        "serial": False,
        "torque": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "mapping_approval": False,
        "simulator_promotion": False,
        "transfer_claim": False,
    }
    _require(set(contract) == expected_keys, "RP01 contract keys changed")
    _require(
        contract.get("schema_version")
        == "sim2claw.parking_transaction_preview.v1",
        "RP01 schema changed",
    )
    _require(
        contract.get("status")
        == "frozen_for_one_motion_free_cpu_fp64_preview",
        "RP01 status widened",
    )
    _require(
        contract.get("authority") == expected_authority,
        "RP01 authority widened",
    )
    setup = contract["setup"]
    _require(
        setup
        == {
            "mode": "no_op_current_anchor",
            "setup_action_rows": 0,
            "moving_chain_root_body": "left_upper_arm",
            "minimum_dynamic_clearance_m": 0.12,
            "dynamic_clearance_targets": ["table", "board", "pawns"],
            "all_robot_contact_free_required": True,
            "fixed_base_and_shoulder_excluded_from_120mm_distance_gate": True,
            "fixed_base_and_shoulder_remain_in_contact_gate": True,
        },
        "RP01 setup changed",
    )
    control = contract["parking_control_law"]
    _require(
        control
        == {
            "joint_name": "elbow_flex",
            "joint_index": 2,
            "target_degrees": 91.0,
            "maximum_request_step_degrees": 5.0,
            "maximum_iterations": 12,
            "wait_after_request_seconds": 2.0,
            "request_formula": "max(91.0, previous_read_degrees - 5.0)",
            "primary_success_maximum_degrees": 92.0,
            "marginal_success_maximum_degrees": 93.0,
            "stall_minimum_progress_degrees": 0.3,
            "stall_consecutive_iterations": 2,
            "pure_frozen_row_tensor": False,
            "one_execution_no_retry_without_new_preregistration": True,
        },
        "RP01 control law changed",
    )
    _require(
        contract["static_preview"]
        == {
            "engine": "mujoco",
            "numeric_mode": "cpu_float64",
            "elbow_interval_degrees": [88.0, 99.6],
            "sample_increment_degrees": 0.1,
            "expected_sample_count": 117,
            "minimum_dynamic_clearance_m": 0.12,
            "no_new_robot_contact_required": True,
        },
        "RP01 static preview changed",
    )


def preview(
    contract_path: Path,
) -> dict[str, Any]:
    """Evaluate the frozen RP01 interval without opening physical authority."""

    contract_path = contract_path.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _validate_contract(contract)
    for binding in contract["inputs"].values():
        _bound(binding)

    preflight = _json(contract["inputs"]["fresh_preflight"])
    rp00 = _json(contract["inputs"]["rp00_closeout"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
    _require(
        preflight.get("passed") is True
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False
        and preflight.get("physical_motion") is False,
        "fresh RP01 preflight is not torque-off and motion-free",
    )
    _require(
        rp00.get("status")
        == "pass_open_rp01_parking_transaction_freeze_only"
        and rp00.get("result", {}).get(
            "recommended_parking_lock_angle_degrees"
        )
        == contract["parking_control_law"]["target_degrees"],
        "RP00 did not authorize this RP01 freeze target",
    )

    anchor = np.asarray(
        preflight["follower_start_degrees"], dtype=np.float64
    )
    expected_anchor = np.asarray(
        contract["fresh_anchor"]["expected_degrees_percent"],
        dtype=np.float64,
    )
    lower = np.asarray(
        preflight["follower_calibrated_minimum"], dtype=np.float64
    )
    upper = np.asarray(
        preflight["follower_calibrated_maximum"], dtype=np.float64
    )
    _require(anchor.shape == lower.shape == upper.shape == (6,), "bad anchor")
    _require(
        bool(np.all(anchor >= lower) and np.all(anchor <= upper)),
        "fresh RP01 anchor is outside calibrated ranges",
    )
    maximum_rebase = float(
        contract["fresh_anchor"]["maximum_absolute_rebase_degrees"]
    )
    rebase_delta = float(np.max(np.abs(anchor - expected_anchor)))
    _require(
        rebase_delta <= maximum_rebase,
        "fresh RP01 anchor exceeded the frozen rebase envelope",
    )
    _require(
        preflight["follower_calibration_sha256"]
        == contract["fresh_anchor"]["follower_calibration_sha256"],
        "fresh RP01 calibration identity changed",
    )

    candidate = manifest["candidate_config"]
    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model, candidate
    )
    model, addresses, robot_bodies, _ = model_builder(rigid, 0.0025)
    data = mujoco.MjData(model)
    moving_bodies = _static._descendants(
        model, contract["setup"]["moving_chain_root_body"]
    )
    moving_geoms = _collision_geoms(model, moving_bodies)
    environment = _environment_geoms(model)
    expected_inventory = contract["fresh_anchor"]["expected_inventory"]
    _require(
        len(moving_geoms) == expected_inventory["moving_chain_geoms"]
        and {
            key: len(value) for key, value in environment.items()
        }
        == expected_inventory["environment_geoms"],
        "RP01 collision inventory changed",
    )

    preview_spec = contract["static_preview"]
    start, stop = preview_spec["elbow_interval_degrees"]
    increment = float(preview_spec["sample_increment_degrees"])
    angles = np.linspace(
        float(start),
        float(stop),
        int(round((float(stop) - float(start)) / increment)) + 1,
        dtype=np.float64,
    )
    _require(
        len(angles) == preview_spec["expected_sample_count"],
        "RP01 preview sample count changed",
    )
    minima: dict[str, dict[str, Any]] = {
        key: {"distance_m": 1.0, "lower_bound_only": True}
        for key in environment
    }
    contact_pairs: set[tuple[str, str]] = set()
    joint_ranges_ok = True
    pinch_minimum: dict[str, Any] = {
        "clearance_above_board_m": 1.0,
        "angle_degrees": None,
    }
    board_top_z_m: float | None = None

    for angle in angles:
        physical = anchor.copy()
        physical[2] = float(angle)
        model_position = _physical_to_model_position(
            physical.reshape(1, 6), candidate
        )[0]
        data.qpos[addresses] = model_position
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        if board_top_z_m is None:
            board_geom = environment["board"][0]
            board_top_z_m = float(
                data.geom_xpos[board_geom][2]
                + model.geom_size[board_geom][2]
            )

        for index, name in enumerate(_static.ALL_JOINTS):
            joint_id = _static._named_id(
                model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            joint_minimum, joint_maximum = model.jnt_range[joint_id]
            if not (
                joint_minimum
                <= model_position[index]
                <= joint_maximum
            ):
                joint_ranges_ok = False
        contact_pairs.update(
            _static._contact_pairs(model, data, robot_bodies)
        )

        for group_name, target_geoms in environment.items():
            best = float(minima[group_name]["distance_m"])
            for robot_geom in moving_geoms:
                for target_geom in target_geoms:
                    distance, raw, witness = _witness_distance(
                        model,
                        data,
                        robot_geom,
                        target_geom,
                        limit_m=best,
                    )
                    if distance < best:
                        best = distance
                        minima[group_name] = {
                            "distance_m": distance,
                            "lower_bound_only": False,
                            "raw_mj_distance_m": raw,
                            "witness_distance_m": witness,
                            "angle_degrees": float(angle),
                            "robot_body": _static._body_name(
                                model,
                                int(model.geom_bodyid[robot_geom]),
                            ),
                            "environment_body": _static._body_name(
                                model,
                                int(model.geom_bodyid[target_geom]),
                            ),
                            "robot_geom": _geom_name(model, robot_geom),
                            "environment_geom": _geom_name(
                                model, target_geom
                            ),
                        }

        pinch = _pinch_point(
            model, data, "left", _pinch_offset(model, data, "left")
        )
        pinch_clearance = float(pinch[2] - float(board_top_z_m))
        if pinch_clearance < pinch_minimum["clearance_above_board_m"]:
            pinch_minimum = {
                "clearance_above_board_m": pinch_clearance,
                "angle_degrees": float(angle),
            }

    clearance_gate = float(preview_spec["minimum_dynamic_clearance_m"])
    passed = bool(
        joint_ranges_ok
        and not contact_pairs
        and all(
            float(row["distance_m"]) >= clearance_gate
            for row in minima.values()
        )
        and float(pinch_minimum["clearance_above_board_m"])
        >= clearance_gate
    )
    return {
        "schema_version": "sim2claw.parking_transaction_preview_receipt.v1",
        "status": (
            "parking_transaction_preview_pass"
            if passed
            else "parking_transaction_preview_reject"
        ),
        "proof_class": "cpu_fp64_motion_free_parking_corridor_preview",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "fresh_preflight_sha256": contract["inputs"]["fresh_preflight"][
            "sha256"
        ],
        "follower_port": preflight["follower_port"],
        "follower_calibration_sha256": preflight[
            "follower_calibration_sha256"
        ],
        "fresh_anchor_degrees_percent": anchor.tolist(),
        "maximum_rebase_delta_degrees": rebase_delta,
        "setup": {
            "mode": "no_op_current_anchor",
            "setup_action_rows": 0,
            "reason": (
                "the fresh anchor itself passes the complete frozen "
                "high-clearance elbow corridor"
            ),
        },
        "elbow_interval_degrees": [float(start), float(stop)],
        "sample_increment_degrees": increment,
        "sample_count": len(angles),
        "joint_ranges_ok": joint_ranges_ok,
        "robot_contact_pairs": [list(pair) for pair in sorted(contact_pairs)],
        "moving_chain_clearance": minima,
        "pinch_clearance": pinch_minimum,
        "minimum_required_clearance_m": clearance_gate,
        "parking_control_law": contract["parking_control_law"],
        "telemetry": contract["telemetry"],
        "cameras": contract["cameras"],
        "cleanup": contract["cleanup"],
        "passed": passed,
        "camera_opened": False,
        "gateway_opened": False,
        "serial_opened": False,
        "torque_enabled": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


def preview_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the immutable motion-free preview once and write its receipt."""

    if output_directory.exists():
        raise ParkingTransactionPreviewError(
            "immutable RP01 preview output already exists"
        )
    receipt = preview(contract_path)
    output_directory.mkdir(parents=True, exist_ok=False)
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "ParkingTransactionPreviewError",
    "ladder_request",
    "preview",
    "preview_and_freeze",
]
