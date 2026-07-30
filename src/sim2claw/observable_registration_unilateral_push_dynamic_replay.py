"""Exact-action dynamic replay after canonical reset-layout repair."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .pawn_bg_demo_sim import _piece_bodies
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .realized_action_outcome_mission import (
    _contact_counts,
    _outcome,
    _tensor,
    load_contract as load_c6_contract,
    physical_to_model,
)

SCHEMA = (
    "sim2claw.observable_registration_unilateral_push_dynamic_replay_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_unilateral_push_dynamic_replay_receipt.v1"
)
TRACE_SCHEMA = (
    "sim2claw.observable_registration_unilateral_push_dynamic_replay_trace.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_unilateral_push_dynamic_replay_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_unilateral_push_dynamic_replay_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_unilateral_push_dynamic_replay_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="unilateral push dynamic replay")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    replay = contract["replay"]
    _require(
        replay["one_run_only"] is True
        and replay["canonical_rank1_near_piece_reset_required"] is True
        and replay["natural_contact_only"] is True,
        "replay identity widened",
    )
    forbidden = (
        "action_change_allowed",
        "camera_change_allowed",
        "contact_parameter_change_allowed",
        "object_parameter_change_allowed",
        "endpoint_injection_allowed",
        "latch_or_attachment_allowed",
    )
    _require(
        all(replay[name] is False for name in forbidden),
        "replay assistance enabled",
    )
    _require(
        contract["candidate"]["selection_used_task_contact_rows"] is True
        and contract["candidate"]["global_mapping_approved"] is False
        and contract["reporting"]["transfer_claim_allowed"] is False,
        "proof boundary widened",
    )
    authority = contract["authority"]
    _require(
        authority["simulator_replay"] is True
        and not any(
            value
            for name, value in authority.items()
            if name != "simulator_replay"
        ),
        "authority widened",
    )
    c6 = load_c6_contract(
        _bound_path(
            contract["sources"]["c6_contract"],
            root=root,
            label="C6 contract",
        ),
        root=root,
    )
    return contract, c6


def run_unilateral_push_dynamic_replay_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR19 one-run receipt already exists")
    contract, c6 = load_unilateral_push_dynamic_replay_contract(
        contract_path, root=root
    )
    or18 = _bound_json(
        contract["sources"]["or18_receipt"], root=root, label="OR18 receipt"
    )
    _require(
        or18["status"]
        == "PASS_QUARANTINED_UNILATERAL_NAMED_CONTACT_NO_DYNAMICS"
        and or18["actions_changed"] is False,
        "OR18 static prerequisite changed",
    )
    source = c6["source"]
    arrays = {
        name: _tensor(
            _bound_path(source[name], root=root, label=name), source[name]
        )
        for name in (
            "requested",
            "gateway_sent",
            "initial_measured",
            "timestamps",
            "identified_applied",
        )
    }
    requested = arrays["requested"]
    sent = arrays["gateway_sent"]
    measured = arrays["initial_measured"]
    timestamps = arrays["timestamps"]
    applied_physical = arrays["identified_applied"]
    _require(
        requested.shape
        == sent.shape
        == measured.shape
        == applied_physical.shape
        == (531, 6)
        and timestamps.shape == (531,)
        and bool(np.all(np.diff(timestamps) > 0.0)),
        "exact action tensor alignment changed",
    )

    candidate_manifest = _bound_json(
        contract["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    candidate_config = copy.deepcopy(candidate_manifest["candidate_config"])
    historical = _bound_json(
        contract["sources"]["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    body_offsets = historical["mapping"]["candidate"][
        "joint_zero_offsets_rad"
    ]
    historical_ranges = historical["mapping"]["candidate"][
        "joint_range_envelope_rad"
    ]
    _require(
        len(body_offsets) == len(historical_ranges) == 5,
        "historical body mapping width changed",
    )
    joints = candidate_config["physical_adapter"]["joint_transform"]["joints"]
    for index, value in enumerate(body_offsets):
        joints[index]["zero_offset"] = float(value)
    joints[5]["zero_offset"] = float(
        contract["candidate"]["gripper_zero_offset_rad"]
    )
    replay_manifest = {"candidate_config": candidate_config}
    applied_model = physical_to_model(applied_physical, replay_manifest)
    initial_model = physical_to_model(measured[:1], replay_manifest)[0]

    scene_path = _bound_path(
        contract["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(
        scene_path,
        pawn_height_m=0.034,
        canonical_piece_reset=True,
    ).compile()
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate_config["bindings"]["joint_names"]
    ]
    actuator_ids = np.asarray(
        [
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            for name in candidate_config["bindings"]["actuator_names"]
        ],
        dtype=np.int64,
    )
    _require(
        min(joint_ids + actuator_ids.tolist()) >= 0,
        "robot binding is incomplete",
    )
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids],
        dtype=np.int64,
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[item]) for item in joint_ids],
        dtype=np.int64,
    )
    range_expansions: list[dict[str, Any]] = []
    for index, joint_id in enumerate(joint_ids):
        if not model.jnt_limited[joint_id]:
            continue
        observed_minimum = min(
            float(np.min(applied_model[:, index])), float(initial_model[index])
        )
        observed_maximum = max(
            float(np.max(applied_model[:, index])), float(initial_model[index])
        )
        original = model.jnt_range[joint_id].copy()
        if index < 5:
            effective = np.asarray(
                historical_ranges[index], dtype=np.float64
            )
            _require(
                effective.shape == (2,)
                and observed_minimum >= float(effective[0])
                and observed_maximum <= float(effective[1]),
                "trajectory exceeds frozen historical range envelope",
            )
        else:
            effective = original.copy()
            maximum_expansion = float(
                c6["replay"]["maximum_joint_range_expansion_rad"]
            )
            effective[0] = min(float(effective[0]), observed_minimum)
            effective[1] = max(float(effective[1]), observed_maximum)
            _require(
                max(
                    0.0,
                    float(original[0] - effective[0]),
                    float(effective[1] - original[1]),
                )
                <= maximum_expansion,
                "gripper trajectory exceeds bounded range union",
            )
        lower = max(0.0, float(original[0] - effective[0]))
        upper = max(0.0, float(effective[1] - original[1]))
        model.jnt_range[joint_id] = effective
        range_expansions.append(
            {
                "joint": candidate_config["bindings"]["joint_names"][index],
                "lower_expansion_rad": lower,
                "upper_expansion_rad": upper,
            }
        )

    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(
        selected_body >= 0 and selected_joint >= 0,
        "selected pawn binding is incomplete",
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = initial_model
    data.ctrl[actuator_ids] = initial_model
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_z = float(data.qpos[selected_qpos + 2])
    upright = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7],
        dtype=np.float64,
    ).copy()
    initial_xy = np.asarray(
        c6["initialization"]["physical_d1_world_position_m"][:2],
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 2] = initial_xy
    data.qpos[selected_qpos + 2] = support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = applied_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = applied_model[0]
    mujoco.mj_forward(model, data)

    initial_position = np.asarray(
        data.xpos[selected_body], dtype=np.float64
    ).copy()
    initial_height = float(initial_position[2])
    pieces = _piece_bodies(model)
    initial_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }
    initial_nonjaw_contacts = []
    for index in range(data.ncon):
        contact = data.contact[index]
        body_a = int(model.geom_bodyid[int(contact.geom1)])
        body_b = int(model.geom_bodyid[int(contact.geom2)])
        if selected_body not in (body_a, body_b):
            continue
        other = body_b if body_a == selected_body else body_a
        other_name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, other)
            or f"body-{other}"
        )
        if other_name != "chess_board":
            initial_nonjaw_contacts.append(other_name)
    _require(
        not initial_nonjaw_contacts,
        "canonical reset still overlaps the selected pawn",
    )

    selected_contact_steps = 0
    first_selected_contact_sample: int | None = None
    trace_rows: list[dict[str, Any]] = []

    def observe(sample_index: int) -> None:
        nonlocal selected_contact_steps, first_selected_contact_sample
        count, _ = _contact_counts(
            model, data, selected_body=selected_body
        )
        selected_contact_steps += count
        if count and first_selected_contact_sample is None:
            first_selected_contact_sample = sample_index

    def capture(sample_index: int) -> None:
        trace_rows.append(
            {
                "sample_index": sample_index,
                "source_timestamp_seconds": float(timestamps[sample_index]),
                "requested_physical": requested[sample_index]
                .astype(float)
                .tolist(),
                "gateway_sent_physical": sent[sample_index]
                .astype(float)
                .tolist(),
                "identified_applied_physical": applied_physical[sample_index]
                .astype(float)
                .tolist(),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).tolist(),
            }
        )

    capture(0)
    timestep = float(model.opt.timestep)
    maximum_quantization_error = 0.0
    for index in range(1, len(applied_model)):
        dt = float(timestamps[index] - timestamps[index - 1])
        nstep = max(1, round(dt / timestep))
        maximum_quantization_error = max(
            maximum_quantization_error, abs(nstep * timestep - dt)
        )
        previous = applied_model[index - 1]
        current = applied_model[index]
        velocity = (current - previous) / dt
        for step in range(nstep):
            alpha = (step + 1) / nstep
            pose = previous + alpha * (current - previous)
            data.qpos[qpos_addresses] = pose
            data.qvel[dof_addresses] = velocity
            data.ctrl[actuator_ids] = pose
            mujoco.mj_forward(model, data)
            mujoco.mj_step(model, data)
            observe(index)
        capture(index)

    data.qpos[qpos_addresses] = applied_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = applied_model[-1]
    mujoco.mj_forward(model, data)
    for _ in range(
        round(
            float(c6["replay"]["post_action_settle_seconds"]) / timestep
        )
    ):
        mujoco.mj_step(model, data)
        observe(len(applied_model) - 1)

    other_displacement = max(
        (
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_piece_positions[name]
                )
            )
            for name, body_id in pieces.items()
            if name != selected_name
        ),
        default=0.0,
    )
    target = np.asarray(
        current_square_center(
            c6["initialization"]["destination_square"],
            config_path=scene_path,
        ),
        dtype=np.float64,
    )
    outcome = _outcome(
        data=data,
        model=model,
        selected_body=selected_body,
        selected_dof=selected_dof,
        initial_height=initial_height,
        target=target,
        other_displacement=other_displacement,
        selected_contact_steps=selected_contact_steps,
        evaluator=c6["evaluator"],
    )
    positions = np.asarray(
        [row["selected_pawn_position_m"] for row in trace_rows],
        dtype=np.float64,
    )
    displacement = np.linalg.norm(
        positions[:, :2] - initial_position[:2], axis=1
    )
    moving = np.flatnonzero(
        displacement
        > float(contract["reporting"]["motion_threshold_m"])
    )
    direction = target[:2] - initial_position[:2]
    direction /= np.linalg.norm(direction)
    progress = float(
        (np.asarray(data.xpos[selected_body])[:2] - initial_position[:2])
        @ direction
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_QUARANTINED_EXACT_ACTION_TASK_OUTCOME"
            if outcome["numeric_task_success"]
            else (
                "PASS_QUARANTINED_EXACT_ACTION_CONTACT_AND_PROGRESS"
                if selected_contact_steps > 0 and progress > 0.0
                else "TERMINAL_NEGATIVE_DYNAMIC_CONSEQUENCE"
            )
        ),
        "source_identity": {
            "recording_id": source["recording_id"],
            "requested_sha256": source["requested"]["sha256"],
            "gateway_sent_sha256": source["gateway_sent"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "identified_applied_sha256": source["identified_applied"][
                "sha256"
            ],
            "row_count": len(applied_model),
            "row_order_preserved": True,
        },
        "candidate": contract["candidate"],
        "initialization": {
            "canonical_rank1_near_piece_reset": True,
            "selected_pawn_initial_position_m": initial_position.tolist(),
            "selected_pawn_initial_nonboard_contacts": initial_nonjaw_contacts,
            "support_z_m": support_z,
        },
        "dynamics": {
            "first_selected_jaw_contact_sample": first_selected_contact_sample,
            "selected_jaw_contact_steps": selected_contact_steps,
            "first_motion_over_1mm_sample": (
                int(moving[0]) if moving.size else None
            ),
            "maximum_planar_displacement_m": float(np.max(displacement)),
            "signed_progress_toward_d2_m": progress,
            "required_progress_m": contract["reporting"][
                "required_progress_m"
            ],
            "required_progress_passed": progress
            >= float(contract["reporting"]["required_progress_m"]),
            "maximum_timestamp_quantization_error_seconds": (
                maximum_quantization_error
            ),
        },
        "outcome": outcome,
        "range_expansions": range_expansions,
        "actions_changed": False,
        "dynamic_replays": 1,
        "task_rows_used_for_candidate_selection": True,
        "global_mapping_approved": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(
        output_directory / "trace.json",
        {"schema_version": TRACE_SCHEMA, "rows": trace_rows},
    )
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_unilateral_push_dynamic_replay_once()
    return 0
