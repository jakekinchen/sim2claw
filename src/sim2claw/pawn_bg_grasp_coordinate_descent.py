"""Action-frozen coordinate descent over B--G simulator grasp mechanisms."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np

from .contact_prior import (
    SimulatorVariant,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .grasp import _pinch_point
from .interaction_events import extract_event_indices
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_demo_sim import BASELINE_PIECE_BY_FILE, _piece_bodies, _trace_row
from .pawn_bg_reward import load_reward_contract, score_episode
from .pawn_bg_servo_load_bias import load_servo_load_bias_contract
from .pawn_bg_timing_ablation import BODY_JOINT_NAMES, _episode_metrics, _mapped_episode, _pool, _strip_arrays
from .pawn_bg_workcell_fit import _workcell_square_center, build_workcell_model
from .state_trace import EpisodeStateTraceRecorder, build_scene_manifest
from .studio_catalog import media_url


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "optimization"
    / "pawn_bg_grasp_coordinate_descent_v1.json"
)
SCHEMA = "sim2claw.pawn_bg_grasp_coordinate_descent.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_grasp_coordinate_descent_receipt.v1"
GRIPPER_EVENT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_fixed_data_event_pipeline_v1.json"
)


class GraspCoordinateDescentError(RuntimeError):
    """The frozen coordinate campaign cannot run without widening authority."""


def _gripper_event_contract() -> dict[str, Any]:
    """Load only the already-frozen kinematic phase definition.

    The interaction-event artifact hashes bind a separate pipeline and should
    not make this simulator diagnostic depend on that pipeline's executable
    identity.  We reuse its immutable event definition and bind the source file
    hash in every returned metric instead.
    """

    try:
        contract = json.loads(GRIPPER_EVENT_CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraspCoordinateDescentError(
            f"cannot read gripper event contract: {error}"
        ) from error
    settings = contract.get("event_extraction", {})
    expected = {
        "joint_signal": "follower_actual_position_degrees",
        "gripper_joint_index": 5,
        "first_open_search_fraction": 0.55,
        "destination_open_search_start_fraction": 0.55,
        "transition_fraction_of_open_to_valley_range": 0.15,
        "flat_gripper_velocity_absolute_threshold_per_second": 0.5,
        "event_order": [
            "open_reference_peak",
            "closure_onset",
            "near_closed_crossing",
            "closed_valley",
            "release_onset",
            "destination_open_peak",
        ],
    }
    for key, value in expected.items():
        if settings.get(key) != value:
            raise GraspCoordinateDescentError(
                f"gripper event definition drifted: {key}"
            )
    if settings.get("contact_claim_allowed") is not False:
        raise GraspCoordinateDescentError("gripper events gained contact authority")
    return contract


def _event_aligned_gripper_metrics(
    *, mapped: dict[str, Any], simulated_states: np.ndarray
) -> dict[str, Any]:
    """Compare real and simulated gripper response in the carried-load window."""

    event_contract = _gripper_event_contract()
    events = extract_event_indices(mapped["samples"], event_contract)
    start = int(events["near_closed_crossing"])
    end = int(events["release_onset"])
    if not 0 <= start < end <= len(simulated_states):
        raise GraspCoordinateDescentError("gripper closed interval is invalid")
    simulated = np.asarray(simulated_states[start:end, -1], dtype=np.float64)
    measured = np.asarray(mapped["measured"][start:end, -1], dtype=np.float64)
    commanded = np.asarray(mapped["actions"][start:end, -1], dtype=np.float64)
    error = simulated - measured
    physical_rows = mapped["samples"][start:end]
    physical_velocity = np.asarray(
        [row["follower_actual_velocity_degrees_s"][5] for row in physical_rows],
        dtype=np.float64,
    )
    physical_command = np.asarray(
        [row["follower_command_degrees"][5] for row in physical_rows],
        dtype=np.float64,
    )
    physical_measured = np.asarray(
        [row["follower_actual_position_degrees"][5] for row in physical_rows],
        dtype=np.float64,
    )
    non_stale_rows = [
        row for row in physical_rows if not bool(row["current_telemetry_stale"])
    ]
    open_end = int(events["open_reference_peak"]) + 1
    open_start = max(
        0,
        open_end
        - int(event_contract["event_extraction"]["open_baseline_window_samples"]),
    )
    open_rows = [
        row
        for row in mapped["samples"][open_start:open_end]
        if not bool(row["current_telemetry_stale"])
    ]
    if not non_stale_rows or not open_rows:
        raise GraspCoordinateDescentError(
            "gripper load proxy requires non-stale cached current rows"
        )
    closed_current = np.asarray(
        [row["available_motor_current_raw"]["gripper"] for row in non_stale_rows],
        dtype=np.float64,
    )
    open_current = np.asarray(
        [row["available_motor_current_raw"]["gripper"] for row in open_rows],
        dtype=np.float64,
    )
    current_delta = float(np.median(closed_current) - np.median(open_current))
    physical_gap = float(np.median(np.abs(physical_command - physical_measured)))
    return {
        "event_definition_path": str(GRIPPER_EVENT_CONTRACT_PATH.resolve()),
        "event_definition_sha256": sha256_file(GRIPPER_EVENT_CONTRACT_PATH),
        "events": {key: int(value) for key, value in events.items()},
        "closed_interval_sample_range": [start, end],
        "closed_interval_sample_count": int(end - start),
        "simulated_minus_measured_bias_rad": float(np.mean(error)),
        "simulated_minus_measured_bias_degrees": float(np.degrees(np.mean(error))),
        "simulated_to_measured_rms_rad": float(
            np.sqrt(np.mean(np.square(error)))
        ),
        "simulated_to_measured_rms_degrees": float(
            np.degrees(np.sqrt(np.mean(np.square(error))))
        ),
        "simulated_median_rad": float(np.median(simulated)),
        "measured_median_rad": float(np.median(measured)),
        "commanded_median_rad": float(np.median(commanded)),
        "physical_measured_median_percent": float(np.median(physical_measured)),
        "physical_commanded_median_percent": float(np.median(physical_command)),
        "physical_median_absolute_command_measurement_gap_percent": physical_gap,
        "physical_flat_measured_velocity_fraction": float(
            np.mean(
                np.abs(physical_velocity)
                < float(
                    event_contract["event_extraction"][
                        "flat_gripper_velocity_absolute_threshold_per_second"
                    ]
                )
            )
        ),
        "physical_closed_minus_open_median_raw_current": current_delta,
        "physical_mechanically_loaded_closure_proxy_supported": bool(
            current_delta > 0.0 and physical_gap > 0.0
        ),
        "physical_contact_observed": False,
        "interpretation": (
            "event_aligned_load_proxy_and_response_fit_not_contact_ground_truth"
        ),
    }


def load_grasp_coordinate_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraspCoordinateDescentError(
            f"cannot read grasp-coordinate contract {path}: {error}"
        ) from error
    if contract.get("schema_version") != SCHEMA:
        raise GraspCoordinateDescentError("unexpected grasp-coordinate schema")
    if any(contract.get("authority", {}).values()):
        raise GraspCoordinateDescentError("grasp-coordinate authority widened")
    if not all(contract.get("action_invariance", {}).values()):
        raise GraspCoordinateDescentError("action invariance is not fail closed")
    sentinels = list(contract["episode_roles"]["adaptive_sentinel_recording_ids"])
    held = list(contract["episode_roles"]["campaign_held_evaluation_recording_ids"])
    if len(sentinels) != 3 or len(held) != 8 or set(sentinels) & set(held):
        raise GraspCoordinateDescentError("episode-role split must be disjoint 3/8")
    if len(set(sentinels + held)) != 11:
        raise GraspCoordinateDescentError("episode-role split must cover 11 unique episodes")
    initial = contract["initial_composite"]
    coordinate_names: list[str] = []
    for row in contract["coordinates"]:
        name = str(row["name"])
        values = [float(value) for value in row["values"]]
        if name in coordinate_names or name not in initial:
            raise GraspCoordinateDescentError(f"invalid coordinate: {name}")
        if len(values) < 3 or values != sorted(set(values)):
            raise GraspCoordinateDescentError(f"coordinate grid is invalid: {name}")
        if float(initial[name]) not in values:
            raise GraspCoordinateDescentError(
                f"coordinate grid omits initial value: {name}"
            )
        coordinate_names.append(name)
    acceptance = contract["acceptance"]
    if int(acceptance["bootstrap_replicates"]) < 1000:
        raise GraspCoordinateDescentError("bootstrap contract is too weak")
    if int(acceptance["minimum_all_episode_lift_and_transport"]) < 6:
        raise GraspCoordinateDescentError("consequence gate was weakened")
    return contract


def _custom_variant(
    *,
    parameters: dict[str, Any],
    contract_path: Path,
    contact_snapshot: Any,
) -> SimulatorVariant:
    solimp = (
        float(parameters.get("solimp_min", 0.95)),
        float(parameters.get("solimp_max", 0.98)),
        float(parameters.get("solimp_width_m", 0.0005)),
        float(parameters.get("solimp_midpoint", 0.5)),
        float(parameters.get("solimp_power", 2.0)),
    )
    if not (
        0.0 < solimp[0] <= solimp[1] < 1.0
        and solimp[2] > 0.0
        and 0.0 < solimp[3] < 1.0
        and solimp[4] >= 1.0
    ):
        raise GraspCoordinateDescentError("invalid bounded rubber contact solimp")
    base = load_simulator_variant(
        "rubber_tip_high", contract_snapshot=contact_snapshot
    )
    payload = copy.deepcopy(base.payload)
    payload.update(
        {
            "label": "B--G coordinate-descent simulator sensitivity",
            "rubber_tip_enabled": bool(parameters["rubber_tip_enabled"]),
            "evidence_class": "action_frozen_grasp_coordinate_sensitivity",
            "effective_wrap_thickness_m": float(parameters["tip_thickness_m"]),
            "effective_box_half_width_m": float(parameters["tip_half_width_m"]),
            "distal_coverage_length_m": float(parameters["tip_coverage_m"]),
            "wrap_segment_count": int(parameters.get("tip_segment_count", 1)),
            "wrap_segment_fill_fraction": float(
                parameters.get("tip_segment_fill_fraction", 1.0)
            ),
            "wrap_ridge_count": int(parameters.get("tip_ridge_count", 0)),
            "wrap_ridge_height_m": float(
                parameters.get("tip_ridge_height_m", 0.0)
            ),
            "wrap_ridge_fill_fraction": float(
                parameters.get("tip_ridge_fill_fraction", 0.5)
            ),
            "normal_compliance": {
                "enabled": bool(
                    parameters.get("rubber_tip_normal_compliance_enabled", False)
                ),
                "travel_m": float(
                    parameters.get("rubber_tip_compliance_travel_m", 0.002)
                ),
                "stiffness_n_per_m": float(
                    parameters.get("rubber_tip_compliance_stiffness_n_per_m", 1000.0)
                ),
                "damping_n_s_per_m": float(
                    parameters.get("rubber_tip_compliance_damping_n_s_per_m", 2.0)
                ),
                "modeled_mass_per_finger_kg": float(
                    parameters.get("rubber_tip_modeled_mass_per_finger_kg", 0.001)
                ),
            },
            "contact_friction": {
                "sliding_dimensionless": float(parameters["sliding_friction"]),
                "torsional_m": float(parameters["torsional_friction_m"]),
                "rolling_m": float(parameters["rolling_friction_m"]),
            },
            "contact_softness": {
                "solref_time_constant_s": float(
                    parameters["solref_time_constant_s"]
                ),
                "solref_damping_ratio": float(
                    parameters["solref_damping_ratio"]
                ),
                "solimp": list(solimp),
            },
            "parameter_provenance": (
                "bounded_adaptive_simulator_sensitivity_not_physical_measurement"
            ),
        }
    )
    identity = {
        "schema_version": SCHEMA,
        "parameters": parameters,
        "source_contact_prior_canonical_sha256": contact_snapshot.sha256,
    }
    collision_approximation = copy.deepcopy(base.collision_approximation)
    anchor_parameter_by_finger = {
        "fixed": "rubber_tip_fixed_anchor_geom_suffix",
        "moving": "rubber_tip_moving_anchor_geom_suffix",
    }
    for finger in collision_approximation["fingers"]:
        parameter_name = anchor_parameter_by_finger[str(finger["finger_id"])]
        if parameter_name not in parameters:
            continue
        suffix = str(parameters[parameter_name])
        required_prefix = f"{finger['finger_id']}_jaw_box"
        if not suffix.startswith(required_prefix):
            raise GraspCoordinateDescentError(
                f"{parameter_name} must name a {required_prefix} primitive"
            )
        finger["anchor_geom_suffix"] = suffix
    return SimulatorVariant(
        contract_path=contract_path.resolve(),
        contract_sha256=sha256_file(contract_path),
        task_id=base.task_id,
        task_contract_sha256=base.task_contract_sha256,
        accepted_checkpoint_sha256=base.accepted_checkpoint_sha256,
        variant_id=f"coordinate_{canonical_digest(identity)[:16]}",
        variant_sha256=canonical_digest(identity),
        payload=payload,
        collision_approximation=collision_approximation,
    )


def _apply_model_coordinates(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    binding: dict[str, Any],
    parameters: dict[str, Any],
) -> None:
    segment_count = int(parameters.get("tip_segment_count", 1))
    segment_fill = float(parameters.get("tip_segment_fill_fraction", 1.0))
    if not 1 <= segment_count <= 8:
        raise GraspCoordinateDescentError(
            "tip_segment_count exceeds diagnostic bounds"
        )
    if not 0.2 <= segment_fill <= 1.0:
        raise GraspCoordinateDescentError(
            "tip_segment_fill_fraction exceeds diagnostic bounds"
        )
    ridge_count = int(parameters.get("tip_ridge_count", 0))
    ridge_height = float(parameters.get("tip_ridge_height_m", 0.0))
    ridge_fill = float(parameters.get("tip_ridge_fill_fraction", 0.5))
    if not 0 <= ridge_count <= 8:
        raise GraspCoordinateDescentError(
            "tip_ridge_count exceeds diagnostic bounds"
        )
    if not 0.0 <= ridge_height <= 0.005:
        raise GraspCoordinateDescentError(
            "tip_ridge_height_m exceeds diagnostic bounds"
        )
    if ridge_count and ridge_height <= 0.0:
        raise GraspCoordinateDescentError(
            "tip ridges require a positive height"
        )
    if not 0.2 <= ridge_fill <= 1.0:
        raise GraspCoordinateDescentError(
            "tip_ridge_fill_fraction exceeds diagnostic bounds"
        )
    if ridge_count and segment_count != 1:
        raise GraspCoordinateDescentError(
            "tip ridges require one continuous base sleeve"
        )
    timestep_multiplier = float(
        parameters.get("simulation_timestep_multiplier", 1.0)
    )
    if not 0.1 <= timestep_multiplier <= 2.0:
        raise GraspCoordinateDescentError(
            "simulation_timestep_multiplier exceeds diagnostic bounds"
        )
    model.opt.timestep *= timestep_multiplier
    solver_iterations = int(
        round(float(parameters.get("solver_iterations", model.opt.iterations)))
    )
    if not 1 <= solver_iterations <= 200:
        raise GraspCoordinateDescentError(
            "solver_iterations exceeds diagnostic bounds"
        )
    model.opt.iterations = solver_iterations
    solver_name = str(parameters.get("contact_solver", "newton")).lower()
    solver_by_name = {
        "pgs": mujoco.mjtSolver.mjSOL_PGS,
        "cg": mujoco.mjtSolver.mjSOL_CG,
        "newton": mujoco.mjtSolver.mjSOL_NEWTON,
    }
    if solver_name not in solver_by_name:
        raise GraspCoordinateDescentError(
            "contact_solver must be one of pgs, cg, or newton"
        )
    model.opt.solver = solver_by_name[solver_name]
    cone_name = str(parameters.get("contact_cone", "elliptic")).lower()
    cone_by_name = {
        "pyramidal": mujoco.mjtCone.mjCONE_PYRAMIDAL,
        "elliptic": mujoco.mjtCone.mjCONE_ELLIPTIC,
    }
    if cone_name not in cone_by_name:
        raise GraspCoordinateDescentError(
            "contact_cone must be pyramidal or elliptic"
        )
    model.opt.cone = cone_by_name[cone_name]
    noslip_iterations = int(
        round(
            float(
                parameters.get(
                    "contact_noslip_iterations", model.opt.noslip_iterations
                )
            )
        )
    )
    if not 0 <= noslip_iterations <= 50:
        raise GraspCoordinateDescentError(
            "contact_noslip_iterations exceeds diagnostic bounds"
        )
    model.opt.noslip_iterations = noslip_iterations
    rubber_contact_condim = int(parameters.get("rubber_contact_condim", 6))
    if rubber_contact_condim not in (1, 3, 4, 6):
        raise GraspCoordinateDescentError(
            "rubber_contact_condim must be one of 1, 3, 4, or 6"
        )
    friction_impratio = float(
        parameters.get("friction_impratio", model.opt.impratio)
    )
    if not 0.1 <= friction_impratio <= 100.0:
        raise GraspCoordinateDescentError(
            "friction_impratio exceeds diagnostic bounds"
        )
    model.opt.impratio = friction_impratio

    for name in (
        "tip_fixed_half_width_multiplier",
        "tip_moving_half_width_multiplier",
        "tip_fixed_coverage_multiplier",
        "tip_moving_coverage_multiplier",
        "tip_fixed_thickness_multiplier",
        "tip_moving_thickness_multiplier",
    ):
        value = float(parameters.get(name, 1.0))
        maximum = 5.0 if "thickness" in name else 2.0
        if not 0.25 <= value <= maximum:
            raise GraspCoordinateDescentError(
                f"{name} exceeds diagnostic bounds"
            )
    for name in ("tip_fixed_width_offset_m", "tip_moving_width_offset_m"):
        value = float(parameters.get(name, 0.0))
        if not -0.02 <= value <= 0.02:
            raise GraspCoordinateDescentError(
                f"{name} exceeds diagnostic bounds"
            )
    for name in (
        "tip_coverage_offset_m",
        "tip_fixed_coverage_offset_m",
        "tip_moving_coverage_offset_m",
    ):
        value = float(parameters.get(name, 0.0))
        if not -0.05 <= value <= 0.05:
            raise GraspCoordinateDescentError(
                f"{name} exceeds diagnostic bounds"
            )

    capsule_shape = bool(parameters.get("rubber_tip_shape_capsule", False))
    ellipsoid_shape = bool(parameters.get("rubber_tip_shape_ellipsoid", False))
    if capsule_shape and ellipsoid_shape:
        raise GraspCoordinateDescentError(
            "rubber tip shape coordinates are mutually exclusive"
        )
    capsule_radius = float(parameters.get("tip_capsule_radius_m", 0.003))
    if not 0.001 <= capsule_radius <= 0.01:
        raise GraspCoordinateDescentError(
            "tip_capsule_radius_m exceeds diagnostic bounds"
        )
    capsule_half_length = max(
        0.0001,
        float(parameters["tip_coverage_m"]) / 2.0 - capsule_radius,
    )

    gripper_index = len(binding["actuator_ids"]) - 1
    arm_gain_multiplier = float(parameters.get("arm_servo_gain_multiplier", 1.0))
    arm_force_multiplier = float(parameters.get("arm_force_limit_multiplier", 1.0))
    arm_damping_multiplier = float(
        parameters.get("arm_joint_damping_multiplier", 1.0)
    )
    if not 0.5 <= arm_gain_multiplier <= 2.0:
        raise GraspCoordinateDescentError(
            "arm_servo_gain_multiplier exceeds diagnostic bounds"
        )
    if not 0.5 <= arm_force_multiplier <= 3.0:
        raise GraspCoordinateDescentError(
            "arm_force_limit_multiplier exceeds diagnostic bounds"
        )
    if not 0.5 <= arm_damping_multiplier <= 2.0:
        raise GraspCoordinateDescentError(
            "arm_joint_damping_multiplier exceeds diagnostic bounds"
        )
    for arm_index in range(gripper_index):
        arm_actuator_id = int(binding["actuator_ids"][arm_index])
        arm_joint_id = int(binding["joint_ids"][arm_index])
        arm_dof_id = int(model.jnt_dofadr[arm_joint_id])
        model.actuator_gainprm[arm_actuator_id, 0] *= arm_gain_multiplier
        model.actuator_biasprm[arm_actuator_id, 1] *= arm_gain_multiplier
        model.actuator_biasprm[arm_actuator_id, 2] *= arm_gain_multiplier
        model.actuator_forcerange[arm_actuator_id] *= arm_force_multiplier
        model.dof_damping[arm_dof_id] *= arm_damping_multiplier
    actuator_id = int(binding["actuator_ids"][gripper_index])
    joint_id = int(binding["joint_ids"][gripper_index])
    dof_id = int(model.jnt_dofadr[joint_id])
    gain_multiplier = float(parameters["gripper_servo_gain_multiplier"])
    model.actuator_gainprm[actuator_id, 0] *= gain_multiplier
    model.actuator_biasprm[actuator_id, 1] *= gain_multiplier
    model.actuator_biasprm[actuator_id, 2] *= gain_multiplier
    actuator_zero_offset_degrees = float(
        parameters.get("gripper_actuator_zero_offset_degrees", 0.0)
    )
    if not -15.0 <= actuator_zero_offset_degrees <= 15.0:
        raise GraspCoordinateDescentError(
            "gripper_actuator_zero_offset_degrees exceeds diagnostic bounds"
        )
    model.actuator_biasprm[actuator_id, 0] += (
        model.actuator_gainprm[actuator_id, 0]
        * math.radians(actuator_zero_offset_degrees)
    )
    model.actuator_forcerange[actuator_id] *= float(
        parameters["gripper_force_limit_multiplier"]
    )
    model.dof_damping[dof_id] *= float(
        parameters["gripper_joint_damping_multiplier"]
    )
    model.dof_frictionloss[dof_id] *= float(
        parameters["gripper_joint_frictionloss_multiplier"]
    )

    kinematic_zero_degrees = float(
        parameters.get("gripper_kinematic_zero_offset_degrees", 0.0)
    )
    if not -15.0 <= kinematic_zero_degrees <= 15.0:
        raise GraspCoordinateDescentError(
            "gripper_kinematic_zero_offset_degrees exceeds diagnostic bounds"
        )
    if kinematic_zero_degrees:
        moving_jaw_body = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            "left_moving_jaw_so101_v1",
        )
        if moving_jaw_body < 0:
            raise GraspCoordinateDescentError("moving jaw body is missing")
        base = np.asarray(model.body_quat[moving_jaw_body], dtype=np.float64)
        half_angle = math.radians(kinematic_zero_degrees) / 2.0
        local_z_rotation = np.asarray(
            [math.cos(half_angle), 0.0, 0.0, math.sin(half_angle)],
            dtype=np.float64,
        )
        w1, x1, y1, z1 = base
        w2, x2, y2, z2 = local_z_rotation
        rotated = np.asarray(
            [
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ],
            dtype=np.float64,
        )
        model.body_quat[moving_jaw_body] = rotated / np.linalg.norm(rotated)

    for geom_id in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
        body_id = int(model.geom_bodyid[geom_id])
        body_name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        )
        geom_is_mesh = int(model.geom_type[geom_id]) == int(mujoco.mjtGeom.mjGEOM_MESH)
        collision_enabled = bool(
            model.geom_contype[geom_id] or model.geom_conaffinity[geom_id]
        )
        left_specific_key = (
            f"{name.removeprefix('left_')}_collision_enabled"
            if name.startswith("left_")
            else None
        )
        if (
            left_specific_key is not None
            and left_specific_key in parameters
            and collision_enabled
            and not bool(parameters[left_specific_key])
        ):
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        elif (
            body_name.endswith("moving_jaw_so101_v1")
            and geom_is_mesh
            and collision_enabled
            and not bool(parameters.get("moving_jaw_mesh_collision_enabled", True))
        ):
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        elif (
            body_name.endswith("moving_jaw_so101_v1")
            and name.startswith("left_moving_jaw_")
            and collision_enabled
            and not bool(parameters.get("moving_jaw_primitive_collision_enabled", True))
        ):
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        elif (
            body_name.endswith("gripper")
            and geom_is_mesh
            and collision_enabled
            and not bool(parameters.get("fixed_jaw_mesh_collision_enabled", True))
        ):
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        elif (
            body_name.endswith("gripper")
            and name.startswith("left_fixed_jaw_")
            and collision_enabled
            and not bool(parameters.get("fixed_jaw_primitive_collision_enabled", True))
        ):
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        if "_rubber_tip_fixed_" in name:
            model.geom_condim[geom_id] = rubber_contact_condim
            if capsule_shape:
                model.geom_type[geom_id] = int(mujoco.mjtGeom.mjGEOM_CAPSULE)
                model.geom_quat[geom_id] = np.asarray(
                    [1.0, 0.0, 0.0, 0.0], dtype=np.float64
                )
                model.geom_size[geom_id, 0] = capsule_radius
                model.geom_size[geom_id, 1] = capsule_half_length
            elif ellipsoid_shape:
                model.geom_type[geom_id] = int(mujoco.mjtGeom.mjGEOM_ELLIPSOID)
            model.geom_pos[geom_id, 2] += float(
                parameters.get("tip_coverage_offset_m", 0.0)
            ) + float(
                parameters.get("tip_fixed_coverage_offset_m", 0.0)
            )
            model.geom_pos[geom_id, 0] += float(
                parameters.get("tip_fixed_normal_offset_m", 0.0)
            )
            model.geom_pos[geom_id, 1] += float(
                parameters.get("tip_fixed_width_offset_m", 0.0)
            )
            model.geom_size[geom_id, 0] *= float(
                parameters.get("tip_fixed_thickness_multiplier", 1.0)
            )
            model.geom_size[geom_id, 1] *= float(
                parameters.get("tip_fixed_half_width_multiplier", 1.0)
            )
            model.geom_size[geom_id, 2] *= float(
                parameters.get("tip_fixed_coverage_multiplier", 1.0)
            )
        elif "_rubber_tip_moving_" in name:
            model.geom_condim[geom_id] = rubber_contact_condim
            if capsule_shape:
                model.geom_type[geom_id] = int(mujoco.mjtGeom.mjGEOM_CAPSULE)
                root_half = math.sqrt(0.5)
                model.geom_quat[geom_id] = np.asarray(
                    [root_half, root_half, 0.0, 0.0], dtype=np.float64
                )
                model.geom_size[geom_id, 0] = capsule_radius
                model.geom_size[geom_id, 1] = capsule_half_length
            elif ellipsoid_shape:
                model.geom_type[geom_id] = int(mujoco.mjtGeom.mjGEOM_ELLIPSOID)
            model.geom_pos[geom_id, 1] += float(
                parameters.get("tip_coverage_offset_m", 0.0)
            ) + float(
                parameters.get("tip_moving_coverage_offset_m", 0.0)
            )
            model.geom_pos[geom_id, 0] += float(
                parameters.get("tip_moving_normal_offset_m", 0.0)
            )
            model.geom_pos[geom_id, 2] += float(
                parameters.get("tip_moving_width_offset_m", 0.0)
            )
            model.geom_size[geom_id, 0] *= float(
                parameters.get("tip_moving_thickness_multiplier", 1.0)
            )
            model.geom_size[geom_id, 2] *= float(
                parameters.get("tip_moving_half_width_multiplier", 1.0)
            )
            model.geom_size[geom_id, 1] *= float(
                parameters.get("tip_moving_coverage_multiplier", 1.0)
            )

    pawn_mass_multiplier = float(parameters["pawn_mass_multiplier"])
    pawn_friction_multiplier = float(parameters["pawn_friction_multiplier"])
    pawn_collision_scale = float(parameters.get("pawn_collision_scale", 1.0))
    if not 0.5 <= pawn_collision_scale <= 1.5:
        raise GraspCoordinateDescentError(
            "pawn_collision_scale must remain within the bounded diagnostic range"
        )
    pawn_radial_collision_scale = float(
        parameters.get("pawn_radial_collision_scale", 1.0)
    )
    if not 0.5 <= pawn_radial_collision_scale <= 1.25:
        raise GraspCoordinateDescentError(
            "pawn_radial_collision_scale exceeds diagnostic bounds"
        )
    for body_id in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        if not name.startswith(("brown_pawn_", "tan_pawn_")):
            continue
        model.body_mass[body_id] *= pawn_mass_multiplier
        model.body_inertia[body_id] *= pawn_mass_multiplier
        for geom_id in range(model.ngeom):
            if int(model.geom_bodyid[geom_id]) == body_id:
                model.geom_friction[geom_id] *= pawn_friction_multiplier
                model.geom_size[geom_id] *= pawn_collision_scale
                geom_type = int(model.geom_type[geom_id])
                if (
                    pawn_radial_collision_scale != 1.0
                    and geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE)
                ):
                    radius = float(model.geom_size[geom_id, 0])
                    model.geom_type[geom_id] = int(
                        mujoco.mjtGeom.mjGEOM_ELLIPSOID
                    )
                    model.geom_size[geom_id] = np.asarray(
                        [
                            radius * pawn_radial_collision_scale,
                            radius * pawn_radial_collision_scale,
                            radius,
                        ],
                        dtype=np.float64,
                    )
                elif pawn_radial_collision_scale != 1.0 and geom_type in (
                    int(mujoco.mjtGeom.mjGEOM_CYLINDER),
                    int(mujoco.mjtGeom.mjGEOM_ELLIPSOID),
                ):
                    model.geom_size[geom_id, 0] *= pawn_radial_collision_scale
                    if geom_type == int(mujoco.mjtGeom.mjGEOM_ELLIPSOID):
                        model.geom_size[geom_id, 1] *= pawn_radial_collision_scale
    mujoco.mj_setConst(model, data)


def _select_load_bearing_contact_pair(
    fixed: list[dict[str, Any]], moving: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Choose one deterministic opposing pair without changing evaluation.

    The weakest side bounds a pinch, so minimum normal force is the primary
    load-bearing score. Opposition and span break physically relevant ties;
    stable geom/contact ids make the final tie-break deterministic.
    """

    if not fixed or not moving:
        return None
    ranked: list[tuple[tuple[float, ...], dict[str, Any]]] = []
    for fixed_contact in fixed:
        for moving_contact in moving:
            opposition = float(
                -np.dot(fixed_contact["normal"], moving_contact["normal"])
            )
            span = float(
                np.linalg.norm(
                    fixed_contact["position_m"] - moving_contact["position_m"]
                )
            )
            minimum_normal_force = min(
                float(fixed_contact["normal_force_n"]),
                float(moving_contact["normal_force_n"]),
            )
            total_normal_force = float(fixed_contact["normal_force_n"]) + float(
                moving_contact["normal_force_n"]
            )
            pair = {
                "fixed": fixed_contact,
                "moving": moving_contact,
                "minimum_normal_force_n": minimum_normal_force,
                "total_normal_force_n": total_normal_force,
                "opposing_normal_score": opposition,
                "contact_span_m": span,
            }
            key = (
                minimum_normal_force,
                opposition,
                span,
                total_normal_force,
                -float(fixed_contact["jaw_geom_id"]),
                -float(moving_contact["jaw_geom_id"]),
                -float(fixed_contact["contact_index"]),
                -float(moving_contact["contact_index"]),
            )
            ranked.append((key, pair))
    return max(ranked, key=lambda item: item[0])[1]


def _contact_witness_json(contact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (value.astype(float).tolist() if isinstance(value, np.ndarray) else value)
        for key, value in contact.items()
    }


def _pawn_surface_label(model: mujoco.MjModel, geom_id: int) -> str:
    """Return a stable semantic label for the current detailed pawn surfaces."""

    geom_type = mujoco.mjtGeom(int(model.geom_type[geom_id]))
    local_z = float(model.geom_pos[geom_id, 2])
    if geom_type == mujoco.mjtGeom.mjGEOM_SPHERE:
        return "head_sphere"
    if geom_type == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
        return "upper_collar_ellipsoid" if local_z >= 0.025 else "lower_body_ellipsoid"
    if geom_type == mujoco.mjtGeom.mjGEOM_CYLINDER:
        return f"body_ring_z_{local_z:.4f}_m"
    return f"unclassified_{geom_type.name.lower()}_z_{local_z:.4f}_m"


def _jaw_contact_geometry(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    selected_body: int,
    fixed_jaw_bodies: set[int],
    moving_jaw_bodies: set[int],
) -> dict[str, Any]:
    contacts: dict[str, list[dict[str, Any]]] = {"fixed": [], "moving": []}
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        body1 = int(model.geom_bodyid[contact.geom1])
        body2 = int(model.geom_bodyid[contact.geom2])
        if selected_body not in (body1, body2):
            continue
        jaw_body = body2 if body1 == selected_body else body1
        side = (
            "fixed"
            if jaw_body in fixed_jaw_bodies
            else "moving" if jaw_body in moving_jaw_bodies else None
        )
        if side is None:
            continue
        normal = np.asarray(contact.frame[:3], dtype=np.float64)
        # MuJoCo's contact normal points from geom1 toward geom2. Orient every
        # stored normal from the jaw toward the selected pawn.
        if jaw_body == body2:
            normal = -normal
        norm = float(np.linalg.norm(normal))
        if norm > 0.0:
            normal = normal / norm
        constraint_force = np.zeros(6, dtype=np.float64)
        mujoco.mj_contactForce(model, data, contact_index, constraint_force)
        jaw_geom = int(contact.geom2 if jaw_body == body2 else contact.geom1)
        pawn_geom = int(contact.geom1 if jaw_body == body2 else contact.geom2)
        position = np.asarray(contact.pos, dtype=np.float64).copy()
        jaw_rotation = np.asarray(data.geom_xmat[jaw_geom], dtype=np.float64).reshape(
            3, 3
        )
        pawn_rotation = np.asarray(
            data.geom_xmat[pawn_geom], dtype=np.float64
        ).reshape(3, 3)
        contacts[side].append(
            {
                "contact_index": int(contact_index),
                "position_m": position,
                "normal": normal.copy(),
                "jaw_body_id": int(jaw_body),
                "jaw_body_name": (
                    mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, jaw_body)
                    or f"body_{jaw_body}"
                ),
                "jaw_geom_id": jaw_geom,
                "jaw_geom_name": (
                    mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, jaw_geom)
                    or f"geom_{jaw_geom}"
                ),
                "jaw_geom_type": mujoco.mjtGeom(
                    int(model.geom_type[jaw_geom])
                ).name,
                "jaw_geom_local_position_m": np.asarray(
                    model.geom_pos[jaw_geom], dtype=np.float64
                ).copy(),
                "jaw_geom_size_m": np.asarray(
                    model.geom_size[jaw_geom], dtype=np.float64
                ).copy(),
                "contact_position_in_jaw_geom_frame_m": (
                    jaw_rotation.T
                    @ (position - np.asarray(data.geom_xpos[jaw_geom]))
                ),
                "pawn_geom_id": pawn_geom,
                "pawn_geom_name": (
                    mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, pawn_geom)
                    or f"geom_{pawn_geom}"
                ),
                "pawn_geom_type": mujoco.mjtGeom(
                    int(model.geom_type[pawn_geom])
                ).name,
                "pawn_surface_label": _pawn_surface_label(model, pawn_geom),
                "pawn_geom_local_position_m": np.asarray(
                    model.geom_pos[pawn_geom], dtype=np.float64
                ).copy(),
                "pawn_geom_size_m": np.asarray(
                    model.geom_size[pawn_geom], dtype=np.float64
                ).copy(),
                "contact_position_in_pawn_geom_frame_m": (
                    pawn_rotation.T
                    @ (position - np.asarray(data.geom_xpos[pawn_geom]))
                ),
                # These are MuJoCo constraint-space magnitudes. They diagnose
                # the simulated mechanism; they are not calibrated force-sensor
                # measurements and cannot establish physical contact force.
                "normal_force_n": max(0.0, float(constraint_force[0])),
                "tangential_force_n": float(
                    np.linalg.norm(constraint_force[1:3])
                ),
            }
        )
    fixed = contacts["fixed"]
    moving = contacts["moving"]
    bilateral = bool(fixed and moving)
    maximum_span = 0.0
    maximum_opposition = -1.0
    if bilateral:
        for fixed_contact in fixed:
            for moving_contact in moving:
                maximum_span = max(
                    maximum_span,
                    float(
                        np.linalg.norm(
                            fixed_contact["position_m"]
                            - moving_contact["position_m"]
                        )
                    ),
                )
                maximum_opposition = max(
                    maximum_opposition,
                    float(
                        -np.dot(
                            fixed_contact["normal"], moving_contact["normal"]
                        )
                    ),
                )
    fixed_normal_force = float(
        sum(contact["normal_force_n"] for contact in fixed)
    )
    moving_normal_force = float(
        sum(contact["normal_force_n"] for contact in moving)
    )
    fixed_tangential_force = float(
        sum(contact["tangential_force_n"] for contact in fixed)
    )
    moving_tangential_force = float(
        sum(contact["tangential_force_n"] for contact in moving)
    )
    load_bearing_pair = _select_load_bearing_contact_pair(fixed, moving)
    return {
        "fixed_contact": bool(fixed),
        "moving_contact": bool(moving),
        "bilateral_contact": bilateral,
        "fixed_contact_count": len(fixed),
        "moving_contact_count": len(moving),
        "maximum_contact_span_m": maximum_span,
        "maximum_opposing_normal_score": maximum_opposition,
        "fixed_normal_force_n": fixed_normal_force,
        "moving_normal_force_n": moving_normal_force,
        "total_normal_force_n": fixed_normal_force + moving_normal_force,
        "fixed_tangential_force_n": fixed_tangential_force,
        "moving_tangential_force_n": moving_tangential_force,
        "total_tangential_force_n": (
            fixed_tangential_force + moving_tangential_force
        ),
        "mean_contact_position_m": (
            np.mean(
                [contact["position_m"] for contact in fixed + moving], axis=0
            ).tolist()
            if bilateral
            else None
        ),
        "contact_witnesses": {
            "fixed": [_contact_witness_json(contact) for contact in fixed],
            "moving": [_contact_witness_json(contact) for contact in moving],
        },
        "load_bearing_pair": (
            None
            if load_bearing_pair is None
            else {
                "fixed": _contact_witness_json(load_bearing_pair["fixed"]),
                "moving": _contact_witness_json(load_bearing_pair["moving"]),
                "minimum_normal_force_n": float(
                    load_bearing_pair["minimum_normal_force_n"]
                ),
                "total_normal_force_n": float(
                    load_bearing_pair["total_normal_force_n"]
                ),
                "opposing_normal_score": float(
                    load_bearing_pair["opposing_normal_score"]
                ),
                "contact_span_m": float(load_bearing_pair["contact_span_m"]),
            }
        ),
    }


def _wrong_piece_robot_contacts(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    selected_body: int,
    piece_bodies: dict[str, int],
    robot_body_ids: set[int],
) -> list[dict[str, Any]]:
    """Return identity-rich wrong-piece contacts for mechanism diagnosis.

    This is deliberately separate from the frozen evaluator.  It explains an
    evaluator failure without changing the evaluator's contact predicate.
    """

    piece_names = {body_id: name for name, body_id in piece_bodies.items()}
    observations: list[dict[str, Any]] = []
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        body1 = int(model.geom_bodyid[geom1])
        body2 = int(model.geom_bodyid[geom2])
        for piece_body, robot_body, piece_geom, robot_geom in (
            (body1, body2, geom1, geom2),
            (body2, body1, geom2, geom1),
        ):
            if (
                piece_body == selected_body
                or piece_body not in piece_names
                or robot_body not in robot_body_ids
            ):
                continue
            observations.append(
                {
                    "piece_name": piece_names[piece_body],
                    "piece_body_id": piece_body,
                    "piece_geom_name": (
                        mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_GEOM, piece_geom
                        )
                        or f"geom_{piece_geom}"
                    ),
                    "piece_geom_id": piece_geom,
                    "piece_geom_type": mujoco.mjtGeom(
                        int(model.geom_type[piece_geom])
                    ).name,
                    "robot_body_name": (
                        mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_BODY, robot_body
                        )
                        or f"body_{robot_body}"
                    ),
                    "robot_body_id": robot_body,
                    "robot_geom_name": (
                        mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_GEOM, robot_geom
                        )
                        or f"geom_{robot_geom}"
                    ),
                    "robot_geom_id": robot_geom,
                    "robot_geom_type": mujoco.mjtGeom(
                        int(model.geom_type[robot_geom])
                    ).name,
                    "robot_geom_local_position_m": np.asarray(
                        model.geom_pos[robot_geom], dtype=np.float64
                    ).tolist(),
                    "robot_geom_size_m": np.asarray(
                        model.geom_size[robot_geom], dtype=np.float64
                    ).tolist(),
                    "robot_geom_mesh_id": int(model.geom_dataid[robot_geom]),
                    "robot_geom_contype": int(model.geom_contype[robot_geom]),
                    "robot_geom_conaffinity": int(
                        model.geom_conaffinity[robot_geom]
                    ),
                    "contact_position_xyz_m": np.asarray(
                        contact.pos, dtype=np.float64
                    ).tolist(),
                }
            )
    return observations


def _run_length_update(active: bool, current: int, maximum: int) -> tuple[int, int]:
    current = current + 1 if active else 0
    return current, max(maximum, current)


def _summarize_retention_trace(
    trace: list[dict[str, Any]], *, lift_threshold_m: float
) -> dict[str, Any]:
    """Localize contact loss and drop ordering without changing evaluation."""

    lift_index = next(
        (
            index
            for index, row in enumerate(trace)
            if bool(row["qualified_bilateral_contact"])
            and float(row["piece_rise_m"]) >= lift_threshold_m
        ),
        None,
    )

    def event_after(field: str, *, expected: bool) -> int | None:
        if lift_index is None:
            return None
        return next(
            (
                index
                for index in range(lift_index + 1, len(trace))
                if bool(trace[index][field]) is expected
            ),
            None,
        )

    qualified_loss_index = event_after(
        "qualified_bilateral_contact", expected=False
    )
    bilateral_loss_index = event_after("bilateral_contact", expected=False)
    first_drop_after_lift_index = (
        None
        if lift_index is None
        else next(
            (
                index
                for index in range(lift_index + 1, len(trace))
                if float(trace[index]["piece_rise_m"]) < lift_threshold_m
            ),
            None,
        )
    )

    def first_drop_at_or_after(index: int | None) -> int | None:
        if index is None:
            return None
        return next(
            (
                candidate
                for candidate in range(index, len(trace))
                if float(trace[candidate]["piece_rise_m"]) < lift_threshold_m
            ),
            None,
        )

    drop_after_qualified_loss_index = first_drop_at_or_after(
        qualified_loss_index
    )
    drop_after_bilateral_loss_index = first_drop_at_or_after(
        bilateral_loss_index
    )

    def snapshot(index: int | None) -> dict[str, Any] | None:
        if index is None:
            return None
        return copy.deepcopy(trace[index])

    def before(index: int | None) -> dict[str, Any] | None:
        if index is None or index <= 0:
            return None
        return copy.deepcopy(trace[index - 1])

    def elapsed(start: int | None, end: int | None) -> float | None:
        if start is None or end is None:
            return None
        return float(
            trace[end]["episode_time_s"] - trace[start]["episode_time_s"]
        )

    return {
        "lift_threshold_m": float(lift_threshold_m),
        "first_qualified_lift": snapshot(lift_index),
        "pre_qualified_contact_loss": before(qualified_loss_index),
        "first_qualified_contact_loss_after_lift": snapshot(
            qualified_loss_index
        ),
        "pre_bilateral_contact_loss": before(bilateral_loss_index),
        "first_bilateral_contact_loss_after_lift": snapshot(
            bilateral_loss_index
        ),
        "first_drop_below_lift_threshold_after_lift": snapshot(
            first_drop_after_lift_index
        ),
        "first_drop_below_lift_threshold_after_qualified_loss": snapshot(
            drop_after_qualified_loss_index
        ),
        "first_drop_below_lift_threshold_after_bilateral_loss": snapshot(
            drop_after_bilateral_loss_index
        ),
        "qualified_lift_to_qualified_loss_seconds": elapsed(
            lift_index, qualified_loss_index
        ),
        "qualified_lift_to_bilateral_loss_seconds": elapsed(
            lift_index, bilateral_loss_index
        ),
        "qualified_loss_to_drop_seconds": elapsed(
            qualified_loss_index, drop_after_qualified_loss_index
        ),
        "bilateral_loss_to_drop_seconds": elapsed(
            bilateral_loss_index, drop_after_bilateral_loss_index
        ),
    }


def _run_episode(
    *,
    mapped: dict[str, Any],
    workcell: Any,
    experiment: dict[str, Any],
    servo_contract: dict[str, Any],
    reward_contract: dict[str, Any],
    contact_snapshot: Any,
    parameters: dict[str, Any],
    contract_path: Path,
    state_trace_output_directory: Path | None = None,
    retention_trace_enabled: bool = False,
) -> dict[str, Any]:
    effective_workcell = replace(
        workcell,
        board_center_in_table_frame_xy_m=(
            float(workcell.board_center_in_table_frame_xy_m[0])
            + float(parameters.get("board_center_offset_x_m", 0.0)),
            float(workcell.board_center_in_table_frame_xy_m[1])
            + float(parameters.get("board_center_offset_y_m", 0.0)),
        ),
        board_yaw_relative_to_table_degrees=(
            float(workcell.board_yaw_relative_to_table_degrees)
            + float(parameters.get("board_yaw_offset_degrees", 0.0))
        ),
        board_side_m=(
            workcell.board_side_m
            if "board_side_multiplier" not in parameters
            else (
                (
                    float(workcell.board_side_m)
                    if workcell.board_side_m is not None
                    else 0.3556
                )
                * float(parameters["board_side_multiplier"])
            )
        ),
        base_z_offset_m=(
            float(workcell.base_z_offset_m)
            + float(parameters.get("base_z_offset_m", 0.0))
        ),
        base_roll_offset_degrees=(
            float(workcell.base_roll_offset_degrees)
            + float(parameters.get("base_roll_offset_degrees", 0.0))
        ),
        base_pitch_offset_degrees=(
            float(workcell.base_pitch_offset_degrees)
            + float(parameters.get("base_pitch_offset_degrees", 0.0))
        ),
    )
    variant = _custom_variant(
        parameters=parameters,
        contract_path=contract_path,
        contact_snapshot=contact_snapshot,
    )
    binding = build_workcell_model(effective_workcell, contact_variant=variant)
    model, data = binding["model"], binding["data"]
    _apply_model_coordinates(
        model, data, binding=binding, parameters=parameters
    )
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    dof_addresses = [
        int(model.jnt_dofadr[joint_id]) for joint_id in binding["joint_ids"]
    ]
    piece_bodies = _piece_bodies(model)
    recording_id = str(mapped["episode"]["recording_id"])
    reset_offsets_by_episode = parameters.get(
        "episode_piece_reset_offsets_m", {}
    )
    if not isinstance(reset_offsets_by_episode, dict):
        raise GraspCoordinateDescentError(
            "episode_piece_reset_offsets_m must be an object"
        )
    raw_reset_offsets = reset_offsets_by_episode.get(recording_id, {})
    if not isinstance(raw_reset_offsets, dict):
        raise GraspCoordinateDescentError(
            "episode_piece_reset_offsets_m episode value must be an object"
        )
    episode_reset_offsets: dict[str, tuple[float, float]] = {}
    for file_name, raw_offset in raw_reset_offsets.items():
        if file_name not in BASELINE_PIECE_BY_FILE:
            raise GraspCoordinateDescentError(
                f"unknown pawn file in reset offsets: {file_name}"
            )
        if not isinstance(raw_offset, (list, tuple)) or len(raw_offset) != 2:
            raise GraspCoordinateDescentError(
                f"reset offset for {file_name} must be [x_m, y_m]"
            )
        offset = (float(raw_offset[0]), float(raw_offset[1]))
        if max(abs(offset[0]), abs(offset[1])) > 0.015:
            raise GraspCoordinateDescentError(
                f"reset offset for {file_name} exceeds 15 mm diagnostic bound"
            )
        episode_reset_offsets[str(file_name)] = offset
        piece_name = BASELINE_PIECE_BY_FILE[str(file_name)]
        piece_joint = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, f"{piece_name}_free"
        )
        if piece_joint < 0:
            raise GraspCoordinateDescentError(
                f"reset-offset pawn joint is missing: {piece_name}_free"
            )
        piece_qpos = int(model.jnt_qposadr[piece_joint])
        data.qpos[piece_qpos] += offset[0]
        data.qpos[piece_qpos + 1] += offset[1]
    source, destination = str(mapped["source"]), str(mapped["destination"])
    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise GraspCoordinateDescentError("selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=effective_workcell.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=effective_workcell.board_yaw_relative_to_table_degrees,
            board_side_m=effective_workcell.board_side_m,
        ),
        dtype=np.float64,
    )
    source_xyz[0] += float(parameters.get("pawn_source_offset_x_m", 0.0))
    source_xyz[1] += float(parameters.get("pawn_source_offset_y_m", 0.0))
    if source[0] in episode_reset_offsets:
        source_xyz[0] += episode_reset_offsets[source[0]][0]
        source_xyz[1] += episode_reset_offsets[source[0]][1]
    target_xyz = np.asarray(
        _workcell_square_center(
            destination,
            board_center_in_table_frame_xy_m=effective_workcell.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=effective_workcell.board_yaw_relative_to_table_degrees,
            board_side_m=effective_workcell.board_side_m,
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)

    state_recorder: EpisodeStateTraceRecorder | None = None
    state_trace_path: Path | None = None
    scene_manifest_path: Path | None = None
    if state_trace_output_directory is not None:
        state_trace_output_directory.mkdir(parents=True, exist_ok=True)
        scene_manifest_path = state_trace_output_directory / "scene_manifest.json"
        state_trace_path = state_trace_output_directory / "state_trace.json"
        atomic_write_json(scene_manifest_path, build_scene_manifest(model=model))
        state_recorder = EpisodeStateTraceRecorder(
            model,
            fps=30,
            proof_class="retained_action_frozen_simulation_replay",
            manifest_url=media_url(scene_manifest_path),
        )
        state_recorder.capture(data, phase="initial", force=True)

    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_height = float(data.xpos[selected_body][2])
    initial_target_distance = float(
        np.linalg.norm(np.asarray(data.xpos[selected_body])[:2] - target_xyz[:2])
    )
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        ).startswith("left_")
    }
    fixed_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1"
    )
    fixed_jaw_body = int(model.geom_bodyid[fixed_geom])
    moving_jaw_body = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        "left_moving_jaw_so101_v1",
    )
    fixed_jaw_bodies = {fixed_jaw_body}
    moving_jaw_bodies = {moving_jaw_body}
    for body_id in range(model.nbody):
        body_name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        )
        if "_rubber_tip_fixed_" in body_name:
            fixed_jaw_bodies.add(body_id)
        elif "_rubber_tip_moving_" in body_name:
            moving_jaw_bodies.add(body_id)
    jaw_body_ids = fixed_jaw_bodies | moving_jaw_bodies
    compliant_pad_qpos_addresses: dict[str, int] = {}
    for joint_id in range(model.njnt):
        joint_name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id) or ""
        )
        if "_rubber_tip_" in joint_name and joint_name.endswith("_normal_joint"):
            compliant_pad_qpos_addresses[joint_name] = int(
                model.jnt_qposadr[joint_id]
            )
    piece_body_ids = set(piece_bodies.values())
    fixed_tip_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_sph_tip2"
    )
    fixed_tip_body = int(model.geom_bodyid[fixed_tip_geom])
    pinch_local = binding["pinch_offset_local"]

    def trace_row() -> dict[str, Any]:
        return _trace_row(
            model,
            data,
            selected_body=selected_body,
            selected_dof=selected_dof,
            piece_bodies=piece_bodies,
            initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids,
            jaw_body_ids=jaw_body_ids,
        )

    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm.copy()
    nominal_force_range = model.actuator_forcerange.copy()
    response = experiment["source"]["arm_response"]
    lift_deadband = float(
        parameters.get(
            "shoulder_lift_deadband_degrees",
            response["shoulder_lift_deadband_degrees"],
        )
    )
    elbow_deadband = float(
        parameters.get(
            "elbow_flex_deadband_degrees",
            response["elbow_flex_deadband_degrees"],
        )
    )
    elbow_load_bias = float(
        parameters.get(
            "elbow_load_bias_coefficient",
            response["elbow_load_bias_coefficient"],
        )
    )
    load_hold_enabled = bool(parameters.get("gripper_load_hold_enabled", False))
    load_hold_dwell_seconds = float(
        parameters.get("gripper_load_hold_dwell_seconds", 0.02)
    )
    load_hold_release_margin_degrees = float(
        parameters.get("gripper_load_hold_release_margin_degrees", 2.0)
    )
    raw_load_hold_target = parameters.get("gripper_load_hold_latch_target_rad")
    load_hold_latch_target_rad = (
        None if raw_load_hold_target is None else float(raw_load_hold_target)
    )
    if not 0.0 <= load_hold_dwell_seconds <= 0.25:
        raise GraspCoordinateDescentError(
            "gripper_load_hold_dwell_seconds exceeds diagnostic bounds"
        )
    if not 0.0 <= load_hold_release_margin_degrees <= 15.0:
        raise GraspCoordinateDescentError(
            "gripper_load_hold_release_margin_degrees exceeds diagnostic bounds"
        )
    if load_hold_latch_target_rad is not None and not (
        -0.174533 <= load_hold_latch_target_rad <= 1.7453292
    ):
        raise GraspCoordinateDescentError(
            "gripper_load_hold_latch_target_rad exceeds gripper joint range"
        )
    load_hold_dwell_steps = max(
        1, round(load_hold_dwell_seconds / float(model.opt.timestep))
    )
    load_hold_state: dict[str, Any] = {
        "armed": load_hold_enabled,
        "active": False,
        "bilateral_steps": 0,
        "target_rad": None,
        "latch_simulation_time_s": None,
        "release_simulation_time_s": None,
    }
    force_latch_enabled = bool(
        parameters.get("gripper_contact_force_limit_latch_enabled", False)
    )
    force_latch_dwell_seconds = float(
        parameters.get("gripper_contact_force_limit_latch_dwell_seconds", 0.01)
    )
    force_latch_release_margin_degrees = float(
        parameters.get("gripper_contact_force_limit_latch_release_margin_degrees", 2.0)
    )
    if not 0.0 <= force_latch_dwell_seconds <= 0.25:
        raise GraspCoordinateDescentError(
            "gripper_contact_force_limit_latch_dwell_seconds exceeds bounds"
        )
    if not 0.0 <= force_latch_release_margin_degrees <= 15.0:
        raise GraspCoordinateDescentError(
            "gripper_contact_force_limit_latch_release_margin_degrees exceeds bounds"
        )
    force_latch_dwell_steps = max(
        1, round(force_latch_dwell_seconds / float(model.opt.timestep))
    )
    force_latch_state: dict[str, Any] = {
        "armed": force_latch_enabled,
        "active": False,
        "bilateral_steps": 0,
        "latch_action_rad": None,
        "latch_simulation_time_s": None,
        "release_simulation_time_s": None,
    }

    def apply_response(action: np.ndarray) -> None:
        data.ctrl[actuator_ids] = action
        data.qfrc_applied[dof_addresses] = 0.0
        gripper_load_multiplier = float(
            parameters.get("gripper_piece_contact_force_limit_multiplier", 1.0)
        )
        if not 0.01 <= gripper_load_multiplier <= 1.0:
            raise GraspCoordinateDescentError(
                "gripper_piece_contact_force_limit_multiplier exceeds bounds"
            )
        gripper_actuator_id = int(actuator_ids[-1])
        loaded_by_piece = False
        fixed_selected_contact = False
        moving_selected_contact = False
        if (
            gripper_load_multiplier != 1.0
            or load_hold_enabled
            or force_latch_enabled
        ):
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                body1 = int(model.geom_bodyid[contact.geom1])
                body2 = int(model.geom_bodyid[contact.geom2])
                if (
                    body1 in jaw_body_ids
                    and body2 in piece_body_ids
                ) or (
                    body2 in jaw_body_ids
                    and body1 in piece_body_ids
                ):
                    loaded_by_piece = True
                fixed_selected_contact = fixed_selected_contact or (
                    (body1 in fixed_jaw_bodies and body2 == selected_body)
                    or (body2 in fixed_jaw_bodies and body1 == selected_body)
                )
                moving_selected_contact = moving_selected_contact or (
                    (body1 in moving_jaw_bodies and body2 == selected_body)
                    or (body2 in moving_jaw_bodies and body1 == selected_body)
                )
        force_limit_active = loaded_by_piece
        if force_latch_enabled:
            gripper_action = float(action[-1])
            latch_action = force_latch_state["latch_action_rad"]
            if force_latch_state["active"]:
                if gripper_action > float(latch_action) + math.radians(
                    force_latch_release_margin_degrees
                ):
                    force_latch_state["active"] = False
                    force_latch_state["armed"] = False
                    force_latch_state["release_simulation_time_s"] = float(
                        data.time
                    )
                    force_limit_active = False
                else:
                    force_limit_active = True
            elif force_latch_state["armed"]:
                if fixed_selected_contact and moving_selected_contact:
                    force_latch_state["bilateral_steps"] += 1
                else:
                    force_latch_state["bilateral_steps"] = 0
                if (
                    force_latch_state["bilateral_steps"]
                    >= force_latch_dwell_steps
                ):
                    force_latch_state["active"] = True
                    force_latch_state["latch_action_rad"] = gripper_action
                    force_latch_state["latch_simulation_time_s"] = float(
                        data.time
                    )
                    force_limit_active = True
        if load_hold_enabled:
            gripper_action = float(action[-1])
            target = load_hold_state["target_rad"]
            if load_hold_state["active"]:
                if gripper_action > float(target) + math.radians(
                    load_hold_release_margin_degrees
                ):
                    load_hold_state["active"] = False
                    load_hold_state["armed"] = False
                    load_hold_state["release_simulation_time_s"] = float(data.time)
                else:
                    data.ctrl[gripper_actuator_id] = float(target)
            elif load_hold_state["armed"]:
                closure_ready = (
                    load_hold_latch_target_rad is None
                    or float(data.qpos[qpos_addresses[-1]])
                    <= load_hold_latch_target_rad
                )
                if (
                    fixed_selected_contact
                    and moving_selected_contact
                    and closure_ready
                ):
                    load_hold_state["bilateral_steps"] += 1
                else:
                    load_hold_state["bilateral_steps"] = 0
                if load_hold_state["bilateral_steps"] >= load_hold_dwell_steps:
                    target = (
                        float(data.qpos[qpos_addresses[-1]])
                        if load_hold_latch_target_rad is None
                        else load_hold_latch_target_rad
                    )
                    load_hold_state["target_rad"] = target
                    load_hold_state["active"] = True
                    load_hold_state["latch_simulation_time_s"] = float(data.time)
                    data.ctrl[gripper_actuator_id] = target
        model.actuator_forcerange[gripper_actuator_id] = (
            nominal_force_range[gripper_actuator_id]
            * (gripper_load_multiplier if force_limit_active else 1.0)
        )
        for joint_name in ("shoulder_lift", "elbow_flex"):
            index = BODY_JOINT_NAMES.index(joint_name)
            actuator_id = actuator_ids[index]
            deadband_degrees = (
                lift_deadband if joint_name == "shoulder_lift" else elbow_deadband
            )
            inactive = abs(
                float(action[index] - data.qpos[qpos_addresses[index]])
            ) <= math.radians(deadband_degrees)
            scale = 0.0 if inactive else 1.0
            model.actuator_gainprm[actuator_id, 0] = (
                nominal_gain[actuator_id] * scale
            )
            model.actuator_biasprm[actuator_id, 1] = (
                nominal_bias[actuator_id, 1] * scale
            )
            if joint_name == "elbow_flex" and inactive:
                data.qfrc_applied[dof_addresses[index]] = float(
                    elbow_load_bias * data.qfrc_bias[dof_addresses[index]]
                )

    thresholds = experiment["dense_metric_thresholds"]
    lift_threshold = float(thresholds["lift_rise_m"])
    span_threshold = float(thresholds["minimum_bilateral_contact_span_m"])
    opposition_threshold = float(thresholds["minimum_opposing_normal_score"])
    timestep = float(model.opt.timestep)
    dense: dict[str, Any] = {
        "bilateral_steps": 0,
        "fixed_contact_steps": 0,
        "moving_contact_steps": 0,
        "qualified_bilateral_steps": 0,
        "current_bilateral_run": 0,
        "maximum_bilateral_run": 0,
        "current_qualified_run": 0,
        "maximum_qualified_run": 0,
        "current_qualified_lift_run": 0,
        "maximum_qualified_lift_run": 0,
        "maximum_contact_span_m": 0.0,
        "maximum_opposing_normal_score": -1.0,
        "maximum_transport_progress_after_lift": 0.0,
        "maximum_transport_progress_after_first_lift": 0.0,
        "minimum_target_distance_after_first_lift_m": float("inf"),
        "first_lift_source_index": None,
        "first_post_lift_destination_entry": None,
        "maximum_post_grasp_slip_m": 0.0,
        "first_qualified_local_piece_offset": None,
        "first_qualified_contact_height_relative_piece_center_m": None,
        "first_qualified_source_index": None,
        "first_qualified_gripper_qpos_rad": None,
        "first_qualified_gripper_ctrl_rad": None,
        "wrong_piece_contact_ledger": {},
        "maximum_displacement_by_other_piece_m": {
            name: 0.0
            for name, body_id in piece_bodies.items()
            if body_id != selected_body
        },
        "first_collateral_threshold_crossing": None,
    }
    minimum_pinch = float("inf")
    retention_trace: list[dict[str, Any]] = []
    last_retention_source_index: int | None = None
    last_retention_state_signature: tuple[Any, ...] | None = None
    collateral_threshold = float(
        reward_contract["hard_gates"]["maximum_other_piece_displacement_m"]
    )

    def observe_dense(
        *, episode_time_s: float, source_index: int | None, replay_phase: str
    ) -> None:
        nonlocal minimum_pinch
        nonlocal last_retention_source_index
        nonlocal last_retention_state_signature
        piece_position = np.asarray(data.xpos[selected_body], dtype=np.float64)
        pinch = _pinch_point(model, data, "left", pinch_local)
        minimum_pinch = min(
            minimum_pinch, float(np.linalg.norm(pinch - piece_position))
        )
        contact = _jaw_contact_geometry(
            model,
            data,
            selected_body=selected_body,
            fixed_jaw_bodies=fixed_jaw_bodies,
            moving_jaw_bodies=moving_jaw_bodies,
        )
        bilateral = bool(contact["bilateral_contact"])
        qualified = bool(
            bilateral
            and contact["maximum_contact_span_m"] >= span_threshold
            and contact["maximum_opposing_normal_score"] >= opposition_threshold
        )
        dense["bilateral_steps"] += int(bilateral)
        dense["fixed_contact_steps"] += int(contact["fixed_contact"])
        dense["moving_contact_steps"] += int(contact["moving_contact"])
        dense["qualified_bilateral_steps"] += int(qualified)
        dense["current_bilateral_run"], dense["maximum_bilateral_run"] = (
            _run_length_update(
                bilateral,
                dense["current_bilateral_run"],
                dense["maximum_bilateral_run"],
            )
        )
        dense["current_qualified_run"], dense["maximum_qualified_run"] = (
            _run_length_update(
                qualified,
                dense["current_qualified_run"],
                dense["maximum_qualified_run"],
            )
        )
        rise = float(piece_position[2] - initial_height)
        mechanism_phase = (
            "after_lift"
            if rise >= lift_threshold
            else (
                "after_qualified_grasp"
                if qualified
                or dense["first_qualified_local_piece_offset"] is not None
                else replay_phase
            )
        )
        for piece_name, body_id in piece_bodies.items():
            if body_id == selected_body:
                continue
            displacement = float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_positions[piece_name]
                )
            )
            dense["maximum_displacement_by_other_piece_m"][piece_name] = max(
                dense["maximum_displacement_by_other_piece_m"][piece_name],
                displacement,
            )
            if (
                displacement > collateral_threshold
                and dense["first_collateral_threshold_crossing"] is None
            ):
                dense["first_collateral_threshold_crossing"] = {
                    "piece_name": piece_name,
                    "displacement_m": displacement,
                    "episode_time_s": float(episode_time_s),
                    "source_index": source_index,
                    "phase": mechanism_phase,
                }
        for observation in _wrong_piece_robot_contacts(
            model,
            data,
            selected_body=selected_body,
            piece_bodies=piece_bodies,
            robot_body_ids=robot_body_ids,
        ):
            key = "|".join(
                str(observation[field])
                for field in (
                    "piece_name",
                    "robot_body_name",
                    "robot_geom_name",
                    "piece_geom_name",
                )
            )
            ledger = dense["wrong_piece_contact_ledger"]
            if key not in ledger:
                ledger[key] = {
                    **observation,
                    "contact_steps": 0,
                    "first_episode_time_s": float(episode_time_s),
                    "last_episode_time_s": float(episode_time_s),
                    "first_source_index": source_index,
                    "last_source_index": source_index,
                    "first_phase": mechanism_phase,
                    "phases": [],
                }
            row = ledger[key]
            row["contact_steps"] += 1
            row["last_episode_time_s"] = float(episode_time_s)
            row["last_source_index"] = source_index
            row["contact_position_xyz_m"] = observation[
                "contact_position_xyz_m"
            ]
            if mechanism_phase not in row["phases"]:
                row["phases"].append(mechanism_phase)
        qualified_lift = qualified and rise >= lift_threshold
        (
            dense["current_qualified_lift_run"],
            dense["maximum_qualified_lift_run"],
        ) = _run_length_update(
            qualified_lift,
            dense["current_qualified_lift_run"],
            dense["maximum_qualified_lift_run"],
        )
        dense["maximum_contact_span_m"] = max(
            dense["maximum_contact_span_m"],
            float(contact["maximum_contact_span_m"]),
        )
        dense["maximum_opposing_normal_score"] = max(
            dense["maximum_opposing_normal_score"],
            float(contact["maximum_opposing_normal_score"]),
        )
        rotation = np.asarray(data.xmat[fixed_tip_body]).reshape(3, 3)
        local_offset = rotation.T @ (piece_position - pinch)
        if qualified and dense["first_qualified_local_piece_offset"] is None:
            dense["first_qualified_local_piece_offset"] = local_offset.copy()
            dense["first_qualified_source_index"] = source_index
            mean_contact = contact["mean_contact_position_m"]
            if mean_contact is not None:
                dense["first_qualified_contact_height_relative_piece_center_m"] = float(
                    np.asarray(mean_contact, dtype=np.float64)[2] - piece_position[2]
                )
            gripper_index = len(qpos_addresses) - 1
            dense["first_qualified_gripper_qpos_rad"] = float(
                data.qpos[qpos_addresses[gripper_index]]
            )
            dense["first_qualified_gripper_ctrl_rad"] = float(
                data.ctrl[actuator_ids[gripper_index]]
            )
        first_offset = dense["first_qualified_local_piece_offset"]
        if first_offset is not None and (qualified or rise >= lift_threshold):
            dense["maximum_post_grasp_slip_m"] = max(
                dense["maximum_post_grasp_slip_m"],
                float(np.linalg.norm(local_offset - first_offset)),
            )
        target_distance = float(
            np.linalg.norm(piece_position[:2] - target_xyz[:2])
        )
        if rise >= lift_threshold and dense["first_lift_source_index"] is None:
            dense["first_lift_source_index"] = source_index
        if dense["first_lift_source_index"] is not None:
            dense["minimum_target_distance_after_first_lift_m"] = min(
                dense["minimum_target_distance_after_first_lift_m"],
                target_distance,
            )
            if initial_target_distance > 0.0:
                post_lift_progress = float(
                    np.clip(
                        (initial_target_distance - target_distance)
                        / initial_target_distance,
                        -1.0,
                        1.0,
                    )
                )
                dense["maximum_transport_progress_after_first_lift"] = max(
                    dense["maximum_transport_progress_after_first_lift"],
                    post_lift_progress,
                )
            if (
                target_distance
                <= float(
                    reward_contract["hard_gates"][
                        "maximum_final_center_distance_for_whole_base_inside_m"
                    ]
                )
                and dense["first_post_lift_destination_entry"] is None
            ):
                dense["first_post_lift_destination_entry"] = {
                    "episode_time_s": float(episode_time_s),
                    "source_index": source_index,
                    "target_distance_m": target_distance,
                    "piece_rise_m": rise,
                    "qualified_bilateral_contact": qualified,
                    "bilateral_contact": bilateral,
                }
        if rise >= lift_threshold and initial_target_distance > 0.0:
            progress = float(
                np.clip(
                    (initial_target_distance - target_distance)
                    / initial_target_distance,
                    -1.0,
                    1.0,
                )
            )
            dense["maximum_transport_progress_after_lift"] = max(
                dense["maximum_transport_progress_after_lift"], progress
            )
        if retention_trace_enabled:
            state_signature = (
                bool(contact["fixed_contact"]),
                bool(contact["moving_contact"]),
                qualified,
                rise >= lift_threshold,
                mechanism_phase,
            )
            if (
                source_index != last_retention_source_index
                or state_signature != last_retention_state_signature
            ):
                resolved_source_index = (
                    None
                    if source_index is None
                    else int(np.clip(source_index, 0, len(mapped["actions"]) - 1))
                )
                mean_contact = contact["mean_contact_position_m"]
                retention_trace.append(
                    {
                        "episode_time_s": float(episode_time_s),
                        "source_index": resolved_source_index,
                        "replay_phase": replay_phase,
                        "mechanism_phase": mechanism_phase,
                        "piece_rise_m": rise,
                        "piece_position_xyz_m": piece_position.astype(
                            float
                        ).tolist(),
                        "piece_linear_speed_m_s": float(
                            np.linalg.norm(
                                data.qvel[selected_dof : selected_dof + 3]
                            )
                        ),
                        "piece_angular_speed_rad_s": float(
                            np.linalg.norm(
                                data.qvel[selected_dof + 3 : selected_dof + 6]
                            )
                        ),
                        "target_distance_m": target_distance,
                        "pinch_position_xyz_m": pinch.astype(float).tolist(),
                        "pinch_to_piece_m": float(
                            np.linalg.norm(pinch - piece_position)
                        ),
                        "piece_offset_in_fixed_tip_frame_xyz_m": (
                            local_offset.astype(float).tolist()
                        ),
                        "fixed_contact": bool(contact["fixed_contact"]),
                        "moving_contact": bool(contact["moving_contact"]),
                        "bilateral_contact": bilateral,
                        "qualified_bilateral_contact": qualified,
                        "fixed_contact_count": int(
                            contact["fixed_contact_count"]
                        ),
                        "moving_contact_count": int(
                            contact["moving_contact_count"]
                        ),
                        "maximum_contact_span_m": float(
                            contact["maximum_contact_span_m"]
                        ),
                        "maximum_opposing_normal_score": float(
                            contact["maximum_opposing_normal_score"]
                        ),
                        "mean_contact_position_xyz_m": mean_contact,
                        "contact_height_relative_piece_center_m": (
                            None
                            if mean_contact is None
                            else float(mean_contact[2] - piece_position[2])
                        ),
                        "fixed_normal_force_n": float(
                            contact["fixed_normal_force_n"]
                        ),
                        "moving_normal_force_n": float(
                            contact["moving_normal_force_n"]
                        ),
                        "total_normal_force_n": float(
                            contact["total_normal_force_n"]
                        ),
                        "fixed_tangential_force_n": float(
                            contact["fixed_tangential_force_n"]
                        ),
                        "moving_tangential_force_n": float(
                            contact["moving_tangential_force_n"]
                        ),
                        "total_tangential_force_n": float(
                            contact["total_tangential_force_n"]
                        ),
                        "contact_witnesses": contact["contact_witnesses"],
                        "load_bearing_pair": contact["load_bearing_pair"],
                        "simulated_gripper_qpos_rad": float(
                            data.qpos[qpos_addresses[-1]]
                        ),
                        "simulated_gripper_qvel_rad_s": float(
                            data.qvel[dof_addresses[-1]]
                        ),
                        "simulated_gripper_ctrl_rad": float(
                            data.ctrl[actuator_ids[-1]]
                        ),
                        "source_commanded_gripper_rad": (
                            None
                            if resolved_source_index is None
                            else float(
                                mapped["actions"][resolved_source_index, -1]
                            )
                        ),
                        "source_measured_gripper_rad": (
                            None
                            if resolved_source_index is None
                            else float(
                                mapped["measured"][resolved_source_index, -1]
                            )
                        ),
                        "compliant_pad_normal_displacement_m": {
                            name: float(data.qpos[address])
                            for name, address in sorted(
                                compliant_pad_qpos_addresses.items()
                            )
                        },
                    }
                )
                last_retention_source_index = source_index
                last_retention_state_signature = state_signature

    trace = [trace_row()]
    observe_dense(episode_time_s=0.0, source_index=0, replay_phase="initial")
    actions = mapped["actions"]
    times = mapped["timestamps"]
    simulated_states = np.empty_like(mapped["measured"])
    delay = float(
        parameters.get(
            "application_delay_seconds",
            experiment["source"]["application_delay_seconds"],
        )
    )
    delay_by_joint = np.asarray(
        [
            float(
                parameters.get(
                    f"application_delay_{name}_seconds",
                    parameters.get("gripper_application_delay_seconds", delay)
                    if name == "gripper"
                    else delay,
                )
            )
            for name in BODY_JOINT_NAMES + ("gripper",)
        ],
        dtype=np.float64,
    )
    if np.any(delay_by_joint < 0.0) or np.any(delay_by_joint > 0.3):
        raise GraspCoordinateDescentError(
            "per-joint application delays must remain within [0, 0.3] seconds"
        )

    def delayed_action(now: float) -> np.ndarray:
        indices = [
            max(
                0,
                int(
                    np.searchsorted(times, now - joint_delay, side="right")
                    - 1
                ),
            )
            for joint_delay in delay_by_joint
        ]
        return np.asarray(
            [actions[index, joint] for joint, index in enumerate(indices)],
            dtype=np.float64,
        )

    measured_state_replay = bool(
        parameters.get("diagnostic_measured_joint_state_replay", False)
    )

    def force_measured_robot_state(now: float) -> None:
        clipped_time = float(np.clip(now, times[0], times[-1]))
        upper = int(np.searchsorted(times, clipped_time, side="right"))
        upper = min(max(upper, 1), len(times) - 1)
        lower = upper - 1
        duration = float(times[upper] - times[lower])
        fraction = (
            0.0
            if duration <= 0.0
            else float((clipped_time - times[lower]) / duration)
        )
        lower_state = np.asarray(mapped["measured"][lower], dtype=np.float64)
        upper_state = np.asarray(mapped["measured"][upper], dtype=np.float64)
        state = lower_state + fraction * (upper_state - lower_state)
        velocity = (
            np.zeros_like(state)
            if duration <= 0.0
            else (upper_state - lower_state) / duration
        )
        data.qpos[qpos_addresses] = state
        data.qvel[dof_addresses] = velocity
        mujoco.mj_forward(model, data)

    for row_index, timestamp in enumerate(times):
        simulated_states[row_index] = data.qpos[qpos_addresses]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        for step in range(max(1, round(interval / timestep))):
            now = float(timestamp) + step * timestep
            source_index = max(
                0,
                int(np.searchsorted(times, now - delay, side="right") - 1),
            )
            if measured_state_replay:
                force_measured_robot_state(now)
            apply_response(delayed_action(now))
            mujoco.mj_step(model, data)
            if measured_state_replay:
                force_measured_robot_state(min(now + timestep, times[-1]))
            observe_dense(
                episode_time_s=float(now - times[0]),
                source_index=source_index,
                replay_phase="before_qualified_grasp",
            )
            if state_recorder is not None:
                rise = float(data.xpos[selected_body][2] - initial_height)
                phase = (
                    "lift_and_transport"
                    if rise >= lift_threshold
                    else "grasp"
                    if dense["first_qualified_local_piece_offset"] is not None
                    else "approach"
                )
                state_recorder.capture(data, phase=phase)
        trace.append(trace_row())
    final_index = max(
        0,
        int(
            np.searchsorted(times, float(times[-1]) - delay, side="right") - 1
        ),
    )
    apply_response(delayed_action(float(times[-1])))
    for _ in range(200):
        if measured_state_replay:
            force_measured_robot_state(float(times[-1]))
        apply_response(np.asarray(data.ctrl[actuator_ids], dtype=np.float64))
        mujoco.mj_step(model, data)
        if measured_state_replay:
            force_measured_robot_state(float(times[-1]))
        observe_dense(
            episode_time_s=float(times[-1] - times[0] + (_ + 1) * timestep),
            source_index=final_index,
            replay_phase="terminal_settle",
        )
        if state_recorder is not None:
            state_recorder.capture(data, phase="terminal_settle")
    trace.append(trace_row())

    state_trace_artifact = None
    if state_recorder is not None and state_trace_path is not None:
        state_recorder.capture(data, phase="terminal_settle", force=True)
        trace_result = state_recorder.write(state_trace_path)
        if scene_manifest_path is None:
            raise GraspCoordinateDescentError("state trace scene manifest is missing")
        state_trace_artifact = {
            "state_trace_path": str(state_trace_path.relative_to(REPO_ROOT)),
            "state_trace_sha256": str(trace_result["sha256"]),
            "scene_manifest_path": str(scene_manifest_path.relative_to(REPO_ROOT)),
            "scene_manifest_sha256": sha256_file(scene_manifest_path),
            "frame_count": int(trace_result["frame_count"]),
            "fps": float(trace_result["fps"]),
            "duration_seconds": float(trace_result["duration_seconds"]),
            "inspection_only": True,
            "physical_authority": False,
        }

    score = score_episode(
        reward_contract,
        skill_id=f"pawn_{source}_to_{destination}",
        trace=trace,
        target_position_xyz_m=target_xyz,
        initial_piece_height_m=initial_height,
        evaluation_mode="source_demonstration_replay",
        action_owner="physical_teleoperator",
        assistance_used=False,
    )
    trace_metrics = _episode_metrics(
        mapped, simulated_states, effective_workcell, servo_contract
    )
    wrong_contact_rows = list(dense["wrong_piece_contact_ledger"].values())
    wrong_source_indices = [
        int(row["first_source_index"])
        for row in wrong_contact_rows
        if row["first_source_index"] is not None
    ]
    first_wrong_index = min(wrong_source_indices) if wrong_source_indices else None

    def aligned_state_snapshot(source_index: int | None) -> dict[str, Any] | None:
        if source_index is None:
            return None
        index = int(np.clip(source_index, 0, len(simulated_states) - 1))
        simulated = np.asarray(simulated_states[index], dtype=np.float64)
        measured = np.asarray(mapped["measured"][index], dtype=np.float64)
        commanded = np.asarray(mapped["actions"][index], dtype=np.float64)
        actual_ee = np.asarray(trace_metrics["actual_points"][index], dtype=np.float64)
        simulated_ee = np.asarray(
            trace_metrics["simulated_points"][index], dtype=np.float64
        )
        return {
            "source_index": index,
            "elapsed_seconds": float(mapped["timestamps"][index]),
            "simulated_minus_measured_joint_degrees": dict(
                zip(
                    BODY_JOINT_NAMES + ("gripper",),
                    np.degrees(simulated - measured).astype(float).tolist(),
                    strict=True,
                )
            ),
            "commanded_minus_measured_joint_degrees": dict(
                zip(
                    BODY_JOINT_NAMES + ("gripper",),
                    np.degrees(commanded - measured).astype(float).tolist(),
                    strict=True,
                )
            ),
            "mapped_measured_ee_xyz_m": actual_ee.astype(float).tolist(),
            "simulated_ee_xyz_m": simulated_ee.astype(float).tolist(),
            "simulated_minus_measured_ee_xyz_m": (
                simulated_ee - actual_ee
            ).astype(float).tolist(),
            "ee_error_m": float(np.linalg.norm(simulated_ee - actual_ee)),
        }

    first_wrong_snapshot = aligned_state_snapshot(first_wrong_index)
    first_qualified_snapshot = aligned_state_snapshot(
        dense["first_qualified_source_index"]
    )
    gripper_error = simulated_states[:, -1] - mapped["measured"][:, -1]
    gripper_command_error = mapped["actions"][:, -1] - mapped["measured"][:, -1]
    event_aligned_gripper = _event_aligned_gripper_metrics(
        mapped=mapped, simulated_states=simulated_states
    )
    gripper_trace = {
        "simulated_to_measured_rms_rad": float(
            np.sqrt(np.mean(np.square(gripper_error)))
        ),
        "simulated_to_measured_rms_degrees": float(
            np.degrees(np.sqrt(np.mean(np.square(gripper_error))))
        ),
        "commanded_to_measured_rms_rad": float(
            np.sqrt(np.mean(np.square(gripper_command_error)))
        ),
        "commanded_to_measured_rms_degrees": float(
            np.degrees(np.sqrt(np.mean(np.square(gripper_command_error))))
        ),
        "simulated_min_rad": float(np.min(simulated_states[:, -1])),
        "simulated_max_rad": float(np.max(simulated_states[:, -1])),
        "measured_min_rad": float(np.min(mapped["measured"][:, -1])),
        "measured_max_rad": float(np.max(mapped["measured"][:, -1])),
        "commanded_min_rad": float(np.min(mapped["actions"][:, -1])),
        "commanded_max_rad": float(np.max(mapped["actions"][:, -1])),
    }
    retained_seconds = float(dense["maximum_qualified_lift_run"] * timestep)
    transported = bool(
        dense["maximum_transport_progress_after_lift"]
        >= float(thresholds["transport_progress_fraction_after_lift"])
    )
    lifted = bool(score["gate_results"]["piece_lifted"])
    qualified_retention = bool(
        retained_seconds
        >= float(thresholds["minimum_bilateral_lift_retention_seconds"])
    )
    retention_event_summary = (
        _summarize_retention_trace(
            retention_trace, lift_threshold_m=lift_threshold
        )
        if retention_trace_enabled
        else None
    )
    return {
        "recording_id": str(mapped["episode"]["recording_id"]),
        "folder_label": str(mapped["episode"]["folder_label"]),
        "parameter_digest": canonical_digest(parameters),
        "effective_workcell": effective_workcell.as_dict(),
        "variant_id": variant.variant_id,
        "variant_sha256": variant.variant_sha256,
        "action_sha256": mapped["action_receipt"]["sha256"],
        "action_array_sha256": _array_sha256(actions),
        "action_byte_identical": (
            mapped["action_receipt"]["sha256"] == _array_sha256(actions)
        ),
        "clipped_action_rows": 0,
        "application_delay_seconds_by_joint": dict(
            zip(
                BODY_JOINT_NAMES + ("gripper",),
                delay_by_joint.astype(float).tolist(),
                strict=True,
            )
        ),
        "diagnostic_measured_joint_state_replay": {
            "enabled": measured_state_replay,
            "simulator_candidate_promotion_allowed": False,
            "purpose": "upper_bound_separating_arm_tracking_from_scene_contact",
            "source_actions_mutated": False,
        },
        "episode_piece_reset_offsets_applied_m": {
            file_name: [float(offset[0]), float(offset[1])]
            for file_name, offset in sorted(episode_reset_offsets.items())
        },
        "episode_piece_reset_offset_authority": {
            "simulator_initial_state_only": True,
            "source_actions_mutated": False,
            "metric_calibration_admission_allowed": False,
            "physical_transfer_claim_allowed": False,
        },
        "minimum_pinch_to_piece_m": minimum_pinch,
        "selected_piece_contact_observed": bool(
            score["gate_results"]["selected_piece_contact_observed"]
        ),
        "bilateral_contact_observed": dense["bilateral_steps"] > 0,
        "qualified_bilateral_contact_observed": (
            dense["qualified_bilateral_steps"] > 0
        ),
        "bilateral_contact_steps": int(dense["bilateral_steps"]),
        "fixed_jaw_contact_steps": int(dense["fixed_contact_steps"]),
        "moving_jaw_contact_steps": int(dense["moving_contact_steps"]),
        "qualified_bilateral_contact_steps": int(
            dense["qualified_bilateral_steps"]
        ),
        "maximum_consecutive_bilateral_contact_seconds": float(
            dense["maximum_bilateral_run"] * timestep
        ),
        "maximum_consecutive_qualified_contact_seconds": float(
            dense["maximum_qualified_run"] * timestep
        ),
        "maximum_contact_span_m": float(dense["maximum_contact_span_m"]),
        "maximum_opposing_normal_score": float(
            dense["maximum_opposing_normal_score"]
        ),
        "first_qualified_contact_height_relative_piece_center_m": dense[
            "first_qualified_contact_height_relative_piece_center_m"
        ],
        "first_qualified_source_index": dense["first_qualified_source_index"],
        "first_qualified_gripper_qpos_rad": dense[
            "first_qualified_gripper_qpos_rad"
        ],
        "first_qualified_gripper_ctrl_rad": dense[
            "first_qualified_gripper_ctrl_rad"
        ],
        "bilateral_lift_retention": qualified_retention,
        "maximum_bilateral_lift_retention_seconds": retained_seconds,
        "maximum_post_grasp_slip_m": float(
            dense["maximum_post_grasp_slip_m"]
        ),
        "piece_lifted": lifted,
        "transported_after_lift": transported,
        "lift_and_transport": lifted and transported,
        "maximum_transport_progress_after_lift": float(
            dense["maximum_transport_progress_after_lift"]
        ),
        "post_first_lift_task_diagnostic": {
            "first_lift_source_index": dense["first_lift_source_index"],
            "maximum_transport_progress": float(
                dense["maximum_transport_progress_after_first_lift"]
            ),
            "minimum_target_distance_m": (
                None
                if not math.isfinite(
                    dense["minimum_target_distance_after_first_lift_m"]
                )
                else float(dense["minimum_target_distance_after_first_lift_m"])
            ),
            "destination_entry": dense["first_post_lift_destination_entry"],
            "semantics": (
                "Secondary diagnostic observed after the first 40 mm rise even "
                "if the pawn later travels below that instantaneous lift gate; "
                "it does not change lift_and_transport or the frozen evaluator."
            ),
            "promotion_authority": False,
        },
        "whole_base_inside_destination": bool(
            score["gate_results"]["whole_base_inside_destination"]
        ),
        "released": bool(score["gate_results"]["released"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_target_distance_m": float(score["final_center_distance_m"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
        "original_gate_results": score["gate_results"],
        "final_piece_upright_cosine": float(score["final_piece_upright_cosine"]),
        "final_piece_linear_speed_m_s": float(score["final_piece_linear_speed_m_s"]),
        "maximum_other_piece_displacement_m": float(
            score["maximum_other_piece_displacement_m"]
        ),
        "maximum_displacement_by_other_piece_m": {
            key: float(value)
            for key, value in sorted(
                dense["maximum_displacement_by_other_piece_m"].items()
            )
        },
        "wrong_piece_robot_contacts": sorted(
            dense["wrong_piece_contact_ledger"].values(),
            key=lambda row: (
                row["first_episode_time_s"],
                row["piece_name"],
                row["robot_geom_name"],
            ),
        ),
        "first_collateral_threshold_crossing": dense[
            "first_collateral_threshold_crossing"
        ],
        "first_wrong_piece_contact_aligned_state": first_wrong_snapshot,
        "first_qualified_contact_aligned_state": first_qualified_snapshot,
        "trace_metrics": trace_metrics,
        "gripper_trace_metrics": gripper_trace,
        "event_aligned_gripper_metrics": event_aligned_gripper,
        "retention_trace_enabled": retention_trace_enabled,
        "retention_trace_semantics": {
            "sampling": (
                "source-frame changes plus contact, lift-gate, and replay-phase "
                "transitions"
            ),
            "contact_force": (
                "MuJoCo constraint-space magnitudes for simulator diagnosis; "
                "not calibrated sensor measurements"
            ),
            "source_actions_mutated": False,
            "metric_or_physical_authority": False,
            "load_bearing_pair": (
                "deterministic diagnostic pair ranked by minimum jaw normal "
                "force, opposing-normal score, span, and stable ids; it does "
                "not alter the frozen evaluator"
            ),
        },
        "retention_event_summary": retention_event_summary,
        "retention_trace": retention_trace if retention_trace_enabled else None,
        "load_sensitive_gripper_response": {
            "piece_contact_force_limit_multiplier": float(
                parameters.get(
                    "gripper_piece_contact_force_limit_multiplier", 1.0
                )
            ),
            "trigger": "any_jaw_body_contact_with_any_pawn_body",
            "source_actions_mutated": False,
            "load_hold": {
                "enabled": load_hold_enabled,
                "trigger": (
                    "sustained_bilateral_selected_pawn_contact"
                    if load_hold_enabled
                    else None
                ),
                "dwell_seconds": load_hold_dwell_seconds,
                "release_margin_degrees": load_hold_release_margin_degrees,
                "requested_latch_target_rad": load_hold_latch_target_rad,
                "latched": load_hold_state["target_rad"] is not None,
                "target_rad": load_hold_state["target_rad"],
                "target_degrees": (
                    None
                    if load_hold_state["target_rad"] is None
                    else math.degrees(float(load_hold_state["target_rad"]))
                ),
                "latch_simulation_time_s": load_hold_state[
                    "latch_simulation_time_s"
                ],
                "release_simulation_time_s": load_hold_state[
                    "release_simulation_time_s"
                ],
                "simulator_actuator_transfer_mutated": load_hold_enabled,
                "source_actions_mutated": False,
            },
            "force_limit_latch": {
                "enabled": force_latch_enabled,
                "trigger": (
                    "sustained_bilateral_selected_pawn_contact"
                    if force_latch_enabled
                    else None
                ),
                "dwell_seconds": force_latch_dwell_seconds,
                "release_margin_degrees": force_latch_release_margin_degrees,
                "latched": force_latch_state["latch_action_rad"] is not None,
                "latch_action_rad": force_latch_state["latch_action_rad"],
                "latch_simulation_time_s": force_latch_state[
                    "latch_simulation_time_s"
                ],
                "release_simulation_time_s": force_latch_state[
                    "release_simulation_time_s"
                ],
                "simulator_ctrl_mutated": False,
                "source_actions_mutated": False,
            },
        },
        "state_trace_artifact": state_trace_artifact,
    }


def _summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    pooled = _pool(row["trace_metrics"] for row in materialized)
    mean = lambda key: float(np.mean([float(row[key]) for row in materialized]))
    return {
        "episode_count": len(materialized),
        "selected_piece_contact": sum(
            int(row["selected_piece_contact_observed"]) for row in materialized
        ),
        "bilateral_contact": sum(
            int(row["bilateral_contact_observed"]) for row in materialized
        ),
        "qualified_bilateral_contact": sum(
            int(row["qualified_bilateral_contact_observed"])
            for row in materialized
        ),
        "bilateral_lift_retention": sum(
            int(row["bilateral_lift_retention"]) for row in materialized
        ),
        "lifted": sum(int(row["piece_lifted"]) for row in materialized),
        "lift_and_transport": sum(
            int(row["lift_and_transport"]) for row in materialized
        ),
        "whole_base_inside_destination": sum(
            int(row["whole_base_inside_destination"]) for row in materialized
        ),
        "strict_successes": sum(
            int(row["task_consequence_success"]) for row in materialized
        ),
        "mean_transport_progress_after_lift": mean(
            "maximum_transport_progress_after_lift"
        ),
        "mean_maximum_piece_rise_m": mean("maximum_piece_rise_m"),
        "mean_final_target_distance_m": mean("final_target_distance_m"),
        "mean_post_grasp_slip_m": mean("maximum_post_grasp_slip_m"),
        "mean_bilateral_lift_retention_seconds": mean(
            "maximum_bilateral_lift_retention_seconds"
        ),
        "trace_metrics": pooled,
        "gripper_trace_metrics": {
            key: float(
                np.mean(
                    [row["gripper_trace_metrics"][key] for row in materialized]
                )
            )
            for key in (
                "simulated_to_measured_rms_rad",
                "simulated_to_measured_rms_degrees",
                "commanded_to_measured_rms_rad",
                "commanded_to_measured_rms_degrees",
            )
        },
        "event_aligned_gripper_metrics": {
            "simulated_minus_measured_bias_degrees": float(
                np.mean(
                    [
                        row["event_aligned_gripper_metrics"][
                            "simulated_minus_measured_bias_degrees"
                        ]
                        for row in materialized
                    ]
                )
            ),
            "simulated_to_measured_rms_degrees": float(
                np.mean(
                    [
                        row["event_aligned_gripper_metrics"][
                            "simulated_to_measured_rms_degrees"
                        ]
                        for row in materialized
                    ]
                )
            ),
            "physical_mechanically_loaded_closure_proxy_supported": sum(
                int(
                    row["event_aligned_gripper_metrics"][
                        "physical_mechanically_loaded_closure_proxy_supported"
                    ]
                )
                for row in materialized
            ),
            "physical_flat_measured_velocity_fraction": float(
                np.mean(
                    [
                        row["event_aligned_gripper_metrics"][
                            "physical_flat_measured_velocity_fraction"
                        ]
                        for row in materialized
                    ]
                )
            ),
            "physical_median_absolute_command_measurement_gap_percent": float(
                np.mean(
                    [
                        row["event_aligned_gripper_metrics"][
                            "physical_median_absolute_command_measurement_gap_percent"
                        ]
                        for row in materialized
                    ]
                )
            ),
        },
        "action_invariance": all(row["action_byte_identical"] for row in materialized),
    }


def _rank(summary: dict[str, Any]) -> tuple[float, ...]:
    return (
        float(summary["strict_successes"]),
        float(summary["lift_and_transport"]),
        float(summary["lifted"]),
        float(summary["bilateral_lift_retention"]),
        float(summary["mean_transport_progress_after_lift"]),
        float(summary["mean_maximum_piece_rise_m"]),
        -float(summary["mean_final_target_distance_m"]),
        -float(summary["mean_post_grasp_slip_m"]),
    )


def _trace_guard_pass(summary: dict[str, Any], contract: dict[str, Any]) -> bool:
    guard = contract["source"]["trace_guardrail"]
    multiplier = 1.0 + float(guard["maximum_relative_regression"])
    metrics = summary["trace_metrics"]
    return bool(
        metrics["overall_joint_rms_degrees"]
        <= float(guard["baseline_joint_rms_degrees"]) * multiplier
        and metrics["ee_rms_m"] <= float(guard["baseline_ee_rms_m"]) * multiplier
        and summary["action_invariance"]
    )


def _public_episode(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: value for key, value in row.items() if key != "trace_metrics"},
        "trace_metrics": _strip_arrays(row["trace_metrics"]),
    }


def _public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: value for key, value in summary.items() if key != "trace_metrics"},
        "trace_metrics": _strip_arrays(summary["trace_metrics"]),
    }


def _paired_bootstrap(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    seed: int,
    replicates: int,
    confidence: float,
) -> dict[str, Any]:
    baseline_by_id = {row["recording_id"]: row for row in baseline}
    candidate_by_id = {row["recording_id"]: row for row in candidate}
    ids = sorted(baseline_by_id)
    if set(ids) != set(candidate_by_id):
        raise GraspCoordinateDescentError("paired bootstrap episode identities differ")
    before = np.asarray(
        [float(baseline_by_id[recording_id]["lift_and_transport"]) for recording_id in ids]
    )
    after = np.asarray(
        [float(candidate_by_id[recording_id]["lift_and_transport"]) for recording_id in ids]
    )
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(ids), size=(replicates, len(ids)))
    deltas = (after[samples] - before[samples]).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    return {
        "seed": seed,
        "replicates": replicates,
        "confidence_level": confidence,
        "resampling_unit": "whole_episode",
        "mean_lift_and_transport_fraction_delta": float(np.mean(after - before)),
        "confidence_interval": [
            float(np.quantile(deltas, alpha)),
            float(np.quantile(deltas, 1.0 - alpha)),
        ],
        "probability_greater_than_zero": float(np.mean(deltas > 0.0)),
        "dependence_boundary": (
            "conditional retained-episode uncertainty within one acquisition session"
        ),
    }


def _plot_summary(*, receipt: dict[str, Any], output_path: Path) -> None:
    baseline = receipt["full_evaluation"]["current_no_tip_baseline"]["summary"]
    initial = receipt["full_evaluation"]["initial_high_prior"]["summary"]
    final = receipt["full_evaluation"]["frozen_composite"]["summary"]
    categories = [
        "touch",
        "bilateral",
        "retained lift",
        "lift+transport",
        "inside target",
        "strict",
    ]
    keys = [
        "selected_piece_contact",
        "bilateral_contact",
        "bilateral_lift_retention",
        "lift_and_transport",
        "whole_base_inside_destination",
        "strict_successes",
    ]
    figure, axes = plt.subplots(1, 3, figsize=(17, 5.5), constrained_layout=True)
    figure.suptitle(
        "Action-frozen B–G grasp coordinate descent",
        fontsize=16,
        fontweight="bold",
    )

    ax = axes[0]
    x = np.arange(len(categories))
    width = 0.25
    for offset, summary, label, color in (
        (-width, baseline, "current no-tip", "#9d9d9d"),
        (0.0, initial, "initial high prior", "#f2a541"),
        (width, final, "frozen composite", "#4c78a8"),
    ):
        ax.bar(x + offset, [summary[key] for key in keys], width, label=label, color=color)
    ax.set(
        xticks=x,
        xticklabels=categories,
        ylim=(0, 11.8),
        ylabel="episodes / 11",
        title="A. Grasp-consequence funnel",
    )
    ax.tick_params(axis="x", rotation=25)
    ax.legend(fontsize=8)

    ax = axes[1]
    decisions = [row for row in receipt["coordinate_search"] if row["accepted"]]
    labels = [f"p{row['pass_index'] + 1}:{row['coordinate']}" for row in decisions]
    values = [row["selected_summary"]["lift_and_transport"] for row in decisions]
    if labels:
        ax.step(range(len(labels)), values, where="mid", marker="o", color="#4c78a8")
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    else:
        ax.text(0.5, 0.5, "No coordinate accepted", ha="center", va="center")
        ax.set_xticks([])
    ax.set(ylabel="sentinel lift+transport / 3", title="B. Accepted-coordinate waterfall")

    ax = axes[2]
    base_rows = receipt["full_evaluation"]["current_no_tip_baseline"]["episodes"]
    final_rows = receipt["full_evaluation"]["frozen_composite"]["episodes"]
    base_by_id = {row["recording_id"]: row for row in base_rows}
    final_by_id = {row["recording_id"]: row for row in final_rows}
    ids = sorted(base_by_id)
    for index, recording_id in enumerate(ids):
        ax.plot(
            [0, 1],
            [
                base_by_id[recording_id]["maximum_transport_progress_after_lift"],
                final_by_id[recording_id]["maximum_transport_progress_after_lift"],
            ],
            color="#7f8c8d",
            alpha=0.7,
            marker="o",
        )
    ax.axhline(0.5, color="#333333", linestyle="--", linewidth=1, label="transport gate")
    ax.set(
        xticks=[0, 1],
        xticklabels=["current no-tip", "frozen composite"],
        ylim=(-0.05, 1.05),
        ylabel="maximum targetward progress after lift",
        title="C. Paired transport progress",
    )
    ax.legend(fontsize=8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_grasp_episode_probe(
    *,
    source_repository_root: Path,
    recording_id: str,
    parameters: dict[str, Any],
    contract_path: Path = CONTRACT_PATH,
    state_trace_output_directory: Path | None = None,
    retention_trace_enabled: bool = False,
) -> dict[str, Any]:
    """Replay one retained episode with diagnostic mechanism instrumentation."""

    contract = load_grasp_coordinate_contract(contract_path)
    train_payloads, events = _load_partition(source_repository_root, "train")
    _parent, workcell, stage_d_parameters, _details = _reconstruct_stage_d(
        train_payloads, events
    )
    mapped_by_id = {
        str(mapped["episode"]["recording_id"]): mapped
        for mapped in (
            _mapped_episode(payload, workcell) for payload in train_payloads
        )
    }
    if recording_id not in mapped_by_id:
        raise GraspCoordinateDescentError(
            f"recording is not in the retained train partition: {recording_id}"
        )
    contact_snapshot = read_contact_prior_snapshot(
        source_repository_root / contract["source"]["contact_prior_path"]
    )
    if (
        contact_snapshot.sha256
        != contract["source"]["expected_contact_prior_canonical_sha256"]
    ):
        raise GraspCoordinateDescentError("contact prior canonical hash drifted")
    row = _run_episode(
        mapped=mapped_by_id[recording_id],
        workcell=workcell,
        experiment=contract,
        servo_contract=load_servo_load_bias_contract(),
        reward_contract=load_reward_contract(),
        contact_snapshot=contact_snapshot,
        parameters=copy.deepcopy(parameters),
        contract_path=contract_path,
        state_trace_output_directory=state_trace_output_directory,
        retention_trace_enabled=retention_trace_enabled,
    )
    receipt = {
        "schema_version": "sim2claw.pawn_bg_grasp_episode_probe.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_mechanism_diagnostic",
        "recording_id": recording_id,
        "parameters": copy.deepcopy(parameters),
        "parameter_digest": canonical_digest(parameters),
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "stage_d_parameters": stage_d_parameters,
        "episode": _public_episode(row),
        "authority": contract["authority"],
        "claim_boundary": (
            "This one-episode action-frozen replay localizes simulated failure "
            "mechanisms. It is adaptive diagnostic evidence, not held-out, physical, "
            "calibration, or promotion proof."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt


def run_grasp_group_probe(
    *,
    source_repository_root: Path,
    recording_ids: Iterable[str],
    parameters: dict[str, Any],
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Replay a declared retained group under one frozen parameter composite."""

    contract = load_grasp_coordinate_contract(contract_path)
    train_payloads, events = _load_partition(source_repository_root, "train")
    _parent, workcell, stage_d_parameters, _details = _reconstruct_stage_d(
        train_payloads, events
    )
    mapped_by_id = {
        str(mapped["episode"]["recording_id"]): mapped
        for mapped in (
            _mapped_episode(payload, workcell) for payload in train_payloads
        )
    }
    selected_ids = list(recording_ids)
    if not selected_ids:
        selected_ids = sorted(mapped_by_id)
    if len(selected_ids) != len(set(selected_ids)):
        raise GraspCoordinateDescentError("group probe recording ids repeat")
    missing = sorted(set(selected_ids) - set(mapped_by_id))
    if missing:
        raise GraspCoordinateDescentError(
            f"group probe ids are outside the retained train partition: {missing}"
        )
    contact_snapshot = read_contact_prior_snapshot(
        source_repository_root / contract["source"]["contact_prior_path"]
    )
    if (
        contact_snapshot.sha256
        != contract["source"]["expected_contact_prior_canonical_sha256"]
    ):
        raise GraspCoordinateDescentError("contact prior canonical hash drifted")
    servo_contract = load_servo_load_bias_contract()
    reward_contract = load_reward_contract()
    rows = [
        _run_episode(
            mapped=mapped_by_id[recording_id],
            workcell=workcell,
            experiment=contract,
            servo_contract=servo_contract,
            reward_contract=reward_contract,
            contact_snapshot=contact_snapshot,
            parameters=copy.deepcopy(parameters),
            contract_path=contract_path,
        )
        for recording_id in selected_ids
    ]
    summary = _summary(rows)
    receipt = {
        "schema_version": "sim2claw.pawn_bg_grasp_group_probe.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_group_mechanism_diagnostic",
        "recording_ids": selected_ids,
        "parameters": copy.deepcopy(parameters),
        "parameter_digest": canonical_digest(parameters),
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "stage_d_parameters": stage_d_parameters,
        "summary": _public_summary(summary),
        "episodes": [_public_episode(row) for row in rows],
        "authority": contract["authority"],
        "claim_boundary": (
            "This declared-group action-frozen replay is adaptive simulator "
            "diagnostic evidence, not held-out, physical, calibration, or "
            "promotion proof."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt


def run_grasp_coordinate_descent(
    *,
    source_repository_root: Path,
    output_root: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_grasp_coordinate_contract(contract_path)
    evidence_binding = contract["source"]["advancement_receipt"]
    advancement_path = source_repository_root / evidence_binding["path"]
    if sha256_file(advancement_path) != evidence_binding["sha256"]:
        raise GraspCoordinateDescentError("advancement receipt hash drifted")
    advancement = json.loads(advancement_path.read_text(encoding="utf-8"))
    if advancement.get("schema_version") != evidence_binding["schema_version"]:
        raise GraspCoordinateDescentError("advancement receipt schema drifted")
    if not advancement["verified_significant_action_frozen_rms_advancement"]:
        raise GraspCoordinateDescentError("accepted trace baseline is unavailable")

    train_payloads, events = _load_partition(source_repository_root, "train")
    confirmation_payloads, _ = _load_partition(source_repository_root, "held_out")
    if len(train_payloads) != int(contract["source"]["expected_episode_count"]):
        raise GraspCoordinateDescentError("train episode inventory drifted")
    _parent, workcell, stage_d_parameters, _details = _reconstruct_stage_d(
        train_payloads, events
    )
    mapped_train = {
        str(mapped["episode"]["recording_id"]): mapped
        for mapped in (_mapped_episode(payload, workcell) for payload in train_payloads)
    }
    expected_ids = set(
        contract["episode_roles"]["adaptive_sentinel_recording_ids"]
        + contract["episode_roles"]["campaign_held_evaluation_recording_ids"]
    )
    if set(mapped_train) != expected_ids:
        raise GraspCoordinateDescentError("episode role identities drifted")
    mapped_confirmation = {
        str(mapped["episode"]["recording_id"]): mapped
        for mapped in (
            _mapped_episode(payload, workcell) for payload in confirmation_payloads
        )
    }
    contact_snapshot = read_contact_prior_snapshot(
        source_repository_root / contract["source"]["contact_prior_path"]
    )
    if (
        contact_snapshot.sha256
        != contract["source"]["expected_contact_prior_canonical_sha256"]
    ):
        raise GraspCoordinateDescentError("contact prior canonical hash drifted")
    servo_contract = load_servo_load_bias_contract()
    reward_contract = load_reward_contract()

    cache: dict[tuple[str, str], dict[str, Any]] = {}

    def evaluate(
        parameters: dict[str, Any], recording_ids: Iterable[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        parameter_digest = canonical_digest(parameters)
        rows: list[dict[str, Any]] = []
        for recording_id in recording_ids:
            key = (parameter_digest, str(recording_id))
            if key not in cache:
                cache[key] = _run_episode(
                    mapped=mapped_train[str(recording_id)],
                    workcell=workcell,
                    experiment=contract,
                    servo_contract=servo_contract,
                    reward_contract=reward_contract,
                    contact_snapshot=contact_snapshot,
                    parameters=parameters,
                    contract_path=contract_path,
                )
            rows.append(cache[key])
        return rows, _summary(rows)

    sentinel_ids = list(
        contract["episode_roles"]["adaptive_sentinel_recording_ids"]
    )
    current = copy.deepcopy(contract["initial_composite"])
    initial_parameters = copy.deepcopy(current)
    current_rows, current_summary = evaluate(current, sentinel_ids)
    if not _trace_guard_pass(current_summary, contract):
        raise GraspCoordinateDescentError("initial composite fails trace guardrails")

    search_receipts: list[dict[str, Any]] = []
    for pass_index in range(int(contract["search"]["coordinate_passes"])):
        for coordinate in contract["coordinates"]:
            name = str(coordinate["name"])
            current_value = float(current[name])
            candidate_receipts: list[dict[str, Any]] = []
            best_parameters = copy.deepcopy(current)
            best_rows = current_rows
            best_summary = current_summary
            best_rank = _rank(current_summary)
            for raw_value in coordinate["values"]:
                value = float(raw_value)
                candidate = copy.deepcopy(current)
                candidate[name] = value
                rows, summary = evaluate(candidate, sentinel_ids)
                guard_pass = _trace_guard_pass(summary, contract)
                rank = _rank(summary)
                candidate_receipts.append(
                    {
                        "value": value,
                        "parameter_digest": canonical_digest(candidate),
                        "trace_guard_pass": guard_pass,
                        "rank": list(rank),
                        "summary": _public_summary(summary),
                    }
                )
                if guard_pass and rank > best_rank:
                    best_parameters = candidate
                    best_rows = rows
                    best_summary = summary
                    best_rank = rank
            accepted = bool(float(best_parameters[name]) != current_value)
            search_receipts.append(
                {
                    "pass_index": pass_index,
                    "coordinate": name,
                    "starting_value": current_value,
                    "selected_value": float(best_parameters[name]),
                    "accepted": accepted,
                    "candidate_count": len(candidate_receipts),
                    "candidates": candidate_receipts,
                    "selected_parameter_digest": canonical_digest(best_parameters),
                    "selected_summary": _public_summary(best_summary),
                }
            )
            if accepted:
                current = best_parameters
                current_rows = best_rows
                current_summary = best_summary

    frozen_parameters = copy.deepcopy(current)
    frozen_parameter_digest = canonical_digest(frozen_parameters)
    no_tip_parameters = copy.deepcopy(initial_parameters)
    no_tip_parameters["rubber_tip_enabled"] = False
    all_ids = sorted(mapped_train)
    held_ids = list(
        contract["episode_roles"]["campaign_held_evaluation_recording_ids"]
    )
    baseline_rows, baseline_summary = evaluate(no_tip_parameters, all_ids)
    initial_rows, initial_summary = evaluate(initial_parameters, all_ids)
    final_rows, final_summary = evaluate(frozen_parameters, all_ids)
    held_final_rows = [
        next(row for row in final_rows if row["recording_id"] == recording_id)
        for recording_id in held_ids
    ]
    held_final_summary = _summary(held_final_rows)

    def evaluate_confirmation(
        parameters: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = [
            _run_episode(
                mapped=mapped,
                workcell=workcell,
                experiment=contract,
                servo_contract=servo_contract,
                reward_contract=reward_contract,
                contact_snapshot=contact_snapshot,
                parameters=parameters,
                contract_path=contract_path,
            )
            for mapped in mapped_confirmation.values()
        ]
        return rows, _summary(rows)

    confirmation_baseline_rows, confirmation_baseline_summary = (
        evaluate_confirmation(no_tip_parameters)
    )
    confirmation_final_rows, confirmation_final_summary = evaluate_confirmation(
        frozen_parameters
    )

    acceptance = contract["acceptance"]
    bootstrap = _paired_bootstrap(
        baseline_rows,
        final_rows,
        seed=int(acceptance["bootstrap_seed"]),
        replicates=int(acceptance["bootstrap_replicates"]),
        confidence=float(acceptance["confidence_level"]),
    )
    consequence_count_gate = bool(
        (
            final_summary["lift_and_transport"]
            >= int(acceptance["minimum_all_episode_lift_and_transport"])
            and held_final_summary["lift_and_transport"]
            >= int(
                acceptance["minimum_campaign_held_evaluation_lift_and_transport"]
            )
        )
        or final_summary["strict_successes"]
        >= int(acceptance["minimum_strict_successes"])
    )
    gates = {
        "frozen_before_held_evaluation_gate": True,
        "action_invariance_gate": bool(final_summary["action_invariance"]),
        "trace_guardrail_gate": _trace_guard_pass(final_summary, contract),
        "significant_consequence_count_gate": consequence_count_gate,
        "paired_bootstrap_direction_gate": (
            bootstrap["confidence_interval"][0] > 0.0
        ),
        "campaign_held_evaluation_gate": bool(
            held_final_summary["lift_and_transport"]
            >= int(
                acceptance["minimum_campaign_held_evaluation_lift_and_transport"]
            )
            or final_summary["strict_successes"]
            >= int(acceptance["minimum_strict_successes"])
        ),
    }
    verified = all(gates.values())

    output_root = output_root.resolve()
    figure_path = output_root / "grasp_coordinate_descent_summary.png"
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_grasp_coordinate_sensitivity",
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "source_advancement_receipt": {
            "path": str(advancement_path.resolve()),
            "sha256": sha256_file(advancement_path),
            "receipt_digest": advancement["receipt_digest"],
        },
        "contact_prior": {
            "path": str(contact_snapshot.source_path.resolve()),
            "canonical_sha256": contact_snapshot.sha256,
        },
        "stage_d_parameters": stage_d_parameters,
        "episode_roles": contract["episode_roles"],
        "coordinate_search": search_receipts,
        "initial_parameters": initial_parameters,
        "frozen_composite_parameters": frozen_parameters,
        "frozen_composite_parameter_digest": frozen_parameter_digest,
        "full_evaluation": {
            "current_no_tip_baseline": {
                "parameters": no_tip_parameters,
                "summary": _public_summary(baseline_summary),
                "episodes": [_public_episode(row) for row in baseline_rows],
            },
            "initial_high_prior": {
                "parameters": initial_parameters,
                "summary": _public_summary(initial_summary),
                "episodes": [_public_episode(row) for row in initial_rows],
            },
            "frozen_composite": {
                "parameters": frozen_parameters,
                "summary": _public_summary(final_summary),
                "episodes": [_public_episode(row) for row in final_rows],
            },
            "campaign_held_evaluation": {
                "selection_use": "none_opened_once_after_composite_freeze",
                "summary": _public_summary(held_final_summary),
                "episodes": [_public_episode(row) for row in held_final_rows],
            },
        },
        "already_opened_confirmation": {
            "selection_use": "none_regression_only",
            "current_no_tip_baseline": {
                "summary": _public_summary(confirmation_baseline_summary),
                "episodes": [
                    _public_episode(row) for row in confirmation_baseline_rows
                ],
            },
            "frozen_composite": {
                "summary": _public_summary(confirmation_final_summary),
                "episodes": [_public_episode(row) for row in confirmation_final_rows],
            },
        },
        "paired_episode_bootstrap": bootstrap,
        "advancement_gates": gates,
        "verified_significant_consequence_advancement": verified,
        "goal_loop_stop_decision": (
            "stop_significant_consequence_win_verified"
            if verified
            else "continue_or_redirect_consequence_gate_not_met"
        ),
        "figure": {"path": str(figure_path)},
        "authority": contract["authority"],
        "claim_boundary": (
            "This adaptive campaign may verify a simulator consequence sensitivity under "
            "byte-identical retained actions. It cannot identify physical gripper, contact, "
            "or pawn parameters; establish independent-session generalization; promote the "
            "simulator; admit training; improve a policy; or establish physical transfer."
        ),
    }
    _plot_summary(receipt=receipt, output_path=figure_path)
    receipt["figure"]["sha256"] = sha256_file(figure_path)
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "grasp_coordinate_descent_receipt.json", receipt)
    return receipt
