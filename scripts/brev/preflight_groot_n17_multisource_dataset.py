#!/usr/bin/env python3
"""Pinned NVIDIA loader preflight for the admitted multisource dataset."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np


SCHEMA = "sim2claw.groot_n17_multisource_remote_loader_preflight.v1"
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


def payload_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "dataset_receipt.json"
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--sim2claw-root", type=Path, required=True)
    parser.add_argument("--nvidia-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--expected-dataset-receipt-sha256", required=True)
    parser.add_argument("--expected-payload-manifest-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    sim2claw_root = args.sim2claw_root.resolve()
    nvidia_root = args.nvidia_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite remote preflight: {output}")

    contract_path = (
        sim2claw_root
        / "configs/tasks/chess_manipulation_groot_multisource_v2.json"
    )
    modality_path = sim2claw_root / "configs/groot/sim2claw_so101_config.py"
    receipt_path = dataset_root / "dataset_receipt.json"
    if sha256_file(contract_path) != args.expected_contract_sha256:
        raise ValueError("remote multisource contract hash mismatch")
    if sha256_file(receipt_path) != args.expected_dataset_receipt_sha256:
        raise ValueError("remote multisource receipt hash mismatch")
    contract = json.loads(contract_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    canonical_receipt = dict(receipt)
    recorded_receipt_hash = canonical_receipt.pop("canonical_payload_sha256")
    if canonical_sha256(canonical_receipt) != recorded_receipt_hash:
        raise ValueError("remote multisource receipt canonical hash mismatch")
    before_manifest = payload_manifest(dataset_root)
    before_manifest_sha256 = canonical_sha256(before_manifest)
    if before_manifest != receipt.get("payload_manifest"):
        raise ValueError("remote multisource payload differs from its receipt")
    if before_manifest_sha256 != args.expected_payload_manifest_sha256:
        raise ValueError("remote multisource manifest identity mismatch")
    if (dataset_root / "meta/relative_stats.json").read_bytes() != b"{}":
        raise ValueError("absolute-action relative stats must be canonical empty JSON")
    if any(
        int(receipt.get(key, -1)) != 0
        for key in ("held_out_rows", "failed_action_rows", "physical_training_rows")
    ):
        raise ValueError("excluded rows entered the remote multisource dataset")

    nvidia_commit = subprocess.check_output(
        ["git", "-C", str(nvidia_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if nvidia_commit != EXPECTED_NVIDIA_COMMIT:
        raise ValueError("remote NVIDIA source commit changed")
    nvidia_status = subprocess.check_output(
        ["git", "-C", str(nvidia_root), "status", "--porcelain"], text=True
    )
    if nvidia_status:
        raise ValueError("remote NVIDIA source is dirty")

    spec = importlib.util.spec_from_file_location("sim2claw_so101_config", modality_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not import frozen sim2claw modality config")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS
    from gr00t.data.dataset.lerobot_episode_loader import LeRobotEpisodeLoader
    from gr00t.data.dataset.sharded_single_step_dataset import (
        ShardedSingleStepDataset,
        extract_step_data,
    )
    from gr00t.data.embodiment_tags import EmbodimentTag

    configs = MODALITY_CONFIGS[EmbodimentTag.NEW_EMBODIMENT.value]
    expected_columns = contract["loader_proof"]["expected_columns"]
    if configs["video"].modality_keys != ["front"]:
        raise ValueError("multisource GR00T video modality changed")
    if configs["state"].modality_keys != ["single_arm", "gripper"]:
        raise ValueError("multisource GR00T state modality changed")
    if configs["action"].modality_keys != ["single_arm", "gripper"]:
        raise ValueError("multisource GR00T action modality changed")
    if configs["action"].delta_indices != list(range(16)):
        raise ValueError("multisource GR00T action horizon changed")
    if configs["language"].modality_keys != [
        "annotation.human.task_description"
    ]:
        raise ValueError("multisource GR00T language modality changed")
    action_configs = configs["action"].action_configs
    if action_configs is None or any(
        config.rep.value != "absolute" for config in action_configs
    ):
        raise ValueError("multisource GR00T action representation changed")

    loader = LeRobotEpisodeLoader(dataset_root, configs)
    episode_rows = read_jsonl(dataset_root / "meta/episodes.jsonl")
    task_rows = read_jsonl(dataset_root / "meta/tasks.jsonl")
    task_by_index = {int(row["task_index"]): str(row["task"]) for row in task_rows}
    expected_lengths = [int(row["length"]) for row in episode_rows]
    if len(loader) != int(contract["dataset"]["derived_dataset_episode_count"]):
        raise ValueError("pinned NVIDIA loader episode count changed")
    if loader.get_episode_lengths() != expected_lengths:
        raise ValueError("pinned NVIDIA loader episode lengths changed")

    import pyarrow.parquet as pq

    action_digest = hashlib.sha256()
    state_digest = hashlib.sha256()
    image_digest = hashlib.sha256()
    image_shapes: set[tuple[int, ...]] = set()
    decoded_video_frame_count = 0
    effective_starts = 0
    for episode_index, expected_length in enumerate(expected_lengths):
        episode = loader[episode_index]
        if episode.columns.tolist() != expected_columns:
            raise ValueError(
                f"pinned NVIDIA loader columns changed: {episode.columns.tolist()}"
            )
        source_table = pq.read_table(
            dataset_root
            / "data/chunk-000"
            / f"episode_{episode_index:06d}.parquet"
        )
        source_actions = np.asarray(
            source_table["action"].to_pylist(), dtype=np.float32
        )
        source_states = np.asarray(
            source_table["observation.state"].to_pylist(), dtype=np.float32
        )
        task_indices = set(source_table["task_index"].to_pylist())
        if len(task_indices) != 1:
            raise ValueError("multisource episode language schedule is not constant")
        instruction = task_by_index[int(next(iter(task_indices)))]
        for frame in episode["video.front"]:
            pixels = np.asarray(frame, dtype=np.uint8)
            image_shapes.add(tuple(pixels.shape))
            image_digest.update(np.ascontiguousarray(pixels).tobytes())
            decoded_video_frame_count += 1

        episode_effective_starts = expected_length - 16 + 1
        for start in range(episode_effective_starts):
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
            if not np.array_equal(action_chunk, source_actions[start : start + 16]):
                raise ValueError(
                    f"pinned NVIDIA action extraction changed at {episode_index}:{start}"
                )
            if not np.array_equal(state_row, source_states[start : start + 1]):
                raise ValueError(
                    f"pinned NVIDIA state extraction changed at {episode_index}:{start}"
                )
            if step.text != instruction:
                raise ValueError(
                    f"pinned NVIDIA language extraction changed at {episode_index}:{start}"
                )
            action_digest.update(np.ascontiguousarray(action_chunk).tobytes())
            state_digest.update(np.ascontiguousarray(state_row).tobytes())
        effective_starts += episode_effective_starts

    expected_shape = tuple(contract["loader_proof"]["expected_video_frame_shape"])
    if image_shapes != {expected_shape}:
        raise ValueError(f"pinned NVIDIA decoded image shape changed: {image_shapes}")
    if decoded_video_frame_count != int(contract["dataset"]["frame_count"]):
        raise ValueError("pinned NVIDIA decoded video frame count changed")
    if effective_starts != int(
        contract["dataset"]["expected_effective_h16_start_count"]
    ):
        raise ValueError("pinned NVIDIA effective-start denominator changed")

    loader_contract = contract["loader_proof"]
    sharded = ShardedSingleStepDataset(
        dataset_path=dataset_root,
        embodiment_tag=EmbodimentTag.NEW_EMBODIMENT,
        modality_configs=configs,
        shard_size=int(loader_contract["shard_size"]),
        episode_sampling_rate=float(loader_contract["episode_sampling_rate"]),
        seed=int(loader_contract["seed"]),
        allow_padding=False,
    )
    sharded_start_count = int(sum(sharded.shard_lengths))
    if sharded_start_count != int(loader_contract["expected_sharded_start_count"]):
        raise ValueError("pinned NVIDIA sharded start denominator changed")
    if len(sharded) != int(loader_contract["expected_shard_count"]):
        raise ValueError("pinned NVIDIA shard count changed")

    after_manifest = payload_manifest(dataset_root)
    if after_manifest != before_manifest:
        raise ValueError("pinned NVIDIA loader mutated the frozen dataset")
    nvidia_files = {
        "lerobot_episode_loader.py": nvidia_root
        / "gr00t/data/dataset/lerobot_episode_loader.py",
        "sharded_single_step_dataset.py": nvidia_root
        / "gr00t/data/dataset/sharded_single_step_dataset.py",
        "dataset_factory.py": nvidia_root / "gr00t/data/dataset/factory.py",
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "passed": True,
        "preflight_script_sha256": sha256_file(Path(__file__)),
        "dataset_contract_sha256": sha256_file(contract_path),
        "dataset_receipt_sha256": sha256_file(receipt_path),
        "dataset_payload_manifest_sha256": before_manifest_sha256,
        "dataset_unmodified_by_loader": True,
        "relative_stats_sha256": sha256_file(
            dataset_root / "meta/relative_stats.json"
        ),
        "nvidia_commit": nvidia_commit,
        "nvidia_source_dirty": False,
        "nvidia_file_sha256": {
            name: sha256_file(path) for name, path in nvidia_files.items()
        },
        "modality_config_sha256": sha256_file(modality_path),
        "episode_count": len(loader),
        "unique_source_episode_count": int(
            contract["dataset"]["unique_source_episode_count"]
        ),
        "source_row_count": int(contract["dataset"]["frame_count"]),
        "effective_start_count": effective_starts,
        "action_horizon": 16,
        "action_target_slot_count": effective_starts * 16,
        "action_scalar_count": effective_starts * 16 * 6,
        "extracted_action_chunks_sha256": action_digest.hexdigest(),
        "extracted_current_states_sha256": state_digest.hexdigest(),
        "decoded_video_frames_sha256": image_digest.hexdigest(),
        "decoded_video_frame_count": decoded_video_frame_count,
        "decoded_video_frame_shapes": [list(shape) for shape in sorted(image_shapes)],
        "distinct_prompt_count": len(task_rows),
        "allow_padding": False,
        "shard_size": int(loader_contract["shard_size"]),
        "shard_episode_sampling_rate": float(
            loader_contract["episode_sampling_rate"]
        ),
        "shard_seed": int(loader_contract["seed"]),
        "shard_count": len(sharded),
        "sharded_start_count": sharded_start_count,
        "held_out_rows": 0,
        "failed_action_rows": 0,
        "physical_training_rows": 0,
        "model_queries": 0,
        "training_started": False,
        "physical_authority": False,
    }
    report["canonical_payload_sha256"] = canonical_sha256(report)
    write_json(output, report)
    print(json.dumps({**report, "receipt_sha256": sha256_file(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
