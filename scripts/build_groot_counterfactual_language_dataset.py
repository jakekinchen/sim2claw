#!/usr/bin/env python3
"""Build a hard-linked GR00T dataset with deterministic wrong instructions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.unlink()
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    if source == output or source in output.parents:
        raise ValueError("output must not be inside the source dataset")

    source_tasks_path = source / "meta" / "tasks.jsonl"
    source_episodes_path = source / "meta" / "episodes.jsonl"
    task_rows = read_jsonl(source_tasks_path)
    episode_rows = read_jsonl(source_episodes_path)
    unique_tasks = list(dict.fromkeys(str(row["task"]) for row in task_rows))
    if len(unique_tasks) < 2:
        raise ValueError("counterfactual rotation requires at least two tasks")
    task_mapping = {
        task: unique_tasks[(index + 1) % len(unique_tasks)]
        for index, task in enumerate(unique_tasks)
    }
    if any(task == replacement for task, replacement in task_mapping.items()):
        raise ValueError("counterfactual mapping contains an unchanged instruction")

    output.mkdir(parents=True)
    for directory in ("data", "videos", "meta"):
        source_directory = source / directory
        if not source_directory.is_dir():
            raise ValueError(f"source dataset is missing {directory}")
        shutil.copytree(
            source_directory,
            output / directory,
            copy_function=os.link,
        )

    counterfactual_tasks = [
        {**row, "task": task_mapping[str(row["task"])]} for row in task_rows
    ]
    counterfactual_episodes = [
        {
            **row,
            "tasks": [task_mapping[str(task)] for task in row["tasks"]],
        }
        for row in episode_rows
    ]
    output_tasks_path = output / "meta" / "tasks.jsonl"
    output_episodes_path = output / "meta" / "episodes.jsonl"
    write_jsonl(output_tasks_path, counterfactual_tasks)
    write_jsonl(output_episodes_path, counterfactual_episodes)

    receipt = {
        "schema_version": "sim2claw.groot_counterfactual_language_dataset.v1",
        "proof_class": "in_sample_counterfactual_language_diagnostic",
        "source_dataset": str(source),
        "source_tasks_sha256": sha256_file(source_tasks_path),
        "source_episodes_sha256": sha256_file(source_episodes_path),
        "counterfactual_tasks_sha256": sha256_file(output_tasks_path),
        "counterfactual_episodes_sha256": sha256_file(output_episodes_path),
        "task_mapping": task_mapping,
        "task_mapping_sha256": canonical_sha256(task_mapping),
        "task_count": len(unique_tasks),
        "episode_count": len(episode_rows),
        "all_instructions_changed": True,
        "held_out": False,
        "promotion_authority": False,
        "physical_policy_result": False,
    }
    receipt["canonical_payload_sha256"] = canonical_sha256(receipt)
    receipt_path = output / "counterfactual_language_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
