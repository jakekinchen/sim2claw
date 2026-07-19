"""Separately invoked CPU/fp32 evaluator for the frozen chess-rook ACT task."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import torch

from .act_model import (
    ACTCheckpointSnapshot,
    load_act_checkpoint_snapshot,
    read_act_checkpoint_snapshot,
)
from .chess_task import ChessRookLiftEnv, load_task_contract, task_contract_sha256
from .contact_prior import SimulatorVariant
from .paths import DEFAULT_OUTPUT_ROOT
from .render import write_rgb_png
from .state_trace import EpisodeStateTraceRecorder
from .studio_events import StudioActivity


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _longest_true_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _longest_true_span(values: list[bool]) -> tuple[int | None, int | None, int]:
    best_start: int | None = None
    best_end: int | None = None
    best_length = 0
    current_start: int | None = None
    for index, value in enumerate(values):
        if value and current_start is None:
            current_start = index
        if current_start is not None and (not value or index == len(values) - 1):
            end = index if value else index - 1
            length = end - current_start + 1
            if length > best_length:
                best_start, best_end, best_length = current_start, end, length
            current_start = None
    return best_start, best_end, best_length


def _encode_video(frames: Path, output: Path, *, fps: int) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return {"created": False, "reason": "ffmpeg_not_found"}
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames / "%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    version = subprocess.run(
        [ffmpeg, "-version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    return {
        "created": True,
        "path": str(output),
        "sha256": _sha256_file(output),
        "ffmpeg": version,
        "stderr": completed.stderr,
    }


def evaluate_act(
    checkpoint_source: Path | ACTCheckpointSnapshot,
    *,
    output_directory: Path | None = None,
    render_video: bool = True,
    simulator_variant: SimulatorVariant | None = None,
) -> dict[str, Any]:
    task = load_task_contract()
    evaluator = task["evaluator"]
    output = output_directory or DEFAULT_OUTPUT_ROOT / "act" / task["task_id"] / "eval"
    frames_directory = output / "frames"
    output.mkdir(parents=True, exist_ok=True)
    activity = StudioActivity(
        kind="evaluation",
        title="Evaluate held-out ACT episode",
        task_id=str(task["task_id"]),
    )
    if render_video:
        frames_directory.mkdir(parents=True, exist_ok=True)

    torch.set_num_threads(1)
    torch.manual_seed(int(task["held_out_split"]["seeds"][0]))
    device = torch.device("cpu")
    if simulator_variant is not None and not isinstance(
        checkpoint_source, ACTCheckpointSnapshot
    ):
        raise ValueError("contact sensitivity evaluation requires an accepted snapshot")
    checkpoint_snapshot = (
        checkpoint_source
        if isinstance(checkpoint_source, ACTCheckpointSnapshot)
        else read_act_checkpoint_snapshot(checkpoint_source)
    )
    if (
        simulator_variant is not None
        and checkpoint_snapshot.sha256
        != simulator_variant.accepted_checkpoint_sha256
    ):
        raise ValueError("contact sensitivity checkpoint snapshot is not accepted")
    model, statistics, checkpoint = load_act_checkpoint_snapshot(
        checkpoint_snapshot, device=device
    )
    if checkpoint.get("task_id") != task["task_id"]:
        raise ValueError("checkpoint task id does not match the frozen evaluator")
    if checkpoint.get("task_contract_sha256") != task_contract_sha256():
        raise ValueError("checkpoint predates or differs from the frozen task contract")
    if simulator_variant is not None and (
        simulator_variant.task_id != task["task_id"]
        or simulator_variant.task_contract_sha256 != task_contract_sha256()
    ):
        raise ValueError("simulator variant does not bind the frozen ACT task contract")
    if next(model.parameters()).dtype != torch.float32:
        raise ValueError("evaluator requires a float32 ACT checkpoint")

    seed = int(task["held_out_split"]["seeds"][0])
    raw_offset = task["held_out_split"]["piece_planar_offsets_m"][0]
    offset = (float(raw_offset[0]), float(raw_offset[1]))
    env = ChessRookLiftEnv(
        task,
        seed=seed,
        piece_offset_xy_m=offset,
        simulator_variant=simulator_variant,
    )
    trace = EpisodeStateTraceRecorder(
        env.model,
        proof_class="simulation_learned_policy_episode_state_trace",
    )
    trace.capture(env.data, phase="initial", force=True)
    phase_boundaries: list[tuple[int, str]] = []
    phase_cursor = 0
    for phase_name, phase_count in task["episode"]["phase_control_steps"].items():
        phase_cursor += int(phase_count)
        phase_boundaries.append((phase_cursor, str(phase_name)))
    renderer = (
        mujoco.Renderer(env.model, height=640, width=960) if render_video else None
    )
    render_stride = 20
    frame_index = 0

    def snapshot() -> None:
        nonlocal frame_index
        if renderer is None:
            return
        write_rgb_png(frames_directory / f"{frame_index:04d}.png", env.render(renderer))
        frame_index += 1

    actions: list[list[float]] = []
    contacts: list[bool] = []
    heights: list[float] = []
    phase_labels: list[str] = []
    piece_linear_speeds: list[float] = []
    piece_angular_speeds: list[float] = []
    maximum_absolute_joint_speed = 0.0
    finite_state = True
    decode_rows: list[dict[str, Any]] = []
    queue: deque[np.ndarray] = deque()
    chunk_size = int(task["act"]["chunk_size"])
    n_action_steps = int(task["act"]["n_action_steps"])
    started = time.monotonic()
    snapshot()
    try:
        for control_step in range(env.horizon):
            if not queue:
                observation = torch.from_numpy(env.observation(control_step)).unsqueeze(0)
                normalized_observation = (
                    observation - statistics["observation_mean"]
                ) / statistics["observation_std"]
                predicted_normalized = model.predict_action_chunk(
                    normalized_observation
                ).squeeze(0)
                predicted = (
                    predicted_normalized * statistics["action_std"]
                    + statistics["action_mean"]
                ).cpu().numpy()
                if predicted.shape != (chunk_size, int(task["action"]["dimension"])):
                    raise ValueError("ACT inference returned an invalid action chunk")
                if not np.isfinite(predicted).all():
                    raise ValueError("ACT inference returned non-finite actions")
                executed = min(n_action_steps, env.horizon - control_step)
                queue.extend(row.copy() for row in predicted[:executed])
                chunk_bytes = json.dumps(
                    predicted.astype(float).tolist(),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                decode_rows.append(
                    {
                        "decode_start_control_step": control_step,
                        "predicted_chunk_size": chunk_size,
                        "executed_action_count": executed,
                        "predicted_chunk_sha256": hashlib.sha256(chunk_bytes).hexdigest(),
                    }
                )
            action = queue.popleft()
            env.step(action)
            phase = next(
                name for boundary, name in phase_boundaries if control_step < boundary
            )
            trace.capture(env.data, phase=phase)
            actions.append(np.asarray(action, dtype=float).tolist())
            contacts.append(env.jaw_piece_contact())
            heights.append(float(env.piece_position()[2]))
            phase_labels.append(phase)
            piece_velocity = env.piece_velocity()
            piece_linear_speeds.append(float(np.linalg.norm(piece_velocity[:3])))
            piece_angular_speeds.append(float(np.linalg.norm(piece_velocity[3:])))
            joint_velocity = np.asarray(
                env.data.qvel[env.dof_addresses], dtype=np.float64
            )
            maximum_absolute_joint_speed = max(
                maximum_absolute_joint_speed,
                float(np.max(np.abs(joint_velocity))),
            )
            finite_state = finite_state and bool(
                np.isfinite(env.data.qpos).all()
                and np.isfinite(env.data.qvel).all()
                and np.isfinite(env.data.ctrl).all()
            )
            if (control_step + 1) % render_stride == 0:
                snapshot()
                activity.update(
                    phase="Running held-out simulation",
                    current=control_step + 1,
                    total=env.horizon,
                    detail=f"Rendered frame {frame_index}",
                    metrics={"piece_height_m": heights[-1]},
                )
        if env.horizon % render_stride:
            snapshot()
        trace.capture(env.data, phase=phase_boundaries[-1][1], force=True)
    finally:
        if renderer is not None:
            renderer.close()

    action_trace_path = output / "action_trace.json"
    action_trace_payload = {
        "schema_version": "sim2claw.act_action_trace.v1",
        "task_id": task["task_id"],
        "seed": seed,
        "actions_rad": actions,
        "decode_rows": decode_rows,
    }
    action_trace_path.write_text(
        json.dumps(action_trace_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    action_trace_sha256 = _sha256_file(action_trace_path)
    state_trace_path = output / "state_trace.json"
    state_trace = trace.write(state_trace_path)

    initial_height = env.initial_piece_height_m
    maximum_rise = float(max(heights) - initial_height)
    final_rise = float(heights[-1] - initial_height)
    longest_contact = _longest_true_run(contacts)
    sustained_contact_start, sustained_contact_end, sustained_contact_length = (
        _longest_true_span(contacts)
    )
    if sustained_contact_length != longest_contact:
        raise RuntimeError("contact timing span disagrees with evaluator contact gate")
    final_window = int(evaluator["final_contact_window_control_steps"])
    final_contact_fraction = float(np.mean(contacts[-final_window:]))
    contact_indices = [index for index, value in enumerate(contacts) if value]
    first_contact = contact_indices[0] if contact_indices else None
    last_contact = contact_indices[-1] if contact_indices else None
    contact_transitions = [
        index
        for index in range(1, len(contacts))
        if contacts[index] != contacts[index - 1]
    ]
    first_contact_loss = next(
        (
            index
            for index in contact_transitions
            if first_contact is not None and index > first_contact and not contacts[index]
        ),
        None,
    )
    first_contact_by_phase = {
        phase_name: next(
            (
                index
                for index, (phase, contacted) in enumerate(
                    zip(phase_labels, contacts, strict=True)
                )
                if phase == phase_name and contacted
            ),
            None,
        )
        for phase_name in task["episode"]["phase_control_steps"]
    }
    gates = {
        "maximum_piece_rise": {
            "measured": maximum_rise,
            "comparison": ">=",
            "threshold": evaluator["minimum_piece_rise_m"],
            "passed": maximum_rise >= evaluator["minimum_piece_rise_m"],
        },
        "final_piece_rise": {
            "measured": final_rise,
            "comparison": ">=",
            "threshold": evaluator["minimum_final_piece_rise_m"],
            "passed": final_rise >= evaluator["minimum_final_piece_rise_m"],
        },
        "consecutive_jaw_piece_contact": {
            "measured": longest_contact,
            "comparison": ">=",
            "threshold": evaluator["minimum_consecutive_contact_control_steps"],
            "passed": longest_contact
            >= evaluator["minimum_consecutive_contact_control_steps"],
        },
        "final_contact_fraction": {
            "measured": final_contact_fraction,
            "comparison": ">=",
            "threshold": evaluator["minimum_final_contact_fraction"],
            "window_control_steps": final_window,
            "passed": final_contact_fraction
            >= evaluator["minimum_final_contact_fraction"],
        },
        "model_owned_actions": {
            "measured": len(actions),
            "comparison": "==",
            "threshold": env.horizon,
            "passed": len(actions) == env.horizon,
        },
        "assistance_frames": {
            "measured": 0,
            "comparison": "==",
            "threshold": 0,
            "passed": True,
        },
    }
    success = all(gate["passed"] for gate in gates.values())
    video = {"created": False, "reason": "render_disabled"}
    if render_video:
        video = _encode_video(
            frames_directory,
            output / "act_chess_rook_lift.mp4",
            fps=10,
        )

    receipt = {
        "schema_version": "sim2claw.act_evaluation_receipt.v1",
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(),
        "proof_class": "simulation_learned_policy_episode",
        "policy": {
            "type": "ACT",
            "architecture": task["act"]["architecture"],
            "checkpoint_source_path": str(checkpoint_snapshot.source_path),
            "checkpoint_snapshot_sha256": checkpoint_snapshot.sha256,
            "checkpoint_snapshot_bytes": len(checkpoint_snapshot.data),
            "checkpoint_snapshot_immutable": True,
            "chunk_size": chunk_size,
            "n_action_steps": n_action_steps,
            "n_obs_steps": 1,
        },
        "simulator_variant": (
            {
                "variant_id": simulator_variant.variant_id,
                "variant_sha256": simulator_variant.variant_sha256,
                "contract": str(simulator_variant.contract_path),
                "contract_sha256": simulator_variant.contract_sha256,
                "rubber_tip_enabled": simulator_variant.rubber_tip_enabled,
                "application": env.variant_application,
                "compiled_identity": env.compiled_variant_identity,
            }
            if simulator_variant is not None
            else {
                "variant_id": "legacy_implicit_nominal",
                "rubber_tip_enabled": False,
                "application": None,
                "compiled_identity": env.compiled_variant_identity,
            }
        ),
        "episode": {
            "seed": seed,
            "seed_role": "held_out_evaluation_only",
            "piece": env.piece_name,
            "arm": env.arm,
            "piece_planar_offset_m": list(offset),
            "control_steps": env.horizon,
            "physics_steps_per_control": env.control_interval,
            "initial_piece_height_m": initial_height,
            "maximum_piece_rise_m": maximum_rise,
            "final_piece_rise_m": final_rise,
            "longest_contact_control_steps": longest_contact,
            "final_contact_fraction": final_contact_fraction,
            "decode_count": len(decode_rows),
            "contact_timing": {
                "first_contact_control_step": first_contact,
                "last_contact_control_step": last_contact,
                "contact_control_steps": len(contact_indices),
                "transition_control_steps": contact_transitions,
                "first_contact_loss_after_first_contact_control_step": first_contact_loss,
                "longest_contact_run": {
                    "start_control_step": sustained_contact_start,
                    "end_control_step": sustained_contact_end,
                    "control_steps": sustained_contact_length,
                },
                "first_contact_by_phase": first_contact_by_phase,
                "task_has_release_phase": False,
                "release_timing_control_step": None,
            },
        },
        "stability": {
            "finite_state": finite_state,
            "maximum_piece_linear_speed_m_s": max(piece_linear_speeds, default=0.0),
            "maximum_piece_angular_speed_rad_s": max(piece_angular_speeds, default=0.0),
            "maximum_absolute_robot_joint_speed_rad_s": maximum_absolute_joint_speed,
        },
        "gates": gates,
        "success": success,
        "failed_gates": [name for name, gate in gates.items() if not gate["passed"]],
        "terminal_outcome": "held_rook_above_board" if success else "act_episode_failed",
        "artifacts": {
            "action_trace": str(action_trace_path),
            "action_trace_sha256": action_trace_sha256,
            "state_trace": str(state_trace_path),
            "state_trace_sha256": state_trace["sha256"],
            "video": video,
        },
        "runtime": {
            "evaluator_owner": evaluator["owner"],
            "device": "cpu",
            "dtype": "float32",
            "torch": torch.__version__,
            "elapsed_seconds": time.monotonic() - started,
        },
        "model_owned_all_actions": True,
        "assistance_used": False,
        "physical_authority": False,
        "camera_accessed": False,
        "serial_accessed": False,
        "gateway_accessed": False,
        "external_compute_started": False,
        "brev_compute_started": False,
    }
    receipt_path = output / "evaluation_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt["receipt"] = str(receipt_path)
    activity.complete(
        detail=str(receipt["terminal_outcome"]),
        metrics={
            "maximum_piece_rise_m": maximum_rise,
            "final_piece_rise_m": final_rise,
        },
        episode_id=f"{task['task_id']}:held-out-{seed}",
    )
    return receipt
