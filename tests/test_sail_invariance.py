from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.sail.invariance import (
    InvarianceError,
    compile_retained_invariance,
    evaluate_invariance,
    run_seeded_invariance_benchmarks,
    verify_invariance_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "invariance_v1.json"
REGISTRY_PATH = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "mechanisms" / "registry.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "invariance"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def benchmarks(config: dict) -> dict:
    return run_seeded_invariance_benchmarks(config)


def test_gold_11_context_specific_not_universal(benchmarks: dict) -> None:
    by_id = {row["mechanism_id"]: row for row in benchmarks["cases"]}
    assert benchmarks["golden_cases"] == {"GOLD-11": True}
    assert by_id["timing_delay_v1"]["verdict"] == "pass_declared_scope"
    assert by_id["load_compliance_v1"]["verdict"] == "fail_context_specific"
    assert by_id["camera_timing_extrinsics_v1"]["verdict"] == "not_evaluable"
    assert benchmarks["context_specific_promoted_as_universal"] is False


def test_invariance_uses_whole_episode_groups(benchmarks: dict) -> None:
    for case in benchmarks["cases"]:
        assert case["whole_episode_grouping"] is True
        assert len(case["episode_ids"]) == len(set(case["episode_ids"]))
    evaluated = [row for row in benchmarks["cases"] if row["verdict"] != "not_evaluable"]
    assert all(row["action_bytes_unchanged"] is True for row in evaluated)


def test_missing_context_returns_not_evaluable(config: dict) -> None:
    episodes = []
    for index in range(4):
        feature = np.linspace(-1.0, 1.0, 10)
        episodes.append(
            {
                "episode_id": f"single:{index}",
                "context": {"workcell_identity": "only_one"},
                "feature": feature,
                "observation": 0.2 * feature,
                "actions": np.zeros((10, 6), dtype=np.float32),
            }
        )
    result = evaluate_invariance(
        mechanism_id="timing_delay_v1",
        invariant_parameter="delay_s",
        context_covariate="workcell_identity",
        episodes=episodes,
        thresholds=config["thresholds"],
        proof_class="seeded_invariance_fixture",
    )
    assert result["verdict"] == "not_evaluable"
    assert result["parameter_range"] is None


def test_duplicate_episode_identity_fails_closed(config: dict) -> None:
    feature = np.linspace(-1.0, 1.0, 10)
    row = {
        "episode_id": "duplicate",
        "context": {"direction": "forward"},
        "feature": feature,
        "observation": feature,
        "actions": np.zeros((10, 6), dtype=np.float32),
    }
    with pytest.raises(InvarianceError, match="invalid or leaked"):
        evaluate_invariance(
            mechanism_id="x",
            invariant_parameter="p",
            context_covariate="direction",
            episodes=[row, copy.deepcopy(row)],
            thresholds=config["thresholds"],
            proof_class="seeded_invariance_fixture",
        )


def test_seeded_invariance_is_deterministic(config: dict) -> None:
    assert run_seeded_invariance_benchmarks(config) == run_seeded_invariance_benchmarks(config)


@pytest.mark.skipif(not REGISTRY_PATH.is_file(), reason="owner-local registry is unavailable")
def test_retained_mechanisms_abstain_without_group_posteriors(config: dict) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    retained = compile_retained_invariance(registry, config)
    assert retained["counts"] == {"mechanism_count": 10, "not_evaluable_count": 10}
    assert {row["verdict"] for row in retained["results"]} == {"not_evaluable"}
    assert all(row["proof_class"] == "retrospective_consistency_only" for row in retained["results"])


def test_invariance_receipt_rejects_tampering() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local invariance receipt is unavailable")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verify_invariance_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["policy_selection"] = True
    with pytest.raises(InvarianceError, match="digest mismatch|widened authority"):
        verify_invariance_receipt(changed, output_root=OUTPUT_ROOT)
