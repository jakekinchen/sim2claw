from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_camera_parallax_edge import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_camera_parallax_once,
    load_camera_parallax_contract,
)


def test_or57_contract_freezes_board_preserving_camera_family() -> None:
    contract = load_camera_parallax_contract()
    family = contract["candidate_family"]
    assert family["board_to_camera_translation_scale"] == [0.85, 1.0, 1.15]
    assert family["focal_length_scale"] == [0.85, 1.0, 1.15]
    assert family["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
    assert family["candidate_count"] == 36
    assert family["minimum_development_mean_full_frame_linear_pixel_similarity"] == 0.78
    assert all(contract["prohibitions"].values())
    assert not any(contract["authority"].values())


def test_or57_selects_camera_on_development_then_scores_once(tmp_path) -> None:
    output = tmp_path / "or57"
    receipt = evaluate_camera_parallax_once(CONTRACT_PATH, output, root=REPO_ROOT)
    assert receipt["status"] in {
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET",
        "PASS_CAMERA_PARALLAX_EDGE_ADVANCE_BELOW_TARGET",
        "TERMINAL_CAMERA_PARALLAX_EDGE_INSUFFICIENT",
        "TERMINAL_RENDER_RUNTIME_UNAVAILABLE_NO_CANDIDATE",
    }
    if receipt["status"] == "TERMINAL_RENDER_RUNTIME_UNAVAILABLE_NO_CANDIDATE":
        assert receipt["selection"] is None
        assert receipt["metrics"] is None
        assert not receipt["all_acceptance_gates_pass"]
        assert not any(receipt["execution"].values())
        with pytest.raises(FactoryArtifactError, match="one-run"):
            evaluate_camera_parallax_once(CONTRACT_PATH, output, root=REPO_ROOT)
        return
    assert receipt["partitions"] == {
        "development": 220,
        "validation": 180,
        "stress": 116,
    }
    assert receipt["selection"]["candidate_count"] == 36
    assert not receipt["selection"]["validation_and_stress_used_for_selection"]
    assert receipt["execution"] == {
        "camera_candidate_count": 9,
        "camera_blur_candidate_evaluations": 36,
        "development_state_renders": 1980,
        "selected_full_state_renders": 531,
        "physics_integrations": 0,
        "action_changes": 0,
        "state_changes": 0,
        "scene_geometry_changes": 0,
        "hardware_actions": 0,
    }
    development = receipt["partition_scores"]["development"]
    assert (
        development["selected_candidate"]["full_frame_linear_pixel_similarity"]["mean"]
        >= 0.75
    )
    for name in ("candidate_video", "candidate_table", "metric_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_camera_parallax_once(CONTRACT_PATH, output, root=REPO_ROOT)
