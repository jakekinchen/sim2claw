#!/usr/bin/env python3
"""Audit whether row-zero evidence justifies a visual-unfreeze challenger."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seed_paths(values: list[str], label: str) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for value in values:
        try:
            seed_text, path_text = value.split("=", 1)
            seed = int(seed_text)
        except ValueError as error:
            raise ValueError(f"{label} must use SEED=PATH: {value}") from error
        if seed in result:
            raise ValueError(f"duplicate {label} seed: {seed}")
        result[seed] = Path(path_text)
    if len(result) < 2:
        raise ValueError(f"{label} needs at least two seeds")
    return result


def _rollout_action(path: Path) -> np.ndarray:
    with np.load(path, allow_pickle=False) as payload:
        return np.asarray(payload["actions"][0], dtype=np.float32)


def _probe_action(path: Path) -> np.ndarray:
    payload = json.loads(path.read_text())
    if not payload.get("repeatable"):
        raise ValueError(f"probe is not repeatable: {path}")
    return np.asarray(payload["probes"][0]["first_action"], dtype=np.float32)


def _cluster(actions: dict[int, np.ndarray], expert: np.ndarray) -> dict[str, object]:
    seeds = sorted(actions)
    stack = np.stack([actions[seed] for seed in seeds])
    centroid = np.mean(stack, axis=0)
    pairwise = [
        float(np.linalg.norm(actions[left] - actions[right]))
        for left, right in itertools.combinations(seeds, 2)
    ]
    per_seed = {
        str(seed): {
            "first_action": actions[seed].tolist(),
            "l2_to_expert": float(np.linalg.norm(actions[seed] - expert)),
            "mae_to_expert": float(np.mean(np.abs(actions[seed] - expert))),
        }
        for seed in seeds
    }
    centroid_l2 = float(np.linalg.norm(centroid - expert))
    max_pair_l2 = max(pairwise)
    return {
        "seeds": seeds,
        "per_seed": per_seed,
        "centroid": centroid.tolist(),
        "centroid_l2_to_expert": centroid_l2,
        "mean_seed_l2_to_centroid": float(
            np.mean(np.linalg.norm(stack - centroid, axis=1))
        ),
        "maximum_pairwise_l2": max_pair_l2,
        "centroid_bias_to_maximum_pairwise_ratio": centroid_l2 / max_pair_l2,
        "median_mae_to_expert": float(
            np.median([row["mae_to_expert"] for row in per_seed.values()])
        ),
        "per_dimension_standard_deviation": np.std(stack, axis=0).tolist(),
    }


def _frame_delta(left: np.ndarray, right: np.ndarray) -> dict[str, object]:
    if left.shape != right.shape:
        raise ValueError(f"frame shape mismatch: {left.shape} != {right.shape}")
    delta = left.astype(np.float64) - right.astype(np.float64)
    mse = float(np.mean(np.square(delta)))
    return {
        "mae": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(mse)),
        "psnr_db": float(20.0 * np.log10(255.0 / np.sqrt(mse))) if mse else None,
        "maximum_absolute_delta": float(np.max(np.abs(delta))),
        "pixels_changed": int(np.any(delta != 0, axis=-1).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expert-parquet", type=Path, required=True)
    parser.add_argument(
        "--fresh-rollout", action="append", default=[], metavar="SEED=PATH"
    )
    parser.add_argument(
        "--dataset-probe", action="append", default=[], metavar="SEED=PATH"
    )
    parser.add_argument("--fresh-frame", type=Path, required=True)
    parser.add_argument("--dataset-frame", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    fresh_paths = _seed_paths(args.fresh_rollout, "--fresh-rollout")
    dataset_paths = _seed_paths(args.dataset_probe, "--dataset-probe")
    if set(fresh_paths) != set(dataset_paths):
        parser.error("fresh rollout and dataset probe seeds must match")

    table = pq.read_table(args.expert_parquet, columns=["action"])
    expert = np.asarray(
        table["action"].combine_chunks().to_pylist()[0], dtype=np.float32
    )
    fresh = _cluster(
        {seed: _rollout_action(path) for seed, path in fresh_paths.items()}, expert
    )
    dataset = _cluster(
        {seed: _probe_action(path) for seed, path in dataset_paths.items()}, expert
    )

    # A tight-but-biased cluster must be at least twice as far from the expert
    # as its widest seed-to-seed separation. Dataset pixels must strictly
    # improve median row-zero MAE. These conservative diagnostic gates cannot
    # promote a model; they only decide whether training is justified.
    gate_a = bool(
        fresh["maximum_pairwise_l2"]
        <= 0.5 * fresh["centroid_l2_to_expert"]
    )
    gate_b = bool(dataset["median_mae_to_expert"] < fresh["median_mae_to_expert"])

    sources = [
        args.expert_parquet,
        args.fresh_frame,
        args.dataset_frame,
        *fresh_paths.values(),
        *dataset_paths.values(),
    ]
    result = {
        "schema_version": "sim2claw.groot_n17_perception_gate.v1",
        "proof_class": "learned_policy_simulation_diagnostic",
        "promotion_authority": False,
        "expert_first_action": expert.tolist(),
        "fresh_render": fresh,
        "dataset_frame": dataset,
        "frame_delta": _frame_delta(
            np.load(args.dataset_frame, allow_pickle=False),
            np.load(args.fresh_frame, allow_pickle=False),
        ),
        "gates": {
            "a_tight_but_biased": gate_a,
            "a_rule": "maximum_pairwise_l2 <= 0.5 * centroid_l2_to_expert",
            "b_dataset_pixels_improve_median_mae": gate_b,
            "b_rule": "dataset median row-zero MAE < fresh-render median row-zero MAE",
            "visual_unfreeze_challenger_justified": gate_a and gate_b,
        },
        "input_sha256": {str(path.resolve()): _sha256(path) for path in sources},
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
