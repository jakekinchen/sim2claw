from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw import cli
from sim2claw.dev_loop.bench import (
    DevLoopBenchmarkError,
    load_benchmark_contract,
    run_dev_loop_benchmark,
    verify_dev_loop_benchmark_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs/dev_loop/dev_loop_benchmark_v1.json"


def test_seeded_benchmark_contract_freezes_modes_cases_and_authority() -> None:
    config, _, cases = load_benchmark_contract(CONFIG)
    assert [row["id"] for row in config["modes"]] == [
        "single_worker",
        "worker_self_review",
        "independent_receipt_gated",
    ]
    assert len(cases["cases"]) == 10
    assert sum(len(row["defects"]) for row in cases["cases"]) == 9
    assert not any(config["authority"].values())


def test_dev_loop_benchmark_contains_all_seeded_defects_only_with_independent_receipts(
    tmp_path: Path,
) -> None:
    result = run_dev_loop_benchmark(CONFIG, output_root=tmp_path / "run")
    assert result["status"] == "pass"
    modes = {row["mode"]: row for row in result["modes"]}
    assert modes["single_worker"] == {
        "mode": "single_worker",
        "detected_defect_count": 0,
        "escaped_defect_count": 9,
        "false_completion_count": 9,
    }
    assert modes["worker_self_review"]["detected_defect_count"] == 1
    assert modes["worker_self_review"]["escaped_defect_count"] == 8
    assert modes["independent_receipt_gated"]["detected_defect_count"] == 9
    assert modes["independent_receipt_gated"]["escaped_defect_count"] == 0
    scorecard = json.loads((tmp_path / "run/scorecard.json").read_text())
    assert "does not measure general model intelligence" in scorecard["claim_boundary"]


def test_benchmark_is_deterministic_and_receipt_rejects_tamper(tmp_path: Path) -> None:
    first = run_dev_loop_benchmark(CONFIG, output_root=tmp_path / "first")
    second = run_dev_loop_benchmark(CONFIG, output_root=tmp_path / "second")
    assert first["scorecard_digest"] == second["scorecard_digest"]
    assert first["receipt_digest"] == second["receipt_digest"]

    receipt = tmp_path / "first/receipt.json"
    verify_dev_loop_benchmark_receipt(receipt, output_root=tmp_path / "first")
    scorecard = tmp_path / "first/scorecard.json"
    changed = json.loads(scorecard.read_text())
    changed["modes"][0]["escaped_defect_count"] = 0
    scorecard.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(DevLoopBenchmarkError, match="scorecard changed"):
        verify_dev_loop_benchmark_receipt(receipt, output_root=tmp_path / "first")


def test_benchmark_rejects_authority_widening(tmp_path: Path) -> None:
    config = json.loads(CONFIG.read_text())
    config["authority"]["physical_capture"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(DevLoopBenchmarkError, match="widened authority"):
        load_benchmark_contract(path)


def test_dev_loop_cli_routes_are_parseable_and_benchmark_dispatches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["dev-loop-audit"]).command == "dev-loop-audit"
    assert parser.parse_args(["dev-loop-render-ledger", "--check"]).check
    assert (
        cli.main(
            [
                "dev-loop-benchmark",
                "--config",
                str(CONFIG),
                "--output",
                str(tmp_path / "cli"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
