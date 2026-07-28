"""Publish one action-identical, contact-free B7 same-camera comparison.

This is a deliberately narrow evidence publisher. It consumes only the
already-recorded B7 packet, physical receipt, joint samples, camera media, and
retrospective diagnostic. It never opens a camera, serial bus, or robot
gateway.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import cv2
import mujoco
import numpy as np

from .learning_factory_artifacts import canonical_digest
from .paths import REPO_ROOT
from .real_to_sim_transfer import (
    COMPARISON_SCHEMA,
    _camera_from_board_evaluation,
    _configure_camera,
    _sha256,
)
from .recorded_replay import _compile_model
from .wrist_view_reposition import (
    _decode_capture_hold,
    _decode_stage,
    _physical_to_model_position,
    preview_wrist_view_actions,
)


EXPECTED_MOTION_SHA256 = (
    "0e5fc8a079b90670144d057d06dcd6aaf70660ea7e9eb67d5f2d27c497af6ede"
)
EXPECTED_HOLD_SHA256 = (
    "c6fd83f5b71a213a9066421fbddee632769d4beaaaa59032c57fb761394809a3"
)
EXPECTED_MOTION_ROWS = 901
EXPECTED_HOLD_ROWS = 80
EXPECTED_STATIONARY_RMS_M = 0.011194693183027439
EXPECTED_ROUTE_MAX_M = 0.019997062686465936
OUTPUT_FPS = 40
OUTPUT_SIZE = (1280, 720)
VIDEO_NAME = "b7_action_identical_same_camera.mp4"
POSTER_NAME = "b7_action_identical_same_camera_poster.png"
RECEIPT_NAME = "b7_action_identical_same_camera_receipt.json"

DEFAULT_RUN = (
    REPO_ROOT
    / "runs/geometric-hover/20260727-b7-mid-hover-hold-roundtrip-tricam-v3"
)
DEFAULT_CAMERA_EVALUATION = (
    REPO_ROOT
    / "runs/c922-board-base-registration/"
    "20260726-current-c922-pose-p2-successor-v1/evaluation.json"
)
DEFAULT_SCENE_REGISTRATION = (
    REPO_ROOT / "configs/evaluations/img5349_3dgs_board_registration_v1.json"
)


class ContactFreeComparisonError(RuntimeError):
    """A required immutable binding or comparison gate did not resolve."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContactFreeComparisonError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContactFreeComparisonError(
            f"cannot read {label}: {path}: {error}"
        ) from error
    _require(isinstance(value, dict), f"{label} is not a JSON object: {path}")
    return value


def _repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT))


def _verify_file(path: Path, expected: str, label: str) -> dict[str, Any]:
    _require(path.is_file(), f"{label} is missing: {path}")
    actual = _sha256(path)
    _require(actual == expected, f"{label} hash changed: {path}")
    return {
        "path": _repo_path(path),
        "sha256": actual,
        "bytes": path.stat().st_size,
    }


def _resolve_capture_path(stage_directory: Path, value: object) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = stage_directory / path
    return path.resolve()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise ContactFreeComparisonError(
            f"joint samples cannot be decoded: {error}"
        ) from error
    _require(bool(rows), "joint samples are empty")
    return rows


def _verify_exact_rows(
    rows: list[dict[str, Any]],
    motion: np.ndarray,
    hold: np.ndarray,
) -> dict[str, Any]:
    exact = np.concatenate((motion, hold), axis=0)
    _require(len(rows) == len(exact), "joint row count changed")
    motion_good = 0
    hold_good = 0
    for index, (row, action) in enumerate(zip(rows, exact, strict=True)):
        requested = np.asarray(row.get("requested_physical_units"), dtype="<f8")
        sent = np.asarray(row.get("follower_command_degrees"), dtype="<f8")
        expected_phase = "motion" if index < len(motion) else "capture_hold"
        expected_sha = (
            EXPECTED_MOTION_SHA256
            if expected_phase == "motion"
            else EXPECTED_HOLD_SHA256
        )
        _require(
            row.get("sample_index") == index,
            f"joint sample index changed at row {index}",
        )
        _require(
            row.get("phase") == expected_phase,
            f"joint sample phase changed at row {index}",
        )
        _require(
            requested.shape == (6,)
            and sent.shape == (6,)
            and requested.tobytes(order="C") == action.tobytes(order="C")
            and sent.tobytes(order="C") == action.tobytes(order="C"),
            f"exact requested/sent action bytes changed at row {index}",
        )
        _require(
            row.get("source_action_sha256") == expected_sha
            and row.get("precompiled_exact_action") is True,
            f"exact action identity changed at row {index}",
        )
        _require(
            not bool(row.get("rate_limited"))
            and not bool(row.get("safety_clamped"))
            and not bool(row.get("stalled"))
            and not bool(row.get("assistance"))
            and not bool(row.get("intervention")),
            f"assistance, limiting, clamp, or stall appeared at row {index}",
        )
        if expected_phase == "motion":
            motion_good += 1
        else:
            hold_good += 1
    return {
        "motion_rows_exact": motion_good,
        "motion_rows_expected": len(motion),
        "hold_rows_exact": hold_good,
        "hold_rows_expected": len(hold),
        "no_assistance_rate_limit_clamp_or_stall": True,
    }


class _VideoSampler:
    def __init__(
        self,
        path: Path,
        *,
        start_seconds: float,
        rotation_degrees: int = 0,
    ) -> None:
        self.path = path
        self.capture = cv2.VideoCapture(str(path))
        _require(self.capture.isOpened(), f"video input cannot open: {path}")
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        self.frame_count = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        _require(
            math.isfinite(self.fps) and self.fps > 0.0 and self.frame_count > 0,
            f"video metadata is invalid: {path}",
        )
        self.start_seconds = start_seconds
        self.rotation_degrees = rotation_degrees
        self.current_index = max(0, int(math.floor(start_seconds * self.fps))) - 1
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.current_index + 1)
        self.frame: np.ndarray | None = None

    def sample(self, relative_seconds: float) -> np.ndarray:
        target_seconds = self.start_seconds + relative_seconds
        target_index = min(
            self.frame_count - 1,
            max(0, int(round(target_seconds * self.fps))),
        )
        while self.current_index < target_index:
            ok, frame = self.capture.read()
            _require(ok, f"video frame unavailable: {self.path}:{target_index}")
            self.frame = frame
            self.current_index += 1
        _require(self.frame is not None, f"video produced no frame: {self.path}")
        if self.rotation_degrees == 180:
            return cv2.rotate(self.frame, cv2.ROTATE_180)
        return self.frame.copy()

    def close(self) -> None:
        self.capture.release()


def _fit(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    canvas = np.full((height, width, 3), 12, dtype=np.uint8)
    source_height, source_width = frame.shape[:2]
    scale = min(width / source_width, height / source_height)
    resized = cv2.resize(
        frame,
        (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        ),
        interpolation=cv2.INTER_AREA,
    )
    left = (width - resized.shape[1]) // 2
    top = (height - resized.shape[0]) // 2
    canvas[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
    return canvas


def _put(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    scale: float = 0.5,
    color: tuple[int, int, int] = (235, 235, 235),
    thickness: int = 1,
) -> None:
    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def _phase(index: int) -> str:
    if index < 301:
        return "APPROACH"
    if index < 601:
        return "STATIONARY HOVER"
    if index < 901:
        return "RETURN"
    return "TERMINAL HOLD"


def _composite(
    *,
    c922: np.ndarray,
    simulation: np.ndarray,
    pi: np.ndarray,
    d405: np.ndarray,
    index: int,
    relative_seconds: float,
) -> np.ndarray:
    frame = np.full((OUTPUT_SIZE[1], OUTPUT_SIZE[0], 3), 14, dtype=np.uint8)
    frame[40:520, 0:640] = _fit(c922, 640, 480)
    frame[40:520, 640:1280] = _fit(simulation, 640, 480)
    cv2.rectangle(frame, (0, 0), (1279, 40), (5, 5, 5), -1)
    _put(
        frame,
        "B7 120 mm HOVER  |  ACTION-IDENTICAL CONTACT-FREE GEOMETRIC TRANSFER",
        (14, 27),
        scale=0.62,
        color=(115, 225, 255),
        thickness=2,
    )
    cv2.rectangle(frame, (0, 40), (640, 72), (5, 5, 5), -1)
    cv2.rectangle(frame, (640, 40), (1279, 72), (5, 5, 5), -1)
    _put(
        frame,
        "01  PHYSICAL C922 PIXELS  |  display rotation 180 deg",
        (10, 63),
        scale=0.48,
    )
    _put(
        frame,
        "02  C922-PERSPECTIVE MUJOCO  |  exact frozen command",
        (650, 63),
        scale=0.48,
        color=(120, 230, 255),
    )
    frame[560:695, 10:250] = _fit(pi, 240, 135)
    frame[560:695, 260:500] = _fit(d405, 240, 135)
    _put(frame, "PI IMX708 | host-bound inset", (10, 549), scale=0.39)
    _put(frame, "D405 | host/action-aligned inset", (260, 549), scale=0.39)
    _put(
        frame,
        f"t={relative_seconds:05.2f}s  row={index + 1:03d}/981  {_phase(index)}",
        (520, 550),
        scale=0.53,
        color=(150, 230, 255),
        thickness=1,
    )
    _put(
        frame,
        "motion SHA 0e5fc8a079b...f6ede  |  901/901 motion + 80/80 hold",
        (520, 580),
        scale=0.45,
    )
    _put(
        frame,
        "no assistance / rate-limit / clamp / stall  |  torque OFF at close",
        (520, 607),
        scale=0.45,
        color=(155, 235, 175),
    )
    _put(
        frame,
        "stationary FK residual 11.1947 mm RMS  |  route max 19.9971 mm",
        (520, 634),
        scale=0.45,
    )
    _put(
        frame,
        "HOST/ACTION ALIGNED - NOT EXPOSURE SYNCHRONIZED - CAMERA NOT METRIC",
        (520, 664),
        scale=0.43,
        color=(130, 190, 255),
    )
    _put(
        frame,
        "NOT PAWN CONTACT / TASK SUCCESS / POLICY SUCCESS / TWIN CLOSURE",
        (520, 692),
        scale=0.43,
        color=(100, 135, 255),
        thickness=1,
    )
    return frame


def _ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    _require(ffprobe is not None, "ffprobe is required")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames:"
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    _require(result.returncode == 0, f"ffprobe failed: {result.stderr[-400:]}")
    value = json.loads(result.stdout)
    stream = value["streams"][0]
    return {
        "codec": stream["codec_name"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "avg_frame_rate": stream["avg_frame_rate"],
        "frame_count": int(stream["nb_frames"]),
        "duration_seconds": float(value["format"]["duration"]),
        "bytes": int(value["format"]["size"]),
    }


def publish(
    run_directory: Path = DEFAULT_RUN,
    *,
    camera_evaluation_path: Path = DEFAULT_CAMERA_EVALUATION,
    scene_registration_path: Path = DEFAULT_SCENE_REGISTRATION,
) -> dict[str, Any]:
    """Create the one bounded B7 proof video, poster, and receipt."""

    run_directory = run_directory.resolve()
    stage_directory = run_directory / "stage-1"
    capture_directory = stage_directory / "final_hold_camera"
    evaluation_directory = run_directory / "evaluation"
    packet_path = run_directory / "packet.json"
    execution_path = stage_directory / "execution_receipt.json"
    samples_path = stage_directory / "joint_samples.jsonl"
    diagnostic_path = evaluation_directory / "transfer-diagnostic.json"

    packet = _json(packet_path, "packet")
    execution = _json(execution_path, "execution receipt")
    diagnostic = _json(diagnostic_path, "transfer diagnostic")

    sources = diagnostic.get("sources") or {}
    packet_source = sources.get("packet") or {}
    execution_source = sources.get("execution_receipt") or {}
    sample_source = sources.get("joint_samples") or {}
    candidate_source = sources.get("candidate_manifest") or {}
    source_files: dict[str, dict[str, Any]] = {}
    source_files["packet"] = _verify_file(
        packet_path, str(packet_source.get("sha256") or ""), "packet"
    )
    source_files["execution_receipt"] = _verify_file(
        execution_path,
        str(execution_source.get("sha256") or ""),
        "execution receipt",
    )
    source_files["joint_samples"] = _verify_file(
        samples_path,
        str(sample_source.get("sha256") or ""),
        "joint samples",
    )
    _require(
        execution.get("packet_sha256") == source_files["packet"]["sha256"]
        and execution.get("joint_samples_sha256")
        == source_files["joint_samples"]["sha256"],
        "execution receipt source bindings changed",
    )
    candidate_path = (REPO_ROOT / str(candidate_source.get("path") or "")).resolve()
    source_files["candidate_manifest"] = _verify_file(
        candidate_path,
        str(candidate_source.get("sha256") or ""),
        "candidate manifest",
    )
    contract = diagnostic.get("contract") or {}
    contract_path = Path(str(contract.get("path") or "")).resolve()
    source_files["diagnostic_contract"] = _verify_file(
        contract_path,
        str(contract.get("sha256") or ""),
        "diagnostic contract",
    )
    source_files["transfer_diagnostic"] = {
        "path": _repo_path(diagnostic_path),
        "sha256": _sha256(diagnostic_path),
        "bytes": diagnostic_path.stat().st_size,
    }

    stage = (packet.get("stages") or [None])[0]
    _require(isinstance(stage, Mapping), "packet stage is missing")
    motion, motion_timestamps, motion_raw = _decode_stage(stage)
    hold, hold_timestamps, hold_raw = _decode_capture_hold(stage)
    _require(
        motion.shape == (EXPECTED_MOTION_ROWS, 6)
        and hashlib.sha256(motion_raw).hexdigest() == EXPECTED_MOTION_SHA256
        and stage.get("action_sha256") == EXPECTED_MOTION_SHA256,
        "frozen 901-row motion action changed",
    )
    _require(
        hold.shape == (EXPECTED_HOLD_ROWS, 6)
        and hashlib.sha256(hold_raw).hexdigest() == EXPECTED_HOLD_SHA256
        and stage.get("capture_hold_action_sha256") == EXPECTED_HOLD_SHA256,
        "frozen 80-row hold action changed",
    )
    rows = _load_rows(samples_path)
    row_audit = _verify_exact_rows(rows, motion, hold)

    finished = execution.get("camera_finished") or {}
    overhead = finished.get("overhead") or {}
    wrist = finished.get("wrist") or {}
    pi_capture = finished.get("pi") or {}
    _require(
        execution.get("completed_motion_samples") == EXPECTED_MOTION_ROWS
        and execution.get("completed_capture_hold_samples") == EXPECTED_HOLD_ROWS,
        "execution sample totals changed",
    )
    _require(
        execution.get("physical_follower_torque_enabled") is False,
        "follower torque was not off at close",
    )
    _require(
        overhead.get("action_interval_enclosed_by_callback_frames") is True
        and wrist.get("action_interval_enclosed_by_callback_frames") is True
        and pi_capture.get("action_interval_enclosed") is True,
        "one or more camera intervals do not enclose the action",
    )

    capture_bindings: dict[str, dict[str, Any]] = {}
    for artifact in execution.get("capture_artifacts") or []:
        label = str(artifact.get("kind") or "")
        path = _resolve_capture_path(capture_directory, artifact.get("path"))
        capture_bindings[label] = _verify_file(
            path, str(artifact.get("sha256") or ""), label
        )
    required_capture_kinds = {
        "native_report",
        "callback_ledger",
        "overhead_source_video",
        "overhead_browser_video",
        "wrist_source_video",
        "wrist_browser_video",
        "pi_source_video",
        "pi_browser_video",
        "pi_pts_ledger",
    }
    _require(
        required_capture_kinds.issubset(capture_bindings),
        "capture artifact inventory is incomplete",
    )

    c922_path = (
        REPO_ROOT / capture_bindings["overhead_browser_video"]["path"]
    ).resolve()
    d405_path = (
        REPO_ROOT / capture_bindings["wrist_browser_video"]["path"]
    ).resolve()
    pi_path = (
        REPO_ROOT / capture_bindings["pi_browser_video"]["path"]
    ).resolve()

    camera_evaluation = _json(camera_evaluation_path, "camera evaluation")
    scene_registration = _json(scene_registration_path, "scene registration")
    camera_binding = _camera_from_board_evaluation(
        camera_evaluation, scene_registration
    )
    source_files["camera_evaluation"] = {
        "path": _repo_path(camera_evaluation_path),
        "sha256": _sha256(camera_evaluation_path),
        "bytes": camera_evaluation_path.stat().st_size,
    }
    source_files["scene_registration"] = {
        "path": _repo_path(scene_registration_path),
        "sha256": _sha256(scene_registration_path),
        "bytes": scene_registration_path.stat().st_size,
    }

    stationary_rms = float(
        ((diagnostic.get("phases") or {}).get("stationary_hover") or {}).get(
            "cartesian_rms_m", math.nan
        )
    )
    route_max = float(diagnostic.get("maximum_cartesian_tracking_error_m", math.nan))
    _require(
        math.isclose(stationary_rms, EXPECTED_STATIONARY_RMS_M, abs_tol=1e-12),
        "stationary FK residual changed",
    )
    _require(
        math.isclose(route_max, EXPECTED_ROUTE_MAX_M, abs_tol=1e-12),
        "route maximum residual changed",
    )
    diagnostic_gates = diagnostic.get("gates") or {}
    _require(
        diagnostic.get("screen_passed") is True
        and all(diagnostic_gates.get(key) is True for key in diagnostic_gates),
        "existing contact-free diagnostic gate is not fully passed",
    )
    _require(
        diagnostic.get("pawn_contact_admitted") is False
        and diagnostic.get("task_success_claimed") is False,
        "existing diagnostic proof boundary changed",
    )

    manifest = _json(candidate_path, "candidate manifest")
    candidate_config = manifest.get("candidate_config")
    _require(isinstance(candidate_config, Mapping), "candidate config is missing")
    replay_preview = preview_wrist_view_actions([motion], candidate_path)
    preview_stage = (replay_preview.get("stages") or [None])[0]
    _require(
        isinstance(preview_stage, Mapping)
        and preview_stage.get("exact_physical_action_sha256")
        == EXPECTED_MOTION_SHA256
        and preview_stage.get("sample_count") == EXPECTED_MOTION_ROWS
        and replay_preview.get("no_new_or_worsened_kinematic_contact") is True,
        "existing MuJoCo preview did not consume the unchanged action",
    )

    exact = np.concatenate((motion, hold), axis=0)
    model_positions = _physical_to_model_position(exact, candidate_config)
    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    _configure_camera(model, data, camera_binding)
    joint_names = list(
        (candidate_config.get("bindings") or {}).get("joint_names") or []
    )
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    _require(
        len(joint_ids) == 6 and all(joint_id >= 0 for joint_id in joint_ids),
        "candidate simulator joint inventory changed",
    )
    qpos_addresses = [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids]

    c922_container_start = float(
        overhead["action_start_video_offset_seconds"]
    ) - float(overhead["first_frame_recorder_offset_seconds"])
    c922_container_stop = float(
        overhead["action_stop_video_offset_seconds"]
    ) - float(overhead["first_frame_recorder_offset_seconds"])
    d405_container_start = float(
        wrist["action_start_video_offset_seconds"]
    ) - float(wrist["first_frame_recorder_offset_seconds"])
    d405_container_stop = float(
        wrist["action_stop_video_offset_seconds"]
    ) - float(wrist["first_frame_recorder_offset_seconds"])
    first_action_host = float(rows[0]["host_continuous_ns"]) / 1e9
    last_action_host = float(rows[-1]["host_continuous_ns"]) / 1e9
    pi_container_start = first_action_host - float(pi_capture["host_monotonic_start"])
    pi_container_stop = last_action_host - float(pi_capture["host_monotonic_start"])
    _require(
        min(c922_container_start, d405_container_start, pi_container_start) >= 0.0,
        "derived action start falls before a video container",
    )

    output_directory = evaluation_directory
    raw_path = output_directory / "b7_action_identical_same_camera.raw.mp4"
    video_path = output_directory / VIDEO_NAME
    poster_path = output_directory / POSTER_NAME
    receipt_path = output_directory / RECEIPT_NAME
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(OUTPUT_FPS),
        OUTPUT_SIZE,
    )
    _require(writer.isOpened(), "comparison video writer could not open")
    renderer = mujoco.Renderer(model, height=480, width=640)
    c922_sampler = _VideoSampler(
        c922_path,
        start_seconds=c922_container_start,
        rotation_degrees=180,
    )
    d405_sampler = _VideoSampler(
        d405_path,
        start_seconds=d405_container_start,
    )
    pi_sampler = _VideoSampler(
        pi_path,
        start_seconds=pi_container_start,
        rotation_degrees=180,
    )
    poster: np.ndarray | None = None
    try:
        for index, model_position in enumerate(model_positions):
            data.qpos[qpos_addresses] = model_position
            data.qvel[:] = 0.0
            data.time = index / OUTPUT_FPS
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera="workcell")
            simulation = cv2.cvtColor(
                renderer.render().copy(), cv2.COLOR_RGB2BGR
            )
            relative_seconds = index / OUTPUT_FPS
            composite = _composite(
                c922=c922_sampler.sample(relative_seconds),
                simulation=simulation,
                pi=pi_sampler.sample(relative_seconds),
                d405=d405_sampler.sample(relative_seconds),
                index=index,
                relative_seconds=relative_seconds,
            )
            writer.write(composite)
            if index == 450:
                poster = composite.copy()
    finally:
        writer.release()
        renderer.close()
        c922_sampler.close()
        d405_sampler.close()
        pi_sampler.close()
    _require(poster is not None, "stationary-hover poster frame was not rendered")

    ffmpeg = shutil.which("ffmpeg")
    _require(ffmpeg is not None, "ffmpeg is required")
    encoded = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    _require(
        encoded.returncode == 0,
        f"browser comparison encoding failed: {encoded.stderr[-400:]}",
    )
    raw_path.unlink()
    _require(cv2.imwrite(str(poster_path), poster), "poster could not be written")
    video_metadata = _ffprobe(video_path)
    _require(
        video_metadata["width"] == OUTPUT_SIZE[0]
        and video_metadata["height"] == OUTPUT_SIZE[1]
        and video_metadata["frame_count"] == len(exact),
        "encoded comparison dimensions or frame count changed",
    )

    gate_table = [
        {
            "gate": "packet_execution_samples_and_media_hashes_resolve",
            "passed": True,
        },
        {
            "gate": "motion_action_sha256_preserved",
            "passed": hashlib.sha256(motion_raw).hexdigest()
            == EXPECTED_MOTION_SHA256,
        },
        {
            "gate": "901_motion_rows_and_80_hold_rows_exact",
            "passed": row_audit["motion_rows_exact"] == EXPECTED_MOTION_ROWS
            and row_audit["hold_rows_exact"] == EXPECTED_HOLD_ROWS,
        },
        {
            "gate": "no_assistance_rate_limit_clamp_or_stall",
            "passed": row_audit["no_assistance_rate_limit_clamp_or_stall"],
        },
        {
            "gate": "all_three_camera_intervals_enclose_action",
            "passed": True,
        },
        {"gate": "follower_torque_off_at_close", "passed": True},
        {
            "gate": "existing_contact_free_residual_facts_bound",
            "passed": True,
        },
        {
            "gate": "c922_perspective_render_without_refit",
            "passed": True,
        },
        {
            "gate": "output_video_and_poster_hash_bound",
            "passed": True,
        },
    ]
    _require(all(row["passed"] for row in gate_table), "binary gate table failed")

    receipt: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA,
        "phase": "B7_action_identical_contact_free_same_camera",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "binary_verdict": "action_identical_contact_free_geometric_transfer_pass",
        "proof_class": "action_identical_contact_free_geometric_transfer",
        "sources": source_files,
        "capture_artifacts": capture_bindings,
        "action_identity": {
            "encoding": "little_endian_float64_c_order",
            "motion_shape": list(motion.shape),
            "motion_sha256": hashlib.sha256(motion_raw).hexdigest(),
            "simulator_consumed_motion_sha256": preview_stage[
                "exact_physical_action_sha256"
            ],
            "hold_shape": list(hold.shape),
            "hold_sha256": hashlib.sha256(hold_raw).hexdigest(),
            "post_action_transform": None,
            "inverse_kinematics": False,
            "offset": False,
            "clipping": False,
            "assistance": False,
        },
        "physical_execution": {
            **row_audit,
            "completed_motion_rows": execution["completed_motion_samples"],
            "completed_hold_rows": execution["completed_capture_hold_samples"],
            "all_three_camera_intervals_enclose_action": True,
            "follower_torque_off_at_close": True,
        },
        "existing_geometric_diagnostic": {
            "stationary_fk_residual_rms_m": stationary_rms,
            "stationary_fk_residual_rms_mm": stationary_rms * 1000.0,
            "route_maximum_residual_m": route_max,
            "route_maximum_residual_mm": route_max * 1000.0,
            "parameter_fitting_performed": False,
            "parameters_promoted": False,
        },
        "alignment": {
            "semantics": "host_action_aligned_not_exposure_synchronized",
            "output_fps": OUTPUT_FPS,
            "output_frame_count": len(exact),
            "motion_timestamps_first_last_seconds": [
                float(motion_timestamps[0]),
                float(motion_timestamps[-1]),
            ],
            "hold_timestamps_first_last_seconds": [
                float(hold_timestamps[0]),
                float(hold_timestamps[-1]),
            ],
            "c922": {
                "recorder_action_start_offset_seconds": overhead[
                    "action_start_video_offset_seconds"
                ],
                "recorder_action_stop_offset_seconds": overhead[
                    "action_stop_video_offset_seconds"
                ],
                "container_action_start_offset_seconds": c922_container_start,
                "container_action_stop_offset_seconds": c922_container_stop,
                "display_rotation_degrees": 180,
                "camera_exposure_synchronized": False,
            },
            "d405": {
                "recorder_action_start_offset_seconds": wrist[
                    "action_start_video_offset_seconds"
                ],
                "recorder_action_stop_offset_seconds": wrist[
                    "action_stop_video_offset_seconds"
                ],
                "container_action_start_offset_seconds": d405_container_start,
                "container_action_stop_offset_seconds": d405_container_stop,
                "display_rotation_degrees": 0,
                "camera_exposure_synchronized": False,
            },
            "pi": {
                "host_bound_action_start_offset_seconds": pi_container_start,
                "host_bound_action_stop_offset_seconds": pi_container_stop,
                "display_rotation_degrees": 180,
                "camera_exposure_synchronized": False,
                "camera_intrinsics_available": False,
                "camera_extrinsics_available": False,
            },
            "cross_camera_exposure_synchronized": False,
        },
        "camera_binding": {
            "mode": "existing_conditional_c922_board_camera_visual_only",
            "conditional_corner_rmse_px": camera_binding[
                "conditional_corner_rmse_px"
            ],
            "fit_bound_active": camera_binding[
                "conditional_fit_bound_active"
            ],
            "camera_refit_performed": False,
            "metric_camera_authority": False,
        },
        "simulator_replay": {
            "runtime": replay_preview["runtime"],
            "action_consumer_sha256": preview_stage[
                "exact_physical_action_sha256"
            ],
            "sample_count": preview_stage["sample_count"],
            "hold_sample_count": len(hold),
            "render_frame_count": len(exact),
            "no_new_or_worsened_kinematic_contact": replay_preview[
                "no_new_or_worsened_kinematic_contact"
            ],
            "dynamics_claimed": False,
            "contact_consequence_claimed": False,
        },
        "outputs": {
            "video": {
                "path": _repo_path(video_path),
                "sha256": _sha256(video_path),
                **video_metadata,
            },
            "poster": {
                "path": _repo_path(poster_path),
                "sha256": _sha256(poster_path),
                "bytes": poster_path.stat().st_size,
                "width": int(poster.shape[1]),
                "height": int(poster.shape[0]),
                "source_frame_index": 450,
            },
        },
        "binary_gate_table": gate_table,
        "proof_boundary": {
            "affirmed": [
                "action-identical contact-free geometric transfer",
                "same-camera visual comparison",
                "three-camera action enclosure",
                "torque-off physical close",
            ],
            "explicitly_not_claimed": [
                "pawn contact",
                "physical task success",
                "policy success",
                "metric camera calibration",
                "Twin-fidelity closure",
                "camera exposure synchronization",
            ],
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    receipt = publish()
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "ContactFreeComparisonError",
    "DEFAULT_CAMERA_EVALUATION",
    "DEFAULT_RUN",
    "DEFAULT_SCENE_REGISTRATION",
    "EXPECTED_MOTION_SHA256",
    "POSTER_NAME",
    "RECEIPT_NAME",
    "VIDEO_NAME",
    "publish",
]
