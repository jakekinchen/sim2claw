from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.cli import build_parser
from sim2claw.sail.capability_campaign import (
    CapabilityCampaignError,
    compile_campaign,
    load_config,
    verify_receipt,
)
from sim2claw.sail.twin_worthiness import validate_capability_certificate


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs/sail/twin_capability_campaign_v1.json"


def _compile(output: Path) -> tuple[dict, dict, dict]:
    result = compile_campaign(CONFIG, output_root=output)
    report = json.loads((output / "capability_report.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    return result, report, receipt


def test_current_tw_replay_opens_diagnostics_only_and_reports_resolution(
    tmp_path: Path,
) -> None:
    result, report, _receipt = _compile(tmp_path / "campaign")
    assert result["current_level"] == "TW-REPLAY"
    assert result["current_allowed_capabilities"] == ["diagnostics"]
    assert report["current"]["denied_capabilities"] == [
        "data_generation",
        "policy_selection",
        "physical_canary",
        "robot_motion",
    ]
    assert report["current"]["training_admitted"] is False
    assert report["current"]["policy_selection_admitted"] is False
    assert report["current"]["physical_authority"] is False
    assert report["current"]["matrix"]["data_generation"]["failed_gates"] == [
        "TW-G2"
    ]
    assert report["current"]["matrix"]["policy_selection"]["failed_gates"] == [
        "TW-G2",
        "TW-G3",
        "TW-G4",
    ]
    assert all(report["golden_cases"].values())


def test_all_revocation_paths_deny_and_synthetic_branches_are_only_reachable(
    tmp_path: Path,
) -> None:
    _result, report, _receipt = _compile(tmp_path / "campaign")
    expected = load_config(CONFIG)["negative_scenarios"]
    assert set(report["revocation_evaluation"]) == set(expected)
    assert all(
        row["allowed"] is False
        for row in report["revocation_evaluation"].values()
    )
    selection = report["synthetic_reachability"]["selection"]["matrix"]
    assert selection["data_generation"]["allowed"] is True
    assert selection["policy_selection"]["allowed"] is True
    assert selection["physical_canary"]["allowed"] is False
    physical = report["synthetic_reachability"]["physical"]["matrix"]
    assert physical["physical_canary"]["allowed"] is True
    assert physical["robot_motion"]["allowed"] is True
    assert report["synthetic_reachability"]["real_capability_claim"] is False
    assert report["proof_class_promotion_is_implicit"] is False


def test_receipt_and_certificate_are_content_addressed_and_cli_is_registered(
    tmp_path: Path,
) -> None:
    first_result, _report, first_receipt = _compile(tmp_path / "first")
    second_result, _report, second_receipt = _compile(tmp_path / "second")
    assert first_result["receipt_digest"] == second_result["receipt_digest"]
    assert first_receipt == second_receipt
    certificate = json.loads(
        (tmp_path / "first/current_capability_certificate.json").read_text(
            encoding="utf-8"
        )
    )
    assert validate_capability_certificate(certificate)["canonical_digest"] == (
        certificate["canonical_digest"]
    )
    tampered = copy.deepcopy(first_receipt)
    tampered["current_level"] = "TW-SELECTION"
    with pytest.raises(CapabilityCampaignError, match="receipt digest mismatch"):
        verify_receipt(tampered, output_root=tmp_path / "first")
    args = build_parser().parse_args(
        [
            "sail-compile-twin-capability",
            "--config",
            str(CONFIG),
            "--output",
            str(tmp_path / "cli"),
        ]
    )
    assert args.command == "sail-compile-twin-capability"


def test_learning_factory_stage_requirements_are_exact() -> None:
    config = load_config(CONFIG)
    operational = json.loads(
        (
            REPO_ROOT
            / config["source_bindings"]["operational_contract"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert operational["learning_factory_stage_requirements"] == {
        "LF-08": "data_generation",
        "LF-09": "data_generation",
        "LF-11": "policy_selection",
        "LF-13": "policy_selection",
    }
    assert operational["training_code_can_issue_or_widen_certificate"] is False
    assert (
        operational[
            "legacy_v1_certificate_without_capability_envelope_can_authorize_downstream"
        ]
        is False
    )
