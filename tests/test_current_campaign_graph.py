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
    assert tracked["active_pointer"]["milestone_id"] == "CC02"
    assert tracked["active_pointer"] == {
        "node_id": "checkpoint:canonical-wrist-path-reset-temporal-v2-frozen",
        "milestone_id": "CC02",
        "status": "preregistered_before_exactly_once_isolated_reset_dynamic_replay",
        "queue_status": "ACTIVE_CC02_CANONICAL_DYNAMIC_REPLAY",
        "resume_action": (
            "execute_canonical_wrist_path_reset_temporal_v2_exactly_once"
        ),
        "resume_authorized": True,
        "heldout_open_count": 1,
        "cumulative_manifest_read_count": 2,
        "counted_task_attempts": 0,
    }
    assert [row["revision"] for row in tracked["revision_timeline"]] == list(
        range(128)
    )
    assert [row["event_id"] for row in tracked["revision_timeline"][:5]] == [
        "V00",
        "V01",
        "V02",
        "V03",
        "V04",
    ]
    assert tracked["revision_timeline"][-1]["event_id"] == (
        "CANONICAL_WRIST_PATH_RESET_TEMPORAL_V2_FROZEN"
    )
    assert tracked["revision_timeline"][-1]["node_ids_added"] == [
        "checkpoint:canonical-wrist-path-reset-temporal-v2-frozen"
    ]
    assert config["active_pointer"] == tracked["active_pointer"]
    assert tracked["active_pointer"]["resume_authorized"] is True
    closeout = next(
        row
        for row in tracked["nodes"]
        if row["id"]
        == "verdict:post-fable-low-planar-static-v2-terminal-negative"
    )
    assert not any(
        value
        for key, value in closeout["data"].items()
        if key.endswith("_authorized") or key == "physical_motion"
    )
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
    assert tracked["current_workcell_hard_cutover"] == config[
        "current_workcell_hard_cutover"
    ]
    assert tracked["canonical_transfer_campaign"] == config[
        "canonical_transfer_campaign"
    ]
    assert (
        tracked["canonical_transfer_campaign"]["physical_authority"] is False
    )


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
