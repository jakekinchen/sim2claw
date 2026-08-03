from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_retained_edge_residual_mechanism_diagnosis import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_retained_edge_residual_once,
    load_retained_edge_residual_contract,
)


def test_or59_contract_freezes_partition_and_diagnostic_boundary() -> None:
    contract = load_retained_edge_residual_contract()
    assert contract["regions"]["classes"] == [
        "motion_union",
        "nonmotion_board",
        "nonmotion_outside_board",
    ]
    assert contract["regions"]["mutually_exclusive"]
    assert contract["regions"]["exhaustive"]
    assert contract["decision_rule"]["target_pass_allowed"] is False
    assert not any(contract["resource_boundary"].values())
    assert all(contract["prohibitions"].values())
    assert not any(contract["authority"].values())


def test_or59_reproduces_edge_metric_and_selects_one_mechanism(tmp_path) -> None:
    output = tmp_path / "or59"
    receipt = evaluate_retained_edge_residual_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] == "PASS_EDGE_RESIDUAL_MECHANISM_ATTRIBUTED_TARGET_STILL_OPEN"
    assert receipt["timeline"]["scored_frame_count"] == 516
    assert receipt["or58_reproduction"]["exact_within_1e_12"]
    regions = receipt["aggregate_region_metrics"]
    assert set(regions) == {
        "motion_union",
        "nonmotion_board",
        "nonmotion_outside_board",
    }
    assert sum(value["edge_denominator_share"] for value in regions.values()) == pytest.approx(1.0)
    selected = receipt["mechanism_selection"]
    assert selected["selected_class"] in regions
    assert selected["target_pass_allowed"] is False
    assert receipt["spatial_residual"]["tile_count"] == 48
    assert len(receipt["spatial_residual"]["worst_five_tiles"]) == 5
    assert receipt["execution"] == {
        "diagnostic_frame_evaluations": 516,
        "candidate_videos": 0,
        "renderer_runs": 0,
        "physics_integrations": 0,
        "action_changes": 0,
        "state_changes": 0,
        "geometric_warps": 0,
        "response_fits": 0,
        "per_frame_transforms": 0,
        "physical_pixel_composites": 0,
        "hardware_actions": 0,
    }
    for name in ("edge_region_rows", "edge_tile_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_retained_edge_residual_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
