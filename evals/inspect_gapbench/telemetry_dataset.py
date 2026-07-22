"""Materialize retrospective physical telemetry sessions for Inspect."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sim2claw.learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from sim2claw.physical_telemetry import (
    TOOL_NAMES,
    PhysicalTelemetrySession,
    build_physical_telemetry_sessions,
)

from .dataset import PACKAGE_ROOT, REPO_ROOT
from .telemetry_agents import TELEMETRY_SKILL_NAMES, telemetry_skill_paths


def telemetry_skill_bundle_digest() -> str:
    paths = telemetry_skill_paths()
    if tuple(path.name for path in paths) != TELEMETRY_SKILL_NAMES or not all(
        (path / "SKILL.md").is_file() for path in paths
    ):
        raise ValueError("physical telemetry skill bundle is incomplete")
    return canonical_digest(
        {path.name: sha256_file(path / "SKILL.md") for path in paths}
    )


def build_telemetry_sessions(
    harness: str,
    build_root: Path | None = None,
) -> tuple[dict[str, PhysicalTelemetrySession], dict[str, Any]]:
    if harness not in {"codex_cli", "claude_code"}:
        raise ValueError(f"unsupported harness: {harness}")
    root = build_root or (REPO_ROOT / ".inspect_ai" / "physical_telemetry" / harness)
    return build_physical_telemetry_sessions(root, render_plots=False)


def telemetry_bindings(
    recording_id: str,
    session: PhysicalTelemetrySession,
) -> dict[str, str]:
    return {
        "prompt_sha256": canonical_digest(prompt_for_telemetry_episode(recording_id)),
        "skill_bundle_sha256": telemetry_skill_bundle_digest(),
        "tool_contract_sha256": canonical_digest(TOOL_NAMES),
        "trace_comparison_sha256": session.comparison["comparison_sha256"],
        "sandbox_image": "sim2claw-gapbench:0.1.0",
    }


def telemetry_sample_files(
    session: PhysicalTelemetrySession,
    build_root: Path,
) -> dict[str, str]:
    card_path = build_root / "cards" / session.recording_id / "episode.json"
    atomic_write_json(
        card_path,
        {
            "schema_version": "sim2claw.physical_telemetry_episode_card.v1",
            "recording_id": session.recording_id,
            "proof_class": session.comparison["proof_class"],
            "sample_count": session.comparison["sample_count"],
            "trace_comparison_sha256": session.comparison["comparison_sha256"],
            "physical_source_bytes_in_sandbox": False,
            "use_bridged_tools_for_evidence": True,
        },
    )
    return {"episode.json": str(card_path)}


def prompt_for_telemetry_episode(recording_id: str) -> str:
    return f"""Audit one immutable Sim2Claw physical telemetry episode: {recording_id}.

Call telemetry_status first. Use the bridged tools to inspect synchronized
joint traces, velocity, raw current proxy, timing, endpoint frames, object and
contact availability, receipt outcome, and the deterministic trace comparison.
Do not infer measurements that are reported unavailable. Finish by submitting
the exact available and unavailable observation inventories and the frozen
comparison digest with
claim_boundary='retrospective_physical_observation_only'. This is human
teleoperation source evidence, not a learned-policy run, calibrated simulator,
domain-randomization admission, or physical-transfer result.
"""


__all__ = [
    "PACKAGE_ROOT",
    "build_telemetry_sessions",
    "prompt_for_telemetry_episode",
    "telemetry_bindings",
    "telemetry_sample_files",
    "telemetry_skill_bundle_digest",
]
