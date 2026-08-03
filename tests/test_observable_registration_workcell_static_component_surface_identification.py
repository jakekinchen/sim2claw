from __future__ import annotations

import cv2
import numpy as np

from sim2claw.observable_registration_workcell_static_component_surface_identification import (
    _classify_frame,
    _detect_fixture_mask,
    _detector,
    load_surface_identification_contract,
)


def test_or125_contract_freezes_tag_fixture_only_without_rendering() -> None:
    contract = load_surface_identification_contract()

    assert contract["detector"]["dictionary"] == "DICT_APRILTAG_36h11"
    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["corroboration_positions"] == list(range(8, 12))
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["resource_boundary"]["dense_mask_vectorizations_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity"] is False


def test_or125_detector_recovers_synthetic_tag36h11() -> None:
    marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11), 3, 120)
    frame = np.full((180, 180, 3), 255, dtype=np.uint8)
    frame[30:150, 30:150] = np.repeat(marker[:, :, None], 3, axis=2)

    mask, detections = _detect_fixture_mask(frame, _detector(), [0.0, 90.0])

    assert len(detections) == 1
    assert max(detections[0]["axis_family_errors_degrees"]) < 12.0
    assert mask.sum() > 10000


def test_or125_frame_classifier_requires_multiple_component_overlap() -> None:
    fixture = np.zeros((20, 20), dtype=bool)
    fixture[2:18, 2:18] = True
    components = []
    for offset in (4, 10):
        mask = np.zeros_like(fixture)
        mask[offset : offset + 3, 5:10] = True
        components.append({"raw_mask": mask, "raw_pixel_count": int(mask.sum())})
    detections = [{"axis_family_errors_degrees": [0.0, 0.0]}]
    decision = {
        "minimum_component_fixture_overlap_fraction": 0.5,
        "minimum_associated_component_count": 2,
        "minimum_associated_raw_pixel_fraction": 0.5,
        "maximum_component_to_fixture_distance_px": 2,
        "maximum_axis_family_error_degrees": 12.0,
    }

    label, summary = _classify_frame(components, fixture, detections, decision)

    assert label == "separate_static_planar_fixture"
    assert summary["associated_component_count"] == 2
