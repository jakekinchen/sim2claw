from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.sail.acquisition import AcquisitionError, rank_acquisition, verify_acquisition_receipt
from sim2claw.sail.contracts import verify_contract


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "acquisition_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "acquisition"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ranking(config: dict) -> dict:
    return rank_acquisition(config)


def test_gold_12_structural_acquisition(ranking: dict) -> None:
    assert ranking["golden_cases"] == {"GOLD-12": True}
    assert ranking["selected_simulator_probe"] == "sim_load_frequency_discriminator"
    by_id = {row["candidate_id"]: row for row in ranking["rows"]}
    winner = by_id[ranking["selected_simulator_probe"]]
    common = by_id["sim_common_mode_rms"]
    assert winner["structural_components"]["structure_entropy_reduction"] == 1.0
    assert common["structural_components"]["structure_entropy_reduction"] == 0.0
    assert winner["structural_score"] > common["structural_score"]


def test_structural_and_parameter_scores_remain_separate(ranking: dict) -> None:
    assert ranking["scores_collapsed"] is False
    assert ranking["parameter_refinement_ranking"][0] == "sim_parameter_refine_load"
    assert ranking["structural_ranking"][0] == "sim_load_frequency_discriminator"
    assert all(row["scores_collapsed"] is False for row in ranking["rows"])


def test_unavailable_hardware_is_plan_not_execution(ranking: dict) -> None:
    hardware = [row for row in ranking["rows"] if row["availability"] == "unavailable_hardware_plan"]
    assert len(hardware) == 2
    assert all(row["available_for_execution"] is False for row in hardware)
    assert all(row["execution_status"] == "ranked_plan_not_executed" for row in hardware)
    assert ranking["hardware_probe_executed"] is False
    assert ranking["simulator_probe_executed"] is False


def test_intervention_plans_are_sealed_and_unprivileged(ranking: dict) -> None:
    assert len(ranking["intervention_plans"]) == 6
    for plan in ranking["intervention_plans"]:
        assert verify_contract(plan) == plan
        assert plan["authority"] == {"physical_capture": False, "robot_motion": False, "agent_can_promote": False}
        assert plan["frozen_action"]["sha256"] == ranking["source_action"]["sha256"]


def test_acquisition_beats_frozen_baselines(ranking: dict) -> None:
    assert all(row["regret"] > 0.0 for row in ranking["baselines"].values())


def test_acquisition_ranking_is_order_invariant(config: dict) -> None:
    changed = copy.deepcopy(config)
    changed["candidates"] = list(reversed(changed["candidates"]))
    assert rank_acquisition(changed) == rank_acquisition(config)


def test_duplicate_candidate_fails_closed(config: dict) -> None:
    changed = copy.deepcopy(config)
    changed["candidates"].append(copy.deepcopy(changed["candidates"][0]))
    with pytest.raises(AcquisitionError, match="identities are invalid"):
        rank_acquisition(changed)


def test_acquisition_receipt_rejects_tampering() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local acquisition receipt is unavailable")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verify_acquisition_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["hardware_execution"] = True
    with pytest.raises(AcquisitionError, match="digest mismatch|widened authority"):
        verify_acquisition_receipt(changed, output_root=OUTPUT_ROOT)
