"""Static sample-232 jaw/pawn gap selection with no dynamics or outcome search."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_jaw_pawn_geometric_gap import (
    _jaw_geom_ids,
    _pawn_geom_ids,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    _candidate_spec,
    load_unilateral_push_dynamic_replay_contract,
)
from .realized_action_outcome_mission import _tensor, physical_to_model


SCHEMA = "sim2claw.observable_registration_sample232_aperture_geometry_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_sample232_aperture_geometry_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_sample232_aperture_geometry_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_sample232_aperture_geometry_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="sample-232 aperture geometry")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    or28, c6 = load_unilateral_push_dynamic_replay_contract(
        _bound_path(contract["sources"]["or28_contract"], root=root, label="OR28")
    )
    or3 = _bound_json(contract["sources"]["or3_closeout"], root=root, label="OR3")
    identity = contract["identity"]
    _require(
        identity["recording_id"] == c6["source"]["recording_id"]
        and identity["row_count"] == 531
        and identity["physical_candidate_contact_interval"]
        == or3["physical_events"]["candidate_contact_interval_samples"]
        and identity["physical_first_definite_enclosure_sample"]
        == or3["physical_events"]["first_definite_enclosure_sample"],
        "retained enclosure identity changed",
    )
    grid = contract["grid"]["gripper_zero_offset_rad"]
    _require(
        len(grid) == 17
        and grid == sorted(grid)
        and grid[0] == -0.17453
        and abs(grid[-1] - or28["candidate"]["gripper_zero_offset_rad"]) < 1e-15,
        "frozen aperture grid changed",
    )
    evaluation = contract["evaluation"]
    _require(
        evaluation["forward_kinematics_allowed"] is True
        and evaluation["physics_integration_allowed"] is False
        and evaluation["dynamic_replay_allowed"] is False
        and not any(
            evaluation[name]
            for name in (
                "action_change_allowed",
                "contact_parameter_change_allowed",
                "object_parameter_change_allowed",
                "body_mapping_change_allowed",
                "scene_change_allowed",
                "camera_change_allowed",
                "global_mapping_promotion_allowed",
                "transfer_claim_allowed",
            )
        ),
        "static evaluation widened",
    )
    _require(
        contract["authority"]["simulator_static_evaluation"] is True
        and not any(
            value
            for name, value in contract["authority"].items()
            if name != "simulator_static_evaluation"
        ),
        "authority widened",
    )
    return contract, or28, c6


def _minimum_gap(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    jaw_geoms: list[int],
    pawn_geoms: list[int],
) -> float:
    values = []
    for jaw_geom in jaw_geoms:
        for pawn_geom in pawn_geoms:
            fromto = np.zeros(6, dtype=np.float64)
            values.append(
                float(
                    mujoco.mj_geomDistance(
                        model, data, jaw_geom, pawn_geom, 1.0, fromto
                    )
                )
            )
    return min(values)


def evaluate_sample232_aperture_geometry(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR29 receipt already exists")
    contract, or28, c6 = load_contract(contract_path, root=root)
    source = c6["source"]
    applied_physical = _tensor(
        _bound_path(source["identified_applied"], root=root, label="applied"),
        source["identified_applied"],
    )
    measured = _tensor(
        _bound_path(source["initial_measured"], root=root, label="measured"),
        source["initial_measured"],
    )
    candidate_manifest = _bound_json(
        or28["sources"]["or6_candidate"], root=root, label="OR6 candidate"
    )
    historical = _bound_json(
        or28["sources"]["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    base_candidate = copy.deepcopy(candidate_manifest["candidate_config"])
    for index, value in enumerate(
        historical["mapping"]["candidate"]["joint_zero_offsets_rad"]
    ):
        base_candidate["physical_adapter"]["joint_transform"]["joints"][index][
            "zero_offset"
        ] = float(value)

    scene_path = _bound_path(
        or28["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in base_candidate["bindings"]["joint_names"]
    ]
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64
    )
    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    fixed = _jaw_geom_ids(model, ["left_fixed_jaw_"])
    moving = _jaw_geom_ids(model, ["left_moving_jaw_"])
    pawn = _pawn_geom_ids(model, selected_body)
    data = mujoco.MjData(model)

    rows = []
    first_sample, last_sample = contract["identity"]["static_sample_interval"]
    guard_first, guard_last = contract["identity"]["precontact_guard_interval"]
    selection_sample = contract["selection"]["sample"]
    for offset in contract["grid"]["gripper_zero_offset_rad"]:
        candidate = copy.deepcopy(base_candidate)
        candidate["physical_adapter"]["joint_transform"]["joints"][5][
            "zero_offset"
        ] = float(offset)
        wrapper = {"candidate_config": candidate}
        applied_model = physical_to_model(applied_physical, wrapper)
        initial_model = physical_to_model(measured[:1], wrapper)[0]
        data.qpos[qpos_addresses] = initial_model
        mujoco.mj_forward(model, data)
        mujoco.mj_step(model, data, nstep=100)
        support_z = float(data.qpos[selected_qpos + 2])
        upright = data.qpos[selected_qpos + 3 : selected_qpos + 7].copy()
        data.qpos[selected_qpos : selected_qpos + 2] = np.asarray(
            c6["initialization"]["physical_d1_world_position_m"][:2],
            dtype=np.float64,
        )
        data.qpos[selected_qpos + 2] = support_z
        data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
        samples = []
        for sample in range(first_sample, last_sample + 1):
            data.qpos[qpos_addresses] = applied_model[sample]
            data.qvel[:] = 0.0
            mujoco.mj_forward(model, data)
            samples.append(
                {
                    "sample_index": sample,
                    "fixed_jaw_signed_gap_m": _minimum_gap(
                        model, data, fixed, pawn
                    ),
                    "moving_jaw_signed_gap_m": _minimum_gap(
                        model, data, moving, pawn
                    ),
                }
            )
        selected = next(row for row in samples if row["sample_index"] == selection_sample)
        guard_rows = [
            row
            for row in samples
            if guard_first <= row["sample_index"] <= guard_last
        ]
        maximum_precontact_penetration = max(
            0.0,
            -min(
                min(
                    row["fixed_jaw_signed_gap_m"],
                    row["moving_jaw_signed_gap_m"],
                )
                for row in guard_rows
            ),
        )
        lower = float(contract["selection"]["minimum_each_jaw_gap_m"])
        upper = float(contract["selection"]["maximum_each_jaw_gap_m"])
        eligible = (
            lower <= selected["fixed_jaw_signed_gap_m"] <= upper
            and lower <= selected["moving_jaw_signed_gap_m"] <= upper
            and maximum_precontact_penetration
            <= float(contract["selection"]["maximum_precontact_penetration_m"])
        )
        rows.append(
            {
                "gripper_zero_offset_rad": float(offset),
                "sample_232": selected,
                "maximum_precontact_penetration_m": maximum_precontact_penetration,
                "score": max(
                    abs(selected["fixed_jaw_signed_gap_m"]),
                    abs(selected["moving_jaw_signed_gap_m"]),
                ),
                "eligible": eligible,
                "samples": samples,
            }
        )
    eligible_rows = [row for row in rows if row["eligible"]]
    selected = (
        min(
            eligible_rows,
            key=lambda row: (
                row["score"],
                abs(row["gripper_zero_offset_rad"]),
                row["gripper_zero_offset_rad"],
            ),
        )
        if eligible_rows
        else None
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_STATIC_SAMPLE232_APERTURE_CANDIDATE"
            if selected is not None
            else "NO_STATIC_BILATERAL_CANDIDATE"
        ),
        "source_identity": {
            "recording_id": source["recording_id"],
            "identified_applied_sha256": source["identified_applied"]["sha256"],
            "row_count": 531,
            "source_row_order_preserved": True,
        },
        "candidate_count": len(rows),
        "eligible_candidate_count": len(eligible_rows),
        "selected_candidate": (
            {
                key: value
                for key, value in selected.items()
                if key != "samples"
            }
            if selected
            else None
        ),
        "rows": rows,
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
