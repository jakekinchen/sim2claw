from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.belief_graph import (
    EDGE_TYPES,
    NODE_TYPES,
    BeliefGraphError,
    build_belief_graph,
    query_negative_nodes,
    traverse_graph,
    validate_graph,
    verify_belief_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "belief_graph_retired_bg_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "belief-graph"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _reseal(graph: dict) -> dict:
    changed = copy.deepcopy(graph)
    changed.pop("graph_digest", None)
    return {**changed, "graph_digest": canonical_digest(changed)}


@pytest.fixture
def retained_graph() -> dict:
    path = OUTPUT_ROOT / "belief_graph.json"
    if not path.is_file():
        pytest.skip("owner-local retained belief graph is unavailable")
    return validate_graph(_load(path))


def test_required_node_and_edge_vocabularies_are_frozen(retained_graph: dict) -> None:
    assert tuple(retained_graph["node_types"]) == NODE_TYPES
    assert tuple(retained_graph["edge_types"]) == EDGE_TYPES
    assert set(retained_graph["counts"]["nodes_by_type"]) == set(NODE_TYPES)
    assert retained_graph["counts"]["edges_by_type"].get("admitted-to", 0) == 0


def test_source_action_traverses_to_terminal_verdict(retained_graph: dict) -> None:
    assert traverse_graph(
        retained_graph,
        "evidence:action-frozen-development",
        "verdict:publication-terminal-negative",
    ) == [
        "evidence:action-frozen-development",
        "candidate:publication-terminal-negative",
        "verdict:publication-terminal-negative",
    ]


def test_negative_and_nonpromoted_history_remains_queryable(retained_graph: dict) -> None:
    negative = query_negative_nodes(retained_graph)
    assert len(negative) == 20
    assert any(row["id"] == "counterexample:reset-first-measured" for row in negative)
    assert any(row["id"] == "verdict:rubber-friction-20" for row in negative)
    candidates = [row for row in retained_graph["nodes"] if row["type"] == "candidate"]
    assert len(candidates) == 12
    assert all(row["data"]["promoted"] is False for row in candidates)


def test_scope_first_influence_never_claims_statistical_similarity() -> None:
    path = OUTPUT_ROOT / "influence_candidates.json"
    if not path.is_file():
        pytest.skip("owner-local retained influence artifact is unavailable")
    rows = _load(path)
    assert len(rows) == 12
    assert all(row["method"] == "declared_scope_only_no_statistical_similarity" for row in rows)
    timing = next(row for row in rows if row["intervention_id"] == "intervention:timing-110ms")
    assert timing["declared_scopes"] == ["timing"]
    assert set(timing["residual_node_ids"]) == {
        "residual:end_effector",
        "residual:event_timing",
        "residual:joint_position",
        "residual:joint_velocity",
    }


def test_history_input_order_does_not_change_graph_digest(retained_graph: dict) -> None:
    config = _load(CONFIG_PATH)
    config["history"] = list(reversed(config["history"]))
    catalog = _load(REPO_ROOT / config["source_bindings"]["evidence_catalog"]["path"])
    residual = _load(REPO_ROOT / config["source_bindings"]["residual_field"]["path"])
    payloads = {
        source_id: _load(REPO_ROOT / binding["path"])
        for source_id, binding in config["history_sources"].items()
    }
    graph, revisions, influence, before = build_belief_graph(
        config,
        catalog=catalog,
        residual=residual,
        history_payloads=payloads,
    )
    assert graph["graph_digest"] == retained_graph["graph_digest"]
    assert revisions[-1]["graph_digest"] == graph["graph_digest"]
    assert len(influence) == 12
    assert before["counts"]["nodes"] == 16


def test_duplicate_node_and_dangling_edge_fail_closed(retained_graph: dict) -> None:
    duplicate = copy.deepcopy(retained_graph)
    duplicate["nodes"].append(copy.deepcopy(duplicate["nodes"][0]))
    duplicate["nodes"].sort(key=lambda row: row["id"])
    with pytest.raises(BeliefGraphError, match="node identity"):
        validate_graph(_reseal(duplicate))

    dangling = copy.deepcopy(retained_graph)
    dangling["edges"].append(
        {"source": "evidence:action-frozen-development", "type": "applied-to", "target": "candidate:missing", "metadata": {}}
    )
    dangling["edges"].sort(
        key=lambda row: (
            row["source"],
            row["type"],
            row["target"],
            canonical_digest(row["metadata"]),
        )
    )
    with pytest.raises(BeliefGraphError, match="dangling"):
        validate_graph(_reseal(dangling))


def test_proof_class_and_evaluator_cannot_be_rewritten(retained_graph: dict) -> None:
    changed = copy.deepcopy(retained_graph)
    timing = next(row for row in changed["nodes"] if row["id"] == "candidate:timing-110ms")
    timing["proof_class"] = "physical_task_success"
    with pytest.raises(BeliefGraphError, match="proof class"):
        validate_graph(_reseal(changed))

    changed = copy.deepcopy(retained_graph)
    verdict = next(row for row in changed["nodes"] if row["id"] == "verdict:timing-110ms")
    verdict["evaluator_identity"] = "0" * 64
    with pytest.raises(BeliefGraphError, match="evaluator identity"):
        validate_graph(_reseal(changed))


def test_certificate_and_policy_gates_remain_closed(retained_graph: dict) -> None:
    nodes = {row["id"]: row for row in retained_graph["nodes"]}
    assert nodes["certificate:current-unissued"]["status"] == "unissued_closed"
    assert nodes["certificate:current-unissued"]["data"]["training_admission"] is False
    assert nodes["checkpoint:campaign-none"]["status"] == "absent"
    assert nodes["policy:campaign-none"]["status"] == "not_admitted"
    assert all(edge["type"] != "admitted-to" for edge in retained_graph["edges"])


def test_receipt_binds_graph_compiler_and_views() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local retained belief receipt is unavailable")
    receipt = _load(path)
    verify_belief_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["authority"]["training_admission"] = True
    with pytest.raises(BeliefGraphError, match="digest mismatch|widened authority"):
        verify_belief_receipt(changed, output_root=OUTPUT_ROOT)
