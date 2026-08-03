import cv2
import numpy as np

from sim2claw.observable_registration_post_final_persistent_linear_workcell_object_attribution import (
    _component_metrics,
    load_post_final_persistent_linear_workcell_object_attribution_contract,
)


def test_contract_freezes_no_refit_topology_attribution() -> None:
    contract = load_post_final_persistent_linear_workcell_object_attribution_contract()
    assert contract["split"]["validation_never_changes_component_or_classification_rules"] is True
    assert contract["topology_extractor"]["component_selector"] == "maximum_seed_intersection_then_lowest_label"
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity_known"] is False


def test_finite_component_and_boundary_classify_differently() -> None:
    contract = load_post_final_persistent_linear_workcell_object_attribution_contract()
    spec = contract["topology_extractor"]
    analysis = np.ones((160, 200), dtype=bool)
    segment = {"p0": [50, 45], "p1": [130, 105]}
    finite = np.zeros((160, 200), dtype=np.uint8)
    cv2.line(finite, (50, 45), (130, 105), 255, 1)
    cv2.ellipse(finite, (137, 110), (9, 6), 35, 0, 360, 255, 1)
    metrics, _, _ = _component_metrics(finite, analysis, [segment], 36.87, [0, 0, 200, 160], spec)
    assert metrics["classification"] == "finite_linear_workcell_object"
    boundary = np.zeros((160, 200), dtype=np.uint8)
    cv2.line(boundary, (0, 8), (130, 105), 255, 1)
    boundary_segment = {"p0": [5, 12], "p1": [130, 105]}
    metrics, _, _ = _component_metrics(boundary, analysis, [boundary_segment], 36.87, [0, 0, 200, 160], spec)
    assert metrics["classification"] == "scene_boundary"
