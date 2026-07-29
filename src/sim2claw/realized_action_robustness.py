"""Deterministic C7 challenger robustness for the immutable C6 outcome."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

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
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import _piece_bodies
from .realized_action_outcome_mission import (
    _contact_counts,
    _outcome,
    physical_to_model,
)
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.realized_action_robustness_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_robustness_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_robustness_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT / "outputs" / "realized_action_robustness_v1" / "receipt.json"
)


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
    contract = load_json_object(path, label="C7 robustness contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported C7 robustness contract")
    for key, entry in contract.get("sources", {}).items():
        _bound_file(root, entry, key)
    for entry in contract.get("challenger_paths", []):
        _bound_file(root, entry, str(entry.get("path_id")))
    if [row.get("path_id") for row in contract["challenger_paths"]] != [
        "direct_target",
        "diagnostic_zoh_0p11s",
    ]:
        raise FactoryArtifactError("C7 challenger paths changed")
    if (
        contract.get("uncertainty", {}).get("unknown_dimensions_randomized")
        is not False
        or not all(contract.get("rules", {}).values())
    ):
        raise FactoryArtifactError("C7 uncertainty or rules widened")
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
        raise FactoryArtifactError("C7 authority widened")
    return contract


def _tensor(path: Path, spec: Mapping[str, Any]) -> np.ndarray:
    shape = tuple(int(value) for value in spec["shape"])
    array = np.fromfile(path, dtype=np.dtype(str(spec["dtype"])))
    if array.size != math.prod(shape):
        raise FactoryArtifactError(f"C7 tensor shape changed: {path}")
    result = array.reshape(shape)
    if not np.all(np.isfinite(result)):
        raise FactoryArtifactError(f"C7 tensor is non-finite: {path}")
    return result


def _simulate(
    *,
    applied_physical: np.ndarray,
    timestamps: np.ndarray,
    initial_measured: np.ndarray,
    manifest: Mapping[str, Any],
    c6: Mapping[str, Any],
) -> dict[str, Any]:
    applied_model = physical_to_model(applied_physical, manifest)
    initial_model = physical_to_model(initial_measured[:1], manifest)[0]
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
        raise FactoryArtifactError("C7 robot binding is incomplete")
    qpos = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids], dtype=np.int64
    )
    dof = np.asarray(
        [int(model.jnt_dofadr[item]) for item in joint_ids], dtype=np.int64
    )
    maximum_expansion = float(c6["replay"]["maximum_joint_range_expansion_rad"])
    expansions = []
    for index, joint_id in enumerate(joint_ids):
        if not model.jnt_limited[joint_id]:
            continue
        original = model.jnt_range[joint_id].copy()
        observed_minimum = min(
            float(np.min(applied_model[:, index])), float(initial_model[index])
        )
        observed_maximum = max(
            float(np.max(applied_model[:, index])), float(initial_model[index])
        )
        lower = max(0.0, float(original[0] - observed_minimum))
        upper = max(0.0, float(observed_maximum - original[1]))
        if max(lower, upper) > maximum_expansion:
            raise FactoryArtifactError(
                f"C7 challenger exceeds C6 range union: {joint_names[index]}"
            )
        model.jnt_range[joint_id, 0] = min(float(original[0]), observed_minimum)
        model.jnt_range[joint_id, 1] = max(float(original[1]), observed_maximum)
        expansions.append(
            {
                "joint": joint_names[index],
                "lower_expansion_rad": lower,
                "upper_expansion_rad": upper,
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
    if selected_body < 0 or selected_joint < 0:
        raise FactoryArtifactError("C7 selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data.qpos[qpos] = initial_model
    data.ctrl[actuator_ids] = initial_model
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    initial_world = np.asarray(
        c6["initialization"]["physical_d1_world_position_m"], dtype=np.float64
    )
    support_z = float(data.qpos[selected_qpos + 2])
    upright = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7], dtype=np.float64
    ).copy()
    data.qpos[selected_qpos : selected_qpos + 2] = initial_world[:2]
    data.qpos[selected_qpos + 2] = support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos] = applied_model[0]
    data.qvel[dof] = 0.0
    data.ctrl[actuator_ids] = applied_model[0]
    mujoco.mj_forward(model, data)
    initial_height = float(data.xpos[selected_body][2])
    pieces = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }
    timestep = float(model.opt.timestep)
    contact_steps = 0
    contact_pairs: set[tuple[str, str]] = set()
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
            data.qpos[qpos] = pose
            data.qvel[dof] = velocity
            data.ctrl[actuator_ids] = pose
            mujoco.mj_forward(model, data)
            mujoco.mj_step(model, data)
            count, pairs = _contact_counts(
                model, data, selected_body=selected_body
            )
            if count:
                contact_steps += 1
                contact_pairs.update(tuple(pair) for pair in pairs)
    data.qpos[qpos] = applied_model[-1]
    data.qvel[dof] = 0.0
    data.ctrl[actuator_ids] = applied_model[-1]
    mujoco.mj_forward(model, data)
    for _ in range(
        round(float(c6["replay"]["post_action_settle_seconds"]) / timestep)
    ):
        mujoco.mj_step(model, data)
        count, pairs = _contact_counts(
            model, data, selected_body=selected_body
        )
        if count:
            contact_steps += 1
            contact_pairs.update(tuple(pair) for pair in pairs)
    other_displacement = max(
        (
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_positions[name]
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
        target=np.asarray(
            current_square_center(c6["initialization"]["destination_square"]),
            dtype=np.float64,
        ),
        other_displacement=other_displacement,
        selected_contact_steps=contact_steps,
        evaluator=c6["evaluator"],
    )
    return {
        "outcome": outcome,
        "maximum_timestamp_quantization_error_seconds": maximum_quantization_error,
        "joint_range_expansions": expansions,
        "contact_pairs": [list(pair) for pair in sorted(contact_pairs)],
    }


def evaluate(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    c6 = load_json_object(
        root / contract["sources"]["c6_contract"]["path"], label="C6 contract"
    )
    c6_receipt = load_json_object(
        root / contract["sources"]["c6_receipt"]["path"], label="C6 receipt"
    )
    if c6_receipt.get("artifact_sha256") != contract["sources"]["c6_receipt"][
        "artifact_sha256"
    ]:
        raise FactoryArtifactError("C6 artifact changed")
    c4 = load_json_object(
        root / contract["sources"]["c4_receipt"]["path"], label="C4 receipt"
    )
    if c4.get("artifact_sha256") != contract["sources"]["c4_receipt"][
        "artifact_sha256"
    ]:
        raise FactoryArtifactError("C4 artifact changed")
    timestamps_spec = c6["source"]["timestamps"]
    measured_spec = c6["source"]["initial_measured"]
    timestamps = _tensor(
        _bound_file(root, timestamps_spec, "timestamps"), timestamps_spec
    )
    measured = _tensor(
        _bound_file(root, measured_spec, "initial measured"), measured_spec
    )
    manifest = load_json_object(
        root / c6["lineage"]["joint_mapping_manifest"]["path"],
        label="C7 mapping manifest",
    )
    challengers = []
    for specification in contract["challenger_paths"]:
        applied = _tensor(
            _bound_file(root, specification, specification["path_id"]),
            specification,
        )
        result = _simulate(
            applied_physical=applied,
            timestamps=timestamps,
            initial_measured=measured,
            manifest=manifest,
            c6=c6,
        )
        challengers.append(
            {
                "path_id": specification["path_id"],
                "applied_sha256": specification["sha256"],
                "diagnostic_only": bool(
                    specification.get("diagnostic_only", False)
                ),
                **result,
            }
        )
    path_results = [
        {
            "path_id": "identified_effective_plant_v1",
            "source": "immutable_C6_receipt_not_rerun",
            "numeric_task_success": c6_receipt["numeric_task_success"],
            "outcome": c6_receipt["outcome"],
        },
        *challengers,
    ]
    success_count = sum(
        bool(
            row.get("numeric_task_success")
            if "numeric_task_success" in row
            else row["outcome"]["numeric_task_success"]
        )
        for row in path_results
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "immutable_c6": {
            "artifact_sha256": c6_receipt["artifact_sha256"],
            "verdict": c6_receipt["verdict"],
            "numeric_task_success": c6_receipt["numeric_task_success"],
            "promotable_mission_success": c6_receipt[
                "promotable_mission_success"
            ],
            "rerun": False,
        },
        "path_results": path_results,
        "deterministic_path_successes": success_count,
        "deterministic_path_attempts": len(path_results),
        "robust_success": success_count == len(path_results),
        "uncertainty": {
            **contract["uncertainty"],
            "probabilistic_robust_success": None,
            "reason_no_probability": (
                "No identified geometry or contact distribution exists; "
                "unknown dimensions were not randomized."
            ),
        },
        "claim_boundary": (
            "Deterministic direct, identified, and diagnostic-ZOH plant "
            "comparison under the same unvalidated natural-contact baseline. "
            "The identified C6 path was not rerun, no unknown distribution was "
            "invented, and this result cannot redefine C6."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
