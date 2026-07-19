"""Honest manipulation evaluator (chess_manipulation_v2).

The frozen v1 evaluator scored a trajectory as success from target lift, jaw
contact, action ownership, and assistance alone. It never measured what the
rest of the arm did to the rest of the board, so a policy that flings the queen
a meter while lifting the rook passes. This evaluator re-scores the SAME lift
with the collateral, safety, and grasp-quality gates that make success honest:

  * per-non-target-piece maximum displacement,
  * board ejection of any non-target piece,
  * any arm contact with a non-target piece,
  * target board clearance,
  * upright + settled target at the final window,
  * bilateral (two-pad) grasp on the target.

It is deliberately separate from `act_evaluator.py`: v1 stays frozen and
untouched. This module re-scores existing v1-trained checkpoints, so it does NOT
require the checkpoint's stored contract hash to equal the v2 contract hash; it
records both instead.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .act_evaluator import evaluate_act
from .act_model import (
    ACTCheckpointSnapshot,
    read_act_checkpoint_snapshot,
    validate_act_checkpoint_snapshot,
)
from .chess_task import ChessRookLiftEnv
from .paths import DEFAULT_OUTPUT_ROOT

V2_SCHEMA = "sim2claw.chess_manipulation_task.v2"
DEFAULT_V2_CONTRACT = (
    Path(__file__).resolve().parents[2] / "configs" / "tasks" / "chess_manipulation_v2.json"
)


def load_manipulation_contract(path: Path = DEFAULT_V2_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != V2_SCHEMA:
        raise ValueError("unsupported chess-manipulation task contract")
    phase_total = sum(contract["episode"]["phase_control_steps"].values())
    if phase_total != contract["episode"]["control_horizon"]:
        raise ValueError("phase control steps do not match the frozen horizon")
    return contract


def manipulation_contract_sha256(path: Path = DEFAULT_V2_CONTRACT) -> str:
    payload = json.dumps(
        load_manipulation_contract(path), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _accepted_checkpoint_snapshot(
    checkpoint_source: Path | ACTCheckpointSnapshot,
    *,
    expected_checkpoint_sha256: str | None,
) -> ACTCheckpointSnapshot:
    """Resolve exactly one authenticated byte snapshot before ACT loads it."""

    if expected_checkpoint_sha256 is None:
        raise ValueError("honest manipulation evaluation requires an accepted digest")
    if isinstance(checkpoint_source, ACTCheckpointSnapshot):
        return validate_act_checkpoint_snapshot(
            checkpoint_source, expected_sha256=expected_checkpoint_sha256
        )
    return read_act_checkpoint_snapshot(
        checkpoint_source, expected_sha256=expected_checkpoint_sha256
    )


def _piece_bodies(model: mujoco.MjModel) -> dict[str, int]:
    """Every free-joint chess piece body, keyed by name."""
    pieces: dict[str, int] = {}
    for joint in range(model.njnt):
        if model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_FREE:
            body = int(model.jnt_bodyid[joint])
            pieces[mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body)] = body
    return pieces


def _arm_body_ids(model: mujoco.MjModel, arm: str) -> set[int]:
    prefix = f"{arm}_"
    ids: set[int] = set()
    for body in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body)
        if name and name.startswith(prefix):
            ids.add(body)
    return ids


def _target_tilt_deg(model: mujoco.MjModel, data: mujoco.MjData, body: int) -> float:
    """Angle between the target body's local +z and world +z."""
    zaxis = np.asarray(data.xmat[body], dtype=np.float64).reshape(3, 3)[:, 2]
    cos = float(np.clip(zaxis[2] / max(np.linalg.norm(zaxis), 1e-9), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def _target_speed_mps(model: mujoco.MjModel, data: mujoco.MjData, body: int) -> float:
    """Linear speed of the target's free joint (first three velocity dofs)."""
    for joint in range(model.njnt):
        if (
            model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_FREE
            and int(model.jnt_bodyid[joint]) == body
        ):
            dof = int(model.jnt_dofadr[joint])
            return float(np.linalg.norm(data.qvel[dof : dof + 3]))
    return 0.0


def evaluate_manipulation(
    checkpoint_source: Path | ACTCheckpointSnapshot,
    *,
    expected_checkpoint_sha256: str | None = None,
    output_directory: Path | None = None,
    contract_path: Path = DEFAULT_V2_CONTRACT,
) -> dict[str, Any]:
    task = load_manipulation_contract(contract_path)
    evaluator = task["evaluator"]
    output = output_directory or DEFAULT_OUTPUT_ROOT / "manipulation_v2" / "eval"
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    checkpoint_snapshot = _accepted_checkpoint_snapshot(
        checkpoint_source,
        expected_checkpoint_sha256=expected_checkpoint_sha256,
    )

    # 1. Canonical rollout: reuse the FROZEN v1 evaluator verbatim as the single
    #    source of truth for the policy trajectory and the v1 gates. Re-running
    #    inference here would diverge by ~1e-6 and, because these policies are
    #    chaotically sensitive, flip the outcome. evaluate_act writes the exact
    #    executed action trace.
    v1_dir = output / "v1_rollout"
    v1_receipt = evaluate_act(
        checkpoint_snapshot, output_directory=v1_dir, render_video=False
    )
    actions = json.loads((v1_dir / "action_trace.json").read_text())["actions_rad"]

    # 2. Replay that EXACT trajectory, measuring what v1 never did: collateral
    #    displacement of every non-target piece, board ejection, any arm contact
    #    with a non-target piece, and target grasp quality (upright/settled/pads).
    seed = int(task["held_out_split"]["seeds"][0])
    raw_offset = task["held_out_split"]["piece_planar_offsets_m"][0]
    offset = (float(raw_offset[0]), float(raw_offset[1]))
    env = ChessRookLiftEnv(task, seed=seed, piece_offset_xy_m=offset)
    model, data = env.model, env.data

    pieces = _piece_bodies(model)
    target_name = env.piece_name
    target_body = env.piece_body
    nontarget = {n: b for n, b in pieces.items() if b != target_body}
    nontarget_ids = set(nontarget.values())
    arm_bodies = _arm_body_ids(model, env.arm)
    fixed_pad_body = int(
        model.geom_bodyid[
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{env.arm}_fixed_jaw_box1")
        ]
    )
    moving_pad_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, f"{env.arm}_moving_jaw_so101_v1"
    )

    initial = {n: data.xpos[b].copy() for n, b in pieces.items()}
    max_disp = {n: 0.0 for n in nontarget}
    nontarget_arm_contact = False
    bilateral_grasp = False

    for raw_action in actions:
        env.step(np.asarray(raw_action, dtype=np.float64))
        touch_fixed = touch_moving = False
        for c in range(data.ncon):
            contact = data.contact[c]
            bodies = {
                int(model.geom_bodyid[contact.geom1]),
                int(model.geom_bodyid[contact.geom2]),
            }
            if bodies & arm_bodies and bodies & nontarget_ids:
                nontarget_arm_contact = True
            if target_body in bodies:
                if fixed_pad_body in bodies:
                    touch_fixed = True
                if moving_pad_body in bodies:
                    touch_moving = True
        if touch_fixed and touch_moving:
            bilateral_grasp = True
        for n, b in nontarget.items():
            disp = float(np.linalg.norm(data.xpos[b] - initial[n]))
            if disp > max_disp[n]:
                max_disp[n] = disp

    # ---- metrics ----
    maximum_rise = float(v1_receipt["episode"]["maximum_piece_rise_m"])
    worst_name = max(max_disp, key=max_disp.get)
    worst_disp = max_disp[worst_name]
    ejected = [n for n, d in max_disp.items() if d > evaluator["nontarget_ejection_displacement_m"]]
    disturbed = {n: d for n, d in max_disp.items() if d > evaluator["maximum_nontarget_displacement_m"]}
    target_tilt = _target_tilt_deg(model, data, target_body)
    target_speed = _target_speed_mps(model, data, target_body)

    def gate(measured, comparison, threshold, passed) -> dict[str, Any]:
        return {"measured": measured, "comparison": comparison, "threshold": threshold, "passed": bool(passed)}

    # v1 gates come straight from the frozen receipt (authoritative, unmodified).
    v1_gates = v1_receipt["gates"]
    v2_gates = {
        "max_nontarget_displacement": gate(round(worst_disp, 5), "<=", evaluator["maximum_nontarget_displacement_m"], worst_disp <= evaluator["maximum_nontarget_displacement_m"]),
        "nontarget_ejections": gate(len(ejected), "==", 0, len(ejected) == 0),
        "no_nontarget_arm_contact": gate(nontarget_arm_contact, "==", False, not nontarget_arm_contact),
        "target_clearance": gate(round(maximum_rise, 5), ">=", evaluator["minimum_target_clearance_m"], maximum_rise >= evaluator["minimum_target_clearance_m"]),
        "target_upright": gate(round(target_tilt, 2), "<=", evaluator["maximum_target_tilt_deg"], target_tilt <= evaluator["maximum_target_tilt_deg"]),
        "target_settled": gate(round(target_speed, 4), "<=", evaluator["maximum_target_settle_speed_mps"], target_speed <= evaluator["maximum_target_settle_speed_mps"]),
        "bilateral_pad_grasp": gate(bilateral_grasp, "==", True, bilateral_grasp),
    }
    gates = {**v1_gates, **v2_gates}

    success_v1 = bool(v1_receipt["success"])
    success_v2 = success_v1 and all(g["passed"] for g in v2_gates.values())

    receipt = {
        "schema_version": "sim2claw.manipulation_v2_evaluation_receipt.v2",
        "task_id": task["task_id"],
        "proof_class": "simulation_honest_manipulation_evaluation",
        "checkpoint_source_path_informational": str(checkpoint_snapshot.source_path),
        "checkpoint_snapshot_sha256": checkpoint_snapshot.sha256,
        "checkpoint_snapshot_bytes": len(checkpoint_snapshot.data),
        "checkpoint_snapshot_immutable": True,
        "v1_task_contract_sha256": v1_receipt["task_contract_sha256"],
        "manipulation_contract_sha256": manipulation_contract_sha256(contract_path),
        "trajectory_source": "frozen_v1_evaluator_action_trace",
        "seed": seed,
        "target_piece": target_name,
        "gates": gates,
        "success_v1_scoring": success_v1,
        "success_v2_scoring": success_v2,
        "terminal_outcome": "held_rook_cleanly" if success_v2 else "act_episode_failed_v2",
        "collateral": {
            "worst_nontarget_piece": worst_name,
            "worst_nontarget_max_displacement_m": round(worst_disp, 5),
            "nontarget_pieces_disturbed_over_threshold": {k: round(v, 5) for k, v in sorted(disturbed.items(), key=lambda kv: kv[1], reverse=True)},
            "nontarget_ejections": ejected,
            "target_final_tilt_deg": round(target_tilt, 2),
            "target_final_speed_mps": round(target_speed, 4),
        },
        "runtime": {"device": "cpu", "dtype": "float32", "elapsed_seconds": round(time.monotonic() - started, 2)},
        "physical_authority": False,
    }
    receipt_path = output / "manipulation_v2_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["receipt"] = str(receipt_path)
    return receipt
