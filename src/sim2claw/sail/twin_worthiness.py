"""Frozen TwinWorthiness truth-table helpers; integration arrives in P1-14."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract


CONTRACT_PATH = REPO_ROOT / "configs" / "sail" / "twin_worthiness_v1.json"


def load_twin_worthiness_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "sim2claw.twin_worthiness_contract.v1":
        raise SailContractError("TwinWorthiness contract version changed")
    return value


def gate_verdict(
    *,
    required: Sequence[str],
    available: Mapping[str, bool],
    threshold_failures: Sequence[str],
) -> dict[str, Any]:
    missing = sorted(name for name in required if not available.get(name, False))
    if missing:
        return {
            "status": "not_evaluable",
            "reason": "missing required observations: " + ", ".join(missing),
            "evidence_ids": [],
        }
    if threshold_failures:
        return {
            "status": "fail",
            "reason": "frozen thresholds failed: " + ", ".join(threshold_failures),
            "evidence_ids": [],
        }
    return {"status": "pass", "reason": "all frozen requirements pass", "evidence_ids": []}


def resolve_level(
    gates: Mapping[str, Mapping[str, Any]], *, physical_canary_authorized: bool = False
) -> str:
    contract = load_twin_worthiness_contract()
    ordered = [
        "TW-DIAGNOSTIC",
        "TW-REPLAY",
        "TW-DATA",
        "TW-SELECTION",
    ]
    level = "NONE"
    for candidate in ordered:
        required = contract["levels"][candidate]
        if all(gates.get(gate, {}).get("status") == "pass" for gate in required):
            level = candidate
        else:
            break
    if level == "TW-SELECTION" and physical_canary_authorized:
        return "TW-PHYSICAL-CANARY"
    return level


def capabilities_for_level(level: str) -> dict[str, bool]:
    contract = load_twin_worthiness_contract()
    if level == "NONE":
        return {
            "diagnostics": False,
            "data_generation": False,
            "policy_selection": False,
            "physical_canary": False,
        }
    try:
        return dict(contract["capabilities"][level])
    except KeyError as error:
        raise SailContractError(f"unknown TwinWorthiness level: {level}") from error


def issue_fixture_certificate(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a certificate fixture after its level and authority agree."""

    return seal_contract(unsigned)


def certificate_is_available(certificate: Mapping[str, Any]) -> bool:
    try:
        verify_contract(certificate)
    except SailContractError:
        return False
    return True
