"""Dataset-consuming trainer for the frozen 61-D goal-conditioned ACT task."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .act_model import ACTModelConfig, ACTPolicy
from .act_pick_place import load_act_pick_place_task_contract, task_contract_sha256
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .learning_factory_goal_data import DATASET_SCHEMA, ROW_SCHEMA
from .paths import REPO_ROOT


RECIPE_SCHEMA = "sim2claw.goal_act_training_recipe.v1"
TRAINING_RECEIPT_SCHEMA = "sim2claw.goal_act_training_receipt.v1"
CHECKPOINT_SCHEMA = "sim2claw.act_checkpoint.v1"


def load_goal_act_recipe(path: Path) -> dict[str, Any]:
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if recipe.get("schema_version") != RECIPE_SCHEMA:
        raise ValueError("unsupported goal ACT training recipe")
    if recipe.get("architecture") != "ACT":
        raise ValueError("goal-conditioned trainer requires ACT")
    if recipe.get("device") not in {"cpu", "mps", "cuda"}:
        raise ValueError("unsupported training device")
    if recipe.get("dtype") != "float32":
        raise ValueError("goal-conditioned ACT training must use float32")
    for key in (
        "chunk_size",
        "n_action_steps",
        "model_dimension",
        "attention_heads",
        "encoder_layers",
        "decoder_layers",
        "feedforward_dimension",
        "latent_dimension",
        "batch_size",
        "optimizer_updates",
    ):
        if int(recipe.get(key, 0)) <= 0:
            raise ValueError(f"training recipe field must be positive: {key}")
    if int(recipe["n_action_steps"]) > int(recipe["chunk_size"]):
        raise ValueError("executed action steps cannot exceed the ACT chunk")
    if int(recipe["model_dimension"]) % int(recipe["attention_heads"]):
        raise ValueError("ACT model dimension must divide evenly across attention heads")
    resource = recipe.get("resource") or {}
    if resource.get("provider") != "local" and not resource.get("cleanup_required"):
        raise ValueError("non-local training resources require explicit cleanup")
    return recipe


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{number} is not an object")
        rows.append(value)
    return rows


def load_goal_act_dataset(receipt_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt_path = receipt_path.resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != DATASET_SCHEMA:
        raise ValueError("unsupported goal ACT dataset")
    unsigned = {key: value for key, value in receipt.items() if key != "dataset_sha256"}
    if receipt.get("dataset_sha256") != canonical_digest(unsigned):
        raise ValueError("goal ACT dataset receipt digest mismatch")
    if int(receipt.get("held_out_training_rows", -1)) != 0:
        raise ValueError("goal ACT dataset contains held-out training rows")
    if int(receipt.get("rejected_training_rows", -1)) != 0:
        raise ValueError("goal ACT dataset contains rejected training rows")
    preflight = receipt.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("goal ACT dataset lacks a flywheel preflight")
    if preflight.get("all_rows_bind_posterior_teacher_simulator") is not True:
        raise ValueError("goal ACT rows lack posterior/teacher/simulator lineage")
    if preflight.get("posterior_sampling_policy") != "identified_posterior_only":
        raise ValueError("goal ACT dataset used another posterior sampling policy")
    if preflight.get("arbitrary_domain_randomization") is not False:
        raise ValueError("goal ACT dataset used arbitrary domain randomization")
    if preflight.get("groot_policy_camera_ids") != ["overhead"]:
        raise ValueError("goal ACT sibling GR00T payload is not overhead-only")
    if preflight.get("wrist_main_policy_input") is not False:
        raise ValueError("wrist imagery entered the principal policy payload")
    generation_lineage_digest = _sha256_text(
        receipt.get("generation_lineage_digest"),
        "generation lineage identity",
    )
    payload = receipt["act_payload"]
    payload_path = receipt_path.parent / str(payload["path"])
    if not payload_path.is_file() or sha256_file(payload_path) != payload["sha256"]:
        raise ValueError("goal ACT training payload is missing or changed")
    rows = _read_jsonl(payload_path)
    if len(rows) != int(payload["row_count"]) or len(rows) != int(receipt["training_row_count"]):
        raise ValueError("goal ACT training row count changed")
    episode_ids = set(receipt["training_episode_ids"])
    for row in rows:
        if row.get("schema_version") != ROW_SCHEMA:
            raise ValueError("unsupported goal ACT dataset row")
        observation = np.asarray(row.get("observation"), dtype=np.float32)
        action = np.asarray(row.get("action_joint_target_rad"), dtype=np.float32)
        if observation.shape != (61,) or action.shape != (6,):
            raise ValueError("goal ACT dataset row has the wrong dimensions")
        if not np.isfinite(observation).all() or not np.isfinite(action).all():
            raise ValueError("goal ACT dataset row is non-finite")
        lineage = row.get("lineage") or {}
        if lineage.get("source_recording_id") not in episode_ids:
            raise ValueError("goal ACT row source is not in the admitted episode set")
        flywheel = (lineage.get("candidate") or {}).get("flywheel")
        if not isinstance(flywheel, dict):
            raise ValueError("goal ACT row lacks flywheel lineage")
        if flywheel.get("generation_lineage_digest") != generation_lineage_digest:
            raise ValueError("goal ACT row binds another generation lineage")
        for key in (
            "simulator_implementation_sha256",
            "source_action_trace_sha256",
            "evaluator_verdict_sha256",
        ):
            _sha256_text(flywheel.get(key), f"row {key}")
        for key in (
            "posterior_particle_id",
            "teacher_id",
            "teacher_action_owner",
            "simulator_id",
        ):
            if not str(flywheel.get(key) or ""):
                raise ValueError(f"goal ACT row lacks {key}")
    return receipt, rows


def _sha256_text(value: object, label: str) -> str:
    normalized = str(value or "")
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return normalized


def _normalization(observations: np.ndarray, actions: np.ndarray) -> dict[str, np.ndarray]:
    result = {
        "observation_mean": observations.mean(axis=0, dtype=np.float64).astype(np.float32),
        "observation_std": observations.std(axis=0, dtype=np.float64).astype(np.float32),
        "action_mean": actions.mean(axis=0, dtype=np.float64).astype(np.float32),
        "action_std": actions.std(axis=0, dtype=np.float64).astype(np.float32),
    }
    result["observation_std"] = np.maximum(result["observation_std"], 1e-4)
    result["action_std"] = np.maximum(result["action_std"], 1e-4)
    return result


def _windows(
    rows: list[dict[str, Any]],
    *,
    chunk_size: int,
    normalization: dict[str, np.ndarray],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    observations: list[np.ndarray] = []
    chunks: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        source_id = str(row["lineage"]["source_recording_id"])
        by_episode.setdefault(source_id, []).append(row)
    for episode_rows in by_episode.values():
        episode_rows.sort(key=lambda row: int(row["source_sample_index"]))
        indices = [int(row["source_sample_index"]) for row in episode_rows]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise ValueError("goal ACT episode rows are not contiguous")
        episode_observations = np.asarray([row["observation"] for row in episode_rows], dtype=np.float32)
        episode_actions = np.asarray([row["action_joint_target_rad"] for row in episode_rows], dtype=np.float32)
        episode_observations = (
            episode_observations - normalization["observation_mean"]
        ) / normalization["observation_std"]
        episode_actions = (
            episode_actions - normalization["action_mean"]
        ) / normalization["action_std"]
        for index in range(len(episode_rows)):
            available = min(chunk_size, len(episode_rows) - index)
            chunk = np.empty((chunk_size, 6), dtype=np.float32)
            chunk[:available] = episode_actions[index : index + available]
            chunk[available:] = episode_actions[-1]
            mask = np.ones(chunk_size, dtype=np.bool_)
            mask[:available] = False
            observations.append(episode_observations[index])
            chunks.append(chunk)
            masks.append(mask)
    return (
        torch.from_numpy(np.asarray(observations, dtype=np.float32)),
        torch.from_numpy(np.asarray(chunks, dtype=np.float32)),
        torch.from_numpy(np.asarray(masks, dtype=np.bool_)),
    )


def _device(name: str) -> torch.device:
    if name == "cpu":
        return torch.device("cpu")
    if name == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if name == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    raise ValueError(f"requested training device is unavailable: {name}")


def train_goal_act(
    *,
    dataset_receipt_path: Path,
    output_directory: Path,
    recipe_path: Path = REPO_ROOT / "configs/training/goal_act_recipe_v1.json",
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
    groot_challenger_declaration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Train one checkpoint from exactly one immutable LF-09 dataset receipt."""

    started_at = datetime.now(UTC).isoformat()
    dataset, rows = load_goal_act_dataset(dataset_receipt_path)
    groot_disposition = None
    if groot_challenger_declaration is not None:
        from .policy_flywheel import compile_groot_challenger_disposition

        groot_disposition = compile_groot_challenger_disposition(
            dataset, groot_challenger_declaration
        )
    task = load_act_pick_place_task_contract(task_contract_path)
    if dataset.get("task_id") != task["task_id"]:
        raise ValueError("dataset task identity differs from the trainer task")
    if dataset.get("task_contract_sha256") != task_contract_sha256(task_contract_path):
        raise ValueError("dataset task contract differs from the trainer task")
    recipe = load_goal_act_recipe(recipe_path)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"training output already exists: {output_directory}")
    output_directory.mkdir(parents=True)
    started = time.monotonic()
    torch.manual_seed(int(recipe["training_seed"]))
    np.random.seed(int(recipe["training_seed"]))
    device = _device(str(recipe["device"]))

    raw_observations = np.asarray([row["observation"] for row in rows], dtype=np.float32)
    raw_actions = np.asarray([row["action_joint_target_rad"] for row in rows], dtype=np.float32)
    normalization = _normalization(raw_observations, raw_actions)
    observations, action_chunks, masks = _windows(
        rows, chunk_size=int(recipe["chunk_size"]), normalization=normalization
    )
    observations = observations.to(device)
    action_chunks = action_chunks.to(device)
    masks = masks.to(device)
    model_config = ACTModelConfig(
        observation_dim=61,
        action_dim=6,
        chunk_size=int(recipe["chunk_size"]),
        model_dim=int(recipe["model_dimension"]),
        attention_heads=int(recipe["attention_heads"]),
        encoder_layers=int(recipe["encoder_layers"]),
        decoder_layers=int(recipe["decoder_layers"]),
        feedforward_dim=int(recipe["feedforward_dimension"]),
        latent_dim=int(recipe["latent_dimension"]),
        dropout=float(recipe["dropout"]),
    )
    model = ACTPolicy(model_config).to(device=device, dtype=torch.float32)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(recipe["learning_rate"]),
        weight_decay=float(recipe["weight_decay"]),
    )
    log_path = output_directory / "training_log.jsonl"
    log_rows: list[dict[str, Any]] = []
    updates = int(recipe["optimizer_updates"])
    batch_size = int(recipe["batch_size"])
    model.train()
    for update in range(1, updates + 1):
        if time.monotonic() - started > float(recipe["maximum_wall_seconds"]):
            raise TimeoutError("goal ACT training exceeded its declared wall-time budget")
        indices = torch.randint(0, observations.shape[0], (batch_size,), device=device)
        predicted, mean, log_variance = model(
            observations[indices], action_chunks[indices], masks[indices]
        )
        valid = (~masks[indices]).unsqueeze(-1)
        l1 = (torch.abs(predicted - action_chunks[indices]) * valid).sum() / (
            valid.sum() * action_chunks.shape[-1]
        )
        kl = -0.5 * torch.mean(
            1.0 + log_variance - mean.square() - log_variance.exp()
        )
        loss = l1 + float(recipe["kl_weight"]) * kl
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), float(recipe["gradient_clip_norm"]))
        optimizer.step()
        if update == 1 or update % int(recipe["checkpoint_interval_updates"]) == 0 or update == updates:
            log_rows.append(
                {
                    "update": update,
                    "loss": float(loss.detach().cpu()),
                    "l1_loss": float(l1.detach().cpu()),
                    "kl_loss": float(kl.detach().cpu()),
                    "elapsed_seconds": time.monotonic() - started,
                }
            )
    log_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in log_rows),
        encoding="utf-8",
    )

    checkpoint_payload = {
        "schema_version": CHECKPOINT_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(task_contract_path),
        "model_config": asdict(model_config),
        "model_state": {name: value.detach().cpu() for name, value in model.state_dict().items()},
        "normalization": {name: value.tolist() for name, value in normalization.items()},
        "training": {
            "dataset_sha256": dataset["dataset_sha256"],
            "dataset_receipt_sha256": sha256_file(dataset_receipt_path),
            "recipe_id": recipe["recipe_id"],
            "recipe_sha256": sha256_file(recipe_path),
            "seed": int(recipe["training_seed"]),
            "optimizer_updates": updates,
            "n_action_steps": int(recipe["n_action_steps"]),
            "final_loss": log_rows[-1]["loss"],
            "device": str(device),
            "dtype": "float32",
        },
    }
    temporary_checkpoint = output_directory / ".checkpoint.pt.tmp"
    checkpoint_path = output_directory / "checkpoint.pt"
    torch.save(checkpoint_payload, temporary_checkpoint)
    os.replace(temporary_checkpoint, checkpoint_path)
    elapsed = time.monotonic() - started
    unsigned = {
        "schema_version": TRAINING_RECEIPT_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(task_contract_path),
        "dataset_sha256": dataset["dataset_sha256"],
        "dataset_receipt_path": str(dataset_receipt_path.resolve()),
        "dataset_receipt_sha256": sha256_file(dataset_receipt_path),
        "recipe_id": recipe["recipe_id"],
        "recipe_sha256": sha256_file(recipe_path),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_log_path": str(log_path),
        "training_log_sha256": sha256_file(log_path),
        "row_count": len(rows),
        "episode_count": len(dataset["training_episode_ids"]),
        "optimizer_updates": updates,
        "final_loss": log_rows[-1]["loss"],
        "elapsed_seconds": elapsed,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "device": str(device),
            "dtype": "float32",
        },
        "resource_closeout": {
            "provider": recipe["resource"]["provider"],
            "paid_compute": bool(recipe["resource"]["paid_compute"]),
            "cleanup_required": bool(recipe["resource"]["cleanup_required"]),
            "cleanup_complete": not bool(recipe["resource"]["cleanup_required"]),
        },
        "training_can_promote": False,
        "groot_challenger": groot_disposition,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "training_receipt.json", receipt)
    return receipt
