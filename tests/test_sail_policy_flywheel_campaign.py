from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.cli import build_parser
from sim2claw.sail.policy_flywheel_campaign import (
    PolicyFlywheelCampaignError,
    compile_campaign,
    load_config,
    verify_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs/sail/policy_flywheel_campaign_v1.json"


def _runner(config: dict) -> dict:
    return {
        "exit_code": 0,
        "passed_count": config["fixture_execution"]["expected_passed_test_count"],
        "stdout": "synthetic injected runner for compiler unit test\n",
        "command": ["pytest", "fixture"],
    }


def _compile(output: Path) -> tuple[dict, dict, dict]:
    result = compile_campaign(CONFIG, output_root=output, test_runner=_runner)
    report = json.loads(
        (output / "policy_flywheel_report.json").read_text(encoding="utf-8")
    )
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    return result, report, receipt


def test_fixture_flywheel_is_complete_while_current_real_lane_is_closed(
    tmp_path: Path,
) -> None:
    result, report, _receipt = _compile(tmp_path / "campaign")
    assert result["full_component_path_executed"] is True
    assert result["current_real_lane_closed"] is True
    assert report["current_real_lane"] == {
        "twin_worthiness_level": "TW-REPLAY",
        "allowed_capabilities": ["diagnostics"],
        "data_generation_allowed": False,
        "policy_selection_allowed": False,
        "generated_rows": 0,
        "admitted_rows": 0,
        "policy_comparisons": 0,
        "training_invoked": False,
    }
    assert [row["stage_id"] for row in report["synthetic_fixture"]["stages"]] == [
        "LF-08",
        "LF-09",
        "LF-10",
        "LF-11",
        "LF-12",
        "LF-13",
    ]
    assert report["synthetic_fixture"]["posterior_sampling_policy"] == (
        "identified_posterior_only"
    )
    assert report["synthetic_fixture"]["arbitrary_domain_randomization"] is False
    assert report["synthetic_fixture"]["training_can_promote"] is False


def test_failed_rows_and_prefixes_never_enter_training_and_groot_is_separate(
    tmp_path: Path,
) -> None:
    _result, report, _receipt = _compile(tmp_path / "campaign")
    for row in report["failure_admission_matrix"]:
        if row["case"] in {"strict_success", "successful_corrective_suffix"}:
            continue
        assert row["training_rows"] == 0
    correction = next(
        row
        for row in report["failure_admission_matrix"]
        if row["case"] == "successful_corrective_suffix"
    )
    assert correction["training_rows"] == "exact_suffix_only"
    groot = report["groot_challenger"]
    assert groot["status"] == "skipped_compute_unavailable"
    assert groot["policy_camera_ids"] == ["overhead"]
    assert groot["evaluator_only_camera_ids"] == ["wrist"]
    assert groot["wrist_main_policy_input"] is False
    assert groot["training_invoked"] is False
    assert groot["separate_from_act_claims"] is True


def test_campaign_receipt_is_content_addressed_and_tamper_fails(tmp_path: Path) -> None:
    first, _report, receipt = _compile(tmp_path / "first")
    second, _report, second_receipt = _compile(tmp_path / "second")
    assert first["report_digest"] == second["report_digest"]
    assert receipt == second_receipt
    tampered = copy.deepcopy(receipt)
    tampered["current_real_lane_closed"] = False
    with pytest.raises(PolicyFlywheelCampaignError, match="receipt digest mismatch"):
        verify_receipt(tampered, output_root=tmp_path / "first")
    args = build_parser().parse_args(
        [
            "sail-run-policy-flywheel",
            "--config",
            str(CONFIG),
            "--output",
            str(tmp_path / "cli"),
        ]
    )
    assert args.command == "sail-run-policy-flywheel"


def test_campaign_source_and_authority_inventory_is_frozen() -> None:
    config = load_config(CONFIG)
    assert config["authority"] == {
        "real_data_generation": False,
        "real_training_admission": False,
        "real_policy_selection": False,
        "physical_canary": False,
        "robot_motion": False,
        "physical_transfer": False,
    }
    assert config["fixture_execution"]["maximum_wall_seconds"] == 300
    assert config["groot_challenger"]["compute_available"] is False
