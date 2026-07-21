"""Freeze public GapBench packets and create Inspect samples."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sim2claw.gapbench_contracts import GapBenchContractError, freeze_public_case
from sim2claw.gapbench_evaluator import SealedEvaluator
from sim2claw.gapbench_tools import GapBenchSession
from sim2claw.gapbench_tools import TOOL_NAMES
from sim2claw.learning_factory_artifacts import canonical_digest, load_json_object, sha256_file


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
PUBLIC_SOURCE = PACKAGE_ROOT / "fixtures" / "public" / "cases.json"
CAMPAIGN_CONTRACT = (
    REPO_ROOT / "configs" / "evaluations" / "sim2claw_gapbench_v1.json"
)


def _case_map(path: Path, expected_schema: str) -> dict[str, dict[str, Any]]:
    source = load_json_object(path, label="GapBench case set")
    if source.get("schema_version") != expected_schema:
        raise GapBenchContractError(f"unsupported case-set schema: {path}")
    cases = source.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GapBenchContractError(f"case set is empty: {path}")
    result: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise GapBenchContractError(f"case set contains an invalid case: {path}")
        if case["case_id"] in result:
            raise GapBenchContractError(f"duplicate case_id: {case['case_id']}")
        result[case["case_id"]] = case
    return result


def skill_bundle_digest() -> str:
    manifest = {
        path.relative_to(PACKAGE_ROOT).as_posix(): sha256_file(path)
        for path in sorted((PACKAGE_ROOT / "skills").glob("*/SKILL.md"))
    }
    if len(manifest) != 5:
        raise GapBenchContractError("the shared skill bundle must contain exactly five skills")
    return canonical_digest(manifest)


def benchmark_bindings(case_id: str) -> dict[str, str]:
    return {
        "prompt_sha256": canonical_digest(prompt_for_case(case_id)),
        "skill_bundle_sha256": skill_bundle_digest(),
        "tool_contract_sha256": canonical_digest(TOOL_NAMES),
        "sandbox_image": "sim2claw-gapbench:0.1.0",
    }


def public_sources() -> dict[str, dict[str, Any]]:
    cases = _case_map(PUBLIC_SOURCE, "sim2claw.gapbench_public_case_set.v1")
    for case_id, case in cases.items():
        case["bindings"] = benchmark_bindings(case_id)
    return cases


def _sealed_source_binding() -> dict[str, Any]:
    contract = load_json_object(CAMPAIGN_CONTRACT, label="GapBench campaign contract")
    environment = contract.get("sealed_case_source_env")
    expected_sha256 = contract.get("sealed_case_source_sha256")
    expected_schema = contract.get("sealed_case_source_schema")
    expected_count = contract.get("sealed_case_count")
    if not isinstance(environment, str) or not environment:
        raise GapBenchContractError("sealed source environment binding is missing")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise GapBenchContractError("sealed source digest binding is invalid")
    if expected_schema != "sim2claw.gapbench_sealed_case_set.v1":
        raise GapBenchContractError("sealed source schema binding is invalid")
    if not isinstance(expected_count, int) or expected_count <= 0:
        raise GapBenchContractError("sealed source case-count binding is invalid")
    return {
        "environment": environment,
        "sha256": expected_sha256,
        "schema": expected_schema,
        "case_count": expected_count,
    }


def resolve_sealed_source(source: Path | None = None) -> Path:
    """Resolve host-private sealed bytes without defining a package-local fallback."""

    binding = _sealed_source_binding()
    if source is None:
        configured = os.environ.get(binding["environment"])
        if not configured:
            raise GapBenchContractError(
                "sealed GapBench source is host-private; set "
                f"{binding['environment']} or pass sealed_source explicitly"
            )
        source = Path(configured)
    path = source.expanduser().resolve()
    if not path.is_file():
        raise GapBenchContractError(f"sealed GapBench source is unavailable: {path}")
    return path


def sealed_sources(source: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load digest-bound sealed cases in the trusted host process only."""

    binding = _sealed_source_binding()
    path = resolve_sealed_source(source)
    expected = str(binding["sha256"])
    if sha256_file(path) != expected:
        raise GapBenchContractError("sealed GapBench source digest mismatch")
    cases = _case_map(path, str(binding["schema"]))
    if len(cases) != int(binding["case_count"]):
        raise GapBenchContractError("sealed GapBench source case count changed")
    return cases


def build_sessions(
    harness: str,
    build_root: Path | None = None,
    *,
    sealed_source: Path | None = None,
) -> dict[str, GapBenchSession]:
    if harness not in {"codex_cli", "claude_code"}:
        raise GapBenchContractError(f"unsupported harness: {harness}")
    public = public_sources()
    sealed = sealed_sources(sealed_source)
    if set(public) != set(sealed):
        raise GapBenchContractError("public and sealed case inventories differ")
    root = build_root or (REPO_ROOT / ".inspect_ai" / "gapbench" / harness)
    sessions: dict[str, GapBenchSession] = {}
    for case_id in sorted(public):
        packet_root = root / "packets" / case_id
        state_root = root / "state" / case_id
        freeze_public_case(public[case_id], packet_root)
        sessions[case_id] = GapBenchSession(
            packet_root,
            SealedEvaluator(sealed[case_id]),
            state_root,
            reset=True,
        )
    return sessions


def sample_files(session: GapBenchSession) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(session.packet_root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(session.packet_root).as_posix()
            files[relative] = str(path)
    return files


def prompt_for_case(case_id: str) -> str:
    return f"""You are diagnosing one frozen Sim2Claw GapBench case: {case_id}.

Start with case_status and inspect only public evidence. Maintain ranked
competing hypotheses, choose probes only when they discriminate mechanisms,
and edit candidate/*.json only. Change one causal mechanism at a time, run the
public evaluator, then submit exactly one final candidate with a prediction and
claim_boundary='synthetic_only'. Do not claim physical transfer or policy task
success. Hidden data, host access, network, credentials, Docker, devices, and
robot actions are forbidden.
"""


def packet_contains_forbidden_bytes(packet_root: Path) -> list[str]:
    """Return explicit boundary violations in a materialized public packet."""

    forbidden_tokens = (
        "target_parameters",
        "hidden_rows",
        "probe_results",
        "promotion_thresholds",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "/var/run/docker.sock",
        str(Path.home()),
    )
    violations: list[str] = []
    for path in packet_root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token and token in text:
                violations.append(f"{path.relative_to(packet_root)}:{token}")
    return violations


def packet_manifest(session: GapBenchSession) -> str:
    return json.dumps(sample_files(session), sort_keys=True)
