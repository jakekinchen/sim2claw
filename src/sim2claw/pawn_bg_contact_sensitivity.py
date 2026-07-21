"""Frozen-prior B--G contact sensitivity after timing and deadband diagnostics."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np

from .contact_prior import load_simulator_variant, read_contact_prior_snapshot
from .grasp import _pinch_point
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_demo_sim import BASELINE_PIECE_BY_FILE, _piece_bodies, _trace_row
from .pawn_bg_reward import load_reward_contract, score_episode
from .pawn_bg_timing_ablation import BODY_JOINT_NAMES, _mapped_episode
from .pawn_bg_workcell_fit import _workcell_square_center, build_workcell_model


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_contact_sensitivity_v1.json"
)
SCHEMA = "sim2claw.pawn_bg_contact_sensitivity.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_contact_sensitivity_receipt.v1"


class ContactSensitivityError(RuntimeError):
    """The B--G contact sensitivity boundary was violated."""


def load_contact_sensitivity_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContactSensitivityError(f"cannot read contact contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise ContactSensitivityError("unexpected B--G contact sensitivity schema")
    if contract.get("selection", {}).get("allowed") is not False:
        raise ContactSensitivityError("contact sensitivity gained selection authority")
    if any(contract.get("authority", {}).values()):
        raise ContactSensitivityError("contact sensitivity authority widened")
    if not all(contract.get("action_invariance", {}).values()):
        raise ContactSensitivityError("action invariance is not fail closed")
    return contract


def _run_episode(
    *, mapped: dict[str, Any], candidate: Any, reward_contract: dict[str, Any],
    variant: Any, delay_seconds: float, deadband: dict[str, float]
) -> dict[str, Any]:
    binding = build_workcell_model(candidate, contact_variant=variant)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    source = str(mapped["source"])
    destination = str(mapped["destination"])
    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free")
    if selected_body < 0 or selected_joint < 0:
        raise ContactSensitivityError("selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_height = float(data.xpos[selected_body][2])
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    fixed_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1")
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"),
    }

    def trace_row() -> dict[str, Any]:
        return _trace_row(
            model, data, selected_body=selected_body, selected_dof=selected_dof,
            piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
        )

    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()

    def apply_servo(action: np.ndarray) -> None:
        data.ctrl[actuator_ids] = action
        for joint_name, threshold in deadband.items():
            joint_index = BODY_JOINT_NAMES.index(joint_name)
            actuator_id = actuator_ids[joint_index]
            qpos_address = qpos_addresses[joint_index]
            inactive = abs(float(action[joint_index] - data.qpos[qpos_address])) <= math.radians(float(threshold))
            scale = 0.0 if inactive else 1.0
            model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
            model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale

    pinch_local = binding["pinch_offset_local"]
    minimum_pinch = float(
        np.linalg.norm(_pinch_point(model, data, "left", pinch_local) - np.asarray(data.xpos[selected_body]))
    )
    trace = [trace_row()]
    actions = mapped["actions"]
    times = mapped["timestamps"]
    timestep = float(model.opt.timestep)
    for row_index, timestamp in enumerate(times[:-1]):
        interval = float(times[row_index + 1] - timestamp)
        for step in range(max(1, round(interval / timestep))):
            now = float(timestamp) + step * timestep
            source_index = max(0, int(np.searchsorted(times, now - delay_seconds, side="right") - 1))
            apply_servo(actions[source_index])
            mujoco.mj_step(model, data)
            minimum_pinch = min(
                minimum_pinch,
                float(np.linalg.norm(_pinch_point(model, data, "left", pinch_local) - np.asarray(data.xpos[selected_body]))),
            )
        trace.append(trace_row())
    final_index = max(0, int(np.searchsorted(times, float(times[-1]) - delay_seconds, side="right") - 1))
    apply_servo(actions[final_index])
    for _ in range(200):
        apply_servo(np.asarray(data.ctrl[actuator_ids], dtype=np.float64))
        mujoco.mj_step(model, data)
        minimum_pinch = min(
            minimum_pinch,
            float(np.linalg.norm(_pinch_point(model, data, "left", pinch_local) - np.asarray(data.xpos[selected_body]))),
        )
    trace.append(trace_row())
    target_xyz = _workcell_square_center(
        destination,
        board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
        board_side_m=candidate.board_side_m,
    )
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
    return {
        "recording_id": mapped["episode"]["recording_id"],
        "folder_label": mapped["episode"]["folder_label"],
        "variant_id": variant.variant_id,
        "variant_sha256": variant.variant_sha256,
        "action_sha256": mapped["action_receipt"]["sha256"],
        "clipped_action_rows": 0,
        "minimum_pinch_to_piece_m": minimum_pinch,
        "selected_piece_contact_observed": bool(score["gate_results"]["selected_piece_contact_observed"]),
        "piece_lifted": bool(score["gate_results"]["piece_lifted"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_target_distance_m": float(score["final_center_distance_m"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
    }


def _summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    return {
        "episode_count": len(materialized),
        "contact": sum(int(row["selected_piece_contact_observed"]) for row in materialized),
        "lifted": sum(int(row["piece_lifted"]) for row in materialized),
        "strict_success": sum(int(row["task_consequence_success"]) for row in materialized),
        "mean_maximum_piece_rise_m": float(np.mean([row["maximum_piece_rise_m"] for row in materialized])),
        "mean_final_target_distance_m": float(np.mean([row["final_target_distance_m"] for row in materialized])),
        "mean_minimum_pinch_to_piece_m": float(np.mean([row["minimum_pinch_to_piece_m"] for row in materialized])),
    }


def run_contact_sensitivity(
    *, source_repository_root: Path, output_root: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_contact_sensitivity_contract(contract_path)
    payloads, events = _load_partition(source_repository_root, "train")
    if len(payloads) != int(contract["source"]["expected_episode_count"]):
        raise ContactSensitivityError("train product episode inventory changed")
    _parent, candidate, stage_d_parameters, _details = _reconstruct_stage_d(payloads, events)
    mapped = [_mapped_episode(payload, candidate) for payload in payloads]
    snapshot = read_contact_prior_snapshot(source_repository_root / contract["source"]["contact_prior_path"])
    if snapshot.sha256 != contract["source"]["expected_contact_prior_canonical_sha256"]:
        raise ContactSensitivityError("frozen contact prior digest changed")
    reward_contract = load_reward_contract()
    rows_by_variant: dict[str, list[dict[str, Any]]] = {}
    for variant_id in contract["source"]["variant_order"]:
        variant = load_simulator_variant(variant_id, contract_snapshot=snapshot)
        rows_by_variant[variant_id] = [
            _run_episode(
                mapped=episode,
                candidate=candidate,
                reward_contract=reward_contract,
                variant=variant,
                delay_seconds=float(contract["source"]["application_delay_seconds"]),
                deadband={key: float(value) for key, value in contract["source"]["servo_deadband_degrees"].items()},
            )
            for episode in mapped
        ]
    action_hashes = {episode["episode"]["recording_id"]: episode["action_receipt"] for episode in mapped}
    action_invariant = all(
        receipt["sha256"] == _array_sha256(episode["actions"])
        for episode, receipt in zip(mapped, action_hashes.values(), strict=True)
    ) and all(
        row["action_sha256"] == action_hashes[row["recording_id"]]["sha256"]
        for rows in rows_by_variant.values() for row in rows
    )
    summaries = {variant_id: _summary(rows) for variant_id, rows in rows_by_variant.items()}
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_contact_prior_sensitivity",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "contact_prior": {"path": str(snapshot.source_path.resolve()), "canonical_sha256": snapshot.sha256},
        "stage_d_parameters": stage_d_parameters,
        "application_delay_seconds": contract["source"]["application_delay_seconds"],
        "servo_deadband_degrees": contract["source"]["servo_deadband_degrees"],
        "action_arrays_byte_identical_across_variants": action_invariant,
        "action_hashes": action_hashes,
        "summaries": summaries,
        "episodes": rows_by_variant,
        "decision": {
            "selected_variant": None,
            "contact_parameters_identified": False,
            "simulator_composite_promoted": False,
            "interpretation": (
                "The frozen rubber-tip ensemble measures simulator consequence sensitivity only. "
                "No variant may be selected because retained observations do not label physical "
                "contact, retention, lift, or transport with sufficient authority."
            ),
        },
        "authority": contract["authority"],
        "claim_boundary": "The contact ensemble is an unmeasured cross-task prior sensitivity, not physical contact calibration, task proof, or training admission.",
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "contact_sensitivity_receipt.json", receipt)
    return receipt
