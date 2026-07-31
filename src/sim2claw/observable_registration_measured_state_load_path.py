"""Trace the OR34 raw-state load path and one fixed actuator envelope.

The robot is observation-conditioned by the immutable follower-measured joint
trace.  The selected pawn is initialized once and subsequently evolves only
through MuJoCo integration and contacts.
"""

from __future__ import annotations

import hashlib
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
from .observable_registration_exact_replay_contact_introspection import (
    JAW_BODY_NAMES,
    _contact_observations,
)
from .observable_registration_measured_state_visual_twin import (
    _range_union,
    _tilt_degrees,
    load_measured_state_visual_twin_contract,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import (
    _candidate_config,
)
from .pawn_bg_demo_sim import _piece_bodies
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .realized_action_outcome_mission import _contact_counts, _outcome


SCHEMA = (
    "sim2claw.observable_registration_measured_state_load_path_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_load_path_receipt.v1"
)
TRACE_SCHEMA = (
    "sim2claw.observable_registration_measured_state_load_path_trace.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_load_path_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_load_path_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_load_path_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR35 measured-state load path")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    trajectory = contract["trajectory"]
    _require(
        trajectory["row_count"] == 531
        and trajectory["robot_driver"]
        == "raw_follower_actual_position_degrees"
        and trajectory[
            "preserve_source_values_order_timestamps_and_interpolation"
        ]
        is True
        and trajectory["action_or_state_assistance_allowed"] is False,
        "raw-state trajectory boundary widened",
    )
    variants = contract["variants"]
    _require(
        len(variants) == 2
        and variants[0]["variant_id"] == "canonical_2p94_nm"
        and variants[0]["sts3215_force_limit_nm"] == 2.94
        and variants[0]["simulator_mechanism_changed"] is False
        and variants[1]["variant_id"]
        == "manufacturer_7p4v_stall_1p91229675_nm"
        and variants[1]["sts3215_force_limit_nm"] == 1.91229675
        and variants[1]["simulator_mechanism_changed"] is True,
        "OR35 variant family widened",
    )
    manufacturer = contract["manufacturer_constraint"]
    _require(
        manufacturer["fixed_stall_torque_nm"] == 1.91229675
        and manufacturer["candidate_selected_without_task_outcome"] is True
        and manufacturer[
            "candidate_is_upper_force_envelope_not_rated_continuous_torque"
        ]
        is True,
        "manufacturer force constraint widened",
    )
    simulation = contract["simulation"]
    _require(
        simulation["natural_pawn_dynamics_only"] is True
        and simulation[
            "selected_pawn_pose_written_only_during_initialization"
        ]
        is True
        and simulation["terminal_result_may_select_or_revise_candidate"]
        is False
        and not any(
            simulation[name]
            for name in (
                "object_pose_injection_allowed",
                "latch_attachment_or_grasp_mode_allowed",
                "contact_geometry_or_material_change_allowed",
                "pawn_mass_com_or_inertia_change_allowed",
                "camera_mapping_or_reset_change_allowed",
            )
        ),
        "natural-dynamics boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values()),
        "claim boundary widened",
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
    return contract


def _first_event(
    rows: list[dict[str, Any]], predicate: Any
) -> dict[str, Any] | None:
    return next((row for row in rows if predicate(row)), None)


def _event_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "internal_step_index": row["internal_step_index"],
        "source_sample_index": row["source_sample_index"],
        "source_timestamp_seconds": row["source_timestamp_seconds"],
        "simulator_time_seconds": row["simulator_time_seconds"],
    }


def _run_variant(
    *,
    contract: dict[str, Any],
    variant: dict[str, Any],
    root: Path,
    spec_mutator: Any | None = None,
    model_mutator: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    or34_path = _bound_path(
        contract["sources"]["or34_contract"],
        root=root,
        label="OR34 contract",
    )
    or34 = load_measured_state_visual_twin_contract(or34_path, root=root)
    or19_path = _bound_path(
        or34["sources"]["or19_contract"],
        root=root,
        label="OR19 contract",
    )
    or19, c6 = load_unilateral_push_dynamic_replay_contract(
        or19_path, root=root
    )
    c6_loaded, candidate, measured_model, _ = _candidate_config(
        or19, root=root
    )
    _require(c6_loaded == c6 and measured_model.shape == (531, 6), "source drift")
    source = c6["source"]
    timestamps = np.fromfile(
        _bound_path(source["timestamps"], root=root, label="timestamps"),
        dtype=np.dtype(source["timestamps"]["dtype"]),
    ).reshape(source["timestamps"]["shape"])
    _require(
        timestamps.shape == (531,) and bool(np.all(np.diff(timestamps) > 0)),
        "timestamp identity changed",
    )

    scene_path = _bound_path(
        or19["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    spec = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    )
    spec_mutation_report = (
        None if spec_mutator is None else spec_mutator(spec)
    )
    model = spec.compile()
    jaw_body_names = set(JAW_BODY_NAMES)
    if spec_mutation_report is not None:
        for binding in spec_mutation_report.get("bindings", []):
            added_body = binding.get("added_body")
            if added_body:
                jaw_body_names.add(str(added_body))
    joint_names = candidate["bindings"]["joint_names"]
    actuator_names = candidate["bindings"]["actuator_names"]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    actuator_ids = np.asarray(
        [
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            for name in actuator_names
        ],
        dtype=np.int64,
    )
    _require(
        min(joint_ids + actuator_ids.tolist()) >= 0,
        "robot binding is incomplete",
    )
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[value]) for value in joint_ids],
        dtype=np.int64,
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[value]) for value in joint_ids],
        dtype=np.int64,
    )
    historical = _bound_json(
        or19["sources"]["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    _range_union(
        model=model,
        joint_ids=joint_ids,
        joint_names=joint_names,
        measured_model=measured_model,
        historical_ranges=historical["mapping"]["candidate"][
            "joint_range_envelope_rad"
        ],
        maximum_gripper_expansion_rad=float(
            c6["replay"]["maximum_joint_range_expansion_rad"]
        ),
    )
    original_force_ranges = np.asarray(
        model.actuator_forcerange[actuator_ids], dtype=np.float64
    ).copy()
    limit = float(variant["sts3215_force_limit_nm"])
    model.actuator_forcerange[actuator_ids, 0] = -limit
    model.actuator_forcerange[actuator_ids, 1] = limit
    _require(
        bool(np.all(model.actuator_forcelimited[actuator_ids]))
        and bool(
            np.allclose(
                model.actuator_forcerange[actuator_ids],
                np.asarray([[-limit, limit]] * len(actuator_ids)),
                atol=0.0,
                rtol=0.0,
            )
        ),
        "force envelope did not compile",
    )
    model_mutation_report = (
        None if model_mutator is None else model_mutator(model)
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
    data.qpos[qpos_addresses] = measured_model[0]
    data.ctrl[actuator_ids] = measured_model[0]
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
    data.qpos[qpos_addresses] = measured_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[0]
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

    trace_policy = contract["trace"]
    internal_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    selected_contact_steps = 0
    first_selected_contact_sample: int | None = None
    maximum_quantization_error = 0.0
    internal_step_index = 0
    timestep = float(model.opt.timestep)

    def observe(source_index: int, phase: str) -> None:
        nonlocal selected_contact_steps
        nonlocal first_selected_contact_sample
        nonlocal internal_step_index
        internal_step_index += 1
        count, _ = _contact_counts(
            model,
            data,
            selected_body=selected_body,
            jaw_names=jaw_body_names,
        )
        selected_contact_steps += count
        if count and first_selected_contact_sample is None:
            first_selected_contact_sample = source_index
        contacts, jaw_bodies, support = _contact_observations(
            model,
            data,
            selected_body=selected_body,
            jaw_body_names=jaw_body_names,
        )
        mujoco.mj_energyPos(model, data)
        mujoco.mj_energyVel(model, data)
        pawn_velocity = np.asarray(
            data.qvel[selected_dof : selected_dof + 6],
            dtype=np.float64,
        )
        internal_rows.append(
            {
                "internal_step_index": internal_step_index,
                "phase": phase,
                "source_sample_index": source_index,
                "source_timestamp_seconds": float(timestamps[source_index]),
                "simulator_time_seconds": float(data.time),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_quaternion_wxyz": np.asarray(
                    data.xquat[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_tilt_degrees": _tilt_degrees(
                    np.asarray(data.xquat[selected_body], dtype=np.float64)
                ),
                "selected_pawn_linear_velocity_m_s": pawn_velocity[:3].tolist(),
                "selected_pawn_angular_velocity_rad_s": pawn_velocity[3:].tolist(),
                "board_support_contact": support,
                "named_jaw_contact_bodies": sorted(jaw_bodies),
                "named_jaw_contact_state": (
                    "bilateral"
                    if len(jaw_bodies) >= 2
                    else ("unilateral" if jaw_bodies else "none")
                ),
                "actuator_force_nm": np.asarray(
                    data.actuator_force[actuator_ids], dtype=np.float64
                ).tolist(),
                "actuator_velocity_rad_s": np.asarray(
                    data.actuator_velocity[actuator_ids], dtype=np.float64
                ).tolist(),
                "generalized_actuator_force_nm": np.asarray(
                    data.qfrc_actuator[dof_addresses], dtype=np.float64
                ).tolist(),
                "energy_potential_and_kinetic_j": np.asarray(
                    data.energy, dtype=np.float64
                ).tolist(),
                "contacts": contacts,
            }
        )

    for index in range(531):
        if index:
            dt = float(timestamps[index] - timestamps[index - 1])
            nstep = max(1, round(dt / timestep))
            maximum_quantization_error = max(
                maximum_quantization_error, abs(nstep * timestep - dt)
            )
            previous = measured_model[index - 1]
            current = measured_model[index]
            velocity = (current - previous) / dt
            for step in range(nstep):
                alpha = (step + 1) / nstep
                pose = previous + alpha * (current - previous)
                data.qpos[qpos_addresses] = pose
                data.qvel[dof_addresses] = velocity
                data.ctrl[actuator_ids] = pose
                mujoco.mj_forward(model, data)
                mujoco.mj_step(model, data)
                observe(index, "task")
        sample_rows.append(
            {
                "sample_index": index,
                "source_timestamp_seconds": float(timestamps[index]),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_quaternion_wxyz": np.asarray(
                    data.xquat[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_tilt_degrees": _tilt_degrees(
                    np.asarray(data.xquat[selected_body], dtype=np.float64)
                ),
            }
        )

    data.qpos[qpos_addresses] = measured_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[-1]
    mujoco.mj_forward(model, data)
    for _ in range(
        round(
            float(contract["simulation"]["post_action_settle_seconds"])
            / timestep
        )
    ):
        mujoco.mj_step(model, data)
        observe(530, "terminal_settle")

    positions = np.asarray(
        [row["selected_pawn_position_m"] for row in sample_rows],
        dtype=np.float64,
    )
    displacement = np.linalg.norm(
        positions[:, :2] - initial_position[:2], axis=1
    )
    moving = np.flatnonzero(
        displacement > float(trace_policy["motion_threshold_m"])
    )
    target = np.asarray(
        current_square_center(
            c6["initialization"]["destination_square"],
            config_path=scene_path,
        ),
        dtype=np.float64,
    )
    direction = target[:2] - initial_position[:2]
    direction /= np.linalg.norm(direction)
    final_position = np.asarray(
        data.xpos[selected_body], dtype=np.float64
    ).copy()
    progress = float((final_position[:2] - initial_position[:2]) @ direction)
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

    analysis_rows = [
        row
        for row in internal_rows
        if row["phase"] == "task"
        and int(trace_policy["analysis_source_sample_start"])
        <= row["source_sample_index"]
        <= int(trace_policy["analysis_source_sample_end"])
    ]
    first_jaw = _first_event(
        analysis_rows,
        lambda row: row["named_jaw_contact_state"] != "none",
    )
    first_bilateral = _first_event(
        analysis_rows,
        lambda row: row["named_jaw_contact_state"] == "bilateral",
    )
    first_tilt = _first_event(
        analysis_rows,
        lambda row: row["selected_pawn_tilt_degrees"]
        >= float(trace_policy["tilt_threshold_degrees"]),
    )
    first_slip = _first_event(
        analysis_rows,
        lambda row: any(
            contact["other_body"] in jaw_body_names
            and contact["tangential_slip_speed_m_s"]
            >= float(trace_policy["slip_threshold_m_s"])
            for contact in row["contacts"]
        ),
    )
    support_minimum = int(
        trace_policy["support_loss_minimum_internal_steps"]
    )
    first_support_loss: dict[str, Any] | None = None
    for index in range(len(analysis_rows) - support_minimum + 1):
        window = analysis_rows[index : index + support_minimum]
        if all(not row["board_support_contact"] for row in window):
            first_support_loss = window[0]
            break

    jaw_forces: list[float] = []
    jaw_slips: list[float] = []
    for row in analysis_rows:
        for contact in row["contacts"]:
            if contact["other_body"] not in jaw_body_names:
                continue
            jaw_forces.append(
                abs(
                    float(
                        contact["mujoco_contact_frame_force_torque_raw"][0]
                    )
                )
            )
            jaw_slips.append(float(contact["tangential_slip_speed_m_s"]))
    actuator_force = np.asarray(
        [row["actuator_force_nm"] for row in internal_rows],
        dtype=np.float64,
    )
    clipping = np.isclose(
        np.abs(actuator_force), limit, rtol=0.0, atol=1e-9
    )
    sample_260 = sample_rows[260]
    trace_summary = {
        "internal_step_count": len(internal_rows),
        "analysis_internal_step_count": len(analysis_rows),
        "first_named_jaw_contact": _event_summary(first_jaw),
        "first_named_jaw_contact_source_sample": (
            None if first_jaw is None else first_jaw["source_sample_index"]
        ),
        "first_bilateral_jaw_contact": _event_summary(first_bilateral),
        "first_orientation_over_5deg": _event_summary(first_tilt),
        "first_sustained_support_loss": _event_summary(first_support_loss),
        "first_jaw_slip_over_threshold": _event_summary(first_slip),
        "maximum_named_jaw_normal_force_raw": max(jaw_forces, default=0.0),
        "maximum_named_jaw_tangential_slip_speed_m_s": max(
            jaw_slips, default=0.0
        ),
        "maximum_absolute_actuator_force_nm_by_joint": np.max(
            np.abs(actuator_force), axis=0
        ).tolist(),
        "actuator_force_limit_hit_count_by_joint": np.sum(
            clipping, axis=0
        ).astype(int).tolist(),
        "tilt_at_sample_260_degrees": sample_260[
            "selected_pawn_tilt_degrees"
        ],
    }
    result = {
        "variant_id": variant["variant_id"],
        "role": variant["role"],
        "sts3215_force_limit_nm": limit,
        "original_actuator_force_ranges_nm": original_force_ranges.tolist(),
        "compiled_actuator_force_ranges_nm": np.asarray(
            model.actuator_forcerange[actuator_ids], dtype=np.float64
        ).tolist(),
        "joint_order": joint_names,
        "source_identity": {
            "raw_measured_sha256": source["initial_measured"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "row_count": 531,
            "values_order_timestamps_and_interpolation_unchanged": True,
        },
        "natural_dynamics": {
            "first_selected_jaw_contact_sample": first_selected_contact_sample,
            "selected_jaw_contact_steps": selected_contact_steps,
            "first_motion_over_1mm_sample": (
                int(moving[0]) if moving.size else None
            ),
            "maximum_planar_displacement_m": float(np.max(displacement)),
            "signed_progress_toward_d2_m": progress,
            "maximum_other_piece_displacement_m": other_displacement,
            "maximum_timestamp_quantization_error_seconds": (
                maximum_quantization_error
            ),
            "object_pose_injected": False,
            "latch_attachment_or_grasp_mode_used": False,
            "outcome": outcome,
        },
        "trace_summary": trace_summary,
    }
    if model_mutation_report is not None:
        result["model_mutation_report"] = model_mutation_report
    if spec_mutation_report is not None:
        result["spec_mutation_report"] = spec_mutation_report
    trace = {
        "schema_version": TRACE_SCHEMA,
        "variant_id": variant["variant_id"],
        "contact_force_semantics": (
            "raw_mujoco_contact_frame_force_torque_no_physical_force_claim"
        ),
        "rows": internal_rows,
        "sample_rows": sample_rows,
    }
    return result, trace


def _candidate_gate_report(
    contract: dict[str, Any], result: dict[str, Any]
) -> dict[str, bool]:
    gates = contract["candidate_gates"]
    natural = result["natural_dynamics"]
    trace = result["trace_summary"]
    contact = natural["first_selected_jaw_contact_sample"]
    motion = natural["first_motion_over_1mm_sample"]
    support_event = trace["first_sustained_support_loss"]
    support_sample = (
        None
        if support_event is None
        else support_event["source_sample_index"]
    )
    contact_interval = gates["first_selected_jaw_contact_interval_samples"]
    support_interval = gates["sustained_support_loss_interval_samples"]
    outcome = natural["outcome"]
    return {
        "contact_timing": (
            contact is not None
            and contact_interval[0] <= contact <= contact_interval[1]
        ),
        "no_early_motion": (
            motion is None
            or motion >= gates["no_motion_over_1mm_before_sample"]
        ),
        "support_loss_timing": (
            support_sample is not None
            and support_interval[0] <= support_sample <= support_interval[1]
        ),
        "upright_at_carry_start": (
            trace["tilt_at_sample_260_degrees"]
            <= gates["maximum_tilt_at_sample_260_degrees"]
        ),
        "final_planar_center": (
            outcome["final_planar_center_error_m"]
            <= gates["final_planar_center_error_m"]
        ),
        "final_upright": (
            outcome["final_upright_tilt_degrees"]
            <= gates["final_upright_tilt_degrees"]
        ),
        "final_height": (
            abs(outcome["final_height_error_m"])
            <= gates["final_height_error_m"]
        ),
        "other_pieces_stationary": (
            outcome["maximum_other_piece_displacement_m"]
            <= gates["maximum_other_piece_displacement_m"]
        ),
        "settled_linear": (
            outcome["final_linear_speed_m_s"]
            <= gates["final_linear_speed_m_s"]
        ),
        "settled_angular": (
            outcome["final_angular_speed_rad_s"]
            <= gates["final_angular_speed_rad_s"]
        ),
        "selected_piece_contact": (
            outcome["gates"]["selected_piece_contact"] is True
        ),
    }


def run_measured_state_load_path_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR35 one-run receipt already exists")
    contract = load_measured_state_load_path_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or34_receipt"],
        root=root,
        label="OR34 receipt",
    )
    output_directory.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    trace_bindings: dict[str, dict[str, str]] = {}
    for variant in contract["variants"]:
        result, trace = _run_variant(
            contract=contract, variant=variant, root=root
        )
        trace_path = output_directory / f"{variant['variant_id']}_trace.json"
        atomic_write_json(trace_path, trace)
        result["trace_path"] = trace_path.name
        result["trace_sha256"] = _sha256(trace_path)
        results.append(result)
        trace_bindings[variant["variant_id"]] = {
            "path": trace_path.name,
            "sha256": result["trace_sha256"],
        }

    baseline, challenger = results
    expected = contract["baseline_regression"]
    baseline_natural = baseline["natural_dynamics"]
    baseline_outcome = baseline_natural["outcome"]
    tolerance = float(expected["absolute_tolerance"])
    baseline_regression = {
        "first_selected_jaw_contact_sample": (
            baseline_natural["first_selected_jaw_contact_sample"]
            == expected["first_selected_jaw_contact_sample"]
        ),
        "first_motion_over_1mm_sample": (
            baseline_natural["first_motion_over_1mm_sample"]
            == expected["first_motion_over_1mm_sample"]
        ),
        "signed_progress_toward_d2_m": (
            abs(
                baseline_natural["signed_progress_toward_d2_m"]
                - expected["signed_progress_toward_d2_m"]
            )
            <= tolerance
        ),
        "final_upright_tilt_degrees": (
            abs(
                baseline_outcome["final_upright_tilt_degrees"]
                - expected["final_upright_tilt_degrees"]
            )
            <= tolerance
        ),
        "final_planar_center_error_m": (
            abs(
                baseline_outcome["final_planar_center_error_m"]
                - expected["final_planar_center_error_m"]
            )
            <= tolerance
        ),
    }
    _require(
        all(baseline_regression.values()),
        "OR34 baseline did not reproduce; OR35 rejected",
    )
    candidate_gates = _candidate_gate_report(contract, challenger)
    early_names = (
        "contact_timing",
        "no_early_motion",
        "support_loss_timing",
        "upright_at_carry_start",
    )
    terminal_names = tuple(
        name for name in candidate_gates if name not in early_names
    )
    early_pass = all(candidate_gates[name] for name in early_names)
    terminal_pass = all(candidate_gates[name] for name in terminal_names)
    full_pass = early_pass and terminal_pass
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else (
            "PARTIAL_CAUSAL_ADVANCEMENT_TERMINAL_FAIL"
            if early_pass
            else "TERMINAL_NEGATIVE_FORCE_ENVELOPE"
        )
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "predecessor_artifact_sha256": predecessor["artifact_sha256"],
        "baseline_regression": baseline_regression,
        "variants": results,
        "candidate_gate_report": candidate_gates,
        "early_causal_gates_pass": early_pass,
        "terminal_task_gates_pass": terminal_pass,
        "full_physics_driven_replay_pass": full_pass,
        "single_simulator_mechanism_changed": "sts3215_actuator_force_envelope",
        "candidate_selected_or_revised_from_task_outcome": False,
        "trace_bindings": trace_bindings,
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "raw_measured_state_changed": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "action_only_transfer": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_measured_state_load_path_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
