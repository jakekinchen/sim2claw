"""Fresh, state-based ACT model used by the frozen chess-rook task."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn


@dataclass(frozen=True)
class ACTModelConfig:
    observation_dim: int
    action_dim: int
    chunk_size: int
    model_dim: int
    attention_heads: int
    encoder_layers: int
    decoder_layers: int
    feedforward_dim: int
    latent_dim: int
    dropout: float

    @classmethod
    def from_task(cls, task: dict[str, Any]) -> "ACTModelConfig":
        act = task["act"]
        return cls(
            observation_dim=int(task["observation"]["dimension"]),
            action_dim=int(task["action"]["dimension"]),
            chunk_size=int(act["chunk_size"]),
            model_dim=int(act["model_dimension"]),
            attention_heads=int(act["attention_heads"]),
            encoder_layers=int(act["encoder_layers"]),
            decoder_layers=int(act["decoder_layers"]),
            feedforward_dim=int(act["feedforward_dimension"]),
            latent_dim=int(act["latent_dimension"]),
            dropout=float(act["dropout"]),
        )


class ACTPolicy(nn.Module):
    """Conditional-VAE Action Chunking Transformer.

    The encoder observes the current state and demonstrated future action chunk
    during training. The decoder predicts the whole chunk in parallel. At
    inference the latent is fixed to zero, matching the ACT convention.
    """

    def __init__(self, config: ACTModelConfig) -> None:
        super().__init__()
        self.config = config
        dim = config.model_dim
        self.observation_projection = nn.Linear(config.observation_dim, dim)
        self.action_projection = nn.Linear(config.action_dim, dim)
        self.encoder_class_token = nn.Parameter(torch.zeros(1, 1, dim))
        self.encoder_positions = nn.Parameter(
            torch.zeros(1, config.chunk_size + 2, dim)
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=dim,
            nhead=config.attention_heads,
            dim_feedforward=config.feedforward_dim,
            dropout=config.dropout,
            activation="relu",
            batch_first=True,
            norm_first=True,
        )
        self.vae_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=config.encoder_layers,
            enable_nested_tensor=False,
        )
        self.latent_parameters = nn.Linear(dim, config.latent_dim * 2)
        self.latent_projection = nn.Linear(config.latent_dim, dim)
        self.decoder_queries = nn.Parameter(
            torch.zeros(1, config.chunk_size, dim)
        )
        self.decoder_positions = nn.Parameter(
            torch.zeros(1, config.chunk_size, dim)
        )
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=dim,
            nhead=config.attention_heads,
            dim_feedforward=config.feedforward_dim,
            dropout=config.dropout,
            activation="relu",
            batch_first=True,
            norm_first=True,
        )
        self.action_decoder = nn.TransformerDecoder(
            decoder_layer, num_layers=config.decoder_layers
        )
        self.action_head = nn.Linear(dim, config.action_dim)
        self._reset_parameters()

    def _reset_parameters(self) -> None:
        nn.init.normal_(self.encoder_class_token, std=0.02)
        nn.init.normal_(self.encoder_positions, std=0.02)
        nn.init.normal_(self.decoder_queries, std=0.02)
        nn.init.normal_(self.decoder_positions, std=0.02)

    def forward(
        self,
        observation: torch.Tensor,
        demonstrated_actions: torch.Tensor | None = None,
        action_padding_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if observation.ndim != 2:
            raise ValueError("ACT observation must have shape [batch, features]")
        batch = observation.shape[0]
        observation_token = self.observation_projection(observation).unsqueeze(1)
        if demonstrated_actions is None:
            mean = torch.zeros(
                batch,
                self.config.latent_dim,
                device=observation.device,
                dtype=observation.dtype,
            )
            log_variance = torch.zeros_like(mean)
            latent = mean
        else:
            if demonstrated_actions.shape[1:] != (
                self.config.chunk_size,
                self.config.action_dim,
            ):
                raise ValueError("ACT demonstrated action chunk shape drifted")
            class_token = self.encoder_class_token.expand(batch, -1, -1)
            encoded_actions = self.action_projection(demonstrated_actions)
            encoder_input = torch.cat(
                [class_token, observation_token, encoded_actions], dim=1
            )
            encoder_input = encoder_input + self.encoder_positions
            encoder_mask = None
            if action_padding_mask is not None:
                prefix = torch.zeros(
                    batch,
                    2,
                    dtype=torch.bool,
                    device=action_padding_mask.device,
                )
                encoder_mask = torch.cat([prefix, action_padding_mask], dim=1)
            encoded = self.vae_encoder(
                encoder_input, src_key_padding_mask=encoder_mask
            )
            mean, log_variance = self.latent_parameters(encoded[:, 0]).chunk(2, dim=-1)
            standard_deviation = torch.exp(0.5 * log_variance)
            latent = mean + standard_deviation * torch.randn_like(standard_deviation)

        memory = torch.cat(
            [observation_token, self.latent_projection(latent).unsqueeze(1)], dim=1
        )
        queries = self.decoder_queries.expand(batch, -1, -1)
        queries = queries + self.decoder_positions
        decoded = self.action_decoder(queries, memory)
        return self.action_head(decoded), mean, log_variance

    @torch.inference_mode()
    def predict_action_chunk(self, observation: torch.Tensor) -> torch.Tensor:
        self.eval()
        actions, _, _ = self(observation)
        return actions


def load_act_checkpoint(
    checkpoint_path: Path, *, device: torch.device
) -> tuple[ACTPolicy, dict[str, torch.Tensor], dict[str, Any]]:
    payload = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if payload.get("schema_version") != "sim2claw.act_checkpoint.v1":
        raise ValueError("unsupported sim2claw ACT checkpoint")
    config = ACTModelConfig(**payload["model_config"])
    model = ACTPolicy(config).to(device=device, dtype=torch.float32)
    model.load_state_dict(payload["model_state"])
    model.eval()
    statistics = {
        name: torch.as_tensor(values, dtype=torch.float32, device=device)
        for name, values in payload["normalization"].items()
    }
    return model, statistics, payload
