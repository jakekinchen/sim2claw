"""Motion-free safety preview for the evidence-directed deep-request corridor."""

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
from .parking_transaction_preview import (
    _collision_geoms,
    _environment_geoms,
    _geom_name,
    _witness_distance,
)
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class ParkingDeepRequestPreviewError(RuntimeError):
    """The bounded successor preview changed or failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParkingDeepRequestPreviewError(message)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "deep-request preview binding escaped repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and _sha(path) == binding.get("sha256"),
        f"deep-request preview binding changed: {relative}",
    )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _robot_contact_depths(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    robot_bodies: set[int],
) -> dict[tuple[str, str], float]:
    """Return the deepest contact distance for each robot-body pair."""

    result: dict[tuple[str, str], float] = {}
    for index in range(data.ncon):
        contact = data.contact[index]
        first_body = int(model.geom_bodyid[contact.geom1])
        second_body = int(model.geom_bodyid[contact.geom2])
        if first_body not in robot_bodies or second_body not in robot_bodies:
            continue
        pair = tuple(
            sorted(
                (
                    _static._body_name(model, first_body),
                    _static._body_name(model, second_body),
                )
            )
        )
        result[pair] = min(result.get(pair, 0.0), float(contact.dist))
    return result


def _contact_envelope_passes(
    *,
    angle_degrees: float,
    contacts: Mapping[tuple[str, str], float],
    live_anchor_contacts: Mapping[tuple[str, str], float],
    contact_free_maximum_degrees: float,
    maximum_additional_penetration_m: float,
) -> bool:
    if angle_degrees <= contact_free_maximum_degrees:
        return not contacts
    if not set(contacts).issubset(live_anchor_contacts):
        return False
    return all(
        depth
        >= live_anchor_contacts[pair] - maximum_additional_penetration_m
        for pair, depth in contacts.items()
    )


def _validate(contract: Mapping[str, Any]) -> None:
    schema_version = contract.get("schema_version")
    _require(
        schema_version
        in {
            "sim2claw.parking_deep_request_preview.v1",
            "sim2claw.parking_deep_request_preview.v2",
        }
        and contract.get("status")
        == "frozen_for_one_motion_free_cpu_fp64_preview"
        and contract.get("authority")
        == {
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
        },
        "deep-request preview identity or authority changed",
    )
    expected_stop = (
        103.5
        if schema_version == "sim2claw.parking_deep_request_preview.v1"
        else 102.1
    )
    expected_samples = 236 if expected_stop == 103.5 else 222
    _require(
        contract.get("static_preview")
        == {
            "engine": "mujoco",
            "numeric_mode": "cpu_float64",
            "elbow_interval_degrees": [80.0, expected_stop],
            "sample_increment_degrees": 0.1,
            "expected_sample_count": expected_samples,
            "strict_contact_free_maximum_degrees": 99.6,
            "live_anchor_contact_maximum_additional_penetration_m": 0.0005,
            "minimum_dynamic_clearance_m": 0.12,
        },
        "deep-request preview interval or gates changed",
    )


def preview(contract_path: Path) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _validate(contract)
    for binding in contract["inputs"].values():
        _bound(binding)

    predecessor = _json(contract["inputs"]["predecessor_execution_receipt"])
    _require(
        predecessor.get("passed") is False
        and predecessor.get("physical_task_attempts") == 0
        and predecessor.get("pawn_contact") is False
        and predecessor.get("failure")
        == (
            "PhysicalGatewayError: Follower made no measurable progress "
            "toward a commanded joint for 5.0 seconds; torque released."
        )
        and predecessor.get("postflight", {}).get(
            "physical_follower_torque_enabled"
        )
        is False,
        "deep-request predecessor is not the exact safe stall receipt",
    )
    anchor = np.asarray(
        predecessor["postflight"]["follower_start_degrees"],
        dtype=np.float64,
    )
    expected_anchor = np.asarray(
        contract["fresh_anchor"]["expected_degrees_percent"],
        dtype=np.float64,
    )
    delta = np.abs(anchor - expected_anchor)
    _require(
        anchor.shape == (6,)
        and float(np.max(delta[[0, 1, 3, 4, 5]])) <= 0.5
        and float(delta[2]) <= 1.0,
        "deep-request postflight anchor exceeded rebase gate",
    )

    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
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
    _require(
        len(moving_geoms)
        == contract["fresh_anchor"]["expected_inventory"][
            "moving_chain_geoms"
        ]
        and {
            key: len(value) for key, value in environment.items()
        }
        == contract["fresh_anchor"]["expected_inventory"][
            "environment_geoms"
        ],
        "deep-request collision inventory changed",
    )

    def set_angle(angle_degrees: float) -> None:
        physical = anchor.copy()
        physical[2] = angle_degrees
        model_position = _physical_to_model_position(
            physical.reshape(1, 6), candidate
        )[0]
        data.qpos[addresses] = model_position
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)

    set_angle(float(anchor[2]))
    live_anchor_contacts = _robot_contact_depths(
        model, data, robot_bodies
    )
    expected_pairs = {
        tuple(sorted(pair))
        for pair in contract["static_preview"][
            "live_anchor_expected_robot_contact_pairs"
        ]
    } if "live_anchor_expected_robot_contact_pairs" in contract[
        "static_preview"
    ] else {
        ("left_lower_arm", "left_shoulder"),
        ("left_shoulder", "left_wrist"),
        ("left_upper_arm", "left_wrist"),
    }
    _require(
        set(live_anchor_contacts) == expected_pairs,
        "live-anchor modeled contact pairs changed",
    )

    spec = contract["static_preview"]
    start, stop = spec["elbow_interval_degrees"]
    increment = float(spec["sample_increment_degrees"])
    angles = np.linspace(
        start,
        stop,
        int(round((stop - start) / increment)) + 1,
        dtype=np.float64,
    )
    _require(
        len(angles) == spec["expected_sample_count"],
        "deep-request sample count changed",
    )
    minima = {
        key: {"distance_m": 1.0, "lower_bound_only": True}
        for key in environment
    }
    pinch_minimum = {
        "clearance_above_board_m": 1.0,
        "angle_degrees": None,
    }
    board_top_z_m: float | None = None
    contact_violations: list[dict[str, Any]] = []
    observed_contact_pairs: set[tuple[str, str]] = set()
    joint_ranges_ok = True

    for angle in angles:
        set_angle(float(angle))
        if board_top_z_m is None:
            board_geom = environment["board"][0]
            board_top_z_m = float(
                data.geom_xpos[board_geom][2]
                + model.geom_size[board_geom][2]
            )
        model_position = data.qpos[addresses]
        for index, name in enumerate(_static.ALL_JOINTS):
            joint_id = _static._named_id(
                model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            low, high = model.jnt_range[joint_id]
            joint_ranges_ok = bool(
                joint_ranges_ok
                and low <= model_position[index] <= high
            )

        contacts = _robot_contact_depths(model, data, robot_bodies)
        observed_contact_pairs.update(contacts)
        if not _contact_envelope_passes(
            angle_degrees=float(angle),
            contacts=contacts,
            live_anchor_contacts=live_anchor_contacts,
            contact_free_maximum_degrees=float(
                spec["strict_contact_free_maximum_degrees"]
            ),
            maximum_additional_penetration_m=float(
                spec[
                    "live_anchor_contact_maximum_additional_penetration_m"
                ]
            ),
        ):
            contact_violations.append(
                {
                    "angle_degrees": float(angle),
                    "contacts": {
                        "/".join(pair): depth
                        for pair, depth in sorted(contacts.items())
                    },
                }
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
        clearance = float(pinch[2] - float(board_top_z_m))
        if clearance < pinch_minimum["clearance_above_board_m"]:
            pinch_minimum = {
                "clearance_above_board_m": clearance,
                "angle_degrees": float(angle),
            }

    clearance_gate = float(spec["minimum_dynamic_clearance_m"])
    passed = bool(
        joint_ranges_ok
        and not contact_violations
        and all(
            float(row["distance_m"]) >= clearance_gate
            for row in minima.values()
        )
        and float(pinch_minimum["clearance_above_board_m"])
        >= clearance_gate
    )
    return {
        "schema_version": "sim2claw.parking_deep_request_preview_receipt.v1",
        "status": (
            "parking_deep_request_preview_pass"
            if passed
            else "parking_deep_request_preview_reject"
        ),
        "proof_class": "cpu_fp64_motion_free_deep_request_corridor_preview",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "predecessor_execution_receipt_sha256": contract["inputs"][
            "predecessor_execution_receipt"
        ]["sha256"],
        "fresh_anchor_degrees_percent": anchor.tolist(),
        "elbow_interval_degrees": [start, stop],
        "sample_increment_degrees": increment,
        "sample_count": len(angles),
        "joint_ranges_ok": joint_ranges_ok,
        "live_anchor_robot_contacts": {
            "/".join(pair): depth
            for pair, depth in sorted(live_anchor_contacts.items())
        },
        "observed_robot_contact_pairs": [
            list(pair) for pair in sorted(observed_contact_pairs)
        ],
        "contact_violations": contact_violations,
        "moving_chain_clearance": minima,
        "pinch_clearance": pinch_minimum,
        "minimum_required_clearance_m": clearance_gate,
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
    if output_directory.exists():
        raise ParkingDeepRequestPreviewError(
            "immutable deep-request preview output already exists"
        )
    receipt = preview(contract_path)
    output_directory.mkdir(parents=True, exist_ok=False)
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "ParkingDeepRequestPreviewError",
    "_contact_envelope_passes",
    "preview",
    "preview_and_freeze",
]
