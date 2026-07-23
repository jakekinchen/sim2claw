"""Canonical generated-state paths and transactional evidence operations."""

from __future__ import annotations

from pathlib import Path

from ..learning_factory_artifacts import canonical_digest
from .contracts import REPO_ROOT
from .live_evidence import (
    EvidenceAdmissionError,
    commit_prepared_state,
    json_artifact_sha256,
    locked_campaign_state,
    prepare_admitted_result,
    validate_campaign_state,
)
from .live_types import (
    CANONICAL_STATE_ROOT,
    STATE_KEY_SCHEMA,
    LiveCampaignContract,
    LiveOperatorError,
)


def _relative_config_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_repo_relative_path(
    value: str, *, repo_root: Path, label: str
) -> Path:
    raw = Path(value)
    if raw.is_absolute() or not value or raw.as_posix() != value or ".." in raw.parts:
        raise LiveOperatorError(f"{label} is not a canonical repository-relative path")
    root = repo_root.resolve()
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise LiveOperatorError(f"{label} escaped the repository") from error
    return resolved


def resolve_live_campaign_state_path(
    contract: LiveCampaignContract, *, repo_root: Path = REPO_ROOT
) -> Path:
    """Return the one generated state path for a campaign/config identity."""

    persistent_state = contract.payload["persistent_state"]
    root = _resolve_repo_relative_path(
        str(persistent_state["repo_relative_root"]),
        repo_root=repo_root,
        label="persistent state root",
    )
    if root != (repo_root.resolve() / CANONICAL_STATE_ROOT).resolve():
        raise LiveOperatorError("persistent state root is not the canonical generated root")
    key = canonical_digest(
        {
            "schema_version": STATE_KEY_SCHEMA,
            "campaign_id": contract.campaign_id,
            "config_digest": contract.config_digest,
        }
    )
    return root / key / "campaign_state.json"

__all__ = [
    "EvidenceAdmissionError",
    "commit_prepared_state",
    "json_artifact_sha256",
    "locked_campaign_state",
    "prepare_admitted_result",
    "resolve_live_campaign_state_path",
    "validate_campaign_state",
]

