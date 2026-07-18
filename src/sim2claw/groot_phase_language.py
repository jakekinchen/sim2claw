"""Training-only phase-language curriculum for the GR00T chess task."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .groot_chess import groot_task_contract_sha256, load_groot_task_contract
from .paths import DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_phase_language_contract(
    path: Path = DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != "sim2claw.groot_chess_phase_language.v1":
        raise ValueError("unsupported GR00T phase-language contract")
    if contract.get("base_task_contract_sha256") != groot_task_contract_sha256():
        raise ValueError("phase-language contract is bound to another base task")
    if not contract.get("frozen_before_held_out"):
        raise ValueError("phase-language contract must be frozen before held-out use")
    scheduler = contract.get("scheduler", {})
    if scheduler.get("mode") != "frozen_sample_step":
        raise ValueError("phase-language scheduler must use frozen sample steps")
    if scheduler.get("uses_observation_geometry") or scheduler.get("uses_reward"):
        raise ValueError("phase-language scheduler may not inspect geometry or reward")
    authority = contract.get("authority", {})
    if authority.get("action_assistance_frames") != 0:
        raise ValueError("phase-language contract may not inject action assistance")
    return contract


def phase_language_contract_sha256(
    path: Path = DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG,
) -> str:
    return _canonical_sha256(load_phase_language_contract(path))


def phase_row_ranges(base_contract: dict[str, Any]) -> dict[str, tuple[int, int]]:
    stride = int(base_contract["episode"]["sample_every_physics_steps"])
    if stride <= 0:
        raise ValueError("sample stride must be positive")
    ranges: dict[str, tuple[int, int]] = {}
    cursor = 0
    for phase, physics_steps in base_contract["episode"]["phase_physics_steps"].items():
        count, remainder = divmod(int(physics_steps), stride)
        if remainder:
            raise ValueError(f"phase {phase} is not divisible by the sample stride")
        ranges[str(phase)] = (cursor, cursor + count)
        cursor += count
    settle_count, remainder = divmod(
        int(base_contract["episode"]["settle_steps_after"]), stride
    )
    if remainder:
        raise ValueError("settle steps are not divisible by the sample stride")
    ranges["settle"] = (cursor, cursor + settle_count)
    return ranges


def phase_for_sample_step(base_contract: dict[str, Any], sample_step: int) -> str:
    if sample_step < 0:
        raise ValueError("sample step must be non-negative")
    for phase, (start, end) in phase_row_ranges(base_contract).items():
        if start <= sample_step < end:
            return phase
    raise ValueError(f"sample step exceeds frozen episode length: {sample_step}")


def _piece_label(case: dict[str, Any]) -> str:
    words = str(case["piece"]).split("_")
    if len(words) < 3:
        raise ValueError(f"cannot derive piece label from {case['piece']}")
    return " ".join(words[:-1])


def _source_square(case: dict[str, Any]) -> str:
    square = str(case["piece"]).split("_")[-1]
    if len(square) != 2:
        raise ValueError(f"cannot derive source square from {case['piece']}")
    return square


def phase_prompt(
    phase_contract: dict[str, Any], case: dict[str, Any], phase: str
) -> str:
    templates = phase_contract["phase_prompt_templates"]
    if phase not in templates:
        raise ValueError(f"phase-language template missing: {phase}")
    return str(templates[phase]).format(
        piece=_piece_label(case),
        source_square=_source_square(case),
        target_square=str(case["target_square"]),
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    rendered = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")


def _case_by_instruction(base_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = [
        *base_contract["training_cases"],
        *base_contract["held_out_cases"],
    ]
    return {str(case["instruction"]): case for case in cases}


def build_phase_language_dataset(
    source: Path,
    destination: Path,
    *,
    phase_contract_path: Path = DEFAULT_GROOT_PHASE_LANGUAGE_CONFIG,
) -> dict[str, Any]:
    """Copy an admitted training dataset and relabel only its language task index."""

    source = source.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    phase_contract = load_phase_language_contract(phase_contract_path)
    source_receipt_path = source / "dataset_receipt.json"
    source_receipt_sha256 = _sha256_file(source_receipt_path)
    if source_receipt_sha256 != phase_contract["source_dataset_receipt_sha256"]:
        raise ValueError("source dataset receipt does not match the frozen contract")

    base_contract = load_groot_task_contract()
    ranges = phase_row_ranges(base_contract)
    phases = list(ranges)
    shutil.copytree(source, destination)
    shutil.copy2(source_receipt_path, destination / "source_dataset_receipt.json")

    meta_dir = destination / "meta"
    source_tasks = [
        json.loads(line)
        for line in (source / "meta" / "tasks.jsonl").read_text().splitlines()
        if line.strip()
    ]
    case_by_instruction = _case_by_instruction(base_contract)
    case_by_source_task: dict[int, dict[str, Any]] = {}
    for row in source_tasks:
        task_index = int(row["task_index"])
        instruction = str(row["task"])
        if instruction not in case_by_instruction:
            raise ValueError(
                f"source task is absent from the base contract: {instruction}"
            )
        case_by_source_task[task_index] = case_by_instruction[instruction]

    phase_task_index: dict[tuple[int, str], int] = {}
    task_rows: list[dict[str, Any]] = []
    for source_task_index in sorted(case_by_source_task):
        case = case_by_source_task[source_task_index]
        for phase in phases:
            task_index = len(task_rows)
            phase_task_index[(source_task_index, phase)] = task_index
            task_rows.append(
                {
                    "task_index": task_index,
                    "task": phase_prompt(phase_contract, case, phase),
                }
            )
    _write_jsonl(meta_dir / "tasks.jsonl", task_rows)

    episode_rows: list[dict[str, Any]] = []
    parquet_paths = sorted((destination / "data").glob("chunk-*/*.parquet"))
    total_frames = 0
    verified_non_task_columns: set[str] = set()
    for parquet_path in parquet_paths:
        source_table = pq.read_table(source / parquet_path.relative_to(destination))
        length = len(source_table)
        expected_length = max(end for _, end in ranges.values())
        if length != expected_length:
            raise ValueError(
                f"episode length {length} does not match phase schedule {expected_length}"
            )
        source_task_values = np.asarray(
            source_table["task_index"].combine_chunks().to_numpy(), dtype=np.int64
        )
        unique_source_tasks = np.unique(source_task_values)
        if len(unique_source_tasks) != 1:
            raise ValueError("source episode must contain exactly one task index")
        source_task_index = int(unique_source_tasks[0])
        relabeled = np.empty(length, dtype=np.int64)
        episode_tasks: list[str] = []
        for phase, (start, end) in ranges.items():
            new_task_index = phase_task_index[(source_task_index, phase)]
            relabeled[start:end] = new_task_index
            episode_tasks.append(str(task_rows[new_task_index]["task"]))
        task_column_index = source_table.schema.get_field_index("task_index")
        table = source_table.set_column(
            task_column_index,
            "task_index",
            pa.array(relabeled, type=pa.int64()),
        )
        pq.write_table(table, parquet_path, compression="zstd")
        roundtrip_table = pq.read_table(parquet_path)
        for column in source_table.column_names:
            if column == "task_index":
                continue
            if not source_table[column].equals(roundtrip_table[column]):
                raise RuntimeError(
                    f"phase-language relabel changed semantic column {column}"
                )
            verified_non_task_columns.add(column)
        roundtrip_tasks = np.asarray(
            roundtrip_table["task_index"].combine_chunks().to_numpy(),
            dtype=np.int64,
        )
        if not np.array_equal(roundtrip_tasks, relabeled):
            raise RuntimeError("phase-language task index failed round-trip validation")
        episode_index_values = np.unique(
            np.asarray(
                table["episode_index"].combine_chunks().to_numpy(), dtype=np.int64
            )
        )
        if len(episode_index_values) != 1:
            raise ValueError("episode parquet must contain exactly one episode index")
        episode_rows.append(
            {
                "episode_index": int(episode_index_values[0]),
                "length": length,
                "tasks": episode_tasks,
            }
        )
        total_frames += length
    _write_jsonl(meta_dir / "episodes.jsonl", episode_rows)

    video_files = sorted((source / "videos").glob("chunk-*/*/*.mp4"))
    for source_video in video_files:
        destination_video = destination / source_video.relative_to(source)
        if _sha256_file(source_video) != _sha256_file(destination_video):
            raise RuntimeError(f"copied video changed bytes: {source_video}")

    info_path = meta_dir / "info.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["total_tasks"] = len(task_rows)
    info_path.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")

    manifest_rows: list[dict[str, Any]] = []
    excluded = {"dataset_receipt.json"}
    for path in sorted(item for item in destination.rglob("*") if item.is_file()):
        relative = path.relative_to(destination).as_posix()
        if relative in excluded:
            continue
        manifest_rows.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    receipt = {
        "schema_version": "sim2claw.groot_phase_language_dataset.v1",
        "proof_class": "synthetic_training_dataset",
        "source_dataset": str(source),
        "source_dataset_receipt_sha256": source_receipt_sha256,
        "phase_language_contract_sha256": phase_language_contract_sha256(
            phase_contract_path
        ),
        "base_task_contract_sha256": groot_task_contract_sha256(),
        "episode_count": len(episode_rows),
        "frame_count": total_frames,
        "task_count": len(task_rows),
        "phase_row_ranges": {
            phase: {"start": start, "end_exclusive": end}
            for phase, (start, end) in ranges.items()
        },
        "changed_fields": ["task_index", "meta/tasks.jsonl", "meta/episodes.jsonl"],
        "states_actions_images_unchanged": True,
        "verified_non_task_columns": sorted(verified_non_task_columns),
        "video_files_byte_equivalent": len(video_files),
        "held_out_rows_used": 0,
        "manifest_sha256": _canonical_sha256(manifest_rows),
        "manifest": manifest_rows,
        "physical_authority": False,
    }
    (destination / "dataset_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
