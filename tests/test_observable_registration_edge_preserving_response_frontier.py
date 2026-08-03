from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_edge_preserving_response_frontier import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_edge_preserving_response_once,
    load_edge_preserving_response_contract,
)


def test_or58_contract_freezes_frontier_and_low_disk_boundary() -> None:
    contract = load_edge_preserving_response_contract()
    family = contract["candidate_family"]
    assert family["common_bgr_gain"] == [0.2, 0.3, 0.4, 0.5, 0.6]
    assert family["common_bgr_bias"] == [48.0, 64.0, 80.0, 96.0, 112.0]
    assert family["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
    assert family["candidate_count"] == 100
    assert family["minimum_development_mean_full_frame_linear_pixel_similarity"] == 0.80
    assert not contract["resource_boundary"]["renderer_allowed"]
    assert not contract["resource_boundary"]["dependency_install_allowed"]
    assert not contract["resource_boundary"]["colima_start_allowed"]
    assert all(contract["prohibitions"].values())
    assert not any(contract["authority"].values())


def test_or58_selects_on_development_and_emits_spatial_residual(tmp_path) -> None:
    output = tmp_path / "or58"
    receipt = evaluate_edge_preserving_response_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] in {
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET",
        "PASS_MEAN_AND_TEMPORAL_PIXEL_TARGET_EDGE_GATE_REMAINS",
        "TERMINAL_GLOBAL_RESPONSE_FRONTIER_BELOW_FULL_TARGET",
    }
    assert receipt["partitions"] == {
        "development": 220,
        "validation": 180,
        "stress": 116,
    }
    assert receipt["selection"]["candidate_count"] == 100
    assert not receipt["selection"]["validation_and_stress_used_for_selection"]
    assert receipt["spatial_residual"]["tile_count"] == 48
    assert len(receipt["spatial_residual"]["worst_five_tiles"]) == 5
    assert receipt["execution"] == {
        "candidate_evaluations": 100,
        "emitted_candidate_videos": 1,
        "renderer_runs": 0,
        "physics_integrations": 0,
        "action_changes": 0,
        "state_changes": 0,
        "geometric_warps": 0,
        "per_frame_transforms": 0,
        "physical_pixel_composites": 0,
        "hardware_actions": 0,
    }
    for name in (
        "candidate_video",
        "candidate_table",
        "metric_rows",
        "spatial_residual_rows",
    ):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_edge_preserving_response_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
