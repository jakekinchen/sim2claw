from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.loop_closure import (
    LoopClosureError,
    run_gold_10_fixture,
    validate_loop_closure,
    verify_loop_closure_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "loop_closure_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "loop-closure"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def closure(config: dict) -> dict:
    return run_gold_10_fixture(config)


def test_gold_10_sparse_vs_full(closure: dict) -> None:
    assert closure["sparse"]["structure_recovered"] is True
    assert closure["full_batch"]["structure_recovered"] is True
    assert closure["sequential_no_revisit"]["structure_recovered"] is False
    assert closure["comparison"]["sparse_full_score_loss_fraction"] <= 1e-9
    assert closure["sparse"]["recomputed_decision_count"] == 2
    assert closure["full_batch"]["recomputed_decision_count"] == 8
    assert closure["comparison"]["credit_reassigned"] is True


def test_sparse_closure_preserves_unaffected_posterior_digests(closure: dict) -> None:
    assert closure["sparse"]["unaffected_posterior_digests_unchanged"] is True
    for decision_id in closure["sparse"]["unaffected_decision_ids"]:
        assert (
            closure["before"]["posteriors"][decision_id]["posterior_digest"]
            == closure["sparse"]["posteriors"][decision_id]["posterior_digest"]
        )


def test_sparse_closure_reassigns_compensator_credit(closure: dict) -> None:
    truth = closure["true_parameters"]
    assert closure["before"]["posteriors"]["timing"]["value"] > 0.8
    assert closure["sparse"]["parameters"]["timing"] == pytest.approx(truth["timing"], abs=0.05)
    assert closure["sparse"]["parameters"]["load_compliance"] == pytest.approx(
        truth["load_compliance"], abs=0.05
    )
    assert closure["sparse"]["compensation_debt"] < closure["before"]["compensation_debt"]


def test_loop_closure_preserves_actions_and_frozen_results(closure: dict) -> None:
    assert closure["action_bytes_unchanged"] is True
    assert closure["frozen_evidence_unchanged"] is True
    assert closure["historical_results_mutated"] is False
    assert closure["physical_mechanism_identified"] is False


def test_material_sparse_full_disagreement_fails_closed(closure: dict) -> None:
    changed = copy.deepcopy(closure)
    changed["comparison"]["sparse_full_score_loss_fraction"] = 0.5
    unsigned = copy.deepcopy(changed)
    unsigned.pop("closure_digest")
    changed["closure_digest"] = canonical_digest(unsigned)
    with pytest.raises(LoopClosureError, match="materially disagrees"):
        validate_loop_closure(changed)


def test_loop_closure_is_deterministic(config: dict) -> None:
    assert run_gold_10_fixture(config) == run_gold_10_fixture(config)


def test_loop_closure_receipt_rejects_tampering() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local loop-closure receipt is unavailable")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verify_loop_closure_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["training_admission"] = True
    with pytest.raises(LoopClosureError, match="digest mismatch|widened authority"):
        verify_loop_closure_receipt(changed, output_root=OUTPUT_ROOT)
