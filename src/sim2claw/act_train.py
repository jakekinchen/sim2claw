"""Local synthetic-data training for the frozen chess-rook ACT task."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .act_model import ACTModelConfig, ACTPolicy
from .chess_task import (
    ExpertEpisode,
    collect_expert_episode,
    load_task_contract,
    task_contract_sha256,
)
from .paths import DEFAULT_OUTPUT_ROOT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _training_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _normalization(
    episodes: list[ExpertEpisode],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    observations = np.concatenate([episode.observations for episode in episodes])
    actions = np.concatenate([episode.actions for episode in episodes])
    observation_mean = observations.mean(axis=0, dtype=np.float64).astype(np.float32)
    observation_std = observations.std(axis=0, dtype=np.float64).astype(np.float32)
    action_mean = actions.mean(axis=0, dtype=np.float64).astype(np.float32)
    action_std = actions.std(axis=0, dtype=np.float64).astype(np.float32)
    observation_std = np.maximum(observation_std, 1e-4)
    action_std = np.maximum(action_std, 1e-4)
    return observation_mean, observation_std, action_mean, action_std


def _windows(
    episodes: list[ExpertEpisode],
    *,
    chunk_size: int,
    observation_mean: np.ndarray,
    observation_std: np.ndarray,
    action_mean: np.ndarray,
    action_std: np.ndarray,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    observations: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    for episode in episodes:
        normalized_observations = (
            episode.observations - observation_mean
        ) / observation_std
        normalized_actions = (episode.actions - action_mean) / action_std
        for index in range(len(episode.actions)):
            available = min(chunk_size, len(episode.actions) - index)
            chunk = np.zeros((chunk_size, episode.actions.shape[1]), dtype=np.float32)
            chunk[:available] = normalized_actions[index : index + available]
            if available < chunk_size:
                chunk[available:] = normalized_actions[-1]
            mask = np.ones(chunk_size, dtype=np.bool_)
            mask[:available] = False
            observations.append(normalized_observations[index])
            actions.append(chunk)
            masks.append(mask)
    return (
        torch.from_numpy(np.asarray(observations, dtype=np.float32)),
        torch.from_numpy(np.asarray(actions, dtype=np.float32)),
        torch.from_numpy(np.asarray(masks, dtype=np.bool_)),
    )


def train_act(
    *,
    output_directory: Path | None = None,
) -> dict[str, Any]:
    task = load_task_contract()
    act = task["act"]
    output = output_directory or DEFAULT_OUTPUT_ROOT / "act" / task["task_id"]
    output.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(int(act["training_seed"]))
    np.random.seed(int(act["training_seed"]))
    device = _training_device()
    started = time.monotonic()

    episodes: list[ExpertEpisode] = []
    for seed, offset in zip(
        task["training_split"]["seeds"],
        task["training_split"]["piece_planar_offsets_m"],
        strict=True,
    ):
        episode = collect_expert_episode(
            task,
            seed=int(seed),
            piece_offset_xy_m=(float(offset[0]), float(offset[1])),
        )
        if (
            episode.maximum_piece_rise_m < task["evaluator"]["minimum_piece_rise_m"]
            or episode.final_piece_height_m - episode.initial_piece_height_m
            < task["evaluator"]["minimum_final_piece_rise_m"]
        ):
            raise RuntimeError(f"training expert episode {seed} failed dataset admission")
        episodes.append(episode)

    observation_mean, observation_std, action_mean, action_std = _normalization(
        episodes
    )
    observations, action_chunks, padding_masks = _windows(
        episodes,
        chunk_size=int(act["chunk_size"]),
        observation_mean=observation_mean,
        observation_std=observation_std,
        action_mean=action_mean,
        action_std=action_std,
    )
    observations = observations.to(device)
    action_chunks = action_chunks.to(device)
    padding_masks = padding_masks.to(device)

    model_config = ACTModelConfig.from_task(task)
    model = ACTPolicy(model_config).to(device=device, dtype=torch.float32)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(act["learning_rate"]),
        weight_decay=float(act["weight_decay"]),
    )
    action_weights = torch.ones(model_config.action_dim, device=device)
    action_weights[-1] = float(act["gripper_l1_weight"])
    updates = int(act["optimizer_updates"])
    batch_size = int(act["batch_size"])
    # Keep this first local policy fit deterministic enough to reproduce the
    # narrow scripted task before adding robustness noise in later recipes.
    state_noise_std = 0.0
    state_dropout_probability = 0.0
    losses: list[float] = []
    l1_losses: list[float] = []
    kl_losses: list[float] = []
    model.train()
    for update in range(1, updates + 1):
        indices = torch.randint(
            0, observations.shape[0], (batch_size,), device=device
        )
        observation_batch = observations[indices].clone()
        action_batch = action_chunks[indices]
        mask_batch = padding_masks[indices]
        progress_features = int(
            task["observation"]["unperturbed_progress_feature_dimension"]
        )
        state_features = observation_batch[:, :-progress_features]
        state_features.add_(
            torch.randn_like(state_features)
            * state_noise_std
        )
        drop_state = torch.rand(batch_size, device=device) < state_dropout_probability
        state_features[drop_state] = 0.0
        predicted, mean, log_variance = model(
            observation_batch, action_batch, mask_batch
        )
        valid = (~mask_batch).unsqueeze(-1)
        weighted_error = torch.abs(predicted - action_batch) * action_weights
        l1 = (weighted_error * valid).sum() / (
            valid.sum() * action_weights.sum()
        )
        kl = -0.5 * torch.mean(1.0 + log_variance - mean.square() - log_variance.exp())
        loss = l1 + float(act["kl_weight"]) * kl
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
        l1_losses.append(float(l1.detach().cpu()))
        kl_losses.append(float(kl.detach().cpu()))
        if update == 1 or update % 200 == 0 or update == updates:
            print(
                f"ACT update {update:04d}/{updates}: "
                f"loss={losses[-1]:.6f} l1={l1_losses[-1]:.6f} "
                f"kl={kl_losses[-1]:.6f}",
                flush=True,
            )

    checkpoint_path = output / "checkpoint.pt"
    checkpoint_payload = {
        "schema_version": "sim2claw.act_checkpoint.v1",
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(),
        "model_config": asdict(model_config),
        "model_state": {
            name: tensor.detach().cpu() for name, tensor in model.state_dict().items()
        },
        "normalization": {
            "observation_mean": observation_mean.tolist(),
            "observation_std": observation_std.tolist(),
            "action_mean": action_mean.tolist(),
            "action_std": action_std.tolist(),
        },
        "training": {
            "seed": int(act["training_seed"]),
            "optimizer_updates": updates,
            "final_loss": losses[-1],
            "final_l1_loss": l1_losses[-1],
            "final_kl_loss": kl_losses[-1],
            "device": str(device),
            "dtype": "float32",
        },
    }
    torch.save(checkpoint_payload, checkpoint_path)
    checkpoint_sha256 = _sha256_file(checkpoint_path)

    receipt = {
        "schema_version": "sim2claw.act_training_receipt.v1",
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(),
        "proof_class": "simulation_synthetic_expert_training",
        "dataset": {
            "episode_count": len(episodes),
            "frame_count": int(sum(len(item.actions) for item in episodes)),
            "window_count": int(observations.shape[0]),
            "held_out_seed_rows": 0,
            "episodes": [
                {
                    "seed": item.seed,
                    "piece_offset_xy_m": list(item.piece_offset_xy_m),
                    "maximum_piece_rise_m": item.maximum_piece_rise_m,
                    "final_piece_rise_m": (
                        item.final_piece_height_m - item.initial_piece_height_m
                    ),
                }
                for item in episodes
            ],
        },
        "model": {
            "architecture": act["architecture"],
            "parameter_count": int(sum(value.numel() for value in model.parameters())),
            "chunk_size": model_config.chunk_size,
            "n_obs_steps": 1,
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": checkpoint_sha256,
        },
        "optimization": {
            "recipe_revision": task["recipe_revision"],
            "optimizer": act["optimizer"],
            "updates": updates,
            "batch_size": batch_size,
            "learning_rate": act["learning_rate"],
            "final_loss": losses[-1],
            "final_l1_loss": l1_losses[-1],
            "final_kl_loss": kl_losses[-1],
            "last_100_mean_loss": float(np.mean(losses[-100:])),
            "normalized_state_noise_std": state_noise_std,
            "state_feature_dropout_probability": state_dropout_probability,
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "training_device": str(device),
            "elapsed_seconds": time.monotonic() - started,
        },
        "training_promoted_checkpoint": False,
        "evaluation_required": True,
        "physical_authority": False,
        "brev_compute_started": False,
    }
    receipt_path = output / "training_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt["receipt"] = str(receipt_path)
    return receipt
