from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_post_environment_primitive_edge_residual_reattribution import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_post_environment_primitive_edge_residual_once,
    load_post_environment_primitive_edge_residual_contract,
)


def test_or65_contract_freezes_full_line_family_and_diagnostic_boundary() -> None:
    contract = load_post_environment_primitive_edge_residual_contract()
    assert contract["counterfactual"]["line_primitive_count"] == 24
    assert contract["regions"]["classes"] == [
        "motion_union",
        "nonmotion_board",
        "nonmotion_outside_board",
    ]
    assert contract["decision_rule"]["target_pass_allowed"] is False
    assert not any(contract["resource_boundary"].values())
    assert not any(contract["authority"].values())


def test_or65_reproduces_predecessors_and_selects_one_residual_class(tmp_path) -> None:
    output = tmp_path / "or65"
    receipt = evaluate_post_environment_primitive_edge_residual_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] == "PASS_POST_ENVIRONMENT_PRIMITIVE_EDGE_RESIDUAL_REATTRIBUTION"
    reproduction = receipt["predecessor_reproduction"]
    assert reproduction["or58_exact_within_1e_12"]
    assert reproduction["or59_aggregate_region_counts_exact"]
    assert reproduction["or64_exact_within_1e_12"]
    assert set(receipt["aggregate_region_metrics"]) == {
        "motion_union",
        "nonmotion_board",
        "nonmotion_outside_board",
    }
    assert sum(
        values["post_vector"]["edge_denominator_share"]
        for values in receipt["aggregate_region_metrics"].values()
    ) == pytest.approx(1.0)
    assert receipt["mechanism_selection"]["selected_class"] in receipt["aggregate_region_metrics"]
    assert receipt["mechanism_selection"]["target_pass_allowed"] is False
    assert receipt["execution"]["line_primitives_applied"] == 24
    assert all(
        receipt["execution"][name] == 0
        for name in (
            "renderer_runs",
            "simulator_replays",
            "candidate_videos",
            "bgr_pixel_outputs",
            "image_outputs",
            "texture_outputs",
            "physical_pixel_composites",
            "geometric_warps",
            "scene_mutations",
            "action_changes",
            "state_changes",
            "validation_or_stress_selections",
            "hardware_actions",
        )
    )
    rows_path = output / receipt["outputs"]["post_vector_edge_region_rows_path"]
    assert receipt["outputs"]["post_vector_edge_region_rows_sha256"] == hashlib.sha256(
        rows_path.read_bytes()
    ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_post_environment_primitive_edge_residual_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
