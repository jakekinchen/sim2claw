from __future__ import annotations

import hashlib

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_static_appearance_factorization import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_static_appearance_once,
    load_static_appearance_contract,
)


def test_or56_contract_freezes_partitions_family_and_prohibitions() -> None:
    contract = load_static_appearance_contract()
    timeline = contract["timeline"]
    assert timeline["development_ranges_inclusive"] == [
        [0, 119],
        [260, 319],
        [400, 439],
    ]
    assert timeline["validation_ranges_inclusive"] == [
        [120, 199],
        [320, 379],
        [440, 479],
    ]
    assert timeline["stress_ranges_inclusive"] == [
        [200, 259],
        [380, 399],
        [480, 515],
    ]
    assert contract["candidate_family"]["models"] == [
        "identity",
        "diagonal_bgr_affine",
        "full_bgr_affine",
    ]
    assert contract["candidate_family"]["gaussian_blur_kernel_px"] == [1, 3, 5, 7]
    assert all(contract["prohibitions"].values())
    assert not any(contract["authority"].values())


def test_or56_selects_on_development_then_scores_sealed_blocks(tmp_path) -> None:
    output = tmp_path / "or56"
    receipt = evaluate_static_appearance_once(CONTRACT_PATH, output, root=REPO_ROOT)
    assert receipt["status"] in {
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET",
        "PASS_TIME_INVARIANT_APPEARANCE_ADVANCE_BELOW_TARGET",
        "TERMINAL_STATIC_APPEARANCE_INSUFFICIENT",
    }
    assert receipt["partitions"] == {
        "development": 220,
        "validation": 180,
        "stress": 116,
    }
    assert receipt["selection"]["candidate_count"] == 12
    assert not receipt["selection"]["validation_and_stress_used_for_selection"]
    assert receipt["execution"] == {
        "candidate_evaluations": 12,
        "camera_response_fits": 8,
        "emitted_candidate_videos": 1,
        "simulator_replays": 0,
        "action_changes": 0,
        "physics_changes": 0,
        "geometric_warps": 0,
        "per_frame_transforms": 0,
        "physical_pixel_composites": 0,
        "hardware_actions": 0,
    }
    validation = receipt["partition_scores"]["validation"]
    assert validation["baseline"]["mean"] == pytest.approx(0.707, abs=0.02)
    assert (
        validation["selected_candidate"]["mean"]
        == pytest.approx(
            validation["baseline"]["mean"]
            + validation["absolute_mean_improvement"],
            abs=1e-12,
        )
    )
    for name in ("candidate_video", "candidate_table", "metric_rows"):
        path = output / receipt["outputs"][f"{name}_path"]
        assert receipt["outputs"][f"{name}_sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_static_appearance_once(CONTRACT_PATH, output, root=REPO_ROOT)
