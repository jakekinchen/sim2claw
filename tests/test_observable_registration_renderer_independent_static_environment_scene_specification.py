from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_renderer_independent_static_environment_scene_specification import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_static_environment_scene_specification_once,
    load_static_environment_scene_specification_contract,
)


def test_or63_contract_freezes_development_only_pixel_free_specification() -> None:
    contract = load_static_environment_scene_specification_contract()
    edge = contract["edge_extraction"]
    assert edge["minimum_development_physical_edge_occurrence"] == 0.35
    assert edge["maximum_development_simulator_edge_occurrence"] == 0.10
    assert edge["maximum_line_primitives"] == 24
    assert contract["timeline"]["selection_may_read_only_development"]
    assert contract["acceptance"]["target_pass_allowed"] is False
    assert not any(contract["resource_boundary"].values())
    assert not any(contract["authority"].values())


def test_or63_emits_json_only_scene_spec_and_heldout_support(tmp_path) -> None:
    output = tmp_path / "or63"
    receipt = evaluate_static_environment_scene_specification_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] in {
        "PASS_PIXEL_FREE_STATIC_ENVIRONMENT_OBSERVATION_SPECIFICATION",
        "TERMINAL_STATIC_ENVIRONMENT_PRIMITIVES_INSUFFICIENT",
    }
    assert receipt["partitions"] == {
        "development": 220,
        "validation": 180,
        "stress": 116,
    }
    assert not receipt["selection"]["validation_and_stress_used_for_selection"]
    assert receipt["selection"]["frozen_line_primitive_count"] <= 24
    assert receipt["selection"]["palette_cluster_count"] == 6
    assert receipt["target_pass_allowed"] is False
    assert receipt["execution"] == {
        "development_frame_evaluations": 220,
        "validation_frame_evaluations": 180,
        "stress_frame_evaluations": 116,
        "renderer_runs": 0,
        "simulator_replays": 0,
        "candidate_videos": 0,
        "image_outputs": 0,
        "texture_outputs": 0,
        "physical_pixel_composites": 0,
        "geometric_warps": 0,
        "dependency_installs": 0,
        "hardware_actions": 0,
    }
    for name in ("scene_spec", "primitive_support_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    scene = __import__("json").loads((output / "scene_spec.json").read_text())
    assert scene["physical_pixels_embedded"] is False
    assert scene["background_plate"] is False
    assert scene["texture"] is False
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_static_environment_scene_specification_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
