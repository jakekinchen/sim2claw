"""Freeze and run OR154's one exact-D1-center sensitivity replay."""

from __future__ import annotations

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
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path
from .observable_registration_measured_state_visual_twin import _range_union, _tilt_degrees
from .observable_registration_or34_canonical_yaw_reversion_replay import (
    load_canonical_yaw_reversion_replay_contract,
    verify_canonical_yaw_reversion_replay,
)
from .observable_registration_or34_coordinate_landmark_audit import (
    board_coordinate_to_scene_world,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import _candidate_config
from .pawn_bg_demo_sim import _piece_bodies
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .realized_action_outcome_mission import _contact_counts, _outcome


SCHEMA = "sim2claw.observable_registration_or153_exact_d1_center_replay_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_or153_exact_d1_center_replay_receipt.v1"
TRACE_SCHEMA = "sim2claw.observable_registration_or153_exact_d1_center_replay_trace.v1"
CLOSEOUT_SCHEMA = "sim2claw.observable_registration_or153_exact_d1_center_replay_closeout.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_or153_exact_d1_center_replay_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_or153_exact_d1_center_replay_v1"
CLOSEOUT_PATH = REPO_ROOT / "configs/decisions/observable_registration_or153_exact_d1_center_replay_v1_closeout.json"
EXECUTOR_LOG_PATH = REPO_ROOT / "docs/session-logs/226-executor-observable-registration-or154-exact-d1-center-replay.md"
BASELINE_BOARD_COORDINATE = [3.568645477294922, 0.48760929703712463]
EXACT_D1_BOARD_COORDINATE = [3.5, 0.5]
EXECUTION_BOUNDARY = {
    "simulator_replays": 1,
    "fits": 0,
    "searches": 0,
    "retries": 0,
    "renders": 0,
    "action_mutations": 0,
    "retimings": 0,
    "hardware_actions": 0,
    "paid_compute": False,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _gate_level_comparison(
    *, baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    baseline_gates = baseline["gates"]
    candidate_gates = candidate["gates"]
    _require(set(baseline_gates) == set(candidate_gates), "frozen task gate set changed")
    false_to_true = sorted(
        name
        for name, value in baseline_gates.items()
        if value is False and candidate_gates[name] is True
    )
    true_to_false = sorted(
        name
        for name, value in baseline_gates.items()
        if value is True and candidate_gates[name] is False
    )
    gate_flips = {
        name: f"{bool(baseline_gates[name])}->{bool(candidate_gates[name])}"
        for name in sorted(baseline_gates)
        if baseline_gates[name] != candidate_gates[name]
    }
    contact_preserved = bool(candidate_gates["selected_piece_contact"])
    numeric_task_success = bool(candidate["numeric_task_success"])
    _require(
        numeric_task_success == all(bool(value) for value in candidate_gates.values()),
        "numeric task success disagrees with frozen gates",
    )
    gate_level_advancement = (
        contact_preserved and bool(false_to_true) and not true_to_false
    )
    return {
        "gate_flips": gate_flips,
        "false_to_true_gates": false_to_true,
        "true_to_false_gate_regressions": true_to_false,
        "selected_piece_contact_preserved": contact_preserved,
        "numeric_task_success": numeric_task_success,
        "metric_only_improvement_accepted": False,
        "accepted_gate_level_advancement": bool(
            numeric_task_success or gate_level_advancement
        ),
    }


def _metric_deltas(
    *, baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, float]:
    return {
        "final_planar_center_error_reduction_m": float(
            baseline["final_planar_center_error_m"]
            - candidate["final_planar_center_error_m"]
        ),
        "final_upright_tilt_reduction_degrees": float(
            baseline["final_upright_tilt_degrees"]
            - candidate["final_upright_tilt_degrees"]
        ),
        "final_height_error_reduction_m": float(
            baseline["final_height_error_m"] - candidate["final_height_error_m"]
        ),
    }


def _assert_or153_clone_identity(
    contract: dict[str, Any], or153_contract: dict[str, Any]
) -> None:
    for name in ("or34_contract", "or34_receipt", "or34_trace", "or19_contract", "or13_scene"):
        _require(
            contract["sources"][name] == or153_contract["sources"][name],
            f"OR153 inherited source changed: {name}",
        )
    replay = contract["replay"]
    inherited = replay["preserved_or153_semantics"]
    expected = {
        "robot_driver": or153_contract["replay"]["robot_driver"],
        "observation_conditioned": or153_contract["replay"]["observation_conditioned"],
        "action_only_transfer": or153_contract["replay"]["action_only_transfer"],
        "row_count": or153_contract["replay"]["row_count"],
        "preserve_source_row_order": or153_contract["replay"]["preserve_source_row_order"],
        "preserve_source_timestamps": or153_contract["replay"]["preserve_source_timestamps"],
        "interpolate_only_between_adjacent_measured_rows_at_native_mujoco_timestep": or153_contract["replay"]["interpolate_only_between_adjacent_measured_rows_at_native_mujoco_timestep"],
        "natural_contact_only": or153_contract["replay"]["natural_contact_only"],
        "post_action_settle_seconds": or153_contract["replay"]["post_action_settle_seconds"],
        "candidate_yaw_relative_to_table_degrees": or153_contract["replay"]["candidate_yaw_relative_to_table_degrees"],
    }
    _require(inherited == expected, "OR153 replay semantics changed")


def load_exact_d1_center_replay_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR154 exact D1 center replay")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR154 contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    replay = contract["replay"]
    _require(
        replay["one_run_only"] is True
        and replay["clone_of"] == "OR153_OR34_CANONICAL_YAW_REVERSION_REPLAY_V1"
        and replay["sole_changed_factor"] == "selected_pawn_initial_board_coordinate"
        and replay["baseline_board_coordinate"] == BASELINE_BOARD_COORDINATE
        and replay["candidate_board_coordinate"] == EXACT_D1_BOARD_COORDINATE
        and replay["fit_search_retry_allowed"] is False,
        "OR154 replay identity widened",
    )
    forbidden = (
        "prototype_or_temporary_replay_allowed",
        "render_allowed",
        "action_mutation_allowed",
        "retiming_allowed",
        "object_pose_injection_allowed",
        "latch_or_attachment_allowed",
        "endpoint_injection_allowed",
        "model_solver_contact_object_range_or_evaluator_change_allowed",
    )
    _require(all(replay[name] is False for name in forbidden), "OR154 assistance enabled")
    acceptance = contract["acceptance"]
    _require(
        acceptance["numeric_task_success_is_accepted"] is True
        and acceptance["selected_piece_contact_must_remain_true"] is True
        and acceptance["minimum_false_to_true_frozen_task_gates"] == 1
        and acceptance["maximum_true_to_false_frozen_task_gate_regressions"] == 0
        and acceptance["metric_only_improvement_is_accepted"] is False,
        "OR154 gate-level acceptance changed",
    )
    _require(not any(contract["claim_limits"].values()), "OR154 claim boundary widened")
    or153_contract = load_canonical_yaw_reversion_replay_contract(
        _bound_path(contract["sources"]["or153_contract"], root=root, label="OR153 contract"),
        root=root,
    )
    _assert_or153_clone_identity(contract, or153_contract)
    or153_receipt = load_json_object(
        _bound_path(contract["sources"]["or153_receipt"], root=root, label="OR153 receipt"),
        label="OR153 receipt",
    )
    receipt_unsigned = {
        key: value for key, value in or153_receipt.items() if key != "artifact_sha256"
    }
    _require(
        or153_receipt["artifact_sha256"] == canonical_digest(receipt_unsigned)
        == contract["baseline"]["or153_receipt_artifact_sha256"],
        "OR153 receipt artifact digest changed",
    )
    _require(
        or153_receipt["natural_dynamics"]["outcome"]["gates"]
        == contract["baseline"]["gates"]
        and or153_receipt["natural_dynamics"]["outcome"]["numeric_task_success"]
        == contract["baseline"]["numeric_task_success"],
        "OR153 frozen gate baseline changed",
    )
    preserved = contract["preserved_state"]
    _require(
        or153_receipt["factor_isolation"]["physical_board_coordinate"]
        == BASELINE_BOARD_COORDINATE
        and or153_receipt["factor_isolation"]["candidate_yaw_relative_to_table_degrees"]
        == preserved["yaw_relative_to_table_degrees"]
        and or153_receipt["factor_isolation"]["support_z_preserved_from_or152_m"]
        == preserved["support_z_m"]
        and or153_receipt["factor_isolation"]["upright_quaternion_preserved_from_or152"]
        == preserved["upright_quaternion_wxyz"]
        and or153_receipt["source_identity"]["raw_measured_sha256"]
        == preserved["raw_measured_sha256"]
        and or153_receipt["source_identity"]["timestamps_sha256"]
        == preserved["timestamps_sha256"]
        and or153_receipt["source_identity"]["row_count"] == preserved["row_count"] == 531,
        "OR153 preserved state changed",
    )
    or153_trace = load_json_object(
        _bound_path(contract["sources"]["or153_trace"], root=root, label="OR153 trace"),
        label="OR153 trace",
    )
    _require(
        or153_trace.get("schema_version")
        == "sim2claw.observable_registration_or34_canonical_yaw_reversion_replay_trace.v1"
        and len(or153_trace.get("rows", [])) == 531
        and [row["sample_index"] for row in or153_trace["rows"]] == list(range(531)),
        "OR153 immutable trace identity changed",
    )
    scene = load_json_object(
        _bound_path(contract["sources"]["or13_scene"], root=root, label="OR13 scene"),
        label="OR13 scene",
    )
    _require(
        scene["simulation_estimates"]["robots"][0]["yaw_relative_to_table_degrees"]
        == -88.0,
        "OR154 canonical -88 degree yaw changed",
    )
    return contract


def run_exact_d1_center_replay(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not output_directory.exists(), "OR154 write-once output already exists")
    contract = load_exact_d1_center_replay_contract(contract_path, root=root)
    sources_before = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    or153 = verify_canonical_yaw_reversion_replay(
        output_directory=_bound_path(
            contract["sources"]["or153_receipt"], root=root, label="OR153 receipt"
        ).parent,
        closeout_path=_bound_path(
            contract["sources"]["or153_closeout"], root=root, label="OR153 closeout"
        ),
        root=root,
    )
    _require(
        or153["artifact_sha256"]
        == contract["baseline"]["or153_receipt_artifact_sha256"],
        "OR153 immutable baseline digest changed",
    )
    or153_trace = load_json_object(
        _bound_path(contract["sources"]["or153_trace"], root=root, label="OR153 trace"),
        label="OR153 trace",
    )
    or19, c6 = load_unilateral_push_dynamic_replay_contract(
        _bound_path(contract["sources"]["or19_contract"], root=root, label="OR19 contract"),
        root=root,
    )
    c6_loaded, candidate_config, measured_model, _ = _candidate_config(or19, root=root)
    _require(c6_loaded == c6, "C6 identity changed")
    scene_path = _bound_path(contract["sources"]["or13_scene"], root=root, label="OR13 scene")
    source = c6["source"]
    timestamps = np.fromfile(
        _bound_path(source["timestamps"], root=root, label="timestamps"),
        dtype=np.dtype(source["timestamps"]["dtype"]),
    ).reshape(source["timestamps"]["shape"])
    _require(measured_model.shape == (531, 6) and timestamps.shape == (531,), "trajectory shape changed")
    _require(bool(np.all(np.diff(timestamps) > 0.0)), "timestamps are not strictly increasing")
    _require(
        [float(row["source_timestamp_seconds"]) for row in or153_trace["rows"]]
        == timestamps.astype(float).tolist(),
        "OR153 trace timestamp correspondence changed",
    )

    model = _candidate_spec(scene_path, pawn_height_m=0.034, canonical_piece_reset=True).compile()
    joint_names = candidate_config["bindings"]["joint_names"]
    actuator_names = candidate_config["bindings"]["actuator_names"]
    joint_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in joint_names]
    actuator_ids = np.asarray(
        [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in actuator_names],
        dtype=np.int64,
    )
    _require(min(joint_ids + actuator_ids.tolist()) >= 0, "robot binding incomplete")
    qpos_addresses = np.asarray([int(model.jnt_qposadr[value]) for value in joint_ids], dtype=np.int64)
    dof_addresses = np.asarray([int(model.jnt_dofadr[value]) for value in joint_ids], dtype=np.int64)
    historical = load_json_object(
        _bound_path(or19["sources"]["historical_mapping_receipt"], root=root, label="historical mapping"),
        label="historical mapping",
    )
    range_expansions = _range_union(
        model=model,
        joint_ids=joint_ids,
        joint_names=joint_names,
        measured_model=measured_model,
        historical_ranges=historical["mapping"]["candidate"]["joint_range_envelope_rad"],
        maximum_gripper_expansion_rad=float(c6["replay"]["maximum_joint_range_expansion_rad"]),
    )
    _require(range_expansions == or153["factor_isolation"]["range_expansions"], "joint-range union changed")

    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free")
    _require(selected_body >= 0 and selected_joint >= 0, "selected pawn missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = measured_model[0]
    data.ctrl[actuator_ids] = measured_model[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    preserved_z = float(or153["factor_isolation"]["support_z_preserved_from_or152_m"])
    preserved_upright = np.asarray(
        or153["factor_isolation"]["upright_quaternion_preserved_from_or152"],
        dtype=np.float64,
    )
    _require(abs(float(data.qpos[selected_qpos + 2]) - preserved_z) <= 1e-12, "support Z changed")
    _require(
        np.max(np.abs(np.asarray(data.qpos[selected_qpos + 3:selected_qpos + 7]) - preserved_upright)) <= 1e-12,
        "upright quaternion changed",
    )
    baseline_coordinate = np.asarray(or153["factor_isolation"]["physical_board_coordinate"], dtype=np.float64)
    candidate_coordinate = np.asarray(contract["replay"]["candidate_board_coordinate"], dtype=np.float64)
    _require(baseline_coordinate.tolist() == BASELINE_BOARD_COORDINATE, "OR153 board coordinate changed")
    initial_world = board_coordinate_to_scene_world(candidate_coordinate, scene_path=scene_path)
    d1_center = np.asarray(current_square_center("d1", config_path=scene_path), dtype=np.float64)
    _require(np.max(np.abs(initial_world - d1_center)) <= 1e-12, "candidate is not exact D1 center")
    data.qpos[selected_qpos:selected_qpos + 2] = initial_world[:2]
    data.qpos[selected_qpos + 2] = preserved_z
    data.qpos[selected_qpos + 3:selected_qpos + 7] = preserved_upright
    data.qvel[selected_dof:selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = measured_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[0]
    mujoco.mj_forward(model, data)
    actual_initial = np.asarray(data.xpos[selected_body]).copy()
    _require(np.max(np.abs(actual_initial - np.asarray([*d1_center[:2], preserved_z]))) <= 1e-12, "exact D1 pose did not apply")
    initial_height = float(actual_initial[2])
    pieces = _piece_bodies(model)
    initial_piece_positions = {name: np.asarray(data.xpos[body_id]).copy() for name, body_id in pieces.items()}

    selected_contact_steps = 0
    first_selected_contact_sample: int | None = None
    trace_rows: list[dict[str, Any]] = []
    timestep = float(model.opt.timestep)
    maximum_quantization_error = 0.0

    def observe(sample_index: int) -> None:
        count, pairs = _contact_counts(model, data, selected_body=selected_body)
        position = np.asarray(data.xpos[selected_body]).copy()
        quaternion = np.asarray(data.xquat[selected_body]).copy()
        trace_rows.append(
            {
                "sample_index": sample_index,
                "source_timestamp_seconds": float(timestamps[sample_index]),
                "selected_pawn_position_m": position.tolist(),
                "selected_pawn_quaternion_wxyz": quaternion.tolist(),
                "selected_pawn_tilt_degrees": _tilt_degrees(quaternion),
                "selected_jaw_contact_count": count,
                "selected_jaw_contact_pairs": pairs,
            }
        )

    observe(0)
    for index in range(1, 531):
        dt = float(timestamps[index] - timestamps[index - 1])
        nstep = max(1, round(dt / timestep))
        maximum_quantization_error = max(maximum_quantization_error, abs(nstep * timestep - dt))
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
            count, _ = _contact_counts(model, data, selected_body=selected_body)
            selected_contact_steps += count
            if count and first_selected_contact_sample is None:
                first_selected_contact_sample = index
        observe(index)
    data.qpos[qpos_addresses] = measured_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[-1]
    mujoco.mj_forward(model, data)
    for _ in range(round(float(contract["replay"]["preserved_or153_semantics"]["post_action_settle_seconds"]) / timestep)):
        mujoco.mj_step(model, data)
        count, _ = _contact_counts(model, data, selected_body=selected_body)
        selected_contact_steps += count

    positions = np.asarray([row["selected_pawn_position_m"] for row in trace_rows], dtype=np.float64)
    displacement = np.linalg.norm(positions[:, :2] - actual_initial[:2], axis=1)
    moving = np.flatnonzero(displacement > 0.001)
    target = np.asarray(current_square_center(c6["initialization"]["destination_square"], config_path=scene_path), dtype=np.float64)
    final_position = np.asarray(data.xpos[selected_body]).copy()
    direction = target[:2] - actual_initial[:2]
    direction /= np.linalg.norm(direction)
    progress = float((final_position[:2] - actual_initial[:2]) @ direction)
    other_displacement = max(
        (
            float(np.linalg.norm(np.asarray(data.xpos[body_id]) - initial_piece_positions[name]))
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
    baseline_outcome = or153["natural_dynamics"]["outcome"]
    comparison = _gate_level_comparison(baseline=baseline_outcome, candidate=outcome)
    metric_deltas = _metric_deltas(baseline=baseline_outcome, candidate=outcome)
    sources_after = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    source_immutability = sources_before == sources_after
    _require(source_immutability, "bound source changed during OR154")
    if outcome["numeric_task_success"]:
        status = "PASS_NUMERIC_TASK_SUCCESS"
    elif comparison["accepted_gate_level_advancement"]:
        status = "PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE"
    else:
        status = "TERMINAL_NO_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT"
    output_directory.mkdir(parents=True, exist_ok=False)
    trace_path = output_directory / "trace.json"
    atomic_write_json(trace_path, {"schema_version": TRACE_SCHEMA, "rows": trace_rows})
    or153_initial = np.asarray(or153["factor_isolation"]["or153_initial_position_m"], dtype=np.float64)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "source_identity": {
            "raw_measured_sha256": source["initial_measured"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "row_count": 531,
            "row_order_preserved": True,
            "source_hashes_unchanged": source_immutability,
        },
        "factor_isolation": {
            "sole_changed_factor": contract["replay"]["sole_changed_factor"],
            "baseline_board_coordinate": baseline_coordinate.tolist(),
            "candidate_board_coordinate": candidate_coordinate.tolist(),
            "or153_initial_position_m": or153_initial.tolist(),
            "or154_initial_position_m": actual_initial.tolist(),
            "initial_xy_change_from_or153_m": float(np.linalg.norm(actual_initial[:2] - or153_initial[:2])),
            "candidate_xy_error_from_exact_d1_m": float(np.linalg.norm(actual_initial[:2] - d1_center[:2])),
            "yaw_relative_to_table_degrees_preserved_from_or153": -88.0,
            "support_z_preserved_from_or153_m": preserved_z,
            "upright_quaternion_preserved_from_or153": preserved_upright.tolist(),
            "range_expansions": range_expansions,
            "fit_search_retry_count": 0,
        },
        "natural_dynamics": {
            "first_selected_jaw_contact_sample": first_selected_contact_sample,
            "selected_jaw_contact_steps": selected_contact_steps,
            "first_motion_over_1mm_sample": int(moving[0]) if moving.size else None,
            "maximum_planar_displacement_m": float(np.max(displacement)),
            "maximum_height_above_initial_m": float(np.max(positions[:, 2] - initial_height)),
            "maximum_tilt_degrees": float(max(row["selected_pawn_tilt_degrees"] for row in trace_rows)),
            "signed_progress_toward_d2_m": progress,
            "maximum_timestamp_quantization_error_seconds": maximum_quantization_error,
            "outcome": outcome,
        },
        "immutable_or153_baseline": {
            "receipt_sha256": contract["sources"]["or153_receipt"]["sha256"],
            "trace_sha256": contract["sources"]["or153_trace"]["sha256"],
            "first_selected_jaw_contact_sample": or153["natural_dynamics"]["first_selected_jaw_contact_sample"],
            "first_motion_over_1mm_sample": or153["natural_dynamics"]["first_motion_over_1mm_sample"],
            "signed_progress_toward_d2_m": or153["natural_dynamics"]["signed_progress_toward_d2_m"],
            "outcome": baseline_outcome,
        },
        "gate_level_comparison": comparison,
        "metric_deltas_diagnostic_only": metric_deltas,
        "execution": EXECUTION_BOUNDARY,
        "trace": {"path": "trace.json"},
        "observation_conditioned": True,
        "action_only_transfer": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "claim_limits": contract["claim_limits"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def verify_exact_d1_center_replay(
    output_directory: Path = OUTPUT_DIRECTORY,
    closeout_path: Path = CLOSEOUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Read and hash-bind the later closeout and all canonical OR154 artifacts."""
    closeout = load_json_object(closeout_path, label="OR154 closeout")
    _require(closeout.get("schema_version") == CLOSEOUT_SCHEMA, "OR154 closeout schema changed")
    contract_path = _bound_path(closeout["contract"], root=root, label="OR154 contract")
    implementation_path = _bound_path(closeout["implementation"], root=root, label="OR154 implementation")
    executor_log_path = _bound_path(closeout["executor_log"], root=root, label="OR154 Executor log")
    receipt_path = _bound_path(closeout["receipt"], root=root, label="OR154 receipt")
    trace_path = _bound_path(closeout["trace"], root=root, label="OR154 trace")
    _require(contract_path == CONTRACT_PATH, "OR154 contract closeout path changed")
    _require(implementation_path == Path(__file__).resolve(), "OR154 implementation closeout path changed")
    _require(executor_log_path == EXECUTOR_LOG_PATH, "OR154 Executor log closeout path changed")
    _require(receipt_path == output_directory / "receipt.json", "OR154 receipt closeout path changed")
    contract = load_exact_d1_center_replay_contract(contract_path, root=root)
    receipt = load_json_object(receipt_path, label="OR154 receipt")
    _require(receipt.get("schema_version") == RECEIPT_SCHEMA, "OR154 receipt schema changed")
    unsigned = {key: value for key, value in receipt.items() if key != "artifact_sha256"}
    _require(receipt.get("artifact_sha256") == canonical_digest(unsigned), "OR154 receipt digest changed")
    _require(
        receipt["artifact_sha256"] == closeout["receipt"]["artifact_sha256"],
        "OR154 receipt artifact digest closeout binding changed",
    )
    _require(closeout.get("status") == receipt["status"], "OR154 closeout status disagrees with receipt")
    _require(
        receipt["status"]
        in {
            "PASS_NUMERIC_TASK_SUCCESS",
            "PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE",
            "TERMINAL_NO_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT",
        },
        "OR154 receipt status widened",
    )
    _require(trace_path == output_directory / receipt["trace"]["path"], "OR154 trace closeout path changed")
    trace = load_json_object(trace_path, label="OR154 trace")
    _require(trace.get("schema_version") == TRACE_SCHEMA, "OR154 trace schema changed")
    _require(len(trace.get("rows", [])) == closeout["trace"]["row_count"] == 531, "OR154 trace row count changed")
    _require([row["sample_index"] for row in trace["rows"]] == list(range(531)), "OR154 trace sample order changed")
    or153_trace = load_json_object(
        _bound_path(contract["sources"]["or153_trace"], root=root, label="OR153 trace"),
        label="OR153 trace",
    )
    _require(
        [row["source_timestamp_seconds"] for row in trace["rows"]]
        == [row["source_timestamp_seconds"] for row in or153_trace["rows"]],
        "OR154 timestamps differ from OR153",
    )
    _require(
        trace["rows"][0]["selected_pawn_position_m"]
        == receipt["factor_isolation"]["or154_initial_position_m"],
        "OR154 receipt and trace initialization disagree",
    )
    _require(receipt["factor_isolation"]["candidate_board_coordinate"] == EXACT_D1_BOARD_COORDINATE, "OR154 D1 coordinate changed")
    _require(receipt["factor_isolation"]["candidate_xy_error_from_exact_d1_m"] <= 1e-12, "OR154 initial XY is not exact D1")
    _require(receipt["factor_isolation"]["yaw_relative_to_table_degrees_preserved_from_or153"] == -88.0, "OR154 yaw changed")
    baseline = receipt["immutable_or153_baseline"]["outcome"]
    candidate = receipt["natural_dynamics"]["outcome"]
    _require(receipt["gate_level_comparison"] == _gate_level_comparison(baseline=baseline, candidate=candidate), "OR154 gate comparison changed")
    _require(receipt["execution"] == EXECUTION_BOUNDARY, "OR154 execution boundary changed")
    _require(receipt["source_identity"]["source_hashes_unchanged"] is True, "OR154 source immutability failed")
    _require(not any(receipt["claim_limits"].values()), "OR154 claim boundary widened")
    return receipt


__all__ = [
    "load_exact_d1_center_replay_contract",
    "run_exact_d1_center_replay",
    "verify_exact_d1_center_replay",
]
