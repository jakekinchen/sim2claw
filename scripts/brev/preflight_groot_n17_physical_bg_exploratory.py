#!/usr/bin/env python3
"""Preflight the exploratory physical B--G dataset with NVIDIA's pinned loader."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np


SCHEMA = "sim2claw.groot_n17_physical_bg_remote_preflight.v1"
EXPECTED_NVIDIA_COMMIT = "23ace64f17aa5015259b8609d371eb61a357c776"


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--sim2claw-root", type=Path, required=True)
    parser.add_argument("--nvidia-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    sim2claw_root = args.sim2claw_root.resolve()
    nvidia_root = args.nvidia_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite preflight receipt: {output}")

    receipt_path = dataset_root / "dataset_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt_copy = dict(receipt)
    recorded_canonical = receipt_copy.pop("canonical_payload_sha256")
    if canonical_sha256(receipt_copy) != recorded_canonical:
        raise ValueError("dataset receipt canonical hash mismatch")
    if receipt.get("episode_count") != 18 or receipt.get("frame_count") != 7741:
        raise ValueError("exploratory dataset count changed")
    if receipt.get("held_out_rows") != 0 or receipt.get("failed_outcome_rows") != 0:
        raise ValueError("excluded rows entered exploratory dataset")
    if receipt.get("physical_training_rows") != 7741:
        raise ValueError("physical row count changed")
    if receipt.get("all_training_rows_evaluator_admitted") is not False:
        raise ValueError("exploratory proof boundary changed")
    if receipt.get("training_cannot_promote") is not True:
        raise ValueError("training promotion boundary changed")
    for relative, expected in receipt["payload_manifest"].items():
        path = dataset_root / relative
        if path.stat().st_size != int(expected["size_bytes"]):
            raise ValueError(f"dataset size changed: {relative}")
        if sha256_file(path) != expected["sha256"]:
            raise ValueError(f"dataset hash changed: {relative}")
    if canonical_sha256(receipt["payload_manifest"]) != receipt[
        "payload_manifest_sha256"
    ]:
        raise ValueError("dataset payload manifest is inconsistent")

    nvidia_commit = subprocess.check_output(
        ["git", "-C", str(nvidia_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if nvidia_commit != EXPECTED_NVIDIA_COMMIT:
        raise ValueError("NVIDIA source commit changed")

    modality_path = sim2claw_root / "configs/groot/sim2claw_so101_config.py"
    spec = importlib.util.spec_from_file_location("sim2claw_so101_config", modality_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load modality config")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS
    from gr00t.data.dataset.lerobot_episode_loader import LeRobotEpisodeLoader
    from gr00t.data.dataset.sharded_single_step_dataset import extract_step_data
    from gr00t.data.embodiment_tags import EmbodimentTag

    configs = MODALITY_CONFIGS[EmbodimentTag.NEW_EMBODIMENT.value]
    loader = LeRobotEpisodeLoader(dataset_root, configs)
    episodes = read_jsonl(dataset_root / "meta/episodes.jsonl")
    tasks = read_jsonl(dataset_root / "meta/tasks.jsonl")
    task_by_index = {int(row["task_index"]): str(row["task"]) for row in tasks}
    expected_lengths = [int(row["length"]) for row in episodes]
    if len(loader) != 18 or loader.get_episode_lengths() != expected_lengths:
        raise ValueError("NVIDIA loader episode inventory changed")
    if sum(expected_lengths) != 7741:
        raise ValueError("NVIDIA loader frame denominator changed")

    import pyarrow.parquet as pq

    decoded_frames = 0
    effective_h16_starts = 0
    image_shapes: set[tuple[int, ...]] = set()
    for episode_index, length in enumerate(expected_lengths):
        episode = loader[episode_index]
        table = pq.read_table(
            dataset_root / "data/chunk-000" / f"episode_{episode_index:06d}.parquet"
        )
        actions = np.asarray(table["action"].to_pylist(), dtype=np.float32)
        states = np.asarray(table["observation.state"].to_pylist(), dtype=np.float32)
        task_indices = set(table["task_index"].to_pylist())
        if len(task_indices) != 1:
            raise ValueError("episode task schedule is not constant")
        instruction = task_by_index[int(next(iter(task_indices)))]
        for frame in episode["video.front"]:
            image_shapes.add(tuple(np.asarray(frame).shape))
            decoded_frames += 1
        for start in (0, length - 16):
            step = extract_step_data(
                episode,
                start,
                configs,
                EmbodimentTag.NEW_EMBODIMENT,
                allow_padding=False,
            )
            action_chunk = np.concatenate(
                [step.actions["single_arm"], step.actions["gripper"]], axis=1
            ).astype(np.float32)
            state_row = np.concatenate(
                [step.states["single_arm"], step.states["gripper"]], axis=1
            ).astype(np.float32)
            if not np.array_equal(action_chunk, actions[start : start + 16]):
                raise ValueError("NVIDIA action extraction changed")
            if not np.array_equal(state_row, states[start : start + 1]):
                raise ValueError("NVIDIA state extraction changed")
            if step.text != instruction:
                raise ValueError("NVIDIA language extraction changed")
        effective_h16_starts += length - 16 + 1

    if decoded_frames != 7741 or image_shapes != {(256, 256, 3)}:
        raise ValueError("NVIDIA decoded video shape or count changed")
    if effective_h16_starts != 7471:
        raise ValueError("H16 training-start denominator changed")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "passed": True,
        "nvidia_commit": nvidia_commit,
        "dataset_receipt_sha256": sha256_file(receipt_path),
        "dataset_payload_manifest_sha256": receipt["payload_manifest_sha256"],
        "episode_count": 18,
        "frame_count": decoded_frames,
        "effective_h16_start_count": effective_h16_starts,
        "image_shapes": [list(shape) for shape in sorted(image_shapes)],
        "held_out_rows": 0,
        "all_training_rows_evaluator_admitted": False,
        "training_cannot_promote": True,
        "model_queries": 0,
        "training_started": False,
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
