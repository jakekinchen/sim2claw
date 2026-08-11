"""Run OR153's single canonical-yaw reversion falsification replay."""

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
from .observable_registration_measured_state_visual_twin import (
    _range_union,
    _tilt_degrees,
    load_measured_state_visual_twin_contract,
)
from .observable_registration_or34_board_coordinate_initialization_replay import (
    _metric_comparison,
    verify_board_coordinate_initialization_replay,
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


SCHEMA = "sim2claw.observable_registration_or34_canonical_yaw_reversion_replay_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_or34_canonical_yaw_reversion_replay_receipt.v1"
TRACE_SCHEMA = "sim2claw.observable_registration_or34_canonical_yaw_reversion_replay_trace.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_or34_canonical_yaw_reversion_replay_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_or34_canonical_yaw_reversion_replay_v1"
CLOSEOUT_PATH = REPO_ROOT / "configs/decisions/observable_registration_or34_canonical_yaw_reversion_replay_v1_closeout.json"
EXPECTED_SCENE_DIFF = {
    "path": "simulation_estimates.robots[0].yaw_relative_to_table_degrees",
    "before": -82.0,
    "after": -88.0,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _semantic_differences(
    before: Any, after: Any, *, path: str = ""
) -> list[dict[str, Any]]:
    """Return deterministic leaf-level semantic JSON differences."""
    if isinstance(before, dict) and isinstance(after, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            if key not in before:
                differences.append({"path": child, "before": None, "after": after[key]})
            elif key not in after:
                differences.append({"path": child, "before": before[key], "after": None})
            else:
                differences.extend(_semantic_differences(before[key], after[key], path=child))
        return differences
    if isinstance(before, list) and isinstance(after, list):
        differences = []
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before):
                differences.append({"path": child, "before": None, "after": after[index]})
            elif index >= len(after):
                differences.append({"path": child, "before": before[index], "after": None})
            else:
                differences.extend(_semantic_differences(before[index], after[index], path=child))
        return differences
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def audit_scene_semantic_diff(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> list[dict[str, Any]]:
    before = load_json_object(
        _bound_path(contract["sources"]["or18_scene"], root=root, label="OR18 scene"),
        label="OR18 scene",
    )
    after = load_json_object(
        _bound_path(contract["sources"]["or13_scene"], root=root, label="OR13 scene"),
        label="OR13 scene",
    )
    differences = _semantic_differences(before, after)
    _require(differences == [EXPECTED_SCENE_DIFF], "scene sources are not an exact one-field yaw diff")
    return differences


def load_canonical_yaw_reversion_replay_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR153 canonical yaw replay")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR153 contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    replay = contract["replay"]
    _require(
        replay["one_run_only"] is True
        and replay["robot_driver"] == "raw_follower_actual_position_degrees"
        and replay["observation_conditioned"] is True
        and replay["action_only_transfer"] is False
        and replay["row_count"] == 531
        and replay["sole_changed_factor"] == "left_robot_base_yaw_relative_to_table_degrees"
        and replay["baseline_yaw_relative_to_table_degrees"] == -82.0
        and replay["candidate_yaw_relative_to_table_degrees"] == -88.0
        and replay["natural_contact_only"] is True
        and replay["fit_search_retry_allowed"] is False,
        "OR153 replay identity widened",
    )
    forbidden = (
        "object_pose_injection_allowed",
        "latch_or_attachment_allowed",
        "endpoint_injection_allowed",
        "action_state_timestamp_model_solver_contact_object_or_evaluator_change_allowed",
    )
    _require(all(replay[name] is False for name in forbidden), "OR153 assistance enabled")
    _require(not any(contract["claim_limits"].values()), "OR153 claim boundary widened")
    audit_scene_semantic_diff(contract, root=root)
    return contract


def run_canonical_yaw_reversion_replay(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR153 write-once receipt already exists")
    contract = load_canonical_yaw_reversion_replay_contract(contract_path, root=root)
    sources_before = {
        name: sha256_file(root / binding["path"])
        for name, binding in contract["sources"].items()
    }
    or152 = verify_board_coordinate_initialization_replay(
        output_directory=_bound_path(
            contract["sources"]["or152_receipt"], root=root, label="OR152 receipt"
        ).parent,
        closeout_path=_bound_path(contract["sources"]["or152_closeout"], root=root, label="OR152 closeout"),
    )
    _require(or152["status"] == "TERMINAL_NO_TASK_OUTCOME_METRIC_ADVANCEMENT", "OR152 baseline changed")
    or34_contract = load_measured_state_visual_twin_contract(
        _bound_path(contract["sources"]["or34_contract"], root=root, label="OR34 contract"),
        root=root,
    )
    del or34_contract
    or34_receipt = load_json_object(
        _bound_path(contract["sources"]["or34_receipt"], root=root, label="OR34 receipt"),
        label="OR34 receipt",
    )
    or34_trace = load_json_object(
        _bound_path(contract["sources"]["or34_trace"], root=root, label="OR34 trace"),
        label="OR34 trace",
    )
    or151_receipt = load_json_object(
        _bound_path(contract["sources"]["or151_receipt"], root=root, label="OR151 receipt"),
        label="OR151 receipt",
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
        [float(row["source_timestamp_seconds"]) for row in or34_trace["rows"]]
        == timestamps.astype(float).tolist(),
        "OR34 timestamp correspondence changed",
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
    settled_z = float(data.qpos[selected_qpos + 2])
    settled_upright = np.asarray(data.qpos[selected_qpos + 3:selected_qpos + 7]).copy()
    preserved_z = float(or152["factor_isolation"]["support_z_unchanged_from_or34_m"])
    preserved_upright = np.asarray(or152["factor_isolation"]["upright_quaternion_unchanged_from_or34_settle"], dtype=np.float64)
    _require(abs(settled_z - preserved_z) <= 1e-12, "support Z changed before replay")
    _require(np.max(np.abs(settled_upright - preserved_upright)) <= 1e-12, "upright quaternion changed before replay")
    board_coordinate = np.asarray(or151_receipt["coordinate_audit"]["physical_board_coordinate"], dtype=np.float64)
    initial_world = board_coordinate_to_scene_world(board_coordinate, scene_path=scene_path)
    or152_initial = np.asarray(or152["factor_isolation"]["or152_initial_position_m"], dtype=np.float64)
    _require(np.max(np.abs(initial_world[:2] - or152_initial[:2])) <= 1e-12, "transported board coordinate changed")
    data.qpos[selected_qpos:selected_qpos + 2] = initial_world[:2]
    data.qpos[selected_qpos + 2] = preserved_z
    data.qpos[selected_qpos + 3:selected_qpos + 7] = preserved_upright
    data.qvel[selected_dof:selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = measured_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[0]
    mujoco.mj_forward(model, data)
    actual_initial = np.asarray(data.xpos[selected_body]).copy()
    _require(np.max(np.abs(actual_initial - or152_initial)) <= 1e-12, "OR152 initial pawn pose was not preserved")
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
        trace_rows.append({
            "sample_index": sample_index,
            "source_timestamp_seconds": float(timestamps[sample_index]),
            "selected_pawn_position_m": position.tolist(),
            "selected_pawn_quaternion_wxyz": quaternion.tolist(),
            "selected_pawn_tilt_degrees": _tilt_degrees(quaternion),
            "selected_jaw_contact_count": count,
            "selected_jaw_contact_pairs": pairs,
        })

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
    for _ in range(round(float(contract["replay"]["post_action_settle_seconds"]) / timestep)):
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
        (float(np.linalg.norm(np.asarray(data.xpos[body_id]) - initial_piece_positions[name])) for name, body_id in pieces.items() if name != selected_name),
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
    or152_baseline = or152["natural_dynamics"]["outcome"]
    comparison = _metric_comparison(contract=contract, baseline=or152_baseline, candidate=outcome)
    or34_baseline = or34_receipt["natural_dynamics"]["outcome"]
    or34_comparison = _metric_comparison(contract=contract, baseline=or34_baseline, candidate=outcome)
    sources_after = {name: sha256_file(root / binding["path"]) for name, binding in contract["sources"].items()}
    source_immutability = sources_before == sources_after
    _require(source_immutability, "bound source changed during OR153")
    status = "PASS_TASK_OUTCOME_METRIC_ADVANCEMENT" if comparison["accepted_task_outcome_metric_advancement"] else "TERMINAL_NO_TASK_OUTCOME_METRIC_ADVANCEMENT"
    output_directory.mkdir(parents=True, exist_ok=False)
    trace_path = output_directory / "trace.json"
    atomic_write_json(trace_path, {"schema_version": TRACE_SCHEMA, "rows": trace_rows})
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
        "scene_semantic_diff": audit_scene_semantic_diff(contract, root=root),
        "factor_isolation": {
            "sole_changed_factor": contract["replay"]["sole_changed_factor"],
            "baseline_yaw_relative_to_table_degrees": -82.0,
            "candidate_yaw_relative_to_table_degrees": -88.0,
            "physical_board_coordinate": board_coordinate.tolist(),
            "or152_initial_position_m": or152_initial.tolist(),
            "or153_initial_position_m": actual_initial.tolist(),
            "initial_pose_max_abs_change_from_or152": float(np.max(np.abs(actual_initial - or152_initial))),
            "support_z_preserved_from_or152_m": preserved_z,
            "upright_quaternion_preserved_from_or152": preserved_upright.tolist(),
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
        "immutable_or152_baseline": {
            "first_selected_jaw_contact_sample": or152["natural_dynamics"]["first_selected_jaw_contact_sample"],
            "first_motion_over_1mm_sample": or152["natural_dynamics"]["first_motion_over_1mm_sample"],
            "signed_progress_toward_d2_m": or152["natural_dynamics"]["signed_progress_toward_d2_m"],
            "outcome": or152_baseline,
        },
        "immutable_or34_baseline": {
            "first_selected_jaw_contact_sample": or34_receipt["natural_dynamics"]["first_selected_jaw_contact_sample"],
            "first_motion_over_1mm_sample": or34_receipt["natural_dynamics"]["first_motion_over_1mm_sample"],
            "signed_progress_toward_d2_m": or34_receipt["natural_dynamics"]["signed_progress_toward_d2_m"],
            "outcome": or34_baseline,
        },
        "task_outcome_metric_comparison": comparison,
        "or34_task_outcome_metric_comparison": or34_comparison,
        "execution": {"simulator_replays": 1, "fits": 0, "searches": 0, "retries": 0, "hardware_actions": 0, "paid_compute": False},
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


def verify_canonical_yaw_reversion_replay(
    output_directory: Path = OUTPUT_DIRECTORY,
    closeout_path: Path = CLOSEOUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    closeout = load_json_object(closeout_path, label="OR153 closeout")
    _require(
        closeout.get("schema_version")
        == "sim2claw.observable_registration_or34_canonical_yaw_reversion_replay_closeout.v1",
        "OR153 closeout schema changed",
    )
    _require(
        closeout.get("status") == "PASS_TASK_OUTCOME_METRIC_ADVANCEMENT_TASK_NEGATIVE",
        "OR153 closeout status changed",
    )
    contract_path = _bound_path(closeout["contract"], root=root, label="OR153 contract")
    implementation_path = _bound_path(
        closeout["implementation"], root=root, label="OR153 implementation"
    )
    receipt_path = _bound_path(closeout["receipt"], root=root, label="OR153 receipt")
    trace_path = _bound_path(closeout["trace"], root=root, label="OR153 trace")
    _bound_path(closeout["executor_log"], root=root, label="OR153 Executor log")
    _require(contract_path == CONTRACT_PATH, "OR153 contract closeout path changed")
    _require(implementation_path == Path(__file__), "OR153 implementation closeout path changed")
    _require(
        receipt_path == output_directory / "receipt.json",
        "OR153 receipt closeout path changed",
    )
    receipt = load_json_object(receipt_path, label="OR153 receipt")
    _require(receipt.get("schema_version") == RECEIPT_SCHEMA, "OR153 receipt schema changed")
    observed_digest = receipt.get("artifact_sha256")
    unsigned = {key: value for key, value in receipt.items() if key != "artifact_sha256"}
    _require(observed_digest == canonical_digest(unsigned), "OR153 receipt digest changed")
    _require(
        observed_digest == closeout["receipt"]["artifact_sha256"],
        "OR153 receipt artifact digest closeout binding changed",
    )
    _require(
        trace_path == output_directory / receipt["trace"]["path"],
        "OR153 trace closeout path changed",
    )
    trace = load_json_object(trace_path, label="OR153 trace")
    _require(trace.get("schema_version") == TRACE_SCHEMA, "OR153 trace schema changed")
    _require(
        len(trace.get("rows", [])) == closeout["trace"]["row_count"] == 531,
        "OR153 trace row count changed",
    )
    _require([row["sample_index"] for row in trace["rows"]] == list(range(531)), "OR153 trace sample order changed")
    _require(trace["rows"][0]["selected_pawn_position_m"] == receipt["factor_isolation"]["or153_initial_position_m"], "OR153 receipt and trace initialization disagree")
    _require(receipt["scene_semantic_diff"] == [EXPECTED_SCENE_DIFF], "OR153 semantic diff changed")
    _require(receipt["factor_isolation"]["initial_pose_max_abs_change_from_or152"] == 0.0, "OR152 initial pose not preserved")
    _require(receipt["execution"] == {"simulator_replays": 1, "fits": 0, "searches": 0, "retries": 0, "hardware_actions": 0, "paid_compute": False}, "OR153 execution boundary changed")
    _require(receipt["source_identity"]["source_hashes_unchanged"] is True, "OR153 source immutability failed")
    return receipt


__all__ = [
    "audit_scene_semantic_diff",
    "load_canonical_yaw_reversion_replay_contract",
    "run_canonical_yaw_reversion_replay",
    "verify_canonical_yaw_reversion_replay",
]
