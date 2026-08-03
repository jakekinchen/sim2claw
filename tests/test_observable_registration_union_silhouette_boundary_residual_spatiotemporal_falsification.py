from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.observable_registration_union_silhouette_boundary_residual_spatiotemporal_falsification import (
    DEFAULT_CONTRACT,
    _union_arm_distance,
    evaluate_once,
    load_union_silhouette_falsification_contract,
)


def test_contract_is_new_identity_single_mechanism_repair_only() -> None:
    contract = load_union_silhouette_falsification_contract()
    assert contract["status"] == "owner_admitted_frozen_not_executed"
    assert contract["repair"] == {
        "classification_distance_source": "morphological_boundary_of_union_of_left_and_right_robot_id_masks",
        "separate_left_right_distances_are_descriptive_only": True,
        "separate_left_right_distances_may_change_membership": False,
        "all_other_or133b_protocol_fields_inherited_without_change": True,
        "same_card_retry": False,
        "new_experiment_identity": True,
    }
    assert contract["inherited_protocol"]["total_frame_count"] == 751
    assert contract["inherited_protocol"]["candidate_intervention_renders"] == 0
    assert contract["inherited_protocol"]["renderer_or_intervention_dof"] == 0
    assert contract["claim_limits"]["operator_or_cable_identity"] is False
    assert contract["claim_limits"]["regional_target_progress"] is False
    assert not any(contract["authority"].values())


def test_union_distance_removes_internal_left_right_group_boundary() -> None:
    ids = np.zeros((20, 24), np.uint16)
    ids[4:16, 3:12] = 7
    ids[4:16, 12:21] = 8
    left, right, union, union_distance = _union_arm_distance(ids, 7, 8)
    assert union[10, 11] and union[10, 12]
    assert min(left[10, 11], right[10, 11]) == 0.0
    assert min(left[10, 12], right[10, 12]) == 0.0
    assert union_distance[10, 11] > 0.0
    assert union_distance[10, 12] > 0.0
    union_edge = cv2.morphologyEx(
        union.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)
    ) > 0
    assert not union_edge[10, 11]
    assert not union_edge[10, 12]


def test_source_failure_packet_prohibits_same_card_retry() -> None:
    contract = load_union_silhouette_falsification_contract()
    import json

    failure = json.loads(Path(contract["sources"]["or133b_terminal_failure"]["path"]).read_text())
    assert failure["status"] == "TERMINAL_BOUNDARY_RESIDUAL_REPRODUCTION_INFEASIBLE"
    assert failure["failure"]["same_card_retry_allowed"] is False
    assert failure["execution"]["instrumented_baseline_id_buffer_renders"] == 222
    assert failure["execution"]["retries"] == 0


def test_evaluator_refuses_existing_receipt_before_any_pixel_read(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="one-run receipt already exists"):
        evaluate_once(DEFAULT_CONTRACT, tmp_path)
