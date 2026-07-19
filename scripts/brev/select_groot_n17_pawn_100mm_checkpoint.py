#!/usr/bin/env python3
"""Select one pawn checkpoint by frozen full-source H16 action error."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
from typing import Any

import numpy as np


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )


def checkpoint_manifest(checkpoint: Path) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for path in sorted(
        (path for path in checkpoint.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(checkpoint).as_posix(),
    ):
        rows.append(
            {
                "path": path.relative_to(checkpoint).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return canonical_sha256(rows), rows


def parse_observation(data_point: object, modality_configs: dict) -> dict:
    observation: dict[str, object] = {}
    for key, value in data_point.states.items():
        observation[f"state.{key}"] = value
    for key, value in data_point.images.items():
        observation[f"video.{key}"] = np.asarray(value)
    for key in modality_configs["language"].modality_keys:
        observation[key] = data_point.text

    parsed: dict[str, dict[str, object]] = {}
    for modality in ("video", "state", "language"):
        parsed[modality] = {}
        for key in modality_configs[modality].modality_keys:
            source_key = key if modality == "language" else f"{modality}.{key}"
            value = observation[source_key]
            parsed[modality][key] = [[value]] if isinstance(value, str) else value[None, :]
    return parsed


def concatenate_actions(action: dict, action_keys: list[str], horizon: int) -> np.ndarray:
    rows = []
    for offset in range(horizon):
        rows.append(
            np.concatenate(
                [
                    np.atleast_1d(np.asarray(action[key])[0][offset])
                    for key in action_keys
                ]
            ).astype(np.float64)
        )
    return np.asarray(rows, dtype=np.float64)


def direct_target(trajectory: object, columns: list[str], indices: list[int]) -> np.ndarray:
    by_column = [
        np.vstack([np.asarray(trajectory[column].iloc[index]) for index in indices])
        for column in columns
    ]
    return np.concatenate(by_column, axis=-1).astype(np.float64)


def validate_dataset(dataset: Path, contract: dict) -> None:
    receipt_path = dataset / "dataset_receipt.json"
    if sha256_file(receipt_path) != contract["identities"]["dataset_receipt_sha256"]:
        raise SystemExit("pawn dataset receipt drifted")
    receipt = json.loads(receipt_path.read_text())
    expected = receipt["payload_manifest"]
    actual = {
        path.relative_to(dataset).as_posix()
        for path in dataset.rglob("*")
        if path.is_file() and path.name != "dataset_receipt.json"
    }
    if actual != set(expected):
        raise SystemExit("pawn dataset inventory drifted")
    for relative, row in expected.items():
        path = dataset / relative
        if path.stat().st_size != int(row["size_bytes"]):
            raise SystemExit(f"pawn dataset size drifted: {relative}")
        if sha256_file(path) != row["sha256"]:
            raise SystemExit(f"pawn dataset content drifted: {relative}")
    if canonical_sha256(expected) != contract["identities"]["dataset_manifest_sha256"]:
        raise SystemExit("pawn dataset payload manifest drifted")
    if receipt["held_out_rows"] != 0:
        raise SystemExit("selector dataset contains held-out rows")


def validate_training(contract: dict) -> None:
    identities = contract["identities"]
    experiment = Path(contract["training_evidence"]["experiment_path"])
    if sha256_file(experiment) != identities["experiment_sha256"]:
        raise SystemExit("parent experiment drifted")
    parent = json.loads(experiment.read_text())
    frozen = parent["training_only_checkpoint_selection"]
    selection = contract["selection"]
    expected = {
        "candidate_steps": frozen["candidate_steps"],
        "inference_seed": frozen["inference_seed"],
        "evaluated_start_count_per_checkpoint": frozen[
            "evaluated_start_count_per_checkpoint"
        ],
        "action_slots_per_checkpoint": frozen["action_slots_per_checkpoint"],
        "action_scalars_per_checkpoint": frozen["action_scalars_per_checkpoint"],
        "tie_break": frozen["tie_break"],
    }
    for key, value in expected.items():
        if selection.get(key) != value:
            raise SystemExit(f"selector redefines frozen field: {key}")

    for key in (
        "launch_receipt",
        "runtime_receipt",
        "completion_receipt",
        "training_log",
        "training_exit",
    ):
        row = contract["training_evidence"][key]
        path = Path(row["path"])
        if sha256_file(path) != row["sha256"]:
            raise SystemExit(f"training evidence drifted: {key}")
    launch = json.loads(Path(contract["training_evidence"]["launch_receipt"]["path"]).read_text())
    runtime = json.loads(Path(contract["training_evidence"]["runtime_receipt"]["path"]).read_text())
    completion = json.loads(
        Path(contract["training_evidence"]["completion_receipt"]["path"]).read_text()
    )
    if launch["experiment_sha256"] != identities["experiment_sha256"]:
        raise SystemExit("launch receipt belongs to another experiment")
    if runtime["experiment_sha256"] != identities["experiment_sha256"]:
        raise SystemExit("runtime receipt belongs to another experiment")
    if completion["experiment_sha256"] != identities["experiment_sha256"]:
        raise SystemExit("completion receipt belongs to another experiment")
    if completion["optimizer_steps"] != 1000 or not completion["training_processes_stopped"]:
        raise SystemExit("completion receipt does not prove bounded training completion")
    if launch["held_out_rows_used"] != 0 or runtime["held_out_rows_used"] != 0:
        raise SystemExit("training evidence consumed held-out rows")
    if Path("/proc", str(runtime["pid"])).exists():
        raise SystemExit("training child is still running")
    if Path("/proc", str(contract["training_evidence"]["supervisor_pid"])).exists():
        raise SystemExit("training supervisor is still running")
    if Path(contract["training_evidence"]["training_exit"]["path"]).read_text().strip() != "0":
        raise SystemExit("training did not exit successfully")
    log = Path(contract["training_evidence"]["training_log"]["path"]).read_bytes()
    if b"1000/1000" not in log or b"Traceback (most recent call last)" in log:
        raise SystemExit("training log does not prove clean 1000-step completion")
    for step, expected_manifest in contract["selection"]["candidate_manifests"].items():
        completed = completion["checkpoints"].get(step)
        if completed is None:
            raise SystemExit(f"completion receipt omits checkpoint-{step}")
        if completed["manifest_sha256"] != expected_manifest["manifest_sha256"]:
            raise SystemExit(f"completion receipt manifest drifted: checkpoint-{step}")
        if completed["file_count"] != expected_manifest["file_count"]:
            raise SystemExit(f"completion receipt file count drifted: checkpoint-{step}")

    groot_root = Path(contract["runtime"]["groot_root"])
    observed_commit = subprocess.check_output(
        ["git", "-C", str(groot_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed_commit != identities["nvidia_commit"]:
        raise SystemExit("NVIDIA source commit drifted")
    dirty = subprocess.check_output(
        [
            "git",
            "-C",
            str(groot_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
        ],
        text=True,
    ).rstrip("\n")
    if dirty != contract["runtime"]["expected_nvidia_tracked_dirtiness"]:
        raise SystemExit("NVIDIA tracked source dirtiness drifted")
    processor = groot_root / "gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py"
    if sha256_file(processor) != identities["patched_processor_sha256"]:
        raise SystemExit("patched NVIDIA processor drifted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if sha256_file(args.contract) != args.expected_contract_sha256:
        raise SystemExit("selector contract hash drifted")
    contract = json.loads(args.contract.read_text())
    if sha256_file(Path(__file__).resolve()) != contract["identities"]["selector_sha256"]:
        raise SystemExit("selector implementation drifted")
    if os.environ.get("GROOT_PROCESSOR_MODEL_PATH") != contract["runtime"]["processor_path"]:
        raise SystemExit("offline processor path drifted")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise SystemExit("selector must run offline")
    validate_training(contract)
    dataset = Path(contract["selection"]["dataset_path"])
    validate_dataset(dataset, contract)

    candidates = contract["selection"]["candidate_manifests"]
    checkpoint_parent = Path(contract["selection"]["checkpoint_parent"])
    actual_steps = sorted(
        int(path.name.removeprefix("checkpoint-"))
        for path in checkpoint_parent.glob("checkpoint-*")
        if path.is_dir() and path.name.removeprefix("checkpoint-").isdigit()
    )
    expected_steps = [int(step) for step in contract["selection"]["candidate_steps"]]
    if actual_steps != expected_steps:
        raise SystemExit(f"checkpoint inventory drifted: {actual_steps}")
    candidate_inventories = {}
    for step in expected_steps:
        checkpoint = checkpoint_parent / f"checkpoint-{step}"
        manifest_sha256, manifest = checkpoint_manifest(checkpoint)
        expected_manifest = candidates[str(step)]
        if manifest_sha256 != expected_manifest["manifest_sha256"]:
            raise SystemExit(f"checkpoint-{step} manifest drifted")
        if len(manifest) != int(expected_manifest["file_count"]):
            raise SystemExit(f"checkpoint-{step} file count drifted")
        candidate_inventories[step] = (manifest_sha256, manifest)
    if args.preflight_only:
        print("pawn GR00T selector no-query preflight passed")
        return 0

    output = Path(contract["selection"]["output_root"])
    if output.exists():
        raise SystemExit("selector output already exists")
    output.mkdir(parents=True)

    import torch
    from gr00t.data.dataset.lerobot_episode_loader import LeRobotEpisodeLoader
    from gr00t.data.dataset.sharded_single_step_dataset import extract_step_data
    from gr00t.data.embodiment_tags import EmbodimentTag
    from gr00t.policy.gr00t_policy import Gr00tPolicy

    horizon = 16
    starts = list(range(547))
    index_evidence = [
        {"start": start, "target_indices": list(range(start, start + horizon))}
        for start in starts
    ]
    index_sha256 = canonical_sha256(index_evidence)
    results = []
    for step in expected_steps:
        checkpoint = checkpoint_parent / f"checkpoint-{step}"
        manifest_sha256, manifest = candidate_inventories[step]

        seed = int(contract["selection"]["inference_seed"])
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        policy = Gr00tPolicy(
            embodiment_tag=EmbodimentTag.resolve("new_embodiment"),
            model_path=str(checkpoint),
            device="cuda",
        )
        modality = policy.get_modality_config()
        loader = LeRobotEpisodeLoader(
            dataset_path=str(dataset),
            modality_configs=modality,
            video_backend="torchcodec",
            video_backend_kwargs=None,
        )
        if len(loader) != 1:
            raise SystemExit("selector must see exactly one training episode")
        trajectory = loader[0]
        if len(trajectory) != 562:
            raise SystemExit("training episode row count drifted")
        observation_modality = deepcopy(modality)
        observation_modality.pop("action")
        action_keys = list(modality["action"].modality_keys)
        action_columns = [f"action.{key}" for key in action_keys]
        squared_error_sum = 0.0
        absolute_error_sum = 0.0
        scalar_count = 0
        predictions = hashlib.sha256()
        prompt_hashes = set()
        for start in starts:
            data_point = extract_step_data(
                trajectory,
                start,
                observation_modality,
                EmbodimentTag.resolve("new_embodiment"),
            )
            prompt_hashes.add(sha256_bytes(str(data_point.text).encode()))
            action, _ = policy.get_action(parse_observation(data_point, modality))
            prediction = concatenate_actions(action, action_keys, horizon)
            target_indices = list(range(start, start + horizon))
            target = direct_target(trajectory, action_columns, target_indices)
            if prediction.shape != (16, 6) or target.shape != (16, 6):
                raise SystemExit("selector action shape drifted")
            if not np.isfinite(prediction).all() or not np.isfinite(target).all():
                raise SystemExit("selector encountered a non-finite action")
            error = prediction - target
            squared_error_sum += float(np.square(error).sum())
            absolute_error_sum += float(np.abs(error).sum())
            scalar_count += int(error.size)
            predictions.update(np.asarray(prediction, dtype="<f8").tobytes())

        if scalar_count != 52512 or len(starts) * horizon != 8752:
            raise SystemExit("selector denominator drifted")
        if len(prompt_hashes) != 1:
            raise SystemExit("selector prompt coverage drifted")
        results.append(
            {
                "checkpoint_step": step,
                "checkpoint_path": str(checkpoint),
                "checkpoint_manifest_sha256": manifest_sha256,
                "checkpoint_file_count": len(manifest),
                "mse": squared_error_sum / scalar_count,
                "mae": absolute_error_sum / scalar_count,
                "query_count": len(starts),
                "target_slot_count": len(starts) * horizon,
                "target_scalar_count": scalar_count,
                "target_index_evidence_sha256": index_sha256,
                "prediction_chunks_sha256": predictions.hexdigest(),
                "prompt_hash_count": len(prompt_hashes),
            }
        )
        del loader, policy
        torch.cuda.empty_cache()

    selected = min(results, key=lambda row: (row["mse"], row["checkpoint_step"]))
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.groot_n17_pawn_training_selector.v1",
        "proof_class": "learned_policy_training_diagnostic_not_task_success",
        "contract_sha256": args.expected_contract_sha256,
        "selector_sha256": contract["identities"]["selector_sha256"],
        "experiment_sha256": contract["identities"]["experiment_sha256"],
        "dataset_receipt_sha256": contract["identities"]["dataset_receipt_sha256"],
        "results": results,
        "selected_checkpoint_step": selected["checkpoint_step"],
        "selected_checkpoint_path": selected["checkpoint_path"],
        "selected_checkpoint_manifest_sha256": selected[
            "checkpoint_manifest_sha256"
        ],
        "selection_metric": "minimum full-dataset float32 H16 action mean_squared_error",
        "tie_break": "lowest_numeric_checkpoint_step",
        "query_count_total": 547 * len(expected_steps),
        "target_index_evidence_sha256": index_sha256,
        "held_out_rows_used": 0,
        "closed_loop_consequences_used_for_selection": False,
        "task_success_authority": False,
        "physical_authority": False,
    }
    receipt["canonical_payload_sha256"] = canonical_sha256(receipt)
    (output / "selector-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
