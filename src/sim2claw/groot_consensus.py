"""Deterministic aggregation helpers for model-derived GR00T action chunks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


CONSENSUS_SCHEMA_VERSION = "sim2claw.groot_n17.action_consensus.v1"
AGGREGATION_METHODS = frozenset({"mean", "median", "medoid", "trimmed_mean"})


def query_seed(episode_seed: int, sample_step: int) -> int:
    """Preserve the original evaluator-owned per-query seed identity."""

    if episode_seed < 0 or sample_step < 0:
        raise ValueError("episode_seed and sample_step must be non-negative")
    payload = (
        f"sim2claw.groot_n17.query_seed.v1:{episode_seed}:{sample_step}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def proposal_seed(episode_seed: int, sample_step: int, proposal_index: int) -> int:
    """Derive a deterministic proposal seed while retaining baseline proposal 0."""

    if proposal_index < 0:
        raise ValueError("proposal_index must be non-negative")
    if proposal_index == 0:
        return query_seed(episode_seed, sample_step)
    payload = (
        "sim2claw.groot_n17.proposal_seed.v1:"
        f"{episode_seed}:{sample_step}:{proposal_index}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _normalized_proposals(
    proposals: Sequence[Mapping[str, np.ndarray]],
) -> tuple[list[str], list[dict[str, np.ndarray]]]:
    if not proposals:
        raise ValueError("at least one action proposal is required")
    keys = sorted(str(key) for key in proposals[0])
    if not keys:
        raise ValueError("action proposals cannot be empty")
    normalized: list[dict[str, np.ndarray]] = []
    reference_shapes: dict[str, tuple[int, ...]] = {}
    for index, proposal in enumerate(proposals):
        if sorted(str(key) for key in proposal) != keys:
            raise ValueError(f"proposal {index} action keys do not match")
        row: dict[str, np.ndarray] = {}
        for key in keys:
            value = np.asarray(proposal[key])
            if not np.issubdtype(value.dtype, np.floating):
                raise ValueError(f"proposal {index} action {key} is not floating point")
            if not np.isfinite(value).all():
                raise ValueError(f"proposal {index} action {key} is non-finite")
            if index == 0:
                reference_shapes[key] = value.shape
            elif value.shape != reference_shapes[key]:
                raise ValueError(f"proposal {index} action {key} shape does not match")
            row[key] = value
        normalized.append(row)
    return keys, normalized


def action_sha256(action: Mapping[str, np.ndarray]) -> str:
    """Hash an action dictionary without relying on mapping insertion order."""

    digest = hashlib.sha256()
    for key in sorted(action):
        value = np.ascontiguousarray(action[key])
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.dtype.str.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(value.shape).encode("ascii"))
        digest.update(b"\0")
        digest.update(value.tobytes())
    return digest.hexdigest()


def aggregate_action_proposals(
    proposals: Sequence[Mapping[str, np.ndarray]],
    *,
    method: str,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Aggregate complete model proposals and return JSON-safe diagnostics."""

    if method not in AGGREGATION_METHODS:
        raise ValueError(f"unsupported action aggregation method: {method}")
    keys, normalized = _normalized_proposals(proposals)
    proposal_count = len(normalized)
    flattened = np.stack(
        [
            np.concatenate([row[key].astype(np.float64).ravel() for key in keys])
            for row in normalized
        ]
    )
    pairwise = np.linalg.norm(flattened[:, None, :] - flattened[None, :, :], axis=-1)
    upper_triangle = pairwise[np.triu_indices(proposal_count, k=1)]
    selected_index: int | None = None

    if method == "medoid":
        selected_index = int(np.argmin(np.sum(pairwise, axis=1)))
        aggregate = {
            key: normalized[selected_index][key].copy()
            for key in keys
        }
    else:
        aggregate = {}
        for key in keys:
            stack = np.stack([row[key] for row in normalized]).astype(np.float64)
            if method == "mean":
                value = np.mean(stack, axis=0)
            elif method == "median":
                value = np.median(stack, axis=0)
            else:
                if proposal_count < 5:
                    raise ValueError("trimmed_mean requires at least five proposals")
                trim_count = max(1, proposal_count // 5)
                if 2 * trim_count >= proposal_count:
                    raise ValueError("trimmed_mean removed every proposal")
                value = np.mean(
                    np.sort(stack, axis=0)[trim_count:-trim_count],
                    axis=0,
                )
            aggregate[key] = value.astype(normalized[0][key].dtype)

    diagnostics: dict[str, Any] = {
        "schema_version": CONSENSUS_SCHEMA_VERSION,
        "method": method,
        "proposal_count": proposal_count,
        "proposal_action_sha256": [action_sha256(row) for row in normalized],
        "aggregate_action_sha256": action_sha256(aggregate),
        "selected_proposal_index": selected_index,
        "mean_pairwise_l2": (
            float(np.mean(upper_triangle)) if len(upper_triangle) else 0.0
        ),
        "maximum_pairwise_l2": (
            float(np.max(upper_triangle)) if len(upper_triangle) else 0.0
        ),
    }
    return aggregate, diagnostics
