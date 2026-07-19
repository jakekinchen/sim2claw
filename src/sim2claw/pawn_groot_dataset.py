"""GR00T LeRobot export for evaluator-admitted canonical pawn source episodes.

This module is an adapter and proof boundary, not a success authority. It can
only consume hash-bound strict source admissions and never reads evaluator-only
privileged state into policy columns.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image

from .groot_chess import _stats, _write_video
from .paths import REPO_ROOT
from .source_episode import (
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    adapt_source_episode,
    load_source_episode,
    sha256_file,
)


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "tasks"
    / "chess_pick_place_pawn_groot_dataset_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.pawn_groot_dataset_contract.v1"
CONTRACT_ID = "chess_pick_place_pawn_groot_dataset_v1"
RECEIPT_SCHEMA = "sim2claw.pawn_groot_lerobot_dataset_receipt.v1"
PREFLIGHT_SCHEMA = "sim2claw.pawn_groot_local_loader_preflight.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _payload_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(path.relative_to(root)): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "dataset_receipt.json"
    }


def dataset_contract_sha256(path: Path = CONTRACT_PATH) -> str:
    return sha256_file(path)


def load_pawn_groot_dataset_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise ValueError("unsupported pawn GR00T dataset contract")
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("pawn GR00T dataset identity changed")
    if contract.get("frozen_before_export") is not True:
        raise ValueError("pawn GR00T dataset contract must be frozen before export")
    scene = contract["scene"]
    if scene.get("scene_id") != CURRENT_SCENE_ID:
        raise ValueError("pawn GR00T dataset scene identity changed")
    if scene.get("board_pose_id") != CURRENT_BOARD_POSE_ID:
        raise ValueError("pawn GR00T dataset board pose identity changed")
    if scene.get("workspace_pose_id") != (
        "workspace_board_fiducial_robotward_100mm_20260718_v3"
    ):
        raise ValueError("pawn GR00T dataset workspace identity changed")
    if scene.get("board_center_in_table_frame_xy_m") != [0.04, -0.065]:
        raise ValueError("pawn GR00T dataset board center changed")
    if not math.isclose(
        float(scene.get("robotward_displacement_from_reference_pose_m", -1.0)),
        0.1,
        abs_tol=1e-12,
    ):
        raise ValueError("pawn GR00T dataset does not bind the 100 mm pose")
    model = contract["model"]
    if model.get("source_commit") != "23ace64f17aa5015259b8609d371eb61a357c776":
        raise ValueError("pawn GR00T NVIDIA source identity changed")
    if int(model.get("action_horizon", 0)) != 16:
        raise ValueError("pawn GR00T action horizon changed")
    dataset = contract["dataset"]
    if int(dataset.get("episode_count", 0)) != len(contract["source"]["episodes"]):
        raise ValueError("pawn GR00T episode count is inconsistent")
    if int(dataset.get("held_out_rows", -1)) != 0:
        raise ValueError("held-out rows may not enter the pawn GR00T dataset")
    if contract["splits"].get("held_out_training_rows") != 0:
        raise ValueError("pawn GR00T held-out split is not sealed")
    proof = contract["loader_proof"]
    rows = int(dataset["frame_count"])
    horizon = int(proof["action_horizon"])
    expected_starts = rows - horizon + 1
    if int(proof.get("expected_effective_start_count", -1)) != expected_starts:
        raise ValueError("pawn GR00T effective-start denominator changed")
    if int(proof.get("expected_action_target_slot_count", -1)) != (
        expected_starts * horizon
    ):
        raise ValueError("pawn GR00T action-slot denominator changed")
    if proof.get("padding_used") is not False:
        raise ValueError("pawn GR00T v1 may not use action padding")
    return contract


def _adapter_sha256(rows: list[dict[str, Any]]) -> str:
    payload = b"".join(_canonical_bytes(row) + b"\n" for row in rows)
    return hashlib.sha256(payload).hexdigest()


def _source_by_recording_id(
    directories: Iterable[Path],
) -> dict[str, tuple[Path, dict[str, Any], list[dict[str, Any]]]]:
    sources: dict[str, tuple[Path, dict[str, Any], list[dict[str, Any]]]] = {}
    for directory in directories:
        root = directory.resolve()
        receipt, rows = load_source_episode(root)
        recording_id = str(receipt["recording_id"])
        if recording_id in sources:
            raise ValueError(f"duplicate pawn source recording: {recording_id}")
        sources[recording_id] = (root, receipt, rows)
    return sources


def _load_rgb_frames(
    source_root: Path,
    adapted_rows: list[dict[str, Any]],
    *,
    expected_height: int,
    expected_width: int,
) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for adapted in adapted_rows:
        reference = adapted["observation"]["top_rgb_path"]
        path = (source_root / str(reference)).resolve()
        if not path.is_relative_to(source_root) or not path.is_file():
            raise ValueError("pawn GR00T source RGB reference escaped or is missing")
        with Image.open(path) as image:
            frame = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if frame.shape != (expected_height, expected_width, 3):
            raise ValueError("pawn GR00T source RGB shape changed")
        frames.append(frame)
    return frames


def export_pawn_groot_dataset(
    output: Path,
    *,
    source_directories: Iterable[Path],
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Build one fail-closed GR00T LeRobot dataset from admitted sources."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    contract = load_pawn_groot_dataset_contract(contract_path)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite pawn GR00T dataset: {output}")
    sources = _source_by_recording_id(source_directories)
    expected_ids = {
        str(row["recording_id"]) for row in contract["source"]["episodes"]
    }
    if set(sources) != expected_ids:
        raise ValueError("pawn GR00T source recording inventory changed")

    meta_dir = output / "meta"
    data_dir = output / "data" / "chunk-000"
    video_original_key = str(contract["dataset"]["video"]["original_key"])
    video_dir = output / "videos" / "chunk-000" / video_original_key
    lineage_dir = output / "source_lineage"
    for directory in (meta_dir, data_dir, video_dir, lineage_dir):
        directory.mkdir(parents=True, exist_ok=False)

    task_rows: list[dict[str, Any]] = []
    episodes_meta: list[dict[str, Any]] = []
    source_evidence: list[dict[str, Any]] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    all_timestamps: list[np.ndarray] = []
    all_rewards: list[np.ndarray] = []
    global_index = 0
    state_type = pa.list_(pa.float32(), 6)
    fps = int(contract["dataset"]["fps"])
    height = int(contract["dataset"]["video"]["height"])
    width = int(contract["dataset"]["video"]["width"])

    for expected in contract["source"]["episodes"]:
        episode_index = int(expected["dataset_episode_index"])
        source_root, receipt, rows = sources[str(expected["recording_id"])]
        admission_path = source_root / "admission_verdict.json"
        if sha256_file(source_root / "recording_receipt.json") != expected[
            "source_receipt_sha256"
        ]:
            raise ValueError("pawn GR00T source receipt drifted")
        if receipt.get("samples_sha256") != expected["source_samples_sha256"]:
            raise ValueError("pawn GR00T source samples drifted")
        if receipt.get("source_contract_sha256") != contract["source"][
            "contract_sha256"
        ]:
            raise ValueError("pawn GR00T source contract drifted")
        if receipt.get("rgb_streams", {}).get("manifest_sha256") != expected[
            "source_rgb_manifest_sha256"
        ]:
            raise ValueError("pawn GR00T source RGB manifest drifted")
        if len(rows) != int(expected["source_row_count"]):
            raise ValueError("pawn GR00T source row count drifted")
        if sha256_file(admission_path) != expected["admission_verdict_sha256"]:
            raise ValueError("pawn GR00T admission verdict drifted")
        admission = json.loads(admission_path.read_text(encoding="utf-8"))
        if admission.get("canonical_payload_sha256") != expected[
            "admission_canonical_payload_sha256"
        ]:
            raise ValueError("pawn GR00T admission payload identity changed")
        if (
            admission.get("strict_success") is not True
            or int(admission.get("training_rows_authorized", 0)) != len(rows)
            or int(admission.get("assistance_frames", -1)) != 0
            or admission.get("held_out_membership") is not False
        ):
            raise ValueError("pawn GR00T source is not eligible for training")
        adapted = adapt_source_episode(
            source_root,
            adapter="groot",
            admission_verdict=admission,
        )
        if _adapter_sha256(adapted) != expected["groot_adapter_sha256"]:
            raise ValueError("pawn GR00T adapter rows drifted")

        states = np.asarray(
            [row["observation"]["joint_position_rad"] for row in adapted],
            dtype=np.float32,
        )
        actions = np.asarray(
            [row["action_joint_target_rad"] for row in adapted], dtype=np.float32
        )
        timestamps = np.asarray(
            [float(row["timestamp_monotonic_seconds"]) for row in rows],
            dtype=np.float32,
        )
        if states.shape != (len(rows), 6) or actions.shape != (len(rows), 6):
            raise ValueError("pawn GR00T state/action shape changed")
        expected_timestamps = np.arange(len(rows), dtype=np.float32) / float(fps)
        if not np.array_equal(timestamps, expected_timestamps):
            raise ValueError("pawn GR00T source timebase changed")
        rewards = np.zeros(len(rows), dtype=np.float32)
        rewards[-1] = 1.0
        frame_indices = np.arange(len(rows), dtype=np.int64)
        task_index = len(task_rows)
        instruction = str(expected["instruction"])
        if any(row["observation"]["language_instruction"] != instruction for row in adapted):
            raise ValueError("pawn GR00T source language schedule changed")
        task_rows.append({"task_index": task_index, "task": instruction})

        table = pa.Table.from_arrays(
            [
                pa.array(states.tolist(), type=state_type),
                pa.array(actions.tolist(), type=state_type),
                pa.array(timestamps, type=pa.float32()),
                pa.array(frame_indices, type=pa.int64()),
                pa.array(np.full(len(rows), episode_index), type=pa.int64()),
                pa.array(
                    np.arange(global_index, global_index + len(rows)),
                    type=pa.int64(),
                ),
                pa.array(np.full(len(rows), task_index), type=pa.int64()),
                pa.array(rewards, type=pa.float32()),
                pa.array(frame_indices == (len(rows) - 1), type=pa.bool_()),
            ],
            names=[
                "observation.state",
                "action",
                "timestamp",
                "frame_index",
                "episode_index",
                "index",
                "task_index",
                "next.reward",
                "next.done",
            ],
        )
        parquet_path = data_dir / f"episode_{episode_index:06d}.parquet"
        video_path = video_dir / f"episode_{episode_index:06d}.mp4"
        lineage_path = lineage_dir / f"episode_{episode_index:06d}.jsonl"
        pq.write_table(table, parquet_path, compression="zstd")
        frames = _load_rgb_frames(
            source_root,
            adapted,
            expected_height=height,
            expected_width=width,
        )
        _write_video(video_path, frames, fps)
        _write_jsonl(
            lineage_path,
            (
                {
                    "dataset_episode_index": episode_index,
                    "dataset_frame_index": index,
                    "source_recording_id": receipt["recording_id"],
                    "source_sample_index": index,
                    "source_top_rgb_sha256": rows[index]["rgb"]["top"]["sha256"],
                    "source_wrist_rgb_sha256": rows[index]["rgb"]["wrist"]["sha256"],
                    "source_action_owner": rows[index]["action"]["owner"],
                    "source_assistance": rows[index]["action"]["assistance"],
                    "admission_canonical_payload_sha256": admission[
                        "canonical_payload_sha256"
                    ],
                }
                for index in range(len(rows))
            ),
        )
        episodes_meta.append(
            {"episode_index": episode_index, "tasks": [instruction], "length": len(rows)}
        )
        source_evidence.append(
            {
                **expected,
                "parquet_sha256": sha256_file(parquet_path),
                "video_sha256": sha256_file(video_path),
                "lineage_sha256": sha256_file(lineage_path),
            }
        )
        all_states.append(states)
        all_actions.append(actions)
        all_timestamps.append(timestamps)
        all_rewards.append(rewards)
        global_index += len(rows)

    _write_jsonl(meta_dir / "tasks.jsonl", task_rows)
    _write_jsonl(meta_dir / "episodes.jsonl", episodes_meta)
    modality = {
        "state": {
            "single_arm": {"start": 0, "end": 5},
            "gripper": {"start": 5, "end": 6},
        },
        "action": {
            "single_arm": {"start": 0, "end": 5},
            "gripper": {"start": 5, "end": 6},
        },
        "video": {"front": {"original_key": video_original_key}},
        "annotation": {
            "human.task_description": {"original_key": "task_index"}
        },
    }
    _write_json(meta_dir / "modality.json", modality)
    info = {
        "codebase_version": "v2.1",
        "robot_type": "sim2claw_so101_pawn_simulation",
        "total_episodes": len(episodes_meta),
        "total_frames": global_index,
        "total_tasks": len(task_rows),
        "chunks_size": 1000,
        "fps": fps,
        "splits": {"train": f"0:{len(episodes_meta)}"},
        "data_path": (
            "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"
        ),
        "video_path": (
            "videos/chunk-{episode_chunk:03d}/{video_key}/"
            "episode_{episode_index:06d}.mp4"
        ),
        "features": {
            "action": {
                "dtype": "float32",
                "shape": [6],
                "names": contract["dataset"]["action_features"],
            },
            "observation.state": {
                "dtype": "float32",
                "shape": [6],
                "names": contract["dataset"]["state_features"],
            },
            video_original_key: {
                "dtype": "video",
                "shape": [height, width, 3],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.height": height,
                    "video.width": width,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "video.fps": fps,
                    "video.channels": 3,
                    "has_audio": False,
                },
            },
            "timestamp": {"dtype": "float32", "shape": [1], "names": None},
            "frame_index": {"dtype": "int64", "shape": [1], "names": None},
            "episode_index": {"dtype": "int64", "shape": [1], "names": None},
            "index": {"dtype": "int64", "shape": [1], "names": None},
            "task_index": {"dtype": "int64", "shape": [1], "names": None},
            "next.reward": {"dtype": "float32", "shape": [1], "names": None},
            "next.done": {"dtype": "bool", "shape": [1], "names": None},
        },
        "total_chunks": 1,
        "total_videos": len(episodes_meta),
    }
    _write_json(meta_dir / "info.json", info)
    _write_json(
        meta_dir / "stats.json",
        {
            "observation.state": _stats(np.concatenate(all_states)),
            "action": _stats(np.concatenate(all_actions)),
            "timestamp": _stats(np.concatenate(all_timestamps)),
            "next.reward": _stats(np.concatenate(all_rewards)),
        },
    )
    # NVIDIA's DatasetFactory unconditionally calls generate_rel_stats. For an
    # absolute-action embodiment that function writes the canonical empty JSON
    # object. Include it before the payload manifest so training cannot create
    # an unreceipted cache file after preflight.
    (meta_dir / "relative_stats.json").write_text("{}", encoding="utf-8")
    manifest = _payload_manifest(output)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "dataset_contract_id": contract["contract_id"],
        "dataset_contract_sha256": dataset_contract_sha256(contract_path),
        "builder_identity": {
            "builder_module_sha256": sha256_file(Path(__file__)),
            "groot_chess_module_sha256": sha256_file(
                REPO_ROOT / "src/sim2claw/groot_chess.py"
            ),
            "source_episode_module_sha256": sha256_file(
                REPO_ROOT / "src/sim2claw/source_episode.py"
            ),
        },
        "scene": contract["scene"],
        "model": contract["model"],
        "format": contract["dataset"]["format"],
        "episode_count": len(episodes_meta),
        "frame_count": global_index,
        "effective_training_start_count": contract["loader_proof"][
            "expected_effective_start_count"
        ],
        "held_out_rows": 0,
        "all_source_rows_evaluator_admitted": True,
        "source_evidence": source_evidence,
        "payload_manifest": manifest,
        "payload_manifest_sha256": _canonical_sha256(manifest),
        "dataset_builder_cannot_declare_task_success": True,
        "training_cannot_promote": True,
        "physical_authority": False,
    }
    receipt["canonical_payload_sha256"] = _canonical_sha256(receipt)
    _write_json(output / "dataset_receipt.json", receipt)
    receipt["receipt_path"] = str(output / "dataset_receipt.json")
    receipt["receipt_sha256"] = sha256_file(output / "dataset_receipt.json")
    return receipt


def _target_index_matrix(row_count: int, horizon: int) -> np.ndarray:
    if row_count < horizon:
        raise ValueError("pawn GR00T episode is shorter than its action horizon")
    starts = np.arange(row_count - horizon + 1, dtype=np.int64)[:, None]
    offsets = np.arange(horizon, dtype=np.int64)[None, :]
    return starts + offsets


def preflight_pawn_groot_dataset(
    dataset_root: Path,
    *,
    output_path: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Independently verify the local payload and frozen chunk denominator."""

    import pyarrow.parquet as pq

    contract = load_pawn_groot_dataset_contract(contract_path)
    dataset_root = dataset_root.resolve()
    receipt_path = dataset_root / "dataset_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("unsupported pawn GR00T dataset receipt")
    if receipt.get("dataset_contract_sha256") != dataset_contract_sha256(
        contract_path
    ):
        raise ValueError("pawn GR00T dataset receipt used another contract")
    if receipt.get("canonical_payload_sha256") != _canonical_sha256(
        {key: value for key, value in receipt.items() if key != "canonical_payload_sha256"}
    ):
        raise ValueError("pawn GR00T dataset receipt payload hash mismatch")
    manifest = _payload_manifest(dataset_root)
    if manifest != receipt.get("payload_manifest"):
        raise ValueError("pawn GR00T dataset payload inventory drifted")
    if _canonical_sha256(manifest) != receipt.get("payload_manifest_sha256"):
        raise ValueError("pawn GR00T dataset manifest hash mismatch")

    expected_episode = contract["source"]["episodes"][0]
    parquet_path = dataset_root / "data/chunk-000/episode_000000.parquet"
    table = pq.read_table(parquet_path)
    expected_columns = [
        "observation.state",
        "action",
        "timestamp",
        "frame_index",
        "episode_index",
        "index",
        "task_index",
        "next.reward",
        "next.done",
    ]
    if table.column_names != expected_columns:
        raise ValueError("pawn GR00T parquet columns changed")
    row_count = table.num_rows
    if row_count != int(expected_episode["source_row_count"]):
        raise ValueError("pawn GR00T parquet row count changed")
    actions = np.asarray(table["action"].to_pylist(), dtype=np.float32)
    states = np.asarray(table["observation.state"].to_pylist(), dtype=np.float32)
    if actions.shape != (row_count, 6) or states.shape != (row_count, 6):
        raise ValueError("pawn GR00T parquet state/action shape changed")
    indices = _target_index_matrix(row_count, int(contract["model"]["action_horizon"]))
    chunks = actions[indices]
    if not np.array_equal(chunks[:, 0, :], actions[: indices.shape[0], :]):
        raise ValueError("pawn GR00T action chunk current-row alignment failed")
    if not np.array_equal(chunks[-1, -1, :], actions[-1, :]):
        raise ValueError("pawn GR00T final action never appears in a target chunk")
    if indices.shape != (
        int(contract["loader_proof"]["expected_effective_start_count"]),
        int(contract["model"]["action_horizon"]),
    ):
        raise ValueError("pawn GR00T action chunk denominator changed")
    if int(indices.size) != int(
        contract["loader_proof"]["expected_action_target_slot_count"]
    ):
        raise ValueError("pawn GR00T action target slot count changed")
    task_indices = np.asarray(table["task_index"].to_numpy(), dtype=np.int64)
    if not np.array_equal(task_indices, np.zeros(row_count, dtype=np.int64)):
        raise ValueError("pawn GR00T task schedule changed")
    tasks = [
        json.loads(line)
        for line in (dataset_root / "meta/tasks.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    if tasks != [{"task_index": 0, "task": expected_episode["instruction"]}]:
        raise ValueError("pawn GR00T language metadata changed")

    video_path = (
        dataset_root
        / "videos/chunk-000/observation.images.front/episode_000000.mp4"
    )
    capture = cv2.VideoCapture(str(video_path))
    try:
        video_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = float(capture.get(cv2.CAP_PROP_FPS))
        video_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if (
        video_frames != row_count
        or not math.isclose(video_fps, 20.0, abs_tol=1e-9)
        or video_width != 224
        or video_height != 224
    ):
        raise ValueError("pawn GR00T encoded video metadata changed")

    report: dict[str, Any] = {
        "schema_version": PREFLIGHT_SCHEMA,
        "passed": True,
        "dataset_contract_sha256": dataset_contract_sha256(contract_path),
        "dataset_receipt_sha256": sha256_file(receipt_path),
        "dataset_payload_manifest_sha256": receipt["payload_manifest_sha256"],
        "preflight_module_sha256": sha256_file(Path(__file__)),
        "episode_count": 1,
        "source_row_count": row_count,
        "effective_start_count": int(indices.shape[0]),
        "action_horizon": int(indices.shape[1]),
        "action_target_slot_count": int(indices.size),
        "action_scalar_count": int(chunks.size),
        "target_index_matrix_sha256": hashlib.sha256(
            np.ascontiguousarray(indices, dtype=np.int64).tobytes()
        ).hexdigest(),
        "all_source_action_rows_appear_in_at_least_one_target": (
            set(indices.reshape(-1).tolist()) == set(range(row_count))
        ),
        "padding_used": False,
        "cross_language_boundary_target_count": 0,
        "distinct_prompt_count": 1,
        "video": {
            "frame_count": video_frames,
            "fps": video_fps,
            "width": video_width,
            "height": video_height,
            "sha256": sha256_file(video_path),
        },
        "held_out_rows": 0,
        "pinned_nvidia_loader_preflight_still_required": True,
        "training_authorized_by_this_local_preflight": False,
        "physical_authority": False,
    }
    report["canonical_payload_sha256"] = _canonical_sha256(report)
    _write_json(output_path, report)
    report["receipt_path"] = str(output_path)
    report["receipt_sha256"] = sha256_file(output_path)
    return report
