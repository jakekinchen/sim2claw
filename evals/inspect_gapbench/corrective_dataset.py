"""Materialize frozen corrective-repair samples for Inspect."""

from __future__ import annotations

from pathlib import Path

from sim2claw.corrective_benchmark import (
    CorrectiveRepairSession,
    TOOL_NAMES,
    case_ids,
    materialize_public_case,
    packet_contains_forbidden_bytes,
)
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file

from .agents import CORRECTIVE_SKILL_NAMES, corrective_skill_paths
from .dataset import PACKAGE_ROOT, REPO_ROOT


def corrective_skill_bundle_digest() -> str:
    paths = corrective_skill_paths()
    if tuple(path.name for path in paths) != CORRECTIVE_SKILL_NAMES or not all((path / "SKILL.md").is_file() for path in paths):
        raise ValueError("corrective repair skill bundle is incomplete")
    return canonical_digest({path.name: sha256_file(path / "SKILL.md") for path in paths})


def corrective_bindings(case_id: str) -> dict[str, str]:
    return {
        "prompt_sha256": canonical_digest(prompt_for_corrective_case(case_id)),
        "skill_bundle_sha256": corrective_skill_bundle_digest(),
        "tool_contract_sha256": canonical_digest(TOOL_NAMES),
        "sandbox_image": "sim2claw-gapbench:0.1.0",
    }


def build_corrective_sessions(harness: str, build_root: Path | None = None) -> dict[str, CorrectiveRepairSession]:
    if harness not in {"codex_cli", "claude_code"}:
        raise ValueError(f"unsupported harness: {harness}")
    root = build_root or (REPO_ROOT / ".inspect_ai" / "corrective_repair" / harness)
    sessions: dict[str, CorrectiveRepairSession] = {}
    for case_id in case_ids():
        packet_root = root / "packets" / case_id
        state_root = root / "state" / case_id
        materialize_public_case(case_id, packet_root, harness)
        violations = packet_contains_forbidden_bytes(packet_root)
        if violations:
            raise ValueError(f"corrective repair public packet leaked forbidden bytes: {violations}")
        sessions[case_id] = CorrectiveRepairSession(packet_root, state_root, reset=True)
    return sessions


def corrective_sample_files(session: CorrectiveRepairSession) -> dict[str, str]:
    return {
        path.relative_to(session.packet_root).as_posix(): str(path)
        for path in sorted(session.packet_root.rglob("*"))
        if path.is_file()
    }


def prompt_for_corrective_case(case_id: str) -> str:
    return f"""You are repairing one frozen Sim2Claw corrective benchmark case: {case_id}.

Call repair_status first. Read only declared public evidence, estimate the
smallest selected-object-frame translation that should recenter the pregrasp,
and submit one evidence-bound hypothesis. Edit candidate/proposal.json while
preserving its schema, identities, non-translation fields, and authority
boundary. You may use declared probes and at most eight public evaluations.
Submit exactly one terminal repair with
claim_boundary='synthetic_benchmark_only'. Never emit raw joints, seek hidden
state, claim training admission or promotion, access the host/network/devices,
or describe synthetic reward as physical transfer.
"""


__all__ = [
    "PACKAGE_ROOT",
    "build_corrective_sessions",
    "corrective_bindings",
    "corrective_sample_files",
    "corrective_skill_bundle_digest",
    "prompt_for_corrective_case",
]
