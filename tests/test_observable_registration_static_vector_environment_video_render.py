from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError, load_json_object
from sim2claw.observable_registration_static_vector_environment_video_render import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_static_vector_environment_video_render_once,
    load_static_vector_environment_video_render_contract,
)


def test_or67_contract_freezes_static_vector_video_family() -> None:
    contract = load_static_vector_environment_video_render_contract()
    assert contract["candidate_family"]["stroke_width_px"] == [1]
    assert contract["candidate_family"]["alpha"] == [0.25, 0.5]
    assert contract["candidate_family"]["candidate_count"] == 2
    assert contract["render"]["physical_pixels_embedded"] is False
    assert contract["evaluation"]["all_five_gates_required"] is True
    assert contract["resource_boundary"]["emitted_candidate_video_limit"] == 1
    assert not any(contract["authority"].values())


def test_or67_emits_one_decoded_video_and_runs_all_gates(tmp_path) -> None:
    output = tmp_path / "or67"
    receipt = evaluate_static_vector_environment_video_render_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] in {
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET_STATIC_VECTOR_VIDEO",
        "TERMINAL_STATIC_VECTOR_VIDEO_BELOW_FULL_TARGET",
    }
    assert set(receipt["acceptance_gates"]) == {
        "mean_full_frame_linear_pixel_similarity",
        "p10_full_frame_linear_pixel_similarity",
        "mean_motion_union_linear_pixel_similarity",
        "each_phase_mean_full_frame_linear_pixel_similarity",
        "mean_tolerant_edge_f1",
    }
    assert receipt["selection"]["validation_and_stress_used_for_selection"] is False
    assert receipt["actions_and_timestamps_unchanged"] is True
    assert receipt["physical_pixels_embedded"] is False
    assert receipt["execution"]["emitted_candidate_videos"] == 1
    assert receipt["execution"]["decoded_candidate_videos"] == 1
    assert receipt["execution"]["physical_pixel_composites"] == 0
    material = load_json_object(
        output / receipt["outputs"]["material_spec_path"], label="OR67 material"
    )
    assert material["static_for_all_frames"] is True
    assert material["physical_pixels_embedded"] is False
    assert len(material["assignments"]) == 56
    for name in ("candidate_video", "material_spec", "candidate_table", "metric_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_static_vector_environment_video_render_once(CONTRACT_PATH, output, root=REPO_ROOT)
