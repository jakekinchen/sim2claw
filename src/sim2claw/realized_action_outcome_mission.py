"""Write-once C6 realized-action trajectory to simulator outcome replay."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import _piece_bodies
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.realized_action_outcome_mission_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_outcome_mission_receipt.v1"
TRACE_SCHEMA = "sim2claw.realized_action_outcome_mission_trace.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_outcome_mission_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "realized_action_outcome_mission_v1"


def _bound_file(
    root: Path, entry: Mapping[str, Any], label: str
) -> Path:
    path = root / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    return path


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="C6 mission contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported C6 mission contract")
    for key, entry in contract.get("source", {}).items():
        if isinstance(entry, dict) and "path" in entry:
            _bound_file(root, entry, f"source {key}")
    for key, entry in contract.get("lineage", {}).items():
        _bound_file(root, entry, f"lineage {key}")
    replay = contract.get("replay")
    if (
        not isinstance(replay, dict)
        or replay.get("one_run_only") is not True
        or replay.get("contact_model_validated") is not False
        or replay.get("preserve_source_row_order") is not True
        or replay.get("preserve_source_timestamps") is not True
    ):
        raise FactoryArtifactError("C6 replay boundary widened")
    forbidden_false = (
        "observed_state_after_initialization_allowed",
        "camera_update_after_initialization_allowed",
        "observed_grasp_or_release_marker_allowed",
        "latch_or_object_attachment_allowed",
        "support_projection_allowed",
        "terminal_endpoint_input_allowed",
        "action_clipping_smoothing_offset_retiming_or_ik_allowed",
    )
    if any(replay.get(key) is not False for key in forbidden_false):
        raise FactoryArtifactError("C6 forbidden input was enabled")
    authority = contract.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("simulator_replay") is not True
        or any(
            value
            for key, value in authority.items()
            if key != "simulator_replay"
        )
    ):
        raise FactoryArtifactError("C6 authority widened")
    if contract["source"]["gateway_sent"]["shape"] != [531, 6]:
        raise FactoryArtifactError("C6 exact action shape changed")
    return contract


def _tensor(path: Path, spec: Mapping[str, Any]) -> np.ndarray:
    shape = tuple(int(value) for value in spec["shape"])
    array = np.fromfile(path, dtype=np.dtype(str(spec["dtype"])))
    if array.size != math.prod(shape):
        raise FactoryArtifactError(f"C6 tensor shape rejected: {path}")
    result = array.reshape(shape)
    if not np.all(np.isfinite(result)):
        raise FactoryArtifactError(f"C6 tensor is non-finite: {path}")
    return result


def physical_to_model(
    physical: np.ndarray, manifest: Mapping[str, Any]
) -> np.ndarray:
    joints = manifest["candidate_config"]["physical_adapter"][
        "joint_transform"
    ]["joints"]
    names = manifest["candidate_config"]["bindings"]["joint_names"]
    if (
        physical.ndim != 2
        or physical.shape[1] != len(joints)
        or [row["simulator_joint"] for row in joints] != names
    ):
        raise FactoryArtifactError("C6 joint transform binding changed")
    output = np.empty_like(physical, dtype=np.float64)
    for index, joint in enumerate(joints):
        scale = float(joint["scale"])
        sign = float(joint["sign"])
        offset = float(joint["zero_offset"])
        if (
            not np.isfinite([scale, sign, offset]).all()
            or scale <= 0.0
            or sign not in (-1.0, 1.0)
        ):
            raise FactoryArtifactError("C6 joint transform is invalid")
        output[:, index] = physical[:, index] * scale * sign + offset
    return output


def _rotation(data: mujoco.MjData, body_id: int) -> np.ndarray:
    return np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3).copy()


def _tilt(rotation: np.ndarray) -> float:
    return math.degrees(
        math.acos(float(np.clip(rotation[2, 2], -1.0, 1.0)))
    )


def _wxyz(rotation: np.ndarray) -> np.ndarray:
    xyzw = Rotation.from_matrix(rotation).as_quat()
    return np.asarray([xyzw[3], xyzw[0], xyzw[1], xyzw[2]])


def _contact_counts(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    selected_body: int,
) -> tuple[int, list[list[str]]]:
    count = 0
    pairs: set[tuple[str, str]] = set()
    jaw_names = {"left_gripper", "left_moving_jaw_so101_v1"}
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
        selected_name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, selected_body)
            or f"body-{selected_body}"
        )
        if other_name in jaw_names:
            count += 1
            pairs.add(tuple(sorted((selected_name, other_name))))
    return count, [list(pair) for pair in sorted(pairs)]


def _outcome(
    *,
    data: mujoco.MjData,
    model: mujoco.MjModel,
    selected_body: int,
    selected_dof: int,
    initial_height: float,
    target: np.ndarray,
    other_displacement: float,
    selected_contact_steps: int,
    evaluator: Mapping[str, Any],
) -> dict[str, Any]:
    position = np.asarray(data.xpos[selected_body], dtype=np.float64).copy()
    rotation = _rotation(data, selected_body)
    velocity = np.asarray(
        data.qvel[selected_dof : selected_dof + 6], dtype=np.float64
    ).copy()
    center_error = float(np.linalg.norm(position[:2] - target[:2]))
    tilt = _tilt(rotation)
    height_error = abs(float(position[2] - initial_height))
    linear_speed = float(np.linalg.norm(velocity[:3]))
    angular_speed = float(np.linalg.norm(velocity[3:]))
    gates = {
        "composable_center": center_error
        <= float(evaluator["maximum_final_planar_center_error_m"]),
        "upright": tilt <= float(evaluator["maximum_upright_tilt_degrees"]),
        "other_pieces_stationary": other_displacement
        <= float(evaluator["maximum_other_piece_displacement_m"]),
        "settled_height": height_error
        <= float(evaluator["maximum_final_height_error_m"]),
        "settled_linear": linear_speed
        <= float(evaluator["maximum_final_linear_speed_m_s"]),
        "settled_angular": angular_speed
        <= float(evaluator["maximum_final_angular_speed_rad_s"]),
        "selected_piece_contact": selected_contact_steps > 0,
    }
    return {
        "final_position_m": position.tolist(),
        "target_position_m": target.tolist(),
        "final_planar_center_error_m": center_error,
        "final_upright_tilt_degrees": tilt,
        "final_height_error_m": height_error,
        "final_linear_speed_m_s": linear_speed,
        "final_angular_speed_rad_s": angular_speed,
        "maximum_other_piece_displacement_m": other_displacement,
        "selected_piece_contact_steps": selected_contact_steps,
        "gates": gates,
        "numeric_task_success": all(gates.values()),
    }


def run_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise FactoryArtifactError("C6 one-run receipt already exists")
    contract = load_contract(contract_path, root=root)
    source = contract["source"]
    arrays = {
        key: _tensor(_bound_file(root, source[key], key), source[key])
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
    if (
        requested.shape != sent.shape
        or sent.shape != applied_physical.shape
        or measured.shape != sent.shape
        or timestamps.shape != (len(sent),)
        or np.any(np.diff(timestamps) <= 0.0)
    ):
        raise FactoryArtifactError("C6 source tensor alignment changed")
    c4 = load_json_object(
        root / contract["lineage"]["c4_receipt"]["path"], label="C4 receipt"
    )
    if c4.get("artifact_sha256") != contract["lineage"]["c4_receipt"][
        "artifact_sha256"
    ]:
        raise FactoryArtifactError("C6 C4 artifact changed")
    sealed = [
        row
        for row in c4["trace_receipts"]
        if row["recording_id"] == source["recording_id"]
    ]
    if (
        len(sealed) != 1
        or sealed[0]["sent_raw_float32le_sha256"]
        != source["gateway_sent"]["sha256"]
        or sealed[0]["paths"]["identified_effective_plant_v1"]["applied"]["sha256"]
        != source["identified_applied"]["sha256"]
    ):
        raise FactoryArtifactError("C6 C4 sealed trace lineage changed")
    c5 = load_json_object(
        root / contract["lineage"]["c5_receipt"]["path"], label="C5 receipt"
    )
    if (
        c5.get("artifact_sha256") != contract["lineage"]["c5_receipt"][
            "artifact_sha256"
        ]
        or c5.get("selected_contact_model") is not None
        or c5["baseline"].get("may_promote_c6_outcome") is not False
    ):
        raise FactoryArtifactError("C6 contact admission changed")
    endpoint = load_json_object(
        root / contract["lineage"]["initial_endpoint_receipt"]["path"],
        label="C6 initial endpoint receipt",
    )
    observed_initial = np.asarray(
        endpoint["observations"]["initial"]["world_position_m"], dtype=np.float64
    )
    if not np.allclose(
        observed_initial,
        np.asarray(contract["initialization"]["physical_d1_world_position_m"]),
        atol=0.0,
        rtol=0.0,
    ):
        raise FactoryArtifactError("C6 initial D1 observation changed")
    manifest = load_json_object(
        root / contract["lineage"]["joint_mapping_manifest"]["path"],
        label="C6 joint mapping manifest",
    )
    applied_model = physical_to_model(applied_physical, manifest)
    initial_model = physical_to_model(measured[:1], manifest)[0]

    model, _ = _compile_model(
        manifest["candidate_config"], base_directory=None
    )
    joint_names = manifest["candidate_config"]["bindings"]["joint_names"]
    actuator_names = manifest["candidate_config"]["bindings"]["actuator_names"]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in actuator_names
    ]
    if min(joint_ids + actuator_ids) < 0:
        raise FactoryArtifactError("C6 current workcell robot binding is incomplete")
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[item]) for item in joint_ids], dtype=np.int64
    )
    range_expansions = []
    maximum_expansion = float(
        contract["replay"]["maximum_joint_range_expansion_rad"]
    )
    for index, joint_id in enumerate(joint_ids):
        if not model.jnt_limited[joint_id]:
            continue
        observed_minimum = min(
            float(np.min(applied_model[:, index])),
            float(initial_model[index]),
        )
        observed_maximum = max(
            float(np.max(applied_model[:, index])),
            float(initial_model[index]),
        )
        original = model.jnt_range[joint_id].copy()
        lower_expansion = max(0.0, float(original[0] - observed_minimum))
        upper_expansion = max(0.0, float(observed_maximum - original[1]))
        if max(lower_expansion, upper_expansion) > maximum_expansion:
            raise FactoryArtifactError(
                f"C6 applied trajectory exceeds bounded range union: {joint_names[index]}"
            )
        model.jnt_range[joint_id, 0] = min(
            float(original[0]), observed_minimum
        )
        model.jnt_range[joint_id, 1] = max(
            float(original[1]), observed_maximum
        )
        range_expansions.append(
            {
                "joint": joint_names[index],
                "original_range_rad": original.astype(float).tolist(),
                "effective_range_rad": model.jnt_range[joint_id]
                .astype(float)
                .tolist(),
                "lower_expansion_rad": lower_expansion,
                "upper_expansion_rad": upper_expansion,
            }
        )
    data = mujoco.MjData(model)
    selected_name = contract["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise FactoryArtifactError("C6 selected pawn is missing")
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
    contact_pairs: set[tuple[str, str]] = set()
    trace_rows = []

    def capture(sample_index: int) -> None:
        nonlocal selected_contact_steps
        count, pairs = _contact_counts(
            model, data, selected_body=selected_body
        )
        if count:
            selected_contact_steps += 1
            contact_pairs.update(tuple(pair) for pair in pairs)
        trace_rows.append(
            {
                "sample_index": sample_index,
                "source_timestamp_seconds": float(timestamps[sample_index]),
                "requested_physical": requested[sample_index].astype(float).tolist(),
                "gateway_sent_physical": sent[sample_index].astype(float).tolist(),
                "plant_applied_physical": applied_physical[sample_index].astype(float).tolist(),
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
            count, pairs = _contact_counts(
                model, data, selected_body=selected_body
            )
            if count:
                selected_contact_steps += 1
                contact_pairs.update(tuple(pair) for pair in pairs)
        capture(index)
    data.qpos[qpos_addresses] = applied_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = applied_model[-1]
    mujoco.mj_forward(model, data)
    settle_steps = round(
        float(contract["replay"]["post_action_settle_seconds"]) / timestep
    )
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
        count, pairs = _contact_counts(
            model, data, selected_body=selected_body
        )
        if count:
            selected_contact_steps += 1
            contact_pairs.update(tuple(pair) for pair in pairs)
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
        current_square_center(contract["initialization"]["destination_square"]),
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
        evaluator=contract["evaluator"],
    )
    promotable = bool(
        outcome["numeric_task_success"]
        and contract["replay"]["contact_model_validated"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    trace_path = output_directory / "trace.json"
    atomic_write_json(
        trace_path,
        {
            "schema_version": TRACE_SCHEMA,
            "rows": trace_rows,
            "post_action_settle_seconds": contract["replay"][
                "post_action_settle_seconds"
            ],
        },
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "source_identity": {
            "recording_id": source["recording_id"],
            "gateway_sent_shape": list(sent.shape),
            "gateway_sent_dtype": str(sent.dtype),
            "gateway_sent_sha256": source["gateway_sent"]["sha256"],
            "requested_sha256": source["requested"]["sha256"],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "identified_applied_sha256": source["identified_applied"]["sha256"],
            "row_order_preserved": True,
        },
        "initialization": {
            "pawn_xy_source": contract["initialization"]["pawn_xy_source"],
            "pawn_xy_m": observed_initial[:2].tolist(),
            "pawn_support_z_m": support_z,
            "robot_state_source": "measured_row_zero_only",
            "later_observed_state_rows_consumed": 0,
        },
        "runtime": {
            "engine": "cpu_mujoco_fp64",
            "timestep_seconds": timestep,
            "maximum_timestamp_quantization_error_seconds": maximum_timestamp_quantization_error,
            "natural_contact_only": True,
            "joint_range_source": contract["replay"]["joint_range_source"],
            "joint_range_expansions": range_expansions,
            "contact_pairs": [list(pair) for pair in sorted(contact_pairs)],
            "contact_model_validated": False,
            "observed_grasp_or_release_markers_consumed": 0,
            "camera_updates_consumed": 0,
            "endpoint_updates_consumed": 0,
        },
        "outcome": outcome,
        "numeric_task_success": bool(outcome["numeric_task_success"]),
        "promotable_mission_success": promotable,
        "verdict": (
            "NUMERIC_PASS_NONPROMOTABLE_CONTACT_UNVALIDATED"
            if outcome["numeric_task_success"]
            else "TERMINAL_MISSION_NEGATIVE"
        ),
        "ledger": {
            "realized_gateway_sent_action_trajectory_real_to_sim": {
                "successes": int(promotable),
                "attempts": 1,
                "numeric_successes_nonpromotable": int(
                    outcome["numeric_task_success"] and not promotable
                ),
            },
            "physical_task_attempts_added": 0,
            "sim_to_real_added": 0,
        },
        "trace": {
            "path": trace_path.relative_to(root).as_posix(),
            "sha256": sha256_file(trace_path),
            "row_count": len(trace_rows),
        },
        "claim_boundary": (
            "One write-once simulator replay of the exact retained physical "
            "gateway-sent action trajectory through the C4 validated effective "
            "joint plant and natural current-MuJoCo contact. C5 found no "
            "validated contact model, so even a numerical task pass is not "
            "promotable as the requested action-to-outcome evidence rung."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt
