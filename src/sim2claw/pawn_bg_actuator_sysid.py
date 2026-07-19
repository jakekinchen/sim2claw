"""Bounded actuator identification for the SO-101 left arm from recorded episodes.

Baseline question first: under recorded commands, is the simulated arm's joint
trajectory closer to the measured encoder trajectory than the command signal
itself is? If not, the simulator's actuator model adds no fidelity beyond a
wire. The identification then fits three bounded global parameters aligned
with the frozen sysid stage-2 semantics (command latency, actuator gain scale,
joint damping scale) plus a bounded force-range scale (torque saturation is
what produces the observed stalls), on the frozen train split only, and
validates once on the frozen held-out split.

Uses the selected workcell candidate geometry (board relabel + planar fit +
shoulder-lift zero offset) so no command clips. No promotion authority.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .pawn_bg_demo_sim import (
    ROBOT_JOINTS,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import sha256_file
from .pawn_bg_workcell_fit import (
    CATALOG_PATH,
    SPLIT_PATH,
    WorkcellCandidate,
    _split_membership,
    build_workcell_model,
)
from .pawn_bg_demo_sim import _load_source

BODY_JOINT_NAMES = ROBOT_JOINTS[:5]

PARAMETER_BOUNDS = {
    "command_latency_seconds": (0.0, 0.15),
    "actuator_gain_scale": (0.5, 1.5),
    "joint_damping_scale": (0.5, 2.0),
    "actuator_forcerange_scale": (0.5, 1.5),
}
NOMINAL_PARAMETERS = {
    "command_latency_seconds": 0.0,
    "actuator_gain_scale": 1.0,
    "joint_damping_scale": 1.0,
    "actuator_forcerange_scale": 1.0,
}


@dataclass(frozen=True)
class TrackedEpisode:
    recording_id: str
    folder_label: str
    split: str
    timestamps: np.ndarray  # (N,)
    commands: np.ndarray  # (N, 6) sim units, adapter-mapped
    measured: np.ndarray  # (N, 6) sim units, adapter-mapped


def load_candidate(receipt_path: Path) -> WorkcellCandidate:
    receipt = json.loads(receipt_path.read_bytes())
    params = receipt["selected_parameters"]
    return WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            params["board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(v) for v in params["board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=tuple(float(v) for v in params["joint_zero_offsets_rad"]),
        joint_range_envelope_rad=tuple(
            (float(a), float(b)) for a, b in params["joint_range_envelope_rad"]
        ),
        base_z_offset_m=float(params.get("base_z_offset_m", 0.0)),
    )


def load_tracked_episodes(
    source_repository_root: Path, candidate: WorkcellCandidate
) -> list[TrackedEpisode]:
    catalog = json.loads(CATALOG_PATH.read_bytes())
    membership = _split_membership()
    binding = build_workcell_model(candidate)
    gripper_bounds = binding["actuator_bounds"][-1]
    adapter = candidate.adapter()
    episodes = []
    for episode in catalog["episodes"]:
        samples = _load_source(episode, source_repository_root)
        timestamps, commands, measured = [], [], []
        for row in samples:
            timestamps.append(float(row["timestamp_monotonic_seconds"]))
            commands.append(physical_values_to_sim_with_adapter(
                row["follower_command_degrees"], gripper_bounds, adapter
            ))
            measured.append(physical_values_to_sim_with_adapter(
                row["follower_actual_position_degrees"], gripper_bounds, adapter
            ))
        timestamps = np.asarray(timestamps)
        timestamps = timestamps - timestamps[0]
        episodes.append(TrackedEpisode(
            recording_id=episode["recording_id"],
            folder_label=episode["folder_label"],
            split=membership[episode["recording_id"]],
            timestamps=timestamps,
            commands=np.asarray(commands),
            measured=np.asarray(measured),
        ))
    return episodes


def _apply_parameters(model: mujoco.MjModel, actuator_ids: list[int],
                      joint_ids: list[int], parameters: dict[str, float]) -> None:
    gain = float(parameters["actuator_gain_scale"])
    damping = float(parameters["joint_damping_scale"])
    force = float(parameters["actuator_forcerange_scale"])
    for actuator_id in actuator_ids:
        model.actuator_gainprm[actuator_id, 0] *= gain
        model.actuator_biasprm[actuator_id, 1] *= gain
        model.actuator_forcerange[actuator_id] *= force
    for joint_id in joint_ids:
        dof = int(model.jnt_dofadr[joint_id])
        model.dof_damping[dof] *= damping


def make_parameterized_binding(
    candidate: WorkcellCandidate, parameters: dict[str, float]
) -> dict[str, Any]:
    binding = build_workcell_model(candidate)
    _apply_parameters(
        binding["model"], binding["actuator_ids"], binding["joint_ids"], parameters
    )
    binding["parameters"] = dict(parameters)
    return binding


def simulate_tracking(
    episode: TrackedEpisode,
    binding: dict[str, Any],
) -> np.ndarray:
    """Replay commands through physics; return sim qpos at sample times (N, 6)."""

    from .scene import initialize_robot_poses

    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    latency = float(binding["parameters"]["command_latency_seconds"])

    mujoco.mj_resetData(model, data)
    initialize_robot_poses(model, data)
    data.qpos[qpos_addresses] = episode.measured[0]
    data.ctrl[actuator_ids] = episode.measured[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)

    timestep = float(model.opt.timestep)
    times = episode.timestamps
    duration = float(times[-1])
    outputs = np.empty_like(episode.measured)
    sample_cursor = 0
    step_count = int(math.ceil(duration / timestep)) + 1
    for step in range(step_count + 1):
        now = step * timestep
        command_index = int(np.searchsorted(times, now - latency, side="right") - 1)
        data.ctrl[actuator_ids] = episode.commands[max(0, command_index)]
        while sample_cursor < len(times) and times[sample_cursor] <= now + timestep / 2:
            outputs[sample_cursor] = data.qpos[qpos_addresses]
            sample_cursor += 1
        if sample_cursor >= len(times):
            break
        mujoco.mj_step(model, data)
    while sample_cursor < len(times):
        outputs[sample_cursor] = data.qpos[qpos_addresses]
        sample_cursor += 1
    return outputs


def tracking_metrics(
    episodes: list[TrackedEpisode],
    candidate: WorkcellCandidate,
    parameters: dict[str, float],
) -> dict[str, Any]:
    binding = make_parameterized_binding(candidate, parameters)
    per_joint_sim = np.zeros(5)
    per_joint_cmd = np.zeros(5)
    rows = 0
    per_episode = []
    for episode in episodes:
        sim = simulate_tracking(episode, binding)
        sim_err = sim[:, :5] - episode.measured[:, :5]
        cmd_err = episode.commands[:, :5] - episode.measured[:, :5]
        per_joint_sim += np.sum(sim_err**2, axis=0)
        per_joint_cmd += np.sum(cmd_err**2, axis=0)
        rows += len(episode.timestamps)
        per_episode.append({
            "recording_id": episode.recording_id,
            "folder_label": episode.folder_label,
            "sim_vs_measured_rms_deg": float(np.degrees(np.sqrt(np.mean(sim_err**2)))),
            "command_vs_measured_rms_deg": float(np.degrees(np.sqrt(np.mean(cmd_err**2)))),
        })
    sim_rms = np.degrees(np.sqrt(per_joint_sim / rows))
    cmd_rms = np.degrees(np.sqrt(per_joint_cmd / rows))
    return {
        "episode_count": len(episodes),
        "sample_rows": rows,
        "per_joint_sim_vs_measured_rms_deg": dict(zip(BODY_JOINT_NAMES, sim_rms.tolist())),
        "per_joint_command_vs_measured_rms_deg": dict(zip(BODY_JOINT_NAMES, cmd_rms.tolist())),
        "overall_sim_vs_measured_rms_deg": float(np.sqrt(np.mean(sim_rms**2))),
        "overall_command_vs_measured_rms_deg": float(np.sqrt(np.mean(cmd_rms**2))),
        "per_episode": per_episode,
    }


def fit_actuator_parameters(
    train: list[TrackedEpisode],
    candidate: WorkcellCandidate,
) -> dict[str, Any]:
    names = list(PARAMETER_BOUNDS)
    lower = np.asarray([PARAMETER_BOUNDS[name][0] for name in names])
    upper = np.asarray([PARAMETER_BOUNDS[name][1] for name in names])
    x0 = np.asarray([NOMINAL_PARAMETERS[name] for name in names])

    def residual(x: np.ndarray) -> np.ndarray:
        parameters = dict(zip(names, x.tolist()))
        binding = make_parameterized_binding(candidate, parameters)
        blocks = []
        for episode in train:
            sim = simulate_tracking(episode, binding)
            blocks.append((sim[:, :5] - episode.measured[:, :5]).ravel())
        return np.concatenate(blocks)

    fit = least_squares(
        residual, x0=x0, bounds=(lower, upper), method="trf",
        diff_step=0.05, xtol=1e-4, ftol=1e-6, max_nfev=60,
    )
    return {
        "fitted_parameters": dict(zip(names, fit.x.tolist())),
        "optimizer_status": int(fit.status),
        "optimizer_nfev": int(fit.nfev),
        "train_cost": float(fit.cost),
    }


def run_actuator_sysid(
    *,
    source_repository_root: Path,
    workcell_receipt_path: Path,
    output_path: Path,
    fit_train_limit: int | None = None,
) -> dict[str, Any]:
    candidate = load_candidate(workcell_receipt_path)
    episodes = load_tracked_episodes(source_repository_root, candidate)
    train = [episode for episode in episodes if episode.split == "train"]
    held_out = [episode for episode in episodes if episode.split == "held_out"]
    fit_train = train[:fit_train_limit] if fit_train_limit else train

    baseline_train = tracking_metrics(train, candidate, NOMINAL_PARAMETERS)
    fit_result = fit_actuator_parameters(fit_train, candidate)
    fitted = fit_result["fitted_parameters"]
    candidate_train = tracking_metrics(train, candidate, fitted)

    baseline_held_out = tracking_metrics(held_out, candidate, NOMINAL_PARAMETERS)
    candidate_held_out = tracking_metrics(held_out, candidate, fitted)

    receipt = {
        "schema_version": "sim2claw.pawn_bg_actuator_sysid_receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workcell_receipt_sha256": sha256_file(workcell_receipt_path),
        "split_sha256": sha256_file(SPLIT_PATH),
        "catalog_sha256": sha256_file(CATALOG_PATH),
        "parameter_bounds": PARAMETER_BOUNDS,
        "nominal_parameters": NOMINAL_PARAMETERS,
        "fit": fit_result,
        "train_baseline": baseline_train,
        "train_candidate": candidate_train,
        "held_out_baseline": baseline_held_out,
        "held_out_candidate": candidate_held_out,
        "claim_boundary": (
            "Bounded global actuator-parameter candidate fitted on the frozen "
            "train split joint-tracking residuals and evaluated once on the "
            "frozen held-out split. Joint-space evidence only; no contact, "
            "task, policy, physical, or promotion claim."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt
