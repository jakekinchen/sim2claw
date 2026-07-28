from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.belief_graph import BeliefGraphError, validate_graph
from sim2claw.sail.current_campaign_graph import (
    build_current_campaign_graph,
    load_current_campaign_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("configs/sail/bidirectional_pawn_push_v2_current_graph_v1.json")
GRAPH = Path(
    "docs/autonomous-workflow/bidirectional-pawn-push-v2-current-graph.json"
)


def test_current_campaign_graph_is_reproducible_and_backtrackable() -> None:
    config = load_current_campaign_config(CONFIG, repo_root=ROOT)
    rebuilt = build_current_campaign_graph(config, repo_root=ROOT)
    tracked = validate_graph(
        json.loads((ROOT / GRAPH).read_text(encoding="utf-8"))
    )

    assert rebuilt == tracked
    assert tracked["active_pointer"]["milestone_id"] == "V04"
    assert tracked["active_pointer"] == {
        "node_id": "checkpoint:v04-masked-static-cad-diagnostic",
        "milestone_id": "V04",
        "status": "schedule_fault_isolated_transform_fit_required_v4_design_active",
        "queue_status": "ACTIVE_V04_PROSPECTIVE_V4_TRUE_TIME_REGISTRATION_DESIGN",
        "resume_action": (
            "freeze_v4_true_time_registration_contract_and_static_route"
        ),
        "resume_authorized": True,
        "heldout_open_count": 0,
        "counted_task_attempts": 0,
    }
    assert [row["revision"] for row in tracked["revision_timeline"]] == list(
        range(20)
    )
    assert [row["event_id"] for row in tracked["revision_timeline"][:5]] == [
        "V00",
        "V01",
        "V02",
        "V03",
        "V04",
    ]
    assert (
        tracked["revision_timeline"][-1]["event_id"]
        == "V04_MASKED_STATIC_CAD_DIAGNOSTIC"
    )
    assert tracked["revision_timeline"][-1]["node_ids_added"] == [
        "checkpoint:v04-masked-static-cad-diagnostic"
    ]
    assert {row["type"] for row in tracked["nodes"]} == set(
        tracked["node_types"]
    )
    assert tracked["delta_assessment"]["world_visual"]["detected"] is True
    assert (
        tracked["delta_assessment"]["directional_task_action"][
            "directional_rmse_available"
        ]
        is False
    )
    assert tracked["authority"] and not any(tracked["authority"].values())


def test_current_campaign_graph_fails_closed_on_source_or_lineage_drift() -> None:
    config = load_current_campaign_config(CONFIG, repo_root=ROOT)

    changed = copy.deepcopy(config)
    changed["source_bindings"]["v04_fit"]["sha256"] = "0" * 64
    with pytest.raises(BeliefGraphError, match="source changed"):
        build_current_campaign_graph(changed, repo_root=ROOT)

    changed = copy.deepcopy(config)
    changed["revision_timeline"][-1]["node_ids_added"].pop()
    with pytest.raises(BeliefGraphError, match="revision lineage is invalid"):
        build_current_campaign_graph(changed, repo_root=ROOT)

    tracked = json.loads((ROOT / GRAPH).read_text(encoding="utf-8"))
    tracked["active_pointer"]["status"] = "motion_authorized"
    unsigned = {
        key: value for key, value in tracked.items() if key != "graph_digest"
    }
    tampered = {**unsigned, "graph_digest": canonical_digest(unsigned)}
    # A valid digest alone cannot be treated as a valid source-bound rebuild.
    assert validate_graph(tampered)["active_pointer"]["status"] == "motion_authorized"
    assert build_current_campaign_graph(config, repo_root=ROOT) != tampered
