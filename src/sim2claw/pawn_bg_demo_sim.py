"""Replay owner-reviewed B-G teleoperation commands in the current simulator.

This is a diagnostic transfer of joint commands. Command clipping, provisional
joint conversion, human action ownership, and missing physical object state
make every result non-admissible as learned-policy or sim-to-real proof.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .contact_prior import (
    apply_contact_variant,
    compiled_contact_identity,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .pawn_bg_reward import CONTRACT_PATH, load_reward_contract, score_episode, sha256_file
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)


SCHEMA_VERSION = "sim2claw.pawn_bg_demonstration_sim_diagnostic.v1"
FOLDER_PATTERN = re.compile(r"^([b-g][12])-to-([b-g][12])(?:-redo)?$")
BASELINE_PIECE_BY_FILE = {
    "b": "brown_pawn_b1", "c": "brown_pawn_c2", "d": "brown_pawn_d1",
    "e": "brown_pawn_e2", "f": "brown_pawn_f1", "g": "brown_pawn_g2",
}


@dataclass(frozen=True)
class JointAdapter:
    """One immutable physical-degree to simulator-joint mapping.

    Source-fit adapters remain diagnostic.  They do not rewrite the scene,
    joint limits, actuator model, contact parameters, or physical calibration.
    """

    adapter_id: str
    body_joint_signs: tuple[int, int, int, int, int]
    body_joint_zero_offsets_rad: tuple[float, float, float, float, float]
    evidence_class: str

    def __post_init__(self) -> None:
        if not self.adapter_id or not self.evidence_class:
            raise ValueError("joint adapter identity and evidence class are required")
        if len(self.body_joint_signs) != 5 or any(
            type(value) is not int or value not in (-1, 1)
            for value in self.body_joint_signs
        ):
            raise ValueError("joint adapter signs must be five exact -1/+1 integers")
        if len(self.body_joint_zero_offsets_rad) != 5 or any(
            type(value) is not float or not math.isfinite(value)
            for value in self.body_joint_zero_offsets_rad
        ):
            raise ValueError("joint adapter offsets must be five finite floats")

    @property
    def sha256(self) -> str:
        payload = {
            "adapter_id": self.adapter_id,
            "body_joint_signs": list(self.body_joint_signs),
            "body_joint_zero_offsets_rad": list(self.body_joint_zero_offsets_rad),
            "evidence_class": self.evidence_class,
            "gripper_transform": "linear_physical_percent_to_current_actuator_ctrlrange",
            "scale_radians_per_degree": math.pi / 180.0,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def receipt(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_sha256": self.sha256,
            "body_joint_signs": list(self.body_joint_signs),
            "body_joint_zero_offsets_rad": list(self.body_joint_zero_offsets_rad),
            "evidence_class": self.evidence_class,
            "gripper_transform": "linear_physical_percent_to_current_actuator_ctrlrange",
            "scale_radians_per_degree": math.pi / 180.0,
            "physical_calibration_approved": False,
        }


BASELINE_JOINT_ADAPTER = JointAdapter(
    adapter_id="so101_physical_degrees_to_current_scene_provisional_v1",
    body_joint_signs=(1, 1, 1, 1, 1),
    body_joint_zero_offsets_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
    evidence_class="provisional_range_audit_blocked_not_calibrated",
)


def physical_values_to_sim_with_adapter(
    values: list[float] | np.ndarray,
    gripper_bounds: np.ndarray,
    adapter: JointAdapter,
) -> np.ndarray:
    physical = np.asarray(values, dtype=np.float64)
    if physical.shape != (6,) or not np.all(np.isfinite(physical)):
        raise ValueError("physical replay requires six finite joint values")
    converted = np.empty(6, dtype=np.float64)
    converted[:5] = (
        np.deg2rad(physical[:5]) * np.asarray(adapter.body_joint_signs)
        + np.asarray(adapter.body_joint_zero_offsets_rad)
    )
    low, high = (float(value) for value in gripper_bounds)
    converted[5] = low + np.clip(physical[5], 0.0, 100.0) / 100.0 * (high - low)
    return converted


def _id(model: mujoco.MjModel, kind: mujoco.mjtObj, name: str) -> int:
    value = mujoco.mj_name2id(model, kind, name)
    if value < 0:
        raise ValueError(f"simulator is missing required identity: {name}")
    return value


def _piece_bodies(model: mujoco.MjModel) -> dict[str, int]:
    result: dict[str, int] = {}
    for body_id in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if name and name.startswith(("brown_pawn_", "tan_pawn_")):
            result[name] = body_id
    return result


def _contact_flags(
    model: mujoco.MjModel, data: mujoco.MjData, *, selected_body: int,
    piece_body_ids: set[int], robot_body_ids: set[int], jaw_body_ids: set[int],
) -> tuple[bool, bool]:
    selected_jaw = False
    wrong_piece = False
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {int(model.geom_bodyid[contact.geom1]), int(model.geom_bodyid[contact.geom2])}
        if selected_body in bodies and bodies & jaw_body_ids:
            selected_jaw = True
        contacted_pieces = bodies & piece_body_ids
        if contacted_pieces and bodies & robot_body_ids and contacted_pieces != {selected_body}:
            wrong_piece = True
    return selected_jaw, wrong_piece


def _trace_row(
    model: mujoco.MjModel, data: mujoco.MjData, *, selected_body: int,
    selected_dof: int, piece_bodies: dict[str, int], initial_piece_positions: dict[str, np.ndarray],
    robot_body_ids: set[int], jaw_body_ids: set[int],
) -> dict[str, Any]:
    selected_contact, wrong_contact = _contact_flags(
        model, data, selected_body=selected_body,
        piece_body_ids=set(piece_bodies.values()), robot_body_ids=robot_body_ids,
        jaw_body_ids=jaw_body_ids,
    )
    collateral = max(
        (
            float(np.linalg.norm(np.asarray(data.xpos[body_id]) - initial_piece_positions[name]))
            for name, body_id in piece_bodies.items() if body_id != selected_body
        ),
        default=0.0,
    )
    rotation = np.asarray(data.xmat[selected_body]).reshape(3, 3)
    finite = bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())
    return {
        "piece_position_xyz_m": np.asarray(data.xpos[selected_body], dtype=float).tolist(),
        "piece_upright_cosine": float(rotation[2, 2]),
        "piece_linear_speed_m_s": float(np.linalg.norm(data.qvel[selected_dof : selected_dof + 3])),
        "selected_piece_jaw_contact": selected_contact,
        "wrong_piece_robot_contact": wrong_contact,
        "maximum_other_piece_displacement_m": collateral,
        "finite_state": finite,
    }


def _catalog_episodes(catalog: dict[str, Any]) -> list[tuple[dict[str, Any], str, str]]:
    selected = []
    for episode in catalog.get("episodes", []):
        match = FOLDER_PATTERN.fullmatch(str(episode.get("folder_label", "")))
        if match is None or match.group(1)[0] != match.group(2)[0] or match.group(1)[1] == match.group(2)[1]:
            continue
        selected.append((episode, match.group(1), match.group(2)))
    if len(selected) != 13:
        raise ValueError(f"owner-reviewed product scope must resolve to 13 recordings, found {len(selected)}")
    if {f"pawn_{source}_to_{destination}" for _, source, destination in selected} != {
        f"pawn_{file_}{source}_to_{file_}{destination}"
        for file_ in "bcdefg" for source, destination in (("1", "2"), ("2", "1"))
    }:
        raise ValueError("owner-reviewed recordings do not cover the frozen 12 skills")
    return selected


def _load_source(episode: dict[str, Any], source_root: Path) -> list[dict[str, Any]]:
    samples_path = source_root / episode["assets"]["samples"]
    receipt_path = source_root / episode["assets"]["receipt"]
    if not samples_path.is_file() or not receipt_path.is_file():
        raise ValueError(f"recording assets are missing for {episode['recording_id']}")
    if sha256_file(samples_path) != episode["samples_sha256"] or sha256_file(receipt_path) != episode["receipt_sha256"]:
        raise ValueError(f"recording bytes fail catalog hashes for {episode['recording_id']}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("mode") != "physical_follower" or receipt.get("samples_sha256") != episode["samples_sha256"]:
        raise ValueError(f"recording receipt identity drifted for {episode['recording_id']}")
    rows = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != episode["sample_count"]:
        raise ValueError(f"sample count drifted for {episode['recording_id']}")
    return rows


def _run_episode(
    *, contract: dict[str, Any], episode: dict[str, Any], source: str, destination: str,
    samples: list[dict[str, Any]], variant: Any,
    joint_adapter: JointAdapter = BASELINE_JOINT_ADAPTER,
) -> dict[str, Any]:
    board_center = registered_board_center(contract["scene_binding"]["scene_id"])
    spec = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
    )
    application = apply_contact_variant(spec, variant)
    model = spec.compile()
    compiled_identity = compiled_contact_identity(model, application)
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)

    file_ = source[0]
    selected_name = BASELINE_PIECE_BY_FILE[file_]
    selected_body = _id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(board_square_center(source, board_center_in_table_frame_xy_m=board_center))
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0

    actuator_ids = [_id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}") for joint in ROBOT_JOINTS]
    joint_ids = [_id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}") for joint in ROBOT_JOINTS]
    qpos_addresses = [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids]
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=float)
    first_actual_raw = physical_values_to_sim_with_adapter(
        samples[0]["follower_actual_position_degrees"], bounds[-1], joint_adapter
    )
    first_actual = np.clip(first_actual_raw, bounds[:, 0], bounds[:, 1])
    data.qpos[qpos_addresses] = first_actual
    data.ctrl[actuator_ids] = first_actual
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)

    piece_bodies = _piece_bodies(model)
    initial_positions = {name: np.asarray(data.xpos[body_id], dtype=float).copy() for name, body_id in piece_bodies.items()}
    initial_height = float(data.xpos[selected_body][2])
    robot_body_ids = {
        body_id for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    fixed_geom = _id(model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1")
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        _id(model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"),
    }
    trace = [_trace_row(
        model, data, selected_body=selected_body, selected_dof=selected_dof,
        piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
        robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
    )]
    clipped_command_rows = 0
    clipped_actual_rows = int(not np.array_equal(first_actual_raw, first_actual))
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(episode["sample_hz"]))
    for sample in samples:
        timestamp = float(sample["timestamp_monotonic_seconds"])
        dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
        if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
            dt = nominal_dt
        previous_timestamp = timestamp
        raw_command = physical_values_to_sim_with_adapter(
            sample["follower_command_degrees"], bounds[-1], joint_adapter
        )
        command = np.clip(raw_command, bounds[:, 0], bounds[:, 1])
        clipped_command_rows += int(not np.array_equal(raw_command, command))
        actual = physical_values_to_sim_with_adapter(
            sample["follower_actual_position_degrees"], bounds[-1], joint_adapter
        )
        clipped_actual_rows += int(np.any((actual < bounds[:, 0]) | (actual > bounds[:, 1])))
        data.ctrl[actuator_ids] = command
        mujoco.mj_step(model, data, nstep=max(1, round(dt / float(model.opt.timestep))))
        trace.append(_trace_row(
            model, data, selected_body=selected_body, selected_dof=selected_dof,
            piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
        ))
    for _ in range(200):
        mujoco.mj_step(model, data)
    trace.append(_trace_row(
        model, data, selected_body=selected_body, selected_dof=selected_dof,
        piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
        robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
    ))
    target_xyz = board_square_center(destination, board_center_in_table_frame_xy_m=board_center)
    score = score_episode(
        contract, skill_id=f"pawn_{source}_to_{destination}", trace=trace,
        target_position_xyz_m=target_xyz, initial_piece_height_m=initial_height,
        evaluation_mode="source_demonstration_replay",
        action_owner="physical_teleoperator", assistance_used=False,
    )
    return {
        "recording_id": episode["recording_id"],
        "folder_label": episode["folder_label"],
        "folder_label_used_as_owner_reviewed_task_identity": True,
        "catalog_source_square_ignored_for_task_identity": episode["source_square"],
        "catalog_destination_square_ignored_for_task_identity": episode["destination_square"],
        "source_samples_sha256": episode["samples_sha256"],
        "sample_count": len(samples),
        "selected_sim_piece_body": selected_name,
        "command_rows_clipped": clipped_command_rows,
        "actual_rows_outside_sim_limits": clipped_actual_rows,
        "exact_replay": clipped_command_rows == 0 and clipped_actual_rows == 0,
        "joint_adapter": joint_adapter.receipt(),
        "transform_status": joint_adapter.evidence_class,
        "variant_id": variant.variant_id,
        "variant_sha256": variant.variant_sha256,
        "compiled_identity": compiled_identity,
        "score": score,
    }


def evaluate_demo_catalog(*, catalog_path: Path, source_root: Path, output_path: Path) -> dict[str, Any]:
    contract = load_reward_contract()
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    episodes = _catalog_episodes(catalog)
    prior_snapshot = read_contact_prior_snapshot()
    results: list[dict[str, Any]] = []
    for variant_id in contract["contact_sensitivity_binding"]["ordered_variants"]:
        variant = load_simulator_variant(variant_id, contract_snapshot=prior_snapshot)
        for episode, source, destination in episodes:
            samples = _load_source(episode, source_root)
            results.append(_run_episode(
                contract=contract, episode=episode, source=source,
                destination=destination, samples=samples, variant=variant,
            ))
    by_variant: dict[str, Any] = {}
    for variant_id in contract["contact_sensitivity_binding"]["ordered_variants"]:
        rows = [row for row in results if row["variant_id"] == variant_id]
        by_variant[variant_id] = {
            "episode_count": len(rows),
            "task_consequence_success_count": sum(row["score"]["task_consequence_success"] for row in rows),
            "task_consequence_success_rate": sum(row["score"]["task_consequence_success"] for row in rows) / len(rows),
            "mean_diagnostic_reward": float(np.mean([row["score"]["diagnostic_reward"] for row in rows])),
            "mean_final_center_distance_m": float(np.mean([row["score"]["final_center_distance_m"] for row in rows])),
            "maximum_piece_rise_m": float(max(row["score"]["maximum_piece_rise_m"] for row in rows)),
            "recordings_with_clipped_commands": sum(row["command_rows_clipped"] > 0 for row in rows),
            "policy_success_count": 0,
        }
    inertial_hashes = {row["compiled_identity"]["compiled_inertial_control_sha256"] for row in results}
    masses = {np.float64(row["compiled_identity"]["compiled_total_body_mass_kg"]).tobytes() for row in results}
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "reward_contract_path": str(CONTRACT_PATH.relative_to(CONTRACT_PATH.parents[2])),
        "reward_contract_sha256": sha256_file(CONTRACT_PATH),
        "product_contract_sha256": contract["product_binding"]["sha256"],
        "language_contract_sha256": contract["language_binding"]["sha256"],
        "catalog_path": str(catalog_path),
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "contact_prior_canonical_sha256": prior_snapshot.sha256,
        "contact_prior_source_task_id": prior_snapshot.payload()["task_id"],
        "contact_prior_parameter_reuse_is_cross_task_diagnostic": True,
        "frozen_seed": contract["fixed_evaluation"]["seeds"][0],
        "episode_count_per_variant": 13,
        "distinct_skill_count": 12,
        "variant_count": 4,
        "results": results,
        "by_variant": by_variant,
        "inertial_control_bitwise_identical_all_variants": len(inertial_hashes) == 1,
        "total_body_mass_bitwise_identical_all_variants": len(masses) == 1,
        "learned_policy_evaluated": False,
        "compatible_b_g_act_checkpoint_available": False,
        "source_demonstrations_are_act_policy_weights": False,
        "source_demonstrations_are_human_owned_candidate_trajectories": True,
        "strict_policy_success_reportable": False,
        "physical_calibration_claimed": False,
        "sim_to_real_error_measured": False,
        "training_admission": "rejected_provisional_transform_and_joint_limit_clipping",
        "claim_boundary": contract["claim_boundary"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return report


__all__ = [
    "BASELINE_JOINT_ADAPTER",
    "JointAdapter",
    "evaluate_demo_catalog",
    "physical_values_to_sim_with_adapter",
]
