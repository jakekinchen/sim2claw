"""Build interaction-event evidence sessions and public Inspect cards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sim2claw.interaction_events import (
    TOOL_NAMES,
    InteractionEventSession,
    build_interaction_event_sessions,
)
from sim2claw.learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file

from .dataset import PACKAGE_ROOT, REPO_ROOT
from .event_agents import EVENT_SKILL_NAMES, event_skill_paths


def event_skill_bundle_digest() -> str:
    paths = event_skill_paths()
    if tuple(path.name for path in paths) != EVENT_SKILL_NAMES or not all(
        (path / "SKILL.md").is_file() for path in paths
    ):
        raise ValueError("interaction-event skill bundle is incomplete")
    return canonical_digest(
        {path.name: sha256_file(path / "SKILL.md") for path in paths}
    )


def build_event_sessions(
    harness: str,
    *,
    partition: str = "train",
    evaluator_owned: bool = False,
    build_root: Path | None = None,
) -> tuple[dict[str, InteractionEventSession], dict[str, Any]]:
    if harness not in {"codex_cli", "claude_code"}:
        raise ValueError(f"unsupported harness: {harness}")
    root = build_root or (
        REPO_ROOT / ".inspect_ai" / "interaction_events" / partition / harness
    )
    return build_interaction_event_sessions(
        root,
        partition=partition,
        evaluator_owned=evaluator_owned,
        render_visuals=True,
    )


def prompt_for_event_episode(recording_id: str) -> str:
    return f"""Audit one immutable Sim2Claw interaction-event episode: {recording_id}.

Call event_status first. Inspect the deterministic phase/event proposals,
event-conditioned metrics, and the synchronized nine-frame strip. Annotate
only what is visibly supported. Use ambiguous or not_visible for occluded
evidence. The receipt outcome is intentionally hidden. A flat or loaded
gripper response is a mechanical proxy, not measured contact. Submit one
visual annotation, then submit the exact event and annotation digests with
claim_boundary='retrospective_multimodal_candidates_only'. Do not claim metric
object pose, exact contact, calibrated force, simulator calibration, learned-
policy success, or physical transfer.
"""


def event_bindings(
    recording_id: str, session: InteractionEventSession
) -> dict[str, str]:
    return {
        "prompt_sha256": canonical_digest(prompt_for_event_episode(recording_id)),
        "skill_bundle_sha256": event_skill_bundle_digest(),
        "tool_contract_sha256": canonical_digest(TOOL_NAMES),
        "event_episode_sha256": session.event["event_episode_sha256"],
        "phase_rows_sha256": session.phase_rows["phase_rows_sha256"],
        "sandbox_image": "sim2claw-gapbench:0.1.0",
    }


def event_sample_files(
    session: InteractionEventSession, build_root: Path
) -> dict[str, str]:
    card_path = build_root / "cards" / session.recording_id / "episode.json"
    atomic_write_json(
        card_path,
        {
            "schema_version": "sim2claw.interaction_event_public_card.v1",
            "recording_id": session.recording_id,
            "partition": session.partition,
            "event_episode_sha256": session.event["event_episode_sha256"],
            "source_physical_bytes_in_sandbox": False,
            "receipt_outcome_in_sandbox": False,
            "use_bridged_tools_for_evidence": True,
            "contact_ground_truth_available": False,
        },
    )
    return {"episode.json": str(card_path)}


__all__ = [
    "PACKAGE_ROOT",
    "REPO_ROOT",
    "build_event_sessions",
    "event_bindings",
    "event_sample_files",
    "event_skill_bundle_digest",
    "prompt_for_event_episode",
]
