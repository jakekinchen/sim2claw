"""Compile the RP04C full-range, high-clearance no-contact route."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from . import canonical_seeded_action_temporal as _temporal
from .coordinated_unloading_shadow_probe import (
    _scene_audit,
    _segment_audit,
)
from .parking_transaction_preview import (
    _collision_geoms,
    _environment_geoms,
    _witness_distance,
)
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class FullRangeNoContactIdentificationError(RuntimeError):
    """A frozen RP04C route or geometry invariant changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FullRangeNoContactIdentificationError(message)


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise FullRangeNoContactIdentificationError(
            "RP04C input escapes repository"
        ) from error
    _require(path.is_file(), f"RP04C input is missing: {path}")
    _require(_sha(path) == entry["sha256"], f"RP04C input changed: {path}")
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _clearance_audit(
    *,
    model_builder: Any,
    rigid: Mapping[str, Any],
    actions: np.ndarray,
) -> dict[str, Any]:
    model, addresses, _, _ = model_builder(dict(rigid), 0.0025)
    data = mujoco.MjData(model)
    moving_bodies = _static._descendants(model, "left_upper_arm")
    moving_geoms = _collision_geoms(model, moving_bodies)
    environment = _environment_geoms(model)
    minima: dict[str, dict[str, Any]] = {
        name: {"distance_m": 1.0, "row": None} for name in environment
    }
    for row_index, row in enumerate(actions):
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        for name, target_geoms in environment.items():
            best = float(minima[name]["distance_m"])
            for moving_geom in moving_geoms:
                for target_geom in target_geoms:
                    distance, raw, witness = _witness_distance(
                        model,
                        data,
                        moving_geom,
                        target_geom,
                        limit_m=best,
                    )
                    if distance < best:
                        best = distance
                        minima[name] = {
                            "distance_m": distance,
                            "row": row_index,
                            "raw_mj_distance_m": raw,
                            "witness_distance_m": witness,
                            "moving_body": _static._body_name(
                                model,
                                int(model.geom_bodyid[moving_geom]),
                            ),
                            "environment_body": _static._body_name(
                                model,
                                int(model.geom_bodyid[target_geom]),
                            ),
                        }
    return {
        "moving_chain_root": "left_upper_arm",
        "moving_geom_count": len(moving_geoms),
        "environment_geom_counts": {
            name: len(geoms) for name, geoms in environment.items()
        },
        "minimum_clearance": minima,
        "minimum_overall_clearance_m": min(
            float(row["distance_m"]) for row in minima.values()
        ),
    }


def _build_route(
    source_model: np.ndarray,
    candidate_config: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, int]:
    source_physical = _static._physical_actions(
        source_model, candidate_config
    )
    start = source_physical[0].copy()
    rotated = start.copy()
    rotated[0] = float(contract["route"]["shoulder_pan_target_degrees"])
    maximum_pan_step = float(
        contract["route"]["maximum_pan_step_degrees_per_row"]
    )
    pan_steps = int(
        math.ceil(abs(float(rotated[0] - start[0])) / maximum_pan_step)
    )
    pan_prefix = np.asarray(
        [
            start + (rotated - start) * (index / pan_steps)
            for index in range(pan_steps + 1)
        ],
        dtype="<f8",
        order="C",
    )
    body = source_physical.copy(order="C")
    body[:, 0] = rotated[0]
    body[:, 1] = np.minimum(
        body[:, 1], float(contract["route"]["shoulder_lift_cap_degrees"])
    )
    physical = np.asarray(
        np.vstack((pan_prefix, body[1:])), dtype="<f8", order="C"
    )
    model = np.asarray(
        _physical_to_model_position(physical, candidate_config),
        dtype="<f8",
        order="C",
    )
    return physical, model, pan_steps


def compile_identification_route(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Compile the immutable high-clearance route without opening hardware."""

    _require(
        not output_directory.exists(),
        "immutable RP04C static output already exists",
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.full_range_no_contact_identification.v1",
        "unexpected RP04C contract schema",
    )
    _require(
        contract["authority"]
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
        "RP04C authority changed",
    )
    for entry in contract["inputs"].values():
        _bound(entry)
    v5 = _json(contract["inputs"]["v5_contract"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    registered_rigid = _json(contract["inputs"]["registered_rigid_candidate"])
    case_index = int(contract["route"]["source_case_index"])
    case = v5["cases"][case_index]
    _require(
        case["case_id"] == contract["route"]["source_case_id"]
        and case["action_sha256"]
        == contract["route"]["source_action_sha256"]
        and case["action_shape"] == contract["route"]["source_action_shape"],
        "RP04C source action identity changed",
    )
    source_model = _temporal._load_action(case)
    physical, model_actions, pan_steps = _build_route(
        source_model, manifest["candidate_config"], contract
    )
    _require(
        list(physical.shape) == contract["route"]["expected_route_shape"]
        and pan_steps == contract["route"]["expected_pan_prefix_steps"],
        "RP04C route denominator changed",
    )
    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )
    uncorrected_rigid = {
        "robot_board_translation_xyz_m": [0.0, 0.0, 0.0],
        "robot_board_yaw_radians": 0.0,
    }
    registered_scene = _scene_audit(
        model_builder=model_builder,
        rigid=registered_rigid,
        actions=model_actions,
        selected_piece_id=case["selected_piece_id"],
    )
    uncorrected_scene = _scene_audit(
        model_builder=model_builder,
        rigid=uncorrected_rigid,
        actions=model_actions,
        selected_piece_id=case["selected_piece_id"],
    )
    registered_clearance = _clearance_audit(
        model_builder=model_builder,
        rigid=registered_rigid,
        actions=model_actions,
    )
    uncorrected_clearance = _clearance_audit(
        model_builder=model_builder,
        rigid=uncorrected_rigid,
        actions=model_actions,
    )
    lower = np.asarray(
        contract["gateway"]["follower_calibrated_minimum"],
        dtype=np.float64,
    )
    upper = np.asarray(
        contract["gateway"]["follower_calibrated_maximum"],
        dtype=np.float64,
    )
    rate_limits = np.asarray(
        contract["gateway"]["maximum_rates_per_second"],
        dtype=np.float64,
    )
    sample_hz = float(contract["route"]["sample_hz"])
    maximum_rates = np.max(
        np.abs(np.diff(physical, axis=0)) * sample_hz, axis=0
    )
    boundaries = [
        int(value) for value in contract["gateway"]["segment_boundaries"]
    ]
    segments = _segment_audit(
        physical,
        boundaries,
        excursion_limit=float(
            contract["gateway"]["segment_excursion_limit_degrees"]
        ),
    )
    minimum_clearance = float(
        contract["geometry"]["minimum_dual_scene_clearance_m"]
    )
    checks = {
        "source_requested_bytes_unchanged_before_route_transform": bool(
            hashlib.sha256(source_model.tobytes(order="C")).hexdigest()
            == case["action_sha256"]
        ),
        "registered_scene_contact_free": registered_scene["passed"],
        "uncorrected_scene_contact_free": uncorrected_scene["passed"],
        "registered_scene_clearance": registered_clearance[
            "minimum_overall_clearance_m"
        ]
        >= minimum_clearance,
        "uncorrected_scene_clearance": uncorrected_clearance[
            "minimum_overall_clearance_m"
        ]
        >= minimum_clearance,
        "all_rows_inside_calibrated_limits": bool(
            np.all(physical >= lower) and np.all(physical <= upper)
        ),
        "all_rates_inside_gateway_limits": bool(
            np.all(maximum_rates <= rate_limits)
        ),
        "all_segments_inside_excursion_limit": all(
            row["all_six_channels_within_frozen_limit"] for row in segments
        ),
        "route_reaches_required_elbow_support": float(
            np.min(physical[:, 2])
        )
        <= float(contract["route"]["required_elbow_minimum_degrees"]),
        "reverse_return_is_exact": bool(
            np.array_equal(physical[::-1][::-1], physical)
        ),
    }
    passed = all(checks.values())
    output_directory.mkdir(parents=True)
    physical_path = output_directory / "physical_route.f64le"
    model_path = output_directory / "model_route.f64le"
    physical_path.write_bytes(physical.tobytes(order="C"))
    model_path.write_bytes(model_actions.tobytes(order="C"))
    receipt = {
        "schema_version":
        "sim2claw.full_range_no_contact_identification_receipt.v1",
        "contract_id": contract["contract_id"],
        "status": (
            "full_range_no_contact_identification_static_pass"
            if passed
            else "full_range_no_contact_identification_static_reject"
        ),
        "passed": passed,
        "source_case_id": case["case_id"],
        "source_action_sha256": case["action_sha256"],
        "route_transform": {
            "shoulder_pan_target_degrees": contract["route"][
                "shoulder_pan_target_degrees"
            ],
            "shoulder_lift_cap_degrees": contract["route"][
                "shoulder_lift_cap_degrees"
            ],
            "task_execution": False,
            "contact_intent": False,
        },
        "physical_route": {
            "path": _display_path(physical_path),
            "sha256": _sha(physical_path),
            "shape": list(physical.shape),
            "dtype": "little_endian_float64",
        },
        "model_route": {
            "path": _display_path(model_path),
            "sha256": _sha(model_path),
            "shape": list(model_actions.shape),
            "dtype": "little_endian_float64",
        },
        "row_zero_physical": physical[0].tolist(),
        "terminal_physical": physical[-1].tolist(),
        "minimum_elbow_degrees": float(np.min(physical[:, 2])),
        "minimum_elbow_row": int(np.argmin(physical[:, 2])),
        "maximum_rates_per_second": maximum_rates.tolist(),
        "segments": segments,
        "registered_scene": registered_scene,
        "uncorrected_scene": uncorrected_scene,
        "registered_clearance": registered_clearance,
        "uncorrected_clearance": uncorrected_clearance,
        "checks": checks,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "FullRangeNoContactIdentificationError",
    "compile_identification_route",
]
