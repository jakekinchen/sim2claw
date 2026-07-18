#!/usr/bin/env python3
"""Serve a GR00T checkpoint with evaluator-controlled per-episode RNG resets."""

from __future__ import annotations

import argparse
import hashlib
import random

import numpy as np
import torch

from gr00t.data.types import ModalityConfig
from gr00t.policy.gr00t_policy import Gr00tPolicy
from gr00t.policy.policy import BasePolicy, PolicyWrapper
from gr00t.policy.server_client import PolicyServer


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


class SeededResetPolicy(PolicyWrapper):
    """Delegate GR00T inference while making reset seed the flow sampler."""

    def __init__(self, policy: BasePolicy) -> None:
        super().__init__(policy, strict=False)
        self._episode_seed: int | None = None

    @staticmethod
    def _query_seed(episode_seed: int, sample_step: int) -> int:
        payload = (
            f"sim2claw.groot_n17.query_seed.v1:{episode_seed}:{sample_step}"
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")

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
        query_seed = self._query_seed(self._episode_seed, sample_step)
        seed_policy_rng(query_seed)
        rng_before = policy_rng_snapshot()
        action, delegated_info = self.policy.get_action(observation, options)
        info = dict(delegated_info)
        info.update(
            {
                "rng_before": rng_before,
                "rng_after": policy_rng_snapshot(),
                "sample_step": sample_step,
                "query_seed": query_seed,
            }
        )
        return action, info

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
                "inference_seed": seed,
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
    args = parser.parse_args()

    seed_policy_rng(0)
    policy = Gr00tPolicy(
        embodiment_tag=args.embodiment_tag,
        model_path=args.model_path,
        device=args.device,
        strict=False,
    )
    server = PolicyServer(
        policy=SeededResetPolicy(policy),
        host=args.host,
        port=args.port,
    )
    print(f"Seeded-reset GR00T server ready on {args.host}:{args.port}")
    server.run()


if __name__ == "__main__":
    main()
