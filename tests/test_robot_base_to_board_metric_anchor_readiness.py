from __future__ import annotations

from pathlib import Path

from sim2claw.robot_base_to_board_metric_anchor_readiness import (
    CONTRACT_PATH,
    build_metric_anchor_readiness_receipt,
    load_metric_anchor_contract,
)


def test_metric_anchor_contract_requires_independent_noncontact_measurement() -> None:
    contract = load_metric_anchor_contract(CONTRACT_PATH)
    assert contract["measurement"]["minimum_non_collinear_points"] == 3
    assert contract["measurement"]["task_episode_allowed"] is False
    assert contract["measurement"]["pawn_contact_allowed"] is False
    assert contract["admission"]["maximum_translation_uncertainty_m"] == 0.003
    assert contract["admission"]["maximum_rotation_uncertainty_degrees"] == 0.5
    assert not any(contract["authority"].values())


def test_readiness_receipt_stops_at_missing_external_measurement(
    tmp_path: Path,
) -> None:
    receipt = build_metric_anchor_readiness_receipt(
        CONTRACT_PATH,
        tmp_path / "receipt.json",
    )
    assert receipt["result"] == "DESIGN_READY_BLOCKED_EXTERNAL_METRIC_ANCHOR"
    assert receipt["measurement_rows"] == 0
    assert receipt["candidate_transform_produced"] is False
    assert receipt["physical_motion"] is False
    assert receipt["task_attempts"] == 0
