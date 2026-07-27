"""Stateful simulator-only joint play for action-frozen geometric replay."""

from __future__ import annotations

import math
from typing import Any, Mapping

import mujoco
import numpy as np

from .learning_factory_artifacts import canonical_digest
from .pawn_bg_timing_ablation import BODY_JOINT_NAMES
from .pawn_bg_workcell_fit import WorkcellCandidate, build_workcell_model


class GeometricJointPlayError(RuntimeError):
    """A joint-play candidate or replay input is invalid."""


def _play_target(
    previous_effective: np.ndarray,
    command: np.ndarray,
    lower_half_width_radians: Mapping[int, float],
    upper_half_width_radians: Mapping[int, float],
) -> np.ndarray:
    """Apply one discrete stop/play update without changing the source command."""

    previous = np.asarray(previous_effective, dtype=np.float64)
    requested = np.asarray(command, dtype=np.float64)
    if (
        previous.shape != requested.shape
        or previous.ndim != 1
        or not np.all(np.isfinite(previous))
        or not np.all(np.isfinite(requested))
    ):
        raise GeometricJointPlayError("play inputs must be equal finite vectors")
    effective = requested.copy()
    if set(lower_half_width_radians) != set(upper_half_width_radians):
        raise GeometricJointPlayError("play lower and upper joints differ")
    for index, lower_radius in lower_half_width_radians.items():
        upper_radius = upper_half_width_radians[index]
        if (
            not 0 <= int(index) < requested.size
            or not math.isfinite(float(lower_radius))
            or not math.isfinite(float(upper_radius))
        ):
            raise GeometricJointPlayError("play joint index or width is invalid")
        if float(lower_radius) < 0.0 or float(upper_radius) < 0.0:
            raise GeometricJointPlayError("play width cannot be negative")
        effective[int(index)] = np.clip(
            previous[int(index)],
            requested[int(index)] - float(lower_radius),
            requested[int(index)] + float(upper_radius),
        )
    return effective


def replay_joint_play(
    mapped: Mapping[str, Any],
    candidate: WorkcellCandidate,
    *,
    settle_steps: int,
    delay_seconds: float,
    half_width_degrees: Mapping[str, Mapping[str, float]],
    load_sign_zero_threshold_nm: float = 0.001,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Replay exact actions through a stateful bounded internal actuator target."""

    widths: dict[int, tuple[float, float]] = {}
    normalized: dict[str, dict[str, float]] = {}
    for joint_name, values in half_width_degrees.items():
        if joint_name not in BODY_JOINT_NAMES:
            raise GeometricJointPlayError(
                f"unsupported joint-play joint: {joint_name}"
            )
        if set(values) != {"with_load", "against_load"}:
            raise GeometricJointPlayError("joint-play load branches changed")
        with_load = float(values["with_load"])
        against_load = float(values["against_load"])
        if (
            not math.isfinite(with_load)
            or not math.isfinite(against_load)
            or not 0.0 <= with_load <= 5.0
            or not 0.0 <= against_load <= 5.0
        ):
            raise GeometricJointPlayError(
                "joint-play width is outside 0..5 degrees"
            )
        widths[BODY_JOINT_NAMES.index(joint_name)] = (
            math.radians(with_load),
            math.radians(against_load),
        )
        normalized[str(joint_name)] = {
            "with_load": with_load,
            "against_load": against_load,
        }
    if (
        not math.isfinite(float(load_sign_zero_threshold_nm))
        or float(load_sign_zero_threshold_nm) <= 0.0
    ):
        raise GeometricJointPlayError("load-sign threshold must be positive")

    binding = build_workcell_model(candidate)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    dof_addresses = [
        int(model.jnt_dofadr[joint_id]) for joint_id in binding["joint_ids"]
    ]
    measured = np.asarray(mapped["measured"], dtype=np.float64)
    actions = np.asarray(mapped["actions"], dtype=np.float64)
    times = np.asarray(mapped["timestamps"], dtype=np.float64)
    if (
        measured.shape != actions.shape
        or measured.ndim != 2
        or measured.shape[1] != len(actuator_ids)
        or times.shape != (measured.shape[0],)
        or not np.all(np.isfinite(measured))
        or not np.all(np.isfinite(actions))
        or not np.all(np.isfinite(times))
        or np.any(np.diff(times) < 0.0)
    ):
        raise GeometricJointPlayError("mapped replay arrays are invalid")

    data.qpos[qpos_addresses] = measured[0]
    data.ctrl[actuator_ids] = measured[0]
    mujoco.mj_forward(model, data)
    if settle_steps:
        mujoco.mj_step(model, data, nstep=int(settle_steps))

    outputs = np.empty_like(measured)
    effective = measured[0].copy()
    last_load_sign = {
        index: (
            1
            if float(data.qfrc_bias[dof_addresses[index]]) >= 0.0
            else -1
        )
        for index in widths
    }
    timestep = float(model.opt.timestep)
    transitions: list[dict[str, Any]] = []
    last_source_index: int | None = None
    for row_index, timestamp in enumerate(times):
        outputs[row_index] = data.qpos[qpos_addresses]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        step_count = max(1, round(interval / timestep))
        for step in range(step_count):
            now = float(timestamp) + step * timestep
            source_index = max(
                0,
                int(
                    np.searchsorted(
                        times,
                        now - float(delay_seconds),
                        side="right",
                    )
                    - 1
                ),
            )
            lower_radii: dict[int, float] = {}
            upper_radii: dict[int, float] = {}
            for joint_index, (with_load, against_load) in widths.items():
                bias = float(data.qfrc_bias[dof_addresses[joint_index]])
                if abs(bias) >= float(load_sign_zero_threshold_nm):
                    last_load_sign[joint_index] = 1 if bias > 0.0 else -1
                if last_load_sign[joint_index] > 0:
                    lower_radii[joint_index] = with_load
                    upper_radii[joint_index] = against_load
                else:
                    lower_radii[joint_index] = against_load
                    upper_radii[joint_index] = with_load
            effective = _play_target(
                effective,
                actions[source_index],
                lower_radii,
                upper_radii,
            )
            data.ctrl[actuator_ids] = effective
            if source_index != last_source_index:
                transitions.append(
                    {
                        "simulator_time_seconds": now,
                        "source_index": source_index,
                        "effective_target": effective.tolist(),
                        "load_sign": {
                            BODY_JOINT_NAMES[index]: last_load_sign[index]
                            for index in sorted(last_load_sign)
                        },
                    }
                )
                last_source_index = source_index
            mujoco.mj_step(model, data)

    schedule = {
        "semantics": (
            "record_at_timestamp_then_apply_zoh_through_stateful_joint_play"
        ),
        "application_delay_seconds": float(delay_seconds),
        "half_width_degrees": normalized,
        "load_sign_source": "mujoco_qfrc_bias_sign",
        "load_sign_zero_threshold_nm": float(load_sign_zero_threshold_nm),
        "zero_sign_behavior": "retain_last_nonzero_sign",
        "source_action_receipt": mapped["action_receipt"],
        "effective_target_transitions": transitions,
        "source_actions_modified": False,
    }
    schedule["sha256"] = canonical_digest(schedule)
    return outputs, schedule
