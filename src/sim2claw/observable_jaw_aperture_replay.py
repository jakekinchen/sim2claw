"""One-run exact C6-action replay with the OR6 jaw-aperture mapping."""

from __future__ import annotations

import copy
import math
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
    sha256_file,
)
from .pawn_bg_demo_sim import _piece_bodies
from .realized_action_outcome_mission import (
    _contact_counts,
    _outcome,
    _rotation,
    _tensor,
    _tilt,
    load_contract as load_c6_contract,
    physical_to_model,
)
from .recorded_replay import _compile_model
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_jaw_aperture_replay_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_jaw_aperture_replay_receipt.v1"
TRACE_SCHEMA = "sim2claw.observable_jaw_aperture_replay_trace.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_jaw_aperture_replay_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "observable_jaw_aperture_replay_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _bound_json(
    binding: dict[str, Any], *, root: Path, label: str
) -> dict[str, Any]:
    return load_json_object(
        _bound_path(binding, root=root, label=label), label=label
    )


def load_aperture_replay_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_json_object(path, label="observable jaw aperture replay")
    _require(contract.get("schema_version") == SCHEMA, "unsupported aperture replay schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "aperture replay sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid replay source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    c6_contract = load_c6_contract(
        _bound_path(sources["c6_contract"], root=root, label="C6 contract"),
        root=root,
    )
    c6_receipt = _bound_json(
        sources["c6_receipt"], root=root, label="C6 receipt"
    )
    _require(
        c6_receipt.get("artifact_sha256")
        == sources["c6_receipt"]["artifact_sha256"]
        and c6_receipt.get("numeric_task_success") is False
        and int(c6_receipt["outcome"]["selected_piece_contact_steps"]) == 0,
        "C6 negative boundary changed",
    )
    closeout = _bound_json(
        sources["or6_closeout"], root=root, label="OR6 closeout"
    )
    _require(
        closeout.get("result")
        == "TASK_BOUNDED_JAW_APERTURE_CANDIDATE_PROMOTED_GLOBAL_MAPPING_FALSE"
        and closeout["identity"]["only_gripper_zero_offset_changed"] is True
        and closeout["proof_boundaries"]["global_mapping_approved"] is False,
        "OR6 promotion boundary changed",
    )
    replay = contract.get("replay")
    _require(
        isinstance(replay, dict)
        and replay.get("one_run_only") is True
        and replay.get(
            "reuse_c6_requested_gateway_sent_timestamps_and_identified_applied"
        )
        is True
        and replay.get("reuse_c6_initialization") is True
        and replay.get("reuse_c6_evaluator") is True
        and replay.get("reuse_c6_post_action_settle") is True
        and replay.get("preserve_source_row_order") is True
        and replay.get("preserve_source_timestamps") is True
        and replay.get("natural_contact_only") is True,
        "aperture replay identity widened",
    )
    forbidden = (
        "observed_state_after_initialization_allowed",
        "camera_update_after_initialization_allowed",
        "observed_grasp_or_release_marker_allowed",
        "latch_or_object_attachment_allowed",
        "support_projection_allowed",
        "terminal_endpoint_input_allowed",
        "action_clipping_smoothing_offset_retiming_or_ik_allowed",
        "actuator_plant_change_allowed",
        "contact_parameter_change_allowed",
        "object_parameter_change_allowed",
        "initialization_change_allowed",
        "camera_change_allowed",
    )
    _require(
        all(replay.get(field) is False for field in forbidden),
        "aperture replay assistance enabled",
    )
    policy = contract.get("proof_policy")
    _require(
        isinstance(policy, dict)
        and policy.get("matching_task_outcome_requires_all_c6_evaluator_gates")
        is True
        and policy.get("full_contact_fidelity_requires_validated_contact_material")
        is True
        and policy.get("contact_material_validated") is False
        and policy.get("global_mapping_approved") is False,
        "aperture replay proof policy widened",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict)
        and authority.get("simulator_replay") is True
        and not any(
            value
            for key, value in authority.items()
            if key != "simulator_replay"
        ),
        "aperture replay authority widened",
    )
    return contract, c6_contract


def _only_gripper_offset_changed(
    base: dict[str, Any],
    candidate: dict[str, Any],
    *,
    expected_baseline: float,
    expected_candidate: float,
) -> bool:
    left = copy.deepcopy(base)
    right = copy.deepcopy(candidate)
    left_joint = left["physical_adapter"]["joint_transform"]["joints"][-1]
    right_joint = right["physical_adapter"]["joint_transform"]["joints"][-1]
    if (
        left_joint["simulator_joint"] != "left_gripper"
        or right_joint["simulator_joint"] != "left_gripper"
        or float(left_joint["zero_offset"]) != expected_baseline
        or float(right_joint["zero_offset"]) != expected_candidate
    ):
        return False
    left_joint["zero_offset"] = expected_candidate
    return left == right


def _first_motion_and_jumps(
    positions: np.ndarray,
    *,
    motion_threshold: float,
    jump_threshold: float,
) -> dict[str, Any]:
    displacement = np.linalg.norm(positions[:, :2] - positions[0, :2], axis=1)
    jumps = np.linalg.norm(np.diff(positions[:, :2], axis=0), axis=1)
    moving = np.flatnonzero(displacement > motion_threshold)
    catastrophic = np.flatnonzero(jumps > jump_threshold)
    return {
        "first_planar_motion_over_1mm_sample": (
            int(moving[0]) if moving.size else None
        ),
        "maximum_planar_displacement_m": float(np.max(displacement)),
        "maximum_inter_sample_planar_jump_m": float(np.max(jumps)),
        "first_catastrophic_jump_sample": (
            int(catastrophic[0] + 1) if catastrophic.size else None
        ),
    }


def run_aperture_replay_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR7 one-run receipt already exists")
    contract, c6 = load_aperture_replay_contract(contract_path, root=root)
    source = c6["source"]
    arrays = {
        key: _tensor(
            _bound_path(source[key], root=root, label=f"C6 {key}"),
            source[key],
        )
        for key in (
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
    expected = contract["expected_identity"]
    _require(
        requested.shape
        == sent.shape
        == measured.shape
        == applied_physical.shape
        == (int(expected["row_count"]), int(expected["joint_count"]))
        and timestamps.shape == (int(expected["row_count"]),)
        and np.all(np.diff(timestamps) > 0.0),
        "OR7 source tensor alignment changed",
    )
    identity = {
        "recording_id": source["recording_id"] == expected["recording_id"],
        "requested": source["requested"]["sha256"] == expected["requested_sha256"],
        "gateway_sent": source["gateway_sent"]["sha256"]
        == expected["gateway_sent_sha256"],
        "timestamps": source["timestamps"]["sha256"] == expected["timestamps_sha256"],
        "identified_applied": source["identified_applied"]["sha256"]
        == expected["identified_applied_sha256"],
        "row_order": expected["row_order_preserved"] is True,
    }
    _require(all(identity.values()), "OR7 exact C6 identity changed")

    base_manifest = load_json_object(
        root / c6["lineage"]["joint_mapping_manifest"]["path"],
        label="C6 joint mapping manifest",
    )
    candidate_manifest = _bound_json(
        contract["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    _require(
        canonical_digest(candidate_manifest)
        == contract["sources"]["or6_candidate"]["canonical_sha256"],
        "OR6 candidate canonical hash changed",
    )
    candidate_change = contract["candidate_change"]
    candidate_config = candidate_manifest["candidate_config"]
    only_offset = _only_gripper_offset_changed(
        base_manifest["candidate_config"],
        candidate_config,
        expected_baseline=float(candidate_change["baseline_value"]),
        expected_candidate=float(candidate_change["candidate_value"]),
    )
    _require(only_offset, "OR7 candidate changed more than gripper zero offset")
    _require(
        canonical_digest(candidate_config)
        == candidate_change["candidate_config_sha256"],
        "OR7 candidate config hash changed",
    )
    replay_manifest = {"candidate_config": candidate_config}
    applied_model = physical_to_model(applied_physical, replay_manifest)
    initial_model = physical_to_model(measured[:1], replay_manifest)[0]

    endpoint = load_json_object(
        root / c6["lineage"]["initial_endpoint_receipt"]["path"],
        label="C6 initial endpoint receipt",
    )
    observed_initial = np.asarray(
        endpoint["observations"]["initial"]["world_position_m"],
        dtype=np.float64,
    )
    _require(
        np.allclose(
            observed_initial,
            np.asarray(c6["initialization"]["physical_d1_world_position_m"]),
            atol=0.0,
            rtol=0.0,
        ),
        "OR7 initial D1 observation changed",
    )

    model, _ = _compile_model(candidate_config, base_directory=None)
    joint_names = candidate_config["bindings"]["joint_names"]
    actuator_names = candidate_config["bindings"]["actuator_names"]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in actuator_names
    ]
    _require(min(joint_ids + actuator_ids) >= 0, "OR7 robot binding is incomplete")
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[item]) for item in joint_ids], dtype=np.int64
    )
    range_expansions = []
    maximum_expansion = float(c6["replay"]["maximum_joint_range_expansion_rad"])
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
        lower_expansion = max(0.0, float(original[0] - observed_minimum))
        upper_expansion = max(0.0, float(observed_maximum - original[1]))
        _require(
            max(lower_expansion, upper_expansion) <= maximum_expansion,
            f"OR7 trajectory exceeds bounded range union: {joint_names[index]}",
        )
        model.jnt_range[joint_id, 0] = min(float(original[0]), observed_minimum)
        model.jnt_range[joint_id, 1] = max(float(original[1]), observed_maximum)
        range_expansions.append(
            {
                "joint": joint_names[index],
                "original_range_rad": original.astype(float).tolist(),
                "effective_range_rad": model.jnt_range[joint_id].astype(float).tolist(),
                "lower_expansion_rad": lower_expansion,
                "upper_expansion_rad": upper_expansion,
            }
        )

    data = mujoco.MjData(model)
    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(selected_body >= 0 and selected_joint >= 0, "OR7 selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data.qpos[qpos_addresses] = initial_model
    data.ctrl[actuator_ids] = initial_model
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_z = float(data.qpos[selected_qpos + 2])
    upright = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7], dtype=np.float64
    ).copy()
    data.qpos[selected_qpos : selected_qpos + 2] = observed_initial[:2]
    data.qpos[selected_qpos + 2] = support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = applied_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = applied_model[0]
    mujoco.mj_forward(model, data)
    initial_height = float(data.xpos[selected_body][2])
    pieces = _piece_bodies(model)
    initial_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }
    timestep = float(model.opt.timestep)
    selected_contact_steps = 0
    first_selected_contact_sample: int | None = None
    contact_pairs: set[tuple[str, str]] = set()
    trace_rows: list[dict[str, Any]] = []

    def observe_contact(sample_index: int) -> int:
        nonlocal selected_contact_steps, first_selected_contact_sample
        count, pairs = _contact_counts(model, data, selected_body=selected_body)
        if count:
            selected_contact_steps += 1
            if first_selected_contact_sample is None:
                first_selected_contact_sample = sample_index
            contact_pairs.update(tuple(pair) for pair in pairs)
        return count

    def capture(sample_index: int) -> None:
        count = observe_contact(sample_index)
        trace_rows.append(
            {
                "sample_index": sample_index,
                "source_timestamp_seconds": float(timestamps[sample_index]),
                "requested_physical": requested[sample_index].astype(float).tolist(),
                "gateway_sent_physical": sent[sample_index].astype(float).tolist(),
                "plant_applied_physical": applied_physical[sample_index]
                .astype(float)
                .tolist(),
                "plant_applied_model": applied_model[sample_index].astype(float).tolist(),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).tolist(),
                "selected_pawn_tilt_degrees": _tilt(
                    _rotation(data, selected_body)
                ),
                "selected_jaw_contact_count": count,
            }
        )

    capture(0)
    maximum_timestamp_quantization_error = 0.0
    for index in range(1, len(applied_model)):
        dt = float(timestamps[index] - timestamps[index - 1])
        nstep = max(1, round(dt / timestep))
        maximum_timestamp_quantization_error = max(
            maximum_timestamp_quantization_error, abs(nstep * timestep - dt)
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
            observe_contact(index)
        capture(index)
    data.qpos[qpos_addresses] = applied_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = applied_model[-1]
    mujoco.mj_forward(model, data)
    settle_steps = round(
        float(c6["replay"]["post_action_settle_seconds"]) / timestep
    )
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
        observe_contact(len(applied_model) - 1)
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
        current_square_center(c6["initialization"]["destination_square"]),
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
    comparison_contract = contract["comparison"]
    dynamics = _first_motion_and_jumps(
        positions,
        motion_threshold=0.001,
        jump_threshold=float(
            comparison_contract[
                "catastrophic_inter_sample_planar_jump_threshold_m"
            ]
        ),
    )
    baseline_trace = _bound_json(
        contract["sources"]["c6_trace"], root=root, label="C6 trace"
    )
    baseline_positions = np.asarray(
        [row["selected_pawn_position_m"] for row in baseline_trace["rows"]],
        dtype=np.float64,
    )
    baseline_dynamics = _first_motion_and_jumps(
        baseline_positions,
        motion_threshold=0.001,
        jump_threshold=float(
            comparison_contract[
                "catastrophic_inter_sample_planar_jump_threshold_m"
            ]
        ),
    )
    c6_receipt = _bound_json(
        contract["sources"]["c6_receipt"], root=root, label="C6 receipt"
    )
    c6_error = float(c6_receipt["outcome"]["final_planar_center_error_m"])
    final_error_improvement = (c6_error - outcome["final_planar_center_error_m"]) / c6_error
    first_motion = dynamics["first_planar_motion_over_1mm_sample"]
    advancement = {
        "selected_jaw_contact_gained": selected_contact_steps > 0,
        "first_pawn_motion_later": (
            first_motion is not None
            and first_motion
            > int(comparison_contract["c6_first_planar_motion_over_1mm_sample"])
        ),
        "catastrophic_jump_eliminated": (
            baseline_dynamics["first_catastrophic_jump_sample"] is not None
            and dynamics["first_catastrophic_jump_sample"] is None
        ),
        "final_planar_error_improved": final_error_improvement
        >= float(
            comparison_contract[
                "minimum_final_planar_error_relative_improvement"
            ]
        ),
    }
    material_advancement = bool(any(advancement.values()))
    matching_task_outcome = bool(outcome["numeric_task_success"])
    full_contact_fidelity = bool(
        matching_task_outcome
        and contract["proof_policy"]["contact_material_validated"]
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    trace_path = output_directory / "trace.json"
    atomic_write_json(
        trace_path,
        {
            "schema_version": TRACE_SCHEMA,
            "rows": trace_rows,
            "post_action_settle_seconds": c6["replay"][
                "post_action_settle_seconds"
            ],
        },
    )
    try:
        trace_receipt_path = trace_path.relative_to(root).as_posix()
    except ValueError:
        trace_receipt_path = trace_path.resolve().as_posix()
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "source_identity": {
            **identity,
            "row_count": len(sent),
            "requested_sha256": source["requested"]["sha256"],
            "gateway_sent_sha256": source["gateway_sent"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "identified_applied_sha256": source["identified_applied"]["sha256"],
        },
        "candidate_identity": {
            "only_gripper_zero_offset_changed": only_offset,
            "baseline_value": candidate_change["baseline_value"],
            "candidate_value": candidate_change["candidate_value"],
            "candidate_config_sha256": canonical_digest(candidate_config),
        },
        "initialization": {
            "pawn_xy_m": observed_initial[:2].tolist(),
            "pawn_support_z_m": support_z,
            "robot_state_source": "C6 measured row zero only",
            "later_observed_state_rows_consumed": 0,
        },
        "runtime": {
            "engine": "cpu_mujoco_fp64",
            "timestep_seconds": timestep,
            "maximum_timestamp_quantization_error_seconds": maximum_timestamp_quantization_error,
            "natural_contact_only": True,
            "joint_range_expansions": range_expansions,
            "contact_pairs": [list(pair) for pair in sorted(contact_pairs)],
            "contact_material_validated": False,
            "observed_grasp_or_release_markers_consumed": 0,
            "camera_updates_consumed": 0,
            "endpoint_updates_consumed": 0,
        },
        "dynamics": {
            **dynamics,
            "first_selected_jaw_contact_sample": first_selected_contact_sample,
            "selected_jaw_contact_steps": selected_contact_steps,
        },
        "outcome": outcome,
        "comparison_to_c6": {
            "c6_dynamics": baseline_dynamics,
            "final_planar_error_relative_improvement": float(
                final_error_improvement
            ),
            "advancement_checks": advancement,
            "material_advancement": material_advancement,
        },
        "matching_task_outcome": matching_task_outcome,
        "full_contact_fidelity_promoted": full_contact_fidelity,
        "result": (
            "MATCHING_TASK_OUTCOME_CONTACT_MATERIAL_UNVALIDATED"
            if matching_task_outcome
            else (
                "MATERIAL_CAUSAL_ADVANCEMENT_TASK_NEGATIVE"
                if material_advancement
                else "NO_MATERIAL_CAUSAL_ADVANCEMENT_TASK_NEGATIVE"
            )
        ),
        "ledger": {
            "realized_physical_action_trajectory_to_matching_simulator_task_outcome": {
                "successes": int(matching_task_outcome),
                "attempts_including_immutable_c6": 2
            },
            "physical_task_attempts_added": 0,
            "sim_to_real_added": 0,
            "global_mapping_approved": False,
        },
        "trace": {
            "path": trace_receipt_path,
            "sha256": sha256_file(trace_path),
            "row_count": len(trace_rows),
        },
        "claim_boundary": (
            "One exact C6-action natural-contact simulator successor. Only the "
            "statically fit and no-refit-validated gripper zero-offset mapping "
            "changes. Contact material remains unvalidated and global mapping "
            "remains false."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "load_aperture_replay_contract",
    "run_aperture_replay_once",
]
