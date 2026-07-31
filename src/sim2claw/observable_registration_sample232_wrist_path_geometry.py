"""Static wrist-flex/roll path-shape diagnostic at retained enclosure timing."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .learning_factory_artifacts import FactoryArtifactError, atomic_write_json, canonical_digest, load_json_object
from .observable_jaw_pawn_geometric_gap import _jaw_geom_ids, _pawn_geom_ids
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_json, _bound_path
from .observable_registration_sample232_aperture_geometry import _minimum_gap
from .observable_registration_sample232_base_yaw_path_geometry import load_contract as load_or32_contract
from .observable_registration_unilateral_push_dynamic_replay import _candidate_spec
from .realized_action_outcome_mission import _tensor, physical_to_model


SCHEMA = "sim2claw.observable_registration_sample232_wrist_path_geometry_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_sample232_wrist_path_geometry_receipt.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_sample232_wrist_path_geometry_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_sample232_wrist_path_geometry_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_contract(path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="sample-232 wrist path geometry")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    _, or28, c6 = load_or32_contract(
        _bound_path(contract["sources"]["or32_contract"], root=root, label="OR32"),
        root=root,
    )
    _require(
        [len(contract["grid"][name]) for name in (
            "left_base_world_x_delta_m",
            "left_base_world_y_delta_m",
            "gripper_zero_offset_rad",
            "wrist_flex_zero_offset_delta_degrees",
            "wrist_roll_zero_offset_delta_degrees",
        )] == [3, 3, 3, 5, 5],
        "wrist grid changed",
    )
    _require(
        contract["evaluation"]["physics_integration_allowed"] is False
        and contract["evaluation"]["dynamic_outcomes_may_not_select_grid_row"] is True,
        "static wrist evaluation widened",
    )
    return contract, or28, c6


def evaluate_wrist_path_geometry(
    *, contract_path: Path = CONTRACT_PATH, output_directory: Path = OUTPUT_DIRECTORY, root: Path = REPO_ROOT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR33 receipt already exists")
    contract, or28, c6 = load_contract(contract_path, root=root)
    source = c6["source"]
    applied = _tensor(_bound_path(source["identified_applied"], root=root, label="applied"), source["identified_applied"])
    measured = _tensor(_bound_path(source["initial_measured"], root=root, label="measured"), source["initial_measured"])
    manifest = _bound_json(or28["sources"]["or6_candidate"], root=root, label="OR6")
    historical = _bound_json(or28["sources"]["historical_mapping_receipt"], root=root, label="mapping")
    base_candidate = copy.deepcopy(manifest["candidate_config"])
    for index, value in enumerate(historical["mapping"]["candidate"]["joint_zero_offsets_rad"]):
        base_candidate["physical_adapter"]["joint_transform"]["joints"][index]["zero_offset"] = float(value)
    scene_path = _bound_path(or28["sources"]["or18_scene"], root=root, label="scene")
    model = _candidate_spec(scene_path, pawn_height_m=0.034, canonical_piece_reset=True).compile()
    left_base = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_base")
    original_xy = model.body_pos[left_base, :2].copy()
    joint_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in base_candidate["bindings"]["joint_names"]]
    qpos_addresses = np.asarray([int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64)
    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    fixed = _jaw_geom_ids(model, ["left_fixed_jaw_"])
    moving = _jaw_geom_ids(model, ["left_moving_jaw_"])
    pawn = _pawn_geom_ids(model, selected_body)
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = physical_to_model(measured[:1], {"candidate_config": base_candidate})[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_z = float(data.qpos[selected_qpos + 2])
    upright = data.qpos[selected_qpos + 3 : selected_qpos + 7].copy()
    selected_xy = np.asarray(c6["initialization"]["physical_d1_world_position_m"][:2], dtype=np.float64)
    guard_first, _ = contract["selection"]["precontact_guard_interval"]
    sample = int(contract["selection"]["sample"])
    lower = float(contract["selection"]["minimum_each_jaw_gap_m"])
    upper = float(contract["selection"]["maximum_each_jaw_gap_m"])
    rows = []
    for dx in contract["grid"]["left_base_world_x_delta_m"]:
        for dy in contract["grid"]["left_base_world_y_delta_m"]:
            model.body_pos[left_base, :2] = original_xy + np.asarray([dx, dy])
            for gripper in contract["grid"]["gripper_zero_offset_rad"]:
                for flex_degrees in contract["grid"]["wrist_flex_zero_offset_delta_degrees"]:
                    for roll_degrees in contract["grid"]["wrist_roll_zero_offset_delta_degrees"]:
                        candidate = copy.deepcopy(base_candidate)
                        joints = candidate["physical_adapter"]["joint_transform"]["joints"]
                        joints[3]["zero_offset"] += math.radians(flex_degrees)
                        joints[4]["zero_offset"] += math.radians(roll_degrees)
                        joints[5]["zero_offset"] = float(gripper)
                        applied_model = physical_to_model(applied, {"candidate_config": candidate})
                        gaps = []
                        for index in range(guard_first, sample + 1):
                            data.qpos[selected_qpos : selected_qpos + 2] = selected_xy
                            data.qpos[selected_qpos + 2] = support_z
                            data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
                            data.qpos[qpos_addresses] = applied_model[index]
                            data.qvel[:] = 0.0
                            mujoco.mj_forward(model, data)
                            gaps.append((index, _minimum_gap(model, data, fixed, pawn), _minimum_gap(model, data, moving, pawn)))
                        final = gaps[-1]
                        penetration = max(0.0, -min(min(a, b) for _, a, b in gaps[:-1]))
                        eligible = lower <= final[1] <= upper and lower <= final[2] <= upper and penetration <= float(contract["selection"]["maximum_precontact_penetration_m"])
                        rows.append({
                            "left_base_world_x_delta_m": float(dx),
                            "left_base_world_y_delta_m": float(dy),
                            "gripper_zero_offset_rad": float(gripper),
                            "wrist_flex_zero_offset_delta_degrees": float(flex_degrees),
                            "wrist_roll_zero_offset_delta_degrees": float(roll_degrees),
                            "sample_232_fixed_jaw_signed_gap_m": final[1],
                            "sample_232_moving_jaw_signed_gap_m": final[2],
                            "maximum_precontact_penetration_m": penetration,
                            "score": max(abs(final[1]), abs(final[2])) + penetration,
                            "eligible": eligible,
                        })
    eligible = [row for row in rows if row["eligible"]]
    selected = min(eligible, key=lambda row: (row["score"], math.hypot(row["wrist_flex_zero_offset_delta_degrees"], row["wrist_roll_zero_offset_delta_degrees"]), math.hypot(row["left_base_world_x_delta_m"], row["left_base_world_y_delta_m"]))) if eligible else None
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_STATIC_WRIST_PATH_CANDIDATE" if selected else "NO_STATIC_WRIST_PATH_CANDIDATE",
        "source_identity": {"recording_id": source["recording_id"], "identified_applied_sha256": source["identified_applied"]["sha256"], "row_count": 531},
        "candidate_count": len(rows),
        "eligible_candidate_count": len(eligible),
        "selected_candidate": selected,
        "closest_candidate": min(rows, key=lambda row: row["score"]),
        "physics_integration_steps": 0,
        "dynamic_outcomes_used_for_selection": False,
        "global_mapping_approved": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt
