from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw import cli
from sim2claw.sail.publication import (
    PublicationError,
    compile_publication,
    verify_publication_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs" / "sail" / "publication_campaign_v1.json"
OUTPUT = REPO_ROOT / "outputs" / "sail" / "publication-v1"


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _all_sources_available() -> bool:
    return all((REPO_ROOT / row["path"]).is_file() for row in _config()["source_bindings"].values())


@pytest.fixture(scope="module")
def compiled(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    if not _all_sources_available():
        pytest.skip("owner-local Phase 1 publication sources are unavailable")
    output = tmp_path_factory.mktemp("sail-publication")
    return compile_publication(CONFIG, output_root=output), output


def test_publication_preregistration_freezes_six_questions_ten_ablations_and_statistics() -> None:
    config = _config()
    assert len(config["research_questions"]) == 6
    assert config["ablation_ids"] == [
        "no_residual_phase_alignment",
        "no_compensation_debt",
        "no_mechanism_plugins",
        "no_influence_discovery",
        "no_invariance",
        "no_loop_closure",
        "no_structural_acquisition",
        "no_twinworthiness_gate",
        "deterministic_only",
        "agent_only_vs_deterministic_plus_agent",
    ]
    assert config["statistics"]["unit"] == "paired_seeded_case"
    assert config["statistics"]["retained_unit"] == "whole_episode"
    assert config["statistics"]["bootstrap_replicates"] == 10_000
    assert config["statistics"]["secondary_correction"] == "holm_bonferroni"
    assert config["statistics"]["missing_result_policy"] == "not_evaluable_never_zero"
    assert not any(config["authority"].values())


def test_publication_compiler_emits_complete_separated_package(compiled: tuple[dict, Path]) -> None:
    result, output = compiled
    assert result["status"] == "compiled"
    assert result["counts"] == {
        "research_question_count": 6,
        "required_ablation_count": 10,
        "paper_slot_count": 9,
        "table_count": 9,
        "figure_count": 7,
        "source_binding_count": 25,
    }
    package = json.loads((output / "publication_package.json").read_text(encoding="utf-8"))
    assert package["ablation_matrix"]["all_required_present"] is True
    assert package["statistics"]["retained_resampling_unit"] == "whole_episode"
    assert [row["lane"] for row in package["proof_lanes"]] == [
        "development",
        "public",
        "sealed",
        "retrospective",
        "prospective_simulator",
        "provider_agent",
        "learned_policy_simulation",
        "future_physical",
    ]
    assert package["proof_lanes"][-1]["count"] is None
    assert package["proof_lanes"][-1]["status"] == "unavailable_phase2_authority_required"
    assert package["policy_status"] == {
        "act": "terminal_negative_synthetic_fixture_no_skill_package",
        "groot": "skipped_compute_unavailable",
        "current_real_generated_rows": 0,
        "current_real_policy_comparisons": 0,
    }
    assert package["current_twinworthiness"]["level"] == "TW-REPLAY"
    assert package["current_twinworthiness"]["allowed_capabilities"] == ["diagnostics"]
    assert not any(package["authority"].values())


def test_paired_ablation_statistics_preserve_small_n_and_terminal_negatives(
    compiled: tuple[dict, Path]
) -> None:
    _result, output = compiled
    matrix = json.loads((output / "ablation_matrix.json").read_text(encoding="utf-8"))
    methods = {row["method"]: row for row in matrix["methods"]}
    assert methods["sail_deterministic"]["mechanism_family_top1_accuracy"] == 0.75
    assert methods["parameter_only"]["mechanism_family_top1_accuracy"] == 0.0
    assert methods["sequential_no_revisit"]["mechanism_family_top1_accuracy"] == 0.5
    assert methods["no_twinworthiness_gate"]["false_promotion_rate"] == 0.25
    assert methods["sail_plus_agent_fixture"]["simulator_evaluations"] == 32
    assert methods["sail_deterministic"]["simulator_evaluations"] == 16
    assert len(matrix["paired_statistics"]) == 11
    assert all(row["case_count"] == 8 for row in matrix["paired_statistics"])
    assert all(row["bootstrap_replicates"] == 10_000 for row in matrix["paired_statistics"])
    assert all(0.0 <= row["holm_adjusted_p"] <= 1.0 for row in matrix["paired_statistics"])
    agent_ablation = next(
        row
        for row in matrix["ablations"]
        if row["ablation_id"] == "agent_only_vs_deterministic_plus_agent"
    )
    assert agent_ablation["agent_only"] == {
        "status": "not_evaluable_provider_transport_blocked",
        "metrics": None,
    }
    assert matrix["sealed_access_by_method"] is False
    assert matrix["action_bytes_unchanged"] is True
    assert matrix["evaluator_state_unchanged"] is True


def test_retained_statistics_resample_whole_episodes_only(compiled: tuple[dict, Path]) -> None:
    _result, output = compiled
    report = json.loads((output / "retained_episode_statistics.json").read_text(encoding="utf-8"))
    assert len(report["rows"]) == 6
    for row in report["rows"]:
        assert row["episode_count"] == 11
        assert row["resampling_unit"] == "whole_episode"
        assert row["confidence_interval"][0] <= row["mean_rmse"] <= row["confidence_interval"][1]
        assert row["proof_class"] == "retained_retrospective"


def test_phase2_packet_is_executable_but_opens_no_hardware_authority(
    compiled: tuple[dict, Path]
) -> None:
    _result, output = compiled
    packet = json.loads((output / "phase2_operator_packet.json").read_text(encoding="utf-8"))
    assert packet["status"] == "executable_but_blocked_pending_owner_authority_and_bound_identity"
    assert packet["required_identity_count"] == 13
    assert len(packet["missing_identity_fields"]) == 13
    assert packet["preflight"] == {
        "workcell_class": "new_related_workcell",
        "capture_allowed": False,
        "motion_allowed": False,
        "policy_camera_ids": ["overhead"],
        "evaluator_only_camera_ids": ["depth", "side", "wrist"],
        "physical_authority": False,
    }
    assert [row["prediction_id"] for row in packet["predictions"]] == [
        "P2-TIMING-RATE",
        "P2-LOAD-PROXY",
        "P2-CONTACT-OBSERVABILITY",
    ]
    assert packet["physical_observations_consumed"] == 0


def test_every_generated_table_figure_and_map_is_receipt_bound(compiled: tuple[dict, Path]) -> None:
    _result, output = compiled
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    assert len([name for name in receipt["outputs"] if name.startswith("table_")]) == 9
    assert len([name for name in receipt["outputs"] if name.startswith("figure_")]) == 7
    assert receipt["statistics_frozen_before_compile"] is True
    assert receipt["whole_episode_retained_resampling"] is True
    assert receipt["provider_results_pooled"] is False
    assert receipt["physical_observations_consumed"] == 0
    assert not any(receipt["authority"].values())
    verify_publication_receipt(receipt, output_root=output)


def test_publication_receipt_rejects_output_tamper(compiled: tuple[dict, Path]) -> None:
    _result, output = compiled
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    target = output / "tables" / "paper_slots.csv"
    original = target.read_bytes()
    target.write_bytes(original + b"tamper\n")
    try:
        with pytest.raises(PublicationError, match="publication output changed"):
            verify_publication_receipt(receipt, output_root=output)
    finally:
        target.write_bytes(original)
    verify_publication_receipt(receipt, output_root=output)


def test_missing_required_ablation_fails_before_source_use(tmp_path: Path) -> None:
    config = _config()
    config["ablation_ids"].pop()
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(PublicationError, match="required publication ablations changed"):
        compile_publication(changed, output_root=tmp_path / "output")


def test_publication_cli_dispatches_and_fails_closed(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, Path] = {}

    def fake_compile(config_path: Path, *, output_root: Path) -> dict:
        captured.update(config=Path(config_path), output=Path(output_root))
        return {
            "schema_version": "sim2claw.sail_publication_compile_result.v1",
            "status": "compiled",
            "physical_authority": False,
        }

    monkeypatch.setattr("sim2claw.sail.publication.compile_publication", fake_compile)
    config = tmp_path / "config.json"
    output = tmp_path / "output"
    assert cli.main(["sail-compile-publication", "--config", str(config), "--output", str(output)]) == 0
    assert captured == {"config": config, "output": output}
    assert json.loads(capsys.readouterr().out)["physical_authority"] is False


def test_current_ignored_publication_receipt_verifies_when_available() -> None:
    if not (OUTPUT / "receipt.json").is_file():
        pytest.skip("owner-local publication output is unavailable")
    receipt = json.loads((OUTPUT / "receipt.json").read_text(encoding="utf-8"))
    verify_publication_receipt(receipt, output_root=OUTPUT)
