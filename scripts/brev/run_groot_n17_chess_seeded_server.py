#!/usr/bin/env python3
"""Serve a GR00T checkpoint with evaluator-controlled per-episode RNG resets."""

from __future__ import annotations

import argparse
import hashlib
import random
from contextlib import contextmanager
from collections.abc import Iterator

import numpy as np
import torch

from gr00t.data.types import ModalityConfig
from gr00t.policy.gr00t_policy import Gr00tPolicy
from gr00t.policy.policy import BasePolicy, PolicyWrapper
from gr00t.policy.server_client import PolicyServer
from sim2claw.groot_consensus import (
    AGGREGATION_METHODS,
    aggregate_action_proposals,
    proposal_seed,
    query_seed,
)


def seed_policy_rng(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def policy_rng_snapshot() -> dict[str, object]:
    """Return hashes of every evaluator-visible Torch RNG stream."""

    cpu_state = torch.random.get_rng_state().cpu().numpy().tobytes()
    cuda_states = (
        torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []
    )
    return {
        "cpu_sha256": hashlib.sha256(cpu_state).hexdigest(),
        "cuda_sha256": [
            hashlib.sha256(state.cpu().numpy().tobytes()).hexdigest()
            for state in cuda_states
        ],
    }


@contextmanager
def scaled_torch_randn(noise_scale: float) -> Iterator[None]:
    """Scale the flow sampler's global ``torch.randn`` input for one call."""

    if not 0.0 <= noise_scale <= 1.0:
        raise ValueError("noise_scale must be between 0 and 1")
    if noise_scale == 1.0:
        yield
        return
    original_randn = torch.randn

    def scaled_randn(*args: object, **kwargs: object) -> torch.Tensor:
        return original_randn(*args, **kwargs) * noise_scale

    torch.randn = scaled_randn  # type: ignore[assignment]
    try:
        yield
    finally:
        torch.randn = original_randn  # type: ignore[assignment]


class SeededResetPolicy(PolicyWrapper):
    """Run deterministic model-only proposals and aggregate complete chunks."""

    def __init__(
        self,
        policy: BasePolicy,
        *,
        proposal_count: int,
        aggregation: str,
        noise_scale: float,
    ) -> None:
        super().__init__(policy, strict=False)
        if proposal_count < 1:
            raise ValueError("proposal_count must be positive")
        if aggregation not in AGGREGATION_METHODS:
            raise ValueError(f"unsupported aggregation method: {aggregation}")
        if aggregation == "trimmed_mean" and proposal_count < 5:
            raise ValueError("trimmed_mean requires at least five proposals")
        if not 0.0 <= noise_scale <= 1.0:
            raise ValueError("noise_scale must be between 0 and 1")
        self._episode_seed: int | None = None
        self._proposal_count = proposal_count
        self._aggregation = aggregation
        self._noise_scale = noise_scale

    @staticmethod
    def _query_seed(episode_seed: int, sample_step: int) -> int:
        return query_seed(episode_seed, sample_step)

    def check_observation(self, observation: dict[str, object]) -> None:
        self.policy.check_observation(observation)

    def check_action(self, action: dict[str, object]) -> None:
        self.policy.check_action(action)

    def _get_action(
        self,
        observation: dict[str, object],
        options: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if self._episode_seed is None:
            raise RuntimeError("seeded GR00T server requires reset before get_action")
        if options is None or "sample_step" not in options:
            raise ValueError("seeded GR00T get_action requires sample_step")
        sample_step = int(options["sample_step"])
        if sample_step < 0:
            raise ValueError("sample_step must be non-negative")
        root_query_seed = self._query_seed(self._episode_seed, sample_step)
        proposals: list[dict[str, np.ndarray]] = []
        delegated_infos: list[dict[str, object]] = []
        proposal_rng: list[dict[str, object]] = []
        seeds: list[int] = []
        for proposal_index in range(self._proposal_count):
            seed = proposal_seed(
                self._episode_seed,
                sample_step,
                proposal_index,
            )
            seeds.append(seed)
            seed_policy_rng(seed)
            rng_before = policy_rng_snapshot()
            with scaled_torch_randn(self._noise_scale):
                action, delegated_info = self.policy.get_action(observation, options)
            proposals.append(
                {key: np.asarray(value) for key, value in action.items()}
            )
            delegated_infos.append(dict(delegated_info))
            proposal_rng.append(
                {
                    "proposal_index": proposal_index,
                    "proposal_seed": seed,
                    "rng_before": rng_before,
                    "rng_after": policy_rng_snapshot(),
                }
            )
        aggregate, consensus = aggregate_action_proposals(
            proposals,
            method=self._aggregation,
        )
        selected_index = consensus["selected_proposal_index"]
        info_index = int(selected_index) if selected_index is not None else 0
        info = dict(delegated_infos[info_index])
        info.update(
            {
                "consensus": consensus,
                "noise_scale": self._noise_scale,
                "proposal_rng": proposal_rng,
                "proposal_seeds": seeds,
                "rng_after": policy_rng_snapshot(),
                "sample_step": sample_step,
                "query_seed": root_query_seed,
            }
        )
        return aggregate, info

    def get_modality_config(self) -> dict[str, ModalityConfig]:
        return self.policy.get_modality_config()

    def reset(self, options: dict[str, object] | None = None) -> dict[str, object]:
        if options is None or "inference_seed" not in options:
            raise ValueError("seeded GR00T server reset requires inference_seed")
        seed = int(options["inference_seed"])
        if seed < 0:
            raise ValueError("inference_seed must be non-negative")
        self._episode_seed = seed
        seed_policy_rng(seed)
        info = dict(self.policy.reset(options))
        info.update(
            {
                "action_aggregation": self._aggregation,
                "inference_seed": seed,
                "noise_scale": self._noise_scale,
                "proposal_count": self._proposal_count,
                "rng_reset": True,
                "rng_after_reset": policy_rng_snapshot(),
            }
        )
        return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--embodiment-tag", default="new_embodiment")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--proposal-count", type=int, default=1)
    parser.add_argument(
        "--action-aggregation",
        choices=sorted(AGGREGATION_METHODS),
        default="medoid",
    )
    parser.add_argument("--noise-scale", type=float, default=1.0)
    args = parser.parse_args()
    if args.proposal_count < 1:
        parser.error("--proposal-count must be positive")
    if args.action_aggregation == "trimmed_mean" and args.proposal_count < 5:
        parser.error("trimmed_mean requires --proposal-count of at least 5")
    if not 0.0 <= args.noise_scale <= 1.0:
        parser.error("--noise-scale must be between 0 and 1")

    seed_policy_rng(0)
    policy = Gr00tPolicy(
        embodiment_tag=args.embodiment_tag,
        model_path=args.model_path,
        device=args.device,
        strict=False,
    )
    server = PolicyServer(
        policy=SeededResetPolicy(
            policy,
            proposal_count=args.proposal_count,
            aggregation=args.action_aggregation,
            noise_scale=args.noise_scale,
        ),
        host=args.host,
        port=args.port,
    )
    print(f"Seeded-reset GR00T server ready on {args.host}:{args.port}")
    server.run()


if __name__ == "__main__":
    main()
