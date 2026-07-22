from __future__ import annotations

import json
import shlex
from pathlib import Path

from sim2claw import cli
from sim2claw.sail.contracts import SailContractError


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_TIERS = REPO_ROOT / "configs" / "sail" / "ci_tiers_v2.json"


def _test_paths(command: str) -> list[Path]:
    return [
        REPO_ROOT / token
        for token in shlex.split(command)
        if token.startswith("tests/")
    ]


def test_active_six_tier_commands_reference_real_test_modules() -> None:
    contract = json.loads(CI_TIERS.read_text(encoding="utf-8"))
    assert contract["schema_version"] == "sim2claw.sail_ci_tiers.v2"
    assert [row["ordinal"] for row in contract["tiers"]] == list(range(1, 7))
    assert [row["id"] for row in contract["tiers"]] == [
        "fast_contract",
        "synthetic_golden",
        "integration",
        "retained_evidence",
        "provider_campaign",
        "hardware",
    ]
    for tier in contract["tiers"]:
        paths = _test_paths(tier["command"])
        assert paths
        assert all(path.is_file() for path in paths), tier["id"]
    assert "tests/test_sail_studio_observatory.py" in contract["tiers"][2]["command"]
    assert contract["tiers"][4]["mode"] == "manual_budgeted"
    assert contract["tiers"][5]["mode"] == "manual_separately_authorized"
    assert contract["tiers"][5]["gateway_only"] is True


def test_all_phase_one_sail_cli_routes_are_parseable() -> None:
    parser = cli.build_parser()
    campaign_commands = {"sail-inventory", "sail-compile-evidence"}
    commands = [
        "sail-inventory",
        "sail-compile-evidence",
        "sail-compile-residuals",
        "sail-compile-belief-graph",
        "sail-compile-structural-surprise",
        "sail-compile-mechanisms",
        "sail-compile-loop-closure",
        "sail-compile-invariance",
        "sail-compile-acquisition",
        "sail-run-live-operator",
        "sail-compile-benchmark",
        "sail-compile-inspect-campaign",
        "sail-compile-retrospective-case",
        "sail-run-prospective-simulator",
        "sail-compile-twin-capability",
        "sail-run-policy-flywheel",
        "sail-compile-studio-observatory",
        "sail-compile-publication",
    ]
    for command in commands:
        source_flag = "--campaign" if command in campaign_commands else "--config"
        argv = [command, source_flag, "input.json"]
        if command != "sail-inventory":
            argv.extend(["--output", "ignored-output"])
        assert parser.parse_args(argv).command == command


def test_studio_observatory_cli_dispatches_without_widening_authority(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config = tmp_path / "config.json"
    output = tmp_path / "output"
    config.write_text("{}\n", encoding="utf-8")
    captured: dict[str, Path] = {}

    def fake_compile(config_path: Path, *, output_root: Path) -> dict:
        captured.update(config=Path(config_path), output=Path(output_root))
        return {
            "schema_version": "sim2claw.sail_studio_observatory_compile_result.v1",
            "status": "compiled",
            "physical_authority": False,
        }

    monkeypatch.setattr(
        "sim2claw.sail.studio.compile_studio_observatory", fake_compile
    )
    assert (
        cli.main(
            [
                "sail-compile-studio-observatory",
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert captured == {"config": config, "output": output}
    assert result["physical_authority"] is False


def test_studio_observatory_cli_fails_closed_on_contract_error(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    def reject(_config_path: Path, *, output_root: Path) -> dict:
        del output_root
        raise SailContractError("bound source changed")

    monkeypatch.setattr("sim2claw.sail.studio.compile_studio_observatory", reject)
    assert (
        cli.main(
            [
                "sail-compile-studio-observatory",
                "--config",
                str(tmp_path / "config.json"),
                "--output",
                str(tmp_path / "output"),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out) == {"error": "bound source changed"}
