"""Review-only visuals for the bounded B-G source-fit diagnostic."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from .contact_prior import (
    apply_contact_variant,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    JointAdapter,
    _id,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, sha256_file
from .pawn_bg_source_fit import (
    EXPECTED_CONTRACT_SHA256,
    SourceFitError,
    _selected_training_episodes,
    extract_phase_indices,
    load_source_fit_contract,
)
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)


VISUAL_SCHEMA = "sim2claw.pawn_bg_source_fit_visual_comparison.v1"
HISTORY_SCHEMA = "sim2claw.pawn_bg_source_fit_score_history.v1"


def _load_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SourceFitError(f"source-fit receipt is missing: {path}")
    try:
        receipt = json.loads(path.read_bytes())
    except json.JSONDecodeError as error:
        raise SourceFitError("source-fit receipt is invalid JSON") from error
    if receipt.get("source_fit_contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise SourceFitError("source-fit visual refuses a receipt from another contract")
    if receipt.get("schema_version") != "sim2claw.pawn_bg_source_fit_receipt.v1":
        raise SourceFitError("source-fit receipt schema drifted")
    return receipt


def _adapter_from_receipt(receipt: dict[str, Any]) -> JointAdapter:
    payload = receipt.get("best_candidate_adapter")
    if type(payload) is not dict:
        raise SourceFitError("source-fit receipt has no best candidate adapter")
    adapter = JointAdapter(
        adapter_id=payload["adapter_id"],
        body_joint_signs=tuple(payload["body_joint_signs"]),
        body_joint_zero_offsets_rad=tuple(payload["body_joint_zero_offsets_rad"]),
        evidence_class=payload["evidence_class"],
    )
    if adapter.sha256 != payload.get("adapter_sha256"):
        raise SourceFitError("best candidate adapter digest drifted")
    return adapter


def _episode_score(receipt: dict[str, Any], folder_label: str) -> dict[str, Any]:
    rows = receipt["final_contact_variants"]["nominal_uncalibrated"]["episodes"]
    matches = [row["score"] for row in rows if row["folder_label"] == folder_label]
    if len(matches) != 1:
        raise SourceFitError("source-fit receipt does not contain exactly one requested episode")
    return matches[0]


def _annotate_pair(
    physical_bgr: np.ndarray,
    simulation_rgb: np.ndarray,
    *,
    relative_time_seconds: float,
    score: dict[str, Any],
) -> np.ndarray:
    simulation_bgr = cv2.cvtColor(simulation_rgb, cv2.COLOR_RGB2BGR)
    if physical_bgr.shape[:2] != (480, 640):
        physical_bgr = cv2.resize(physical_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    if simulation_bgr.shape[:2] != (480, 640):
        simulation_bgr = cv2.resize(simulation_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((512, 1280, 3), dtype=np.uint8)
    canvas[32:, :640] = physical_bgr
    canvas[32:, 640:] = simulation_bgr
    cv2.putText(
        canvas,
        "PHYSICAL C922 SOURCE (owner-reviewed)",
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "SIM NOMINAL + BEST REJECTED SOURCE-FIT ADAPTER",
        (650, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (120, 220, 255),
        1,
        cv2.LINE_AA,
    )
    footer = (
        f"t={relative_time_seconds:5.2f}s | diagnostic reward={score['diagnostic_reward']:.3f} | "
        f"contact={int(score['gate_results']['selected_piece_contact_observed'])} | "
        f"success={int(score['task_consequence_success'])} | NOT CALIBRATED"
    )
    cv2.rectangle(canvas, (0, 486), (1280, 512), (0, 0, 0), -1)
    cv2.putText(
        canvas,
        footer,
        (10, 505),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return canvas


def render_episode_comparison(
    *,
    source_repository_root: Path,
    source_fit_receipt_path: Path,
    folder_label: str,
    output_directory: Path,
) -> dict[str, Any]:
    contract = load_source_fit_contract()
    receipt = _load_receipt(source_fit_receipt_path)
    adapter = _adapter_from_receipt(receipt)
    selected, _ = _selected_training_episodes(contract, source_repository_root.resolve())
    matches = [row for row in selected if row[0]["folder_label"] == folder_label]
    if len(matches) != 1:
        raise SourceFitError("visual comparison requires one allowed training episode")
    episode, source, _, samples = matches[0]
    score = _episode_score(receipt, folder_label)

    reward = load_reward_contract()
    board_center = registered_board_center(reward["scene_binding"]["scene_id"])
    spec = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
    )
    prior = read_contact_prior_snapshot()
    variant = load_simulator_variant("nominal_uncalibrated", contract_snapshot=prior)
    apply_contact_variant(spec, variant)
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)

    piece_name = BASELINE_PIECE_BY_FILE[source[0]]
    piece_joint = _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{piece_name}_free")
    piece_qpos = int(model.jnt_qposadr[piece_joint])
    data.qpos[piece_qpos : piece_qpos + 3] = board_square_center(
        source, board_center_in_table_frame_xy_m=board_center
    )
    actuator_ids = [
        _id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    joint_ids = [
        _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    qpos_addresses = [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids]
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
    first_actual = physical_values_to_sim_with_adapter(
        samples[0]["follower_actual_position_degrees"], bounds[-1], adapter
    )
    if np.any(first_actual < bounds[:, 0]) or np.any(first_actual > bounds[:, 1]):
        raise SourceFitError("visual comparison refuses an initial command that would clip")
    data.qpos[qpos_addresses] = first_actual
    data.ctrl[actuator_ids] = first_actual
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)

    source_receipt = json.loads(
        (source_repository_root / episode["assets"]["receipt"]).read_bytes()
    )
    video_metadata = source_receipt.get("overhead_video", {})
    video_path = source_repository_root / episode["assets"]["overhead_video"]
    if video_metadata.get("video_sha256") != episode["overhead_video_sha256"]:
        raise SourceFitError("overhead video identity drifted in source receipt")
    action_offset = float(video_metadata["action_start_video_offset_seconds"])
    rotation = int(video_metadata["orientation_rotation_degrees"])
    if rotation not in (0, 180):
        raise SourceFitError("visual comparison only supports frozen 0/180 orientation")

    output_directory.mkdir(parents=True, exist_ok=True)
    raw_path = output_directory / f"{folder_label}_physical_vs_sim.raw.mp4"
    video_output = output_directory / f"{folder_label}_physical_vs_sim.mp4"
    poster_output = output_directory / f"{folder_label}_physical_vs_sim_poster.png"
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(episode["sample_hz"]),
        (1280, 512),
    )
    if not writer.isOpened():
        raise SourceFitError("OpenCV could not open the diagnostic comparison writer")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        writer.release()
        raise SourceFitError("OpenCV could not open the hash-bound overhead video")
    renderer = mujoco.Renderer(model, height=480, width=640)
    open_index, close_index, release_index = extract_phase_indices(samples, contract)
    poster_indices = {
        0: "start",
        open_index: "source open",
        close_index: "source near-close",
        (close_index + release_index) // 2: "transfer",
        release_index: "destination reopen",
        len(samples) - 1: "end",
    }
    poster_frames: list[tuple[str, np.ndarray]] = []
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / float(episode["sample_hz"])
    try:
        for index, sample in enumerate(samples):
            timestamp = float(sample["timestamp_monotonic_seconds"])
            dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
            if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
                dt = nominal_dt
            previous_timestamp = timestamp
            command = physical_values_to_sim_with_adapter(
                sample["follower_command_degrees"], bounds[-1], adapter
            )
            if np.any(command < bounds[:, 0]) or np.any(command > bounds[:, 1]):
                raise SourceFitError("comparison refuses to clip a source-fit command")
            data.ctrl[actuator_ids] = command
            mujoco.mj_step(
                model,
                data,
                nstep=max(1, round(dt / float(model.opt.timestep))),
            )
            renderer.update_scene(data, camera="overhead")
            simulation_rgb = renderer.render().copy()
            capture.set(cv2.CAP_PROP_POS_MSEC, (action_offset + timestamp) * 1000.0)
            ok, physical_bgr = capture.read()
            if not ok:
                raise SourceFitError(f"overhead frame decode failed at sample {index}")
            if rotation == 180:
                physical_bgr = cv2.rotate(physical_bgr, cv2.ROTATE_180)
            paired = _annotate_pair(
                physical_bgr,
                simulation_rgb,
                relative_time_seconds=timestamp,
                score=score,
            )
            writer.write(paired)
            if index in poster_indices:
                poster_frames.append((poster_indices[index], paired.copy()))
    finally:
        renderer.close()
        capture.release()
        writer.release()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SourceFitError("ffmpeg is required to encode the diagnostic comparison")
    completed = subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_path),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", str(video_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SourceFitError(f"ffmpeg comparison encoding failed: {completed.stderr[-500:]}")
    raw_path.unlink()

    poster = Image.new("RGB", (1280, 768), color=(18, 18, 18))
    for index, (label, paired_bgr) in enumerate(poster_frames):
        image = Image.fromarray(cv2.cvtColor(paired_bgr, cv2.COLOR_BGR2RGB))
        image = image.resize((640, 256), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 180, 22), fill=(0, 0, 0))
        draw.text((6, 5), label, fill=(255, 255, 255))
        poster.paste(image, ((index % 2) * 640, (index // 2) * 256))
    poster.save(poster_output)

    report = {
        "schema_version": VISUAL_SCHEMA,
        "folder_label": folder_label,
        "recording_id": episode["recording_id"],
        "frame_count": len(samples),
        "fps": episode["sample_hz"],
        "source_samples_sha256": episode["samples_sha256"],
        "source_overhead_video_sha256": episode["overhead_video_sha256"],
        "source_fit_receipt_sha256": sha256_file(source_fit_receipt_path),
        "source_fit_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "best_candidate_adapter_sha256": adapter.sha256,
        "candidate_accepted": receipt["candidate_accepted"],
        "optimization_status": receipt["optimization_status"],
        "contact_variant": "nominal_uncalibrated",
        "episode_score": score,
        "physical_orientation_rotation_degrees_applied": rotation,
        "comparison_video_path": str(video_output),
        "comparison_video_sha256": sha256_file(video_output),
        "poster_path": str(poster_output),
        "poster_sha256": sha256_file(poster_output),
        "claim_boundary": "Review-only synchronized physical-source versus simulated diagnostic. The simulator adapter was rejected and is not physical calibration or ACT policy proof.",
    }
    report_path = output_directory / f"{folder_label}_physical_vs_sim_receipt.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def _draw_series(
    draw: ImageDraw.ImageDraw,
    values: list[float],
    *,
    box: tuple[int, int, int, int],
    low: float,
    high: float,
    color: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, outline=(90, 90, 90), width=1)
    points = []
    for index, value in enumerate(values):
        x = left + 80 + index * ((right - left - 160) / max(1, len(values) - 1))
        y = bottom - 35 - (value - low) / (high - low) * (bottom - top - 70)
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=color, width=4)
    for point, value in zip(points, values, strict=True):
        x, y = point
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
        draw.text((x - 35, y - 26), f"{value:.3f}", fill=(235, 235, 235))


def render_score_history(
    *, source_fit_receipt_path: Path, output_directory: Path
) -> dict[str, Any]:
    contract = load_source_fit_contract()
    receipt = _load_receipt(source_fit_receipt_path)
    baseline = receipt["baseline"]
    rows = [
        {
            "configuration_sequence": 0,
            "iteration": "00_provisional_baseline",
            "adapter_sha256": baseline["adapter"]["adapter_sha256"],
            "contact_variant_id": "nominal_uncalibrated",
            "accepted": False,
            "reason": "provisional_adapter_clips_every_episode",
            "event_rms_m": baseline["kinematic"]["event_rms_distance_m"],
            **baseline["nominal_physics"]["aggregate"],
        }
    ]
    expected_variants = contract["selection"]["selected_adapter_final_contact_variants"]
    if set(receipt["final_contact_variants"]) != set(expected_variants):
        raise SourceFitError("source-fit receipt final contact variants drifted")
    for sequence, variant_id in enumerate(expected_variants, start=1):
        variant_result = receipt["final_contact_variants"][variant_id]
        rows.append({
            "configuration_sequence": sequence,
            "iteration": f"{sequence:02d}_best_candidate__{variant_id}",
            "adapter_sha256": receipt["best_candidate_adapter"]["adapter_sha256"],
            "contact_variant_id": variant_id,
            "accepted": receipt["candidate_accepted"],
            "reason": receipt["optimization_status"],
            "event_rms_m": receipt["best_candidate_kinematic"]["event_rms_distance_m"],
            **variant_result["aggregate"],
        })
    history = {
        "schema_version": HISTORY_SCHEMA,
        "source_fit_contract_sha256": receipt["source_fit_contract_sha256"],
        "reward_contract_sha256": receipt["reward_contract_sha256"],
        "contact_prior_sha256": receipt["contact_prior_sha256"],
        "source_fit_receipt_sha256": sha256_file(source_fit_receipt_path),
        "cohort": "same_11_existing_train_partition_owner_reviewed_product_episodes",
        "rows": rows,
        "claim_boundary": "These are source-fit configurations scored on the same training-side source replay and frozen simulator evaluator. They are not physical calibration history or held-out validation.",
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "source_fit_score_history.json"
    json_path.write_text(
        json.dumps(history, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    chart = Image.new("RGB", (1600, 980), color=(20, 23, 28))
    draw = ImageDraw.Draw(chart)
    draw.text((45, 28), "B-G source-fit score history", fill=(255, 255, 255))
    draw.text(
        (45, 52),
        "Same 11 training-side source episodes | frozen reward/evaluator | no held-out validation",
        fill=(170, 178, 188),
    )
    draw.text((45, 93), "Mean diagnostic reward", fill=(220, 225, 230))
    rewards = [float(row["mean_diagnostic_reward"]) for row in rows]
    _draw_series(
        draw, rewards, box=(45, 120, 1555, 350), low=-1.0, high=1.0,
        color=(255, 166, 70),
    )
    draw.text((45, 385), "Pinch-point event RMS (millimeters; lower is better)", fill=(220, 225, 230))
    rms_mm = [1000.0 * float(row["event_rms_m"]) for row in rows]
    _draw_series(
        draw, rms_mm, box=(45, 412, 1555, 642), low=0.0,
        high=max(350.0, 1.1 * max(rms_mm)), color=(80, 196, 255),
    )
    for index, row in enumerate(rows):
        y = 666 + index * 48
        draw.text((45, y), row["iteration"], fill=(235, 235, 235))
        draw.text((500, y), f"reward {row['mean_diagnostic_reward']:.3f}", fill=(185, 190, 195))
        draw.text((655, y), f"RMS {1000.0 * row['event_rms_m']:.3f} mm", fill=(185, 190, 195))
        draw.text((850, y), f"clipped {row['recordings_with_clipped_commands']}/11", fill=(185, 190, 195))
        draw.text((1015, y), f"contact {row['selected_piece_contact_episode_count']}/11", fill=(185, 190, 195))
        draw.text((1175, y), f"success {row['task_consequence_success_count']}/11", fill=(185, 190, 195))
        draw.text(
            (1340, y),
            f"accepted {'yes' if row['accepted'] else 'no'}",
            fill=(90, 220, 130) if row["accepted"] else (255, 105, 105),
        )
    draw.text(
        (45, 930),
        "Result: geometry fit improved, consequence score worsened; contact variants were insensitive; no adapter accepted.",
        fill=(255, 190, 95),
    )
    chart_path = output_directory / "source_fit_score_history.png"
    chart.save(chart_path)
    history["history_json_path"] = str(json_path)
    history["history_json_sha256"] = sha256_file(json_path)
    history["chart_path"] = str(chart_path)
    history["chart_sha256"] = sha256_file(chart_path)
    return history


__all__ = ["render_episode_comparison", "render_score_history"]
