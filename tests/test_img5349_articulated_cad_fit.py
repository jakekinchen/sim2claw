from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.img5349_articulated_cad_fit import evaluate_contract, load_contract


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/img5349_articulated_cad_fit_v1.json"


def test_contract_retains_only_the_visible_right_pose_as_a_diagnostic() -> None:
    contract = load_contract(CONTRACT)
    assert contract["target"]["board_sim3_frozen"] is True
    assert contract["target"]["robot_base_pose_frozen"] is True
    assert contract["target"]["complete_reviewed_visual_meshes"] is True
    assert contract["visibility"]["visible_white_so101_target_side"] == "right"
    assert contract["visibility"]["left_arm_independent_so101_silhouette"] is False
    assert contract["verdict"]["right_arm"] == "retained_pose_hypothesis_not_promoted"
    assert contract["verdict"]["left_arm"] == "rejected_absent_independent_silhouette"
    assert not any(contract["authority"].values())


def test_private_splat_reproduces_bounded_surface_diagnostic() -> None:
    contract = load_contract(CONTRACT)
    ply = ROOT / contract["source"]["ply_path"]
    board = ROOT / contract["source"]["board_registration_path"]
    if not ply.is_file() or not board.is_file():
        pytest.skip("private IMG_5349 diagnostic inputs are unavailable")
    result = evaluate_contract(contract, repo_root=ROOT)
    assert result["selected_splat_count"] == 5337
    baseline = result["surface_metrics"]["baseline"]
    candidate = result["surface_metrics"]["candidate"]
    assert candidate["right_base"]["median_m"] == pytest.approx(
        baseline["right_base"]["median_m"], abs=1e-12
    )
    for body in (
        "right_upper_arm",
        "right_lower_arm",
        "right_wrist",
        "right_gripper",
    ):
        assert candidate[body]["median_m"] < baseline[body]["median_m"]
    assert (
        candidate["right_shoulder"]["median_m"]
        > baseline["right_shoulder"]["median_m"]
    )
    silhouette = result["heldout_silhouette"]
    assert (
        silhouette["candidate_distance_px_half_resolution"]["median"]
        < silhouette["baseline_distance_px_half_resolution"]["median"]
    )
