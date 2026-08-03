from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_pixel_free_environment_primitive_edge_headroom import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_environment_primitive_edge_headroom_once,
    load_environment_primitive_edge_headroom_contract,
)


def test_or64_contract_freezes_all_prefixes_and_counterfactual_boundary() -> None:
    contract = load_environment_primitive_edge_headroom_contract()
    assert contract["counterfactual"]["primitive_prefix_counts"] == [8, 16, 24]
    assert contract["counterfactual"]["selection_allowed"] is False
    assert contract["acceptance"]["target_pass_allowed"] is False
    assert not any(contract["resource_boundary"].values())
    assert not any(contract["authority"].values())


def test_or64_reproduces_or58_and_emits_edge_rows_only(tmp_path) -> None:
    output = tmp_path / "or64"
    receipt = evaluate_environment_primitive_edge_headroom_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] in {
        "PASS_PIXEL_FREE_ENVIRONMENT_PRIMITIVE_EDGE_HEADROOM_ADVANCE",
        "TERMINAL_LINE_PRIMITIVE_EDGE_HEADROOM_INSUFFICIENT",
    }
    assert receipt["or58_reproduction"]["exact_within_1e_12"]
    assert receipt["primitive_prefixes_evaluated_without_selection"] == [8, 16, 24]
    assert set(receipt["prefix_summaries"]) == {"8", "16", "24"}
    assert receipt["target_pass_allowed"] is False
    assert receipt["execution"] == {
        "frame_evaluations": 516,
        "primitive_prefixes_evaluated": 3,
        "renderer_runs": 0,
        "simulator_replays": 0,
        "candidate_videos": 0,
        "image_outputs": 0,
        "texture_outputs": 0,
        "physical_pixel_composites": 0,
        "geometric_warps": 0,
        "scene_mutations": 0,
        "validation_or_stress_selections": 0,
        "hardware_actions": 0,
    }
    rows_path = output / receipt["outputs"]["edge_headroom_rows_path"]
    assert receipt["outputs"]["edge_headroom_rows_sha256"] == hashlib.sha256(
        rows_path.read_bytes()
    ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_environment_primitive_edge_headroom_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
