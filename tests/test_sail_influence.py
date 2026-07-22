from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.sail.influence import InfluenceError, discover_influence_set, run_gold_09_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "loop_closure_v1.json"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_gold_09_influence_set(config: dict) -> None:
    result = run_gold_09_fixture(config)
    assert result["affected_intervention_ids"] == [
        "intervention:fidelity-rms-closeout",
        "intervention:load-bias-boundary",
    ]
    assert result["metrics"] == {
        "true_positive": 2,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
    }
    assert result["passed"] is True


def test_residual_overlap_alone_does_not_admit_distractors(config: dict) -> None:
    result = run_gold_09_fixture(config)
    by_id = {row["intervention_id"]: row for row in result["candidates"]}
    timing = by_id["intervention:timing-110ms"]
    deadband = by_id["intervention:deadband-2deg"]
    assert timing["signals"]["residual_overlap_count"] == 2
    assert deadband["signals"]["residual_overlap_count"] == 2
    assert timing["selected"] is False
    assert deadband["selected"] is False
    assert timing["signals"]["declared_scope_match"] is False


def test_influence_discovery_is_order_invariant(config: dict) -> None:
    case = config["gold_09"]
    first = run_gold_09_fixture(config)
    second = discover_influence_set(
        mechanism_id=case["mechanism_id"],
        mechanism_family=case["mechanism_family"],
        graph_factors=list(reversed(case["graph_factors"])),
        interventions=list(reversed(case["interventions"])),
        graph_edges=list(reversed(case["graph_edges"])),
        thresholds=config["influence_thresholds"],
        oracle_affected_intervention_ids=list(reversed(case["oracle_affected_intervention_ids"])),
    )
    assert first == second


def test_missing_predicts_paths_abstain(config: dict) -> None:
    case = config["gold_09"]
    result = discover_influence_set(
        mechanism_id=case["mechanism_id"],
        mechanism_family=case["mechanism_family"],
        graph_factors=case["graph_factors"],
        interventions=case["interventions"],
        graph_edges=[],
        thresholds=config["influence_thresholds"],
    )
    assert result["affected_intervention_ids"] == []
    assert result["abstained"] is True
    assert result["physical_cause_asserted"] is False


def test_duplicate_intervention_identity_fails_closed(config: dict) -> None:
    case = copy.deepcopy(config["gold_09"])
    case["interventions"].append(copy.deepcopy(case["interventions"][0]))
    with pytest.raises(InfluenceError, match="identities are invalid"):
        discover_influence_set(
            mechanism_id=case["mechanism_id"],
            mechanism_family=case["mechanism_family"],
            graph_factors=case["graph_factors"],
            interventions=case["interventions"],
            graph_edges=case["graph_edges"],
            thresholds=config["influence_thresholds"],
        )
