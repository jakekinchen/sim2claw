"""Render a nominal wrist view from the retained OR34 state trace.

This is a presentation-only projection. It assigns retained robot and selected
pawn poses, updates MuJoCo kinematics, and rasterizes the unchanged nominal
``left_wrist_cam``. It does not integrate actions or evaluate physics.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_path,
)
from .observable_registration_measured_state_visual_twin import (
    load_measured_state_visual_twin_contract,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import _candidate_config
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .realized_action_outcome_mission import physical_to_model


SCHEMA = (
    "sim2claw.observable_registration_d1_d2_nominal_wrist_presentation_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_d1_d2_nominal_wrist_presentation_receipt.v1"
)
FRAME_MANIFEST_SCHEMA = (
    "sim2claw.observable_registration_d1_d2_nominal_wrist_frame_manifest.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_d1_d2_nominal_wrist_presentation_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_d1_d2_nominal_wrist_presentation_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _binding_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    return _bound_path(binding, root=root, label=label)


def load_nominal_wrist_presentation_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="nominal wrist presentation contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _binding_path(binding, root=root, label=name)
    for name, binding in contract["frozen_executable"].items():
        _binding_path(binding, root=root, label=name)

    projection = contract["trace_projection"]
    _require(
        projection["row_count"] == 531
        and projection["output_fps"] == 20
        and projection["between_row_interpolation"] is False
        and projection["mujoco_forward_for_kinematics_and_rasterization_only"]
        is True
        and projection["mujoco_step_calls"] == 0
        and projection["action_or_controller_writes"] == 0
        and projection["contact_or_task_metrics"] == 0,
        "trace projection boundary widened",
    )
    camera = contract["camera"]
    _require(
        camera["compiled_name"] == "left_wrist_cam"
        and camera["mount_body"] == "left_camera_mount"
        and camera["camera_or_display_refit"] is False
        and camera["pixel_warp"] is False
        and camera["provenance"]
        == "vendored_upstream_simulator_geometry_not_calibrated_d405_extrinsics",
        "camera boundary widened",
    )
    render = contract["render"]
    _require(
        render["width"] == 424
        and render["height"] == 240
        and render["fps"] == 20
        and render["frame_count"] == 531
        and render["codec"] == "h264"
        and render["pixel_format"] == "yuv420p"
        and render["audio"] is False
        and render["overlay_text"] == "NOMINAL SIM WRIST / UNCALIBRATED",
        "render identity widened",
    )
    _require(
        contract["authority"] and not any(contract["authority"].values()),
        "authority widened",
    )
    _require(
        contract["claim_limits"]
        and not any(contract["claim_limits"].values()),
        "claim boundary widened",
    )
    return contract


@dataclass(frozen=True)
class ProjectionContext:
    model: mujoco.MjModel
    data: mujoco.MjData
    trace_rows: list[dict[str, Any]]
    timestamps: np.ndarray
    trace_model: np.ndarray
    robot_qpos_addresses: np.ndarray
    selected_qpos_address: int
    camera_id: int
    selected_piece: str
    scene_path: Path


def _validated_trace_rows(
    trace: dict[str, Any], *, expected_count: int
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray]:
    _require(
        trace.get("schema_version")
        == "sim2claw.observable_registration_measured_state_visual_twin_trace.v1",
        "OR34 trace schema drifted",
    )
    rows = trace.get("rows")
    _require(isinstance(rows, list) and len(rows) == expected_count, "trace row count drifted")
    _require(
        [int(row.get("sample_index", -1)) for row in rows]
        == list(range(expected_count)),
        "trace sample order drifted",
    )
    timestamps = np.asarray(
        [row["source_timestamp_seconds"] for row in rows], dtype=np.float64
    )
    raw_physical = np.asarray(
        [row["raw_measured_physical"] for row in rows], dtype=np.float64
    )
    pawn_pose = np.asarray(
        [
            [
                *row["selected_pawn_position_m"],
                *row["selected_pawn_quaternion_wxyz"],
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    _require(
        timestamps.shape == (expected_count,)
        and raw_physical.shape == (expected_count, 6)
        and pawn_pose.shape == (expected_count, 7)
        and np.all(np.isfinite(timestamps))
        and np.all(np.isfinite(raw_physical))
        and np.all(np.isfinite(pawn_pose))
        and np.all(np.diff(timestamps) > 0.0),
        "trace values are invalid",
    )
    quaternion_norms = np.linalg.norm(pawn_pose[:, 3:7], axis=1)
    _require(
        bool(np.all(np.abs(quaternion_norms - 1.0) <= 1e-8)),
        "trace pawn quaternion is not normalized",
    )
    return rows, timestamps, raw_physical, pawn_pose


def build_projection_context(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> ProjectionContext:
    or34_path = _binding_path(
        contract["sources"]["or34_contract"], root=root, label="OR34 contract"
    )
    or34 = load_measured_state_visual_twin_contract(or34_path, root=root)
    or19_path = _binding_path(
        or34["sources"]["or19_contract"], root=root, label="OR19 contract"
    )
    or19, c6 = load_unilateral_push_dynamic_replay_contract(or19_path, root=root)
    c6_loaded, candidate, measured_model, _ = _candidate_config(or19, root=root)
    _require(c6_loaded == c6, "OR34 predecessor identity changed")

    trace_path = _binding_path(
        contract["sources"]["or34_trace"], root=root, label="OR34 trace"
    )
    trace = load_json_object(trace_path, label="OR34 trace")
    rows, timestamps, raw_physical, _ = _validated_trace_rows(
        trace, expected_count=int(contract["trace_projection"]["row_count"])
    )
    trace_model = physical_to_model(
        raw_physical, {"candidate_config": candidate}
    )
    _require(
        trace_model.shape == measured_model.shape == (531, 6)
        and bool(np.allclose(trace_model, measured_model, rtol=0.0, atol=1e-12)),
        "trace robot projection disagrees with OR34",
    )

    scene_path = _binding_path(
        or19["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate["bindings"]["joint_names"]
    ]
    _require(min(joint_ids) >= 0, "robot joint binding is incomplete")
    robot_qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[index]) for index in joint_ids], dtype=np.int64
    )
    selected_piece = str(c6["initialization"]["selected_piece"])
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_piece}_free"
    )
    _require(selected_joint >= 0, "selected pawn free joint is missing")
    selected_qpos_address = int(model.jnt_qposadr[selected_joint])

    camera_name = str(contract["camera"]["compiled_name"])
    camera_names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_CAMERA, index)
        for index in range(model.ncam)
    ]
    _require(camera_names.count(camera_name) == 1, "nominal wrist camera identity is ambiguous")
    camera_id = camera_names.index(camera_name)
    mount_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_BODY,
        str(contract["camera"]["mount_body"]),
    )
    _require(mount_id >= 0, "nominal wrist camera mount is missing")
    _require(
        bool(
            np.allclose(
                model.cam_pos[camera_id],
                contract["camera"]["model_local_position_m"],
                rtol=0.0,
                atol=1e-12,
            )
        )
        and bool(
            np.allclose(
                model.cam_quat[camera_id],
                contract["camera"]["model_local_quaternion_wxyz"],
                rtol=0.0,
                atol=1e-12,
            )
        )
        and math.isclose(
            float(model.cam_fovy[camera_id]),
            float(contract["camera"]["vertical_fov_degrees"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ),
        "nominal wrist camera values drifted",
    )
    return ProjectionContext(
        model=model,
        data=data,
        trace_rows=rows,
        timestamps=timestamps,
        trace_model=trace_model,
        robot_qpos_addresses=robot_qpos_addresses,
        selected_qpos_address=selected_qpos_address,
        camera_id=camera_id,
        selected_piece=selected_piece,
        scene_path=scene_path,
    )


def _encode_h264(raw_path: Path, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    _require(ffmpeg is not None, "ffmpeg is required")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    _require(
        completed.returncode == 0,
        f"H.264 encoding failed: {completed.stderr[-500:]}",
    )


def _decoded_media_identity(path: Path) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(path))
    _require(capture.isOpened(), "encoded nominal wrist video did not open")
    hashes: list[str] = []
    try:
        width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
    finally:
        capture.release()
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": len(hashes),
        "decoded_frame_hashes_digest": canonical_digest(hashes),
    }


def render_nominal_wrist_presentation(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    _require(not output_directory.exists(), "OR149 output already exists")
    temporary = output_directory.with_name(output_directory.name + ".tmp")
    _require(not temporary.exists(), "OR149 temporary output already exists")
    contract = load_nominal_wrist_presentation_contract(contract_path, root=root)
    context = build_projection_context(contract, root=root)
    render = contract["render"]
    width = int(render["width"])
    height = int(render["height"])
    fps = float(render["fps"])
    temporary.mkdir(parents=True, exist_ok=False)
    raw_path = temporary / "nominal_wrist.raw.mp4"
    video_path = temporary / "nominal_wrist.mp4"
    poster_path = temporary / "poster_sample_248.png"
    manifest_path = temporary / "frame_manifest.json"
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    renderer = mujoco.Renderer(context.model, height=height, width=width)
    _require(writer.isOpened(), "raw nominal wrist writer did not open")
    frame_rows: list[dict[str, Any]] = []
    poster: np.ndarray | None = None
    try:
        for index, row in enumerate(context.trace_rows):
            context.data.qpos[context.robot_qpos_addresses] = context.trace_model[index]
            pawn_qpos = context.selected_qpos_address
            context.data.qpos[pawn_qpos : pawn_qpos + 3] = row[
                "selected_pawn_position_m"
            ]
            context.data.qpos[pawn_qpos + 3 : pawn_qpos + 7] = row[
                "selected_pawn_quaternion_wxyz"
            ]
            mujoco.mj_forward(context.model, context.data)
            renderer.update_scene(context.data, camera=context.camera_id)
            frame = cv2.cvtColor(renderer.render().copy(), cv2.COLOR_RGB2BGR)
            cv2.rectangle(frame, (0, 0), (width, 27), (8, 8, 8), -1)
            cv2.putText(
                frame,
                str(render["overlay_text"]),
                (9, 19),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (115, 225, 255),
                1,
                cv2.LINE_AA,
            )
            writer.write(frame)
            frame_rows.append(
                {
                    "sample_index": index,
                    "source_timestamp_seconds": float(context.timestamps[index]),
                    "preencode_bgr_sha256": hashlib.sha256(
                        frame.tobytes()
                    ).hexdigest(),
                }
            )
            if index == int(render["poster_sample_index"]):
                poster = frame.copy()
    finally:
        renderer.close()
        writer.release()
    _require(len(frame_rows) == 531 and poster is not None, "render frame count drifted")
    _encode_h264(raw_path, video_path)
    raw_path.unlink()
    _require(cv2.imwrite(str(poster_path), poster), "poster write failed")
    media = _decoded_media_identity(video_path)
    _require(
        media["width"] == width
        and media["height"] == height
        and math.isclose(media["fps"], fps, rel_tol=0.0, abs_tol=1e-6)
        and media["frame_count"] == 531,
        "encoded media identity drifted",
    )
    frame_manifest = {
        "schema_version": FRAME_MANIFEST_SCHEMA,
        "recording_id": "20260727T041737Z-89190e53",
        "camera": "left_wrist_cam",
        "rows": frame_rows,
    }
    atomic_write_json(manifest_path, frame_manifest)
    source_identities = {
        name: {
            "path": str(binding["path"]),
            "sha256": str(binding["sha256"]),
        }
        for name, binding in contract["sources"].items()
    }
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_NOMINAL_UNCALIBRATED_WRIST_PRESENTATION",
        "proof_class": contract["proof_class"],
        "recording_id": "20260727T041737Z-89190e53",
        "contract": {
            "path": str(contract_path.resolve().relative_to(root.resolve())),
            "sha256": sha256_file(contract_path),
        },
        "source_identities": source_identities,
        "frozen_executable": contract["frozen_executable"],
        "state_sources": {
            "robot_and_camera": "OR34 raw measured physical rows through frozen candidate kinematics",
            "selected_pawn": "OR34 retained selected pawn xyz and quaternion",
            "other_pieces": "OR34 canonical initial scene; no dynamic pose claim",
        },
        "camera": {
            **contract["camera"],
            "compiled_id": context.camera_id,
            "compiled_fovy_degrees": float(
                context.model.cam_fovy[context.camera_id]
            ),
        },
        "timeline": {
            "frame_count": 531,
            "fps": 20,
            "first_source_timestamp_seconds": float(context.timestamps[0]),
            "last_source_timestamp_seconds": float(context.timestamps[-1]),
            "presentation_sampling": "source_row_order_at_constant_20_fps",
            "camera_exposure_synchronized": False,
            "device_clock_synchronized": False,
            "actuator_application_timestamps_available": False,
        },
        "execution": {
            "mujoco_forward_calls": 531,
            "rasterized_frames": 531,
            "mujoco_step_calls": 0,
            "action_integrations": 0,
            "controller_writes": 0,
            "state_interpolations": 0,
            "camera_or_extrinsic_fits": 0,
            "parameter_or_object_fits": 0,
            "contact_or_task_evaluations": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "mujoco": mujoco.__version__,
            "opencv": cv2.__version__,
            "platform": platform.platform(),
        },
        "outputs": {
            "video_path": "nominal_wrist.mp4",
            "video_sha256": sha256_file(video_path),
            "poster_path": "poster_sample_248.png",
            "poster_sha256": sha256_file(poster_path),
            "frame_manifest_path": "frame_manifest.json",
            "frame_manifest_sha256": sha256_file(manifest_path),
            "media": media,
        },
        "gates": {
            "source_hashes_exact": True,
            "camera_identity_exact": True,
            "trace_identity_exact": True,
            "zero_step_action_fit_or_scoring": True,
            "media_identity_exact": True,
            "labels_exact": True,
        },
        "authority": contract["authority"],
        "claim_limits": contract["claim_limits"],
        "claim_boundary": "Nominal retained-OR34-trace wrist presentation only; not a calibrated D405-equivalent camera, full-state replay, physics-fidelity result, task-success result, or transfer result.",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(temporary / "receipt.json", receipt)
    temporary.replace(output_directory)
    return receipt


def verify_nominal_wrist_presentation(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_nominal_wrist_presentation_contract(contract_path, root=root)
    receipt_path = output_directory / "receipt.json"
    receipt = load_json_object(receipt_path, label="nominal wrist receipt")
    outputs = receipt["outputs"]
    video_path = output_directory / outputs["video_path"]
    poster_path = output_directory / outputs["poster_path"]
    manifest_path = output_directory / outputs["frame_manifest_path"]
    media = _decoded_media_identity(video_path)
    frame_manifest = load_json_object(manifest_path, label="nominal wrist frames")
    unsigned = dict(receipt)
    observed_artifact = str(unsigned.pop("artifact_sha256", ""))
    gates = {
        "receipt_schema": receipt.get("schema_version") == RECEIPT_SCHEMA,
        "status": receipt.get("status")
        == "PASS_NOMINAL_UNCALIBRATED_WRIST_PRESENTATION",
        "contract_hash": receipt.get("contract", {}).get("sha256")
        == sha256_file(contract_path),
        "artifact_digest": observed_artifact == canonical_digest(unsigned),
        "video_hash": outputs.get("video_sha256") == sha256_file(video_path),
        "poster_hash": outputs.get("poster_sha256") == sha256_file(poster_path),
        "manifest_hash": outputs.get("frame_manifest_sha256")
        == sha256_file(manifest_path),
        "media_identity": media == outputs.get("media"),
        "frame_manifest": frame_manifest.get("schema_version")
        == FRAME_MANIFEST_SCHEMA
        and len(frame_manifest.get("rows", [])) == 531,
        "execution_boundary": receipt.get("execution", {}).get("mujoco_step_calls")
        == 0
        and receipt.get("execution", {}).get("action_integrations") == 0
        and receipt.get("execution", {}).get("controller_writes") == 0
        and receipt.get("execution", {}).get("contact_or_task_evaluations") == 0
        and receipt.get("execution", {}).get("simulator_replays") == 0,
        "authority_false": receipt.get("authority") == contract["authority"]
        and not any(receipt.get("authority", {}).values()),
        "claims_false": receipt.get("claim_limits") == contract["claim_limits"]
        and not any(receipt.get("claim_limits", {}).values()),
    }
    return {"status": "pass" if all(gates.values()) else "fail", "gates": gates}


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "ProjectionContext",
    "build_projection_context",
    "load_nominal_wrist_presentation_contract",
    "render_nominal_wrist_presentation",
    "verify_nominal_wrist_presentation",
]
