#!/usr/bin/env python3
"""Export all finalized physical B--G recordings for an exploratory GR00T run.

This deliberately does not admit the source rows, promote a policy, or create
physical/sim-to-real authority.  It produces a hash-bound LeRobot v2.1 dataset
whose receipt keeps the source proof class and pending-admission status intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from sim2claw.groot_chess import _stats, _write_video


SCHEMA = "sim2claw.groot_n17_physical_bg_exploratory_dataset.v1"
RECEIPT_SCHEMA = "sim2claw.groot_n17_physical_bg_exploratory_receipt.v1"
JOINT_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        )
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def payload_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "dataset_receipt.json"
    }


def canonical_instruction(source: str, destination: str) -> str:
    return (
        f"Pick up the brown pawn on {source} and place it upright on the empty "
        f"square {destination}."
    )


def load_video_frames(
    video_path: Path,
    sample_times: list[float],
    *,
    width: int,
    height: int,
) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"could not open source video: {video_path}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not 29.0 <= source_fps <= 31.0:
        raise ValueError(f"unexpected source video rate: {source_fps}")
    source_frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        source_frames.append(frame)
    capture.release()
    if len(source_frames) != frame_count:
        raise ValueError("decoded source video frame count changed")

    result: list[np.ndarray] = []
    for timestamp in sample_times:
        index = min(max(int(round(timestamp * source_fps)), 0), frame_count - 1)
        frame = cv2.rotate(source_frames[index], cv2.ROTATE_180)
        frame_height, frame_width = frame.shape[:2]
        side = min(frame_height, frame_width)
        x0 = (frame_width - side) // 2
        y0 = (frame_height - side) // 2
        frame = frame[y0 : y0 + side, x0 : x0 + side]
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        result.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    catalog_path = (repo_root / args.catalog).resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite dataset: {output}")
    catalog = json.loads(catalog_path.read_text())
    episodes = catalog.get("episodes", [])
    if len(episodes) != 18:
        raise ValueError("expected the complete 18-recording physical catalog")

    meta_dir = output / "meta"
    data_dir = output / "data" / "chunk-000"
    video_key = "observation.images.front"
    video_dir = output / "videos" / "chunk-000" / video_key
    lineage_dir = output / "source_lineage"
    for directory in (meta_dir, data_dir, video_dir, lineage_dir):
        directory.mkdir(parents=True, exist_ok=False)

    fps = 20
    width = 256
    height = 256
    list6 = pa.list_(pa.float32(), 6)
    task_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    all_timestamps: list[np.ndarray] = []
    all_rewards: list[np.ndarray] = []
    global_index = 0

    for episode_index, catalog_row in enumerate(episodes):
        if catalog_row.get("held_out_membership", False):
            raise ValueError("held-out source entered exploratory export")
        if catalog_row.get("proof_class") != "physical_teleoperation_source_unqualified":
            raise ValueError("physical source proof class changed")
        if catalog_row.get("outcome_label") != "success":
            raise ValueError("non-success source entered exploratory export")
        source_root = (repo_root / catalog_row["source_path"]).resolve()
        if not source_root.is_relative_to(repo_root):
            raise ValueError("source path escaped repository")
        receipt_path = source_root / "recording_receipt.json"
        samples_path = source_root / "samples.jsonl"
        video_path = source_root / "overhead_c922.mp4"
        if sha256_file(receipt_path) != catalog_row["receipt_sha256"]:
            raise ValueError("source receipt hash changed")
        if sha256_file(samples_path) != catalog_row["samples_sha256"]:
            raise ValueError("source sample hash changed")
        if sha256_file(video_path) != catalog_row["overhead_video_sha256"]:
            raise ValueError("source video hash changed")
        receipt = json.loads(receipt_path.read_text())
        samples = read_jsonl(samples_path)
        if len(samples) != int(catalog_row["sample_count"]):
            raise ValueError("source row count changed")
        if receipt.get("held_out_membership") is not False:
            raise ValueError("held-out receipt entered exploratory export")
        if receipt.get("action_owner") != "human_teleoperator":
            raise ValueError("source action owner changed")
        if receipt.get("training_admission") != "pending_deterministic_replay_and_separate_evaluator":
            raise ValueError("source admission state changed")

        states = np.deg2rad(
            np.asarray([row["follower_actual_position_degrees"] for row in samples])
        ).astype(np.float32)
        actions = np.deg2rad(
            np.asarray([row["follower_command_degrees"] for row in samples])
        ).astype(np.float32)
        if states.shape != (len(samples), 6) or actions.shape != (len(samples), 6):
            raise ValueError("source state/action shape changed")
        timestamps = np.arange(len(samples), dtype=np.float32) / float(fps)
        rewards = np.zeros(len(samples), dtype=np.float32)
        rewards[-1] = 1.0
        frame_indices = np.arange(len(samples), dtype=np.int64)
        source_square = str(catalog_row["source_square"])
        destination_square = str(catalog_row["destination_square"])
        instruction = canonical_instruction(source_square, destination_square)
        task_index = len(task_rows)
        task_rows.append({"task_index": task_index, "task": instruction})

        table = pa.Table.from_arrays(
            [
                pa.array(states.tolist(), type=list6),
                pa.array(actions.tolist(), type=list6),
                pa.array(timestamps, type=pa.float32()),
                pa.array(frame_indices, type=pa.int64()),
                pa.array(np.full(len(samples), episode_index), type=pa.int64()),
                pa.array(np.arange(global_index, global_index + len(samples)), type=pa.int64()),
                pa.array(np.full(len(samples), task_index), type=pa.int64()),
                pa.array(rewards, type=pa.float32()),
                pa.array(frame_indices == len(samples) - 1, type=pa.bool_()),
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
        output_video_path = video_dir / f"episode_{episode_index:06d}.mp4"
        pq.write_table(table, parquet_path, compression="zstd")
        frames = load_video_frames(
            video_path,
            [float(row["overhead_video_time_seconds"]) for row in samples],
            width=width,
            height=height,
        )
        _write_video(output_video_path, frames, fps)
        lineage_path = lineage_dir / f"episode_{episode_index:06d}.jsonl"
        write_jsonl(
            lineage_path,
            (
                {
                    "dataset_episode_index": episode_index,
                    "dataset_frame_index": index,
                    "source_recording_id": receipt["recording_id"],
                    "source_sample_index": int(sample["sample_index"]),
                    "source_video_time_seconds": float(sample["overhead_video_time_seconds"]),
                    "source_action_owner": "human_teleoperator",
                    "source_proof_class": "physical_teleoperation_source_unqualified",
                    "source_training_admission": "pending_deterministic_replay_and_separate_evaluator",
                }
                for index, sample in enumerate(samples)
            ),
        )
        episode_rows.append(
            {"episode_index": episode_index, "tasks": [instruction], "length": len(samples)}
        )
        source_rows.append(
            {
                "dataset_episode_index": episode_index,
                "recording_id": receipt["recording_id"],
                "move_id": catalog_row["move_id"],
                "sample_count": len(samples),
                "proof_class": receipt["proof_class"],
                "training_admission": receipt["training_admission"],
                "receipt_sha256": catalog_row["receipt_sha256"],
                "samples_sha256": catalog_row["samples_sha256"],
                "source_video_sha256": catalog_row["overhead_video_sha256"],
                "parquet_sha256": sha256_file(parquet_path),
                "derived_video_sha256": sha256_file(output_video_path),
                "lineage_sha256": sha256_file(lineage_path),
            }
        )
        all_states.append(states)
        all_actions.append(actions)
        all_timestamps.append(timestamps)
        all_rewards.append(rewards)
        global_index += len(samples)

    write_jsonl(meta_dir / "tasks.jsonl", task_rows)
    write_jsonl(meta_dir / "episodes.jsonl", episode_rows)
    write_json(
        meta_dir / "modality.json",
        {
            "state": {"single_arm": {"start": 0, "end": 5}, "gripper": {"start": 5, "end": 6}},
            "action": {"single_arm": {"start": 0, "end": 5}, "gripper": {"start": 5, "end": 6}},
            "video": {"front": {"original_key": video_key}},
            "annotation": {"human.task_description": {"original_key": "task_index"}},
        },
    )
    info = {
        "codebase_version": "v2.1",
        "robot_type": "sim2claw_so101_physical_exploratory",
        "total_episodes": len(episode_rows),
        "total_frames": global_index,
        "total_tasks": len(task_rows),
        "chunks_size": 1000,
        "fps": fps,
        "splits": {"train": f"0:{len(episode_rows)}"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            "action": {"dtype": "float32", "shape": [6], "names": JOINT_NAMES},
            "observation.state": {"dtype": "float32", "shape": [6], "names": JOINT_NAMES},
            video_key: {
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
        "total_videos": len(episode_rows),
    }
    write_json(meta_dir / "info.json", info)
    write_json(
        meta_dir / "stats.json",
        {
            "observation.state": _stats(np.concatenate(all_states)),
            "action": _stats(np.concatenate(all_actions)),
            "timestamp": _stats(np.concatenate(all_timestamps)),
            "next.reward": _stats(np.concatenate(all_rewards)),
        },
    )
    (meta_dir / "relative_stats.json").write_text("{}")
    manifest = payload_manifest(output)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "dataset_schema": SCHEMA,
        "catalog_path": catalog_path.relative_to(repo_root).as_posix(),
        "catalog_sha256": sha256_file(catalog_path),
        "episode_count": len(episode_rows),
        "unique_source_episode_count": len(episode_rows),
        "frame_count": global_index,
        "held_out_rows": 0,
        "failed_outcome_rows": 0,
        "physical_training_rows": global_index,
        "all_training_rows_evaluator_admitted": False,
        "source_proof_class": "physical_teleoperation_source_unqualified",
        "source_training_admission": "pending_deterministic_replay_and_separate_evaluator",
        "purpose": "bounded_exploratory_groot_n17_finetune_only",
        "training_cannot_promote": True,
        "policy_results_require_separate_frozen_evaluation": True,
        "physical_authority": False,
        "sim_to_real_authority": False,
        "source_episodes": source_rows,
        "payload_manifest": manifest,
        "payload_manifest_sha256": canonical_sha256(manifest),
    }
    receipt["canonical_payload_sha256"] = canonical_sha256(receipt)
    write_json(output / "dataset_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
