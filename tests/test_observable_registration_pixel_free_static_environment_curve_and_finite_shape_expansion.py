from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError, load_json_object
from sim2claw.observable_registration_pixel_free_static_environment_curve_and_finite_shape_expansion import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_curve_and_finite_shape_expansion_once,
    load_curve_and_finite_shape_expansion_contract,
)


def test_or66_contract_freezes_development_only_vector_family() -> None:
    contract = load_curve_and_finite_shape_expansion_contract()
    assert contract["timeline"]["selection_may_read_only_development"] is True
    assert contract["extraction"]["maximum_primitives"] == 32
    assert contract["extraction"]["maximum_total_vertices"] == 512
    assert contract["evaluation"]["evaluate_full_frozen_family_only"] is True
    assert contract["acceptance"]["target_pass_allowed"] is False
    assert not any(contract["resource_boundary"].values())
    assert not any(contract["authority"].values())


def test_or66_freezes_pixel_free_vectors_and_scores_all_partitions(tmp_path) -> None:
    output = tmp_path / "or66"
    receipt = evaluate_curve_and_finite_shape_expansion_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] in {
        "PASS_PIXEL_FREE_CURVE_AND_FINITE_SHAPE_EDGE_HEADROOM_ADVANCE",
        "TERMINAL_CURVE_AND_FINITE_SHAPE_EDGE_HEADROOM_INSUFFICIENT",
    }
    assert receipt["predecessor_reproduction"]["or58_exact_within_1e_12"]
    assert receipt["predecessor_reproduction"]["or64_exact_within_1e_12"]
    assert set(receipt["partition_scores"]) == {"development", "validation", "stress"}
    scene_path = output / receipt["outputs"]["scene_spec_path"]
    scene = load_json_object(scene_path, label="OR66 scene")
    assert scene["physical_pixels_embedded"] is False
    assert scene["background_plate"] is False
    assert scene["texture"] is False
    assert scene["mask_embedded"] is False
    assert len(scene["curve_and_finite_shape_primitives"]) <= 32
    assert scene["total_vertices"] <= 512
    for name in ("scene_spec", "edge_headroom_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["target_pass_allowed"] is False
    assert all(
        receipt["execution"][name] == 0
        for name in (
            "renderer_runs",
            "simulator_replays",
            "candidate_videos",
            "mask_outputs",
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
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_curve_and_finite_shape_expansion_once(CONTRACT_PATH, output, root=REPO_ROOT)
