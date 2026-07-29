from __future__ import annotations

import mujoco
import numpy as np

from sim2claw.pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from sim2claw.pawn_bg_workcell_fit import build_workcell_model
from sim2claw.paths import REPO_ROOT
from sim2claw.retrospective_real_to_sim_support_handoff import (
    apply_support_handoff,
    load_contract,
)


def test_support_handoff_contract_is_bounded_and_has_no_hardware_authority() -> None:
    contract = load_contract()
    assert contract["replay"]["release_event_sample_offsets"] == [-1, 0, 1]
    assert contract["replay"]["preserve_handoff_xy"] is True
    assert contract["replay"]["terminal_xy_forcing_allowed"] is False
    assert contract["replay"]["terminal_destination_pose_forcing_allowed"] is False
    assert contract["authority"] == {
        "camera": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "free_release_physics_transfer": False,
        "simulator_replay": True,
    }


def test_support_handoff_preserves_xy_and_projects_only_support_mode() -> None:
    train, events = _load_partition(REPO_ROOT, "train")
    _, candidate, _, _ = _reconstruct_stage_d(train, events)
    binding = build_workcell_model(candidate)
    model: mujoco.MjModel = binding["model"]
    data: mujoco.MjData = binding["data"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "brown_pawn_d1"
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "brown_pawn_d1_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    mujoco.mj_forward(model, data)
    upright = np.asarray(data.xmat[selected_body]).reshape(3, 3).copy()
    original_xy = np.asarray(data.qpos[selected_qpos : selected_qpos + 2]).copy()
    data.qpos[selected_qpos + 2] += 0.03
    data.qvel[selected_dof : selected_dof + 6] = 1.0
    mujoco.mj_forward(model, data)
    result = apply_support_handoff(
        model=model,
        data=data,
        selected_body=selected_body,
        selected_qpos=selected_qpos,
        selected_dof=selected_dof,
        support_height_m=float(data.qpos[selected_qpos + 2] - 0.03),
        upright_rotation=upright,
    )
    assert np.array_equal(
        np.asarray(data.qpos[selected_qpos : selected_qpos + 2]), original_xy
    )
    assert result["xy_projection_m"] == 0.0
    assert np.isclose(result["vertical_projection_m"], 0.03)
    assert np.array_equal(
        np.asarray(data.qvel[selected_dof : selected_dof + 6]), np.zeros(6)
    )
