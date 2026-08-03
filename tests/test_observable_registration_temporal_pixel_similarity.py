from __future__ import annotations

import hashlib
import json

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_temporal_pixel_similarity import (
    CONTRACT_PATH,
    REPO_ROOT,
    evaluate_temporal_pixel_similarity_once,
    load_temporal_pixel_similarity_contract,
)


def test_or55_contract_freezes_pixel_target_and_anti_cheating_rules() -> None:
    contract = load_temporal_pixel_similarity_contract()
    assert contract["acceptance"] == {
        "minimum_mean_full_frame_linear_pixel_similarity": 0.80,
        "minimum_p10_full_frame_linear_pixel_similarity": 0.75,
        "minimum_mean_motion_union_linear_pixel_similarity": 0.75,
        "minimum_each_phase_mean_full_frame_linear_pixel_similarity": 0.78,
        "minimum_mean_tolerant_edge_f1": 0.40,
        "all_gates_required": True,
    }
    assert not contract["metric"]["additional_geometric_warp_allowed"]
    assert not contract["metric"]["color_fit_allowed"]
    assert not contract["metric"]["physical_pixel_compositing_allowed"]
    assert not contract["metric"]["physical_pixels_as_simulator_texture_allowed"]
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())


def test_or55_scores_immutable_or26_baseline_once(tmp_path) -> None:
    output = tmp_path / "or55"
    receipt = evaluate_temporal_pixel_similarity_once(
        CONTRACT_PATH, output, root=REPO_ROOT
    )
    assert receipt["status"] == "BASELINE_BELOW_TEMPORAL_PIXEL_SIMILARITY_TARGET"
    assert receipt["timeline"] == {
        "decoded_frame_count": 531,
        "available_physical_frame_count": 516,
        "missing_physical_frame_count": 15,
        "missing_frames_filled": False,
    }
    metrics = receipt["metrics"]
    assert metrics["full_frame_linear_pixel_similarity"]["mean"] == pytest.approx(
        0.7036233737, abs=1e-8
    )
    assert metrics["full_frame_linear_pixel_similarity"]["p10"] == pytest.approx(
        0.6863253117, abs=1e-8
    )
    assert metrics["motion_union_linear_pixel_similarity"]["mean"] == pytest.approx(
        0.6702985640, abs=1e-8
    )
    assert metrics["tolerant_edge_f1"]["mean"] == pytest.approx(
        0.2266972290, abs=1e-8
    )
    assert not any(receipt["acceptance_gates"].values())
    assert not receipt["all_acceptance_gates_pass"]
    assert receipt["execution"] == {
        "simulator_replays": 0,
        "candidate_renders": 0,
        "geometric_registration_changes": 0,
        "color_fits": 0,
        "parameter_changes": 0,
        "physical_frame_substitutions": 0,
        "hardware_actions": 0,
        "heldout_opened": False,
    }
    rows_path = output / "metric_rows.json"
    assert receipt["metric_rows_sha256"] == hashlib.sha256(
        rows_path.read_bytes()
    ).hexdigest()
    rows = json.loads(rows_path.read_text())["rows"]
    assert len(rows) == 531
    assert sum(bool(row["physical_frame_available"]) for row in rows) == 516
    with pytest.raises(FactoryArtifactError, match="one-run"):
        evaluate_temporal_pixel_similarity_once(
            CONTRACT_PATH, output, root=REPO_ROOT
        )
