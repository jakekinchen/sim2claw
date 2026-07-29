"""Elbow-locked static successor with no unreachable high-clearance stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_elbow_locked_wrist_path_static as _elbow
from . import canonical_seeded_action_static as _static
from . import canonical_wrist_path_static as _wrist


def _compile_low_direct(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    live_seed: np.ndarray,
    candidate_config: Mapping[str, Any],
    source_xyz: np.ndarray,
    direction: np.ndarray,
    wrist_roll_rad: float,
    contact_offset_m: float,
    contact_height_m: float,
    clearance_height_m: float,
    stroke_m: float,
    closed_jaw_rad: float,
    sample_hz: float,
    target_rates: np.ndarray,
    maximum_ik_residual_m: float,
    precontact_backoff_m: float = 0.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    del clearance_height_m
    closed_seed = live_seed.copy()
    closed_seed[-1] = closed_jaw_rad
    data = mujoco.MjData(model)
    data.qpos[addresses] = closed_seed
    mujoco.mj_forward(model, data)
    pinch_local = _static._pinch_offset(model, data, "left")
    contact = source_xyz.copy()
    contact[:2] -= direction[:2] * contact_offset_m
    contact[2] += contact_height_m
    low_precontact = contact - direction * precontact_backoff_m
    pushed = contact + direction * stroke_m
    cartesian_targets = [low_precontact, contact, pushed]
    targets = [live_seed.copy(), closed_seed.copy()]
    active = closed_seed.copy()
    active[4] = wrist_roll_rad
    residuals: list[float] = []
    for target in cartesian_targets:
        active, residual = _static._solve_fixed_roll(
            model,
            active,
            target,
            pinch_local,
            iterations=260,
            damping=0.015,
            step_limit=0.08,
        )
        residuals.append(float(residual))
        if residual > maximum_ik_residual_m:
            raise _wrist.CanonicalWristPathStaticError(
                "canonical elbow-locked low-path IK residual exceeded gate"
            )
        active[-1] = closed_jaw_rad
        targets.append(active.copy())
    action = _static._interpolate_targets(
        targets,
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    if not np.array_equal(action[0], live_seed):
        raise _wrist.CanonicalWristPathStaticError(
            "canonical elbow-locked low-path row zero changed"
        )
    margins = []
    for index, name in enumerate(_static.ALL_JOINTS):
        joint_id = _static._named_id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        low, high = model.jnt_range[joint_id]
        margins.append(
            float(
                min(
                    np.min(action[:, index] - low),
                    np.min(high - action[:, index]),
                )
            )
        )
    return action, {
        "maximum_ik_residual_m": max(residuals),
        "minimum_model_joint_margin_rad": min(margins),
        "cartesian_targets_xyz_m": [
            item.tolist() for item in cartesian_targets
        ],
        "wrist_roll_target_rad": wrist_roll_rad,
        "wrist_rotation_after_live_lift": False,
        "precontact_backoff_m": precontact_backoff_m,
        "low_horizontal_precontact_approach": True,
        "high_clearance_stage_removed": True,
        "high_retreat_stage_removed": True,
        "ends_at_pushed_target": True,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run immutable elbow V1 with only the low-path compile replacement."""

    original = _wrist._compile
    _wrist._compile = _compile_low_direct
    try:
        receipt = _elbow.enumerate_and_freeze(
            contract_path, output_directory
        )
    finally:
        _wrist._compile = original
    receipt["path_shape"] = {
        "high_clearance_stage_removed": True,
        "high_retreat_stage_removed": True,
        "ends_at_pushed_target": True,
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["enumerate_and_freeze"]
