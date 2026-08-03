from __future__ import annotations

import cv2

from sim2claw.observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT
from sim2claw.observable_registration_renderer_native_dense_static_support_reconstruction import (
    _dense_segments_from_audit,
    load_dense_static_support_contract,
)


def test_or125_contract_freezes_real_geometry_and_no_refit_corroboration() -> None:
    contract = load_dense_static_support_contract()
    assert contract["split"]["development_positions"] == list(range(1, 8))
    assert contract["split"]["corroboration_positions"] == list(range(8, 12))
    assert contract["split"]["corroboration_requires_development_gate"] is True
    assert contract["split"]["corroboration_refit_allowed"] is False
    assert contract["geometry"]["primitive_type"] == "tabletop_supported_capsule_contours"
    assert contract["geometry"]["physical_pixel_composite"] is False
    assert contract["resource_boundary"]["material_refits_allowed"] == 0
    assert contract["resource_boundary"]["plane_or_camera_changes_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity"] is False
    assert contract["claim_limits"]["physics_fidelity"] is False


def test_or125_vectorization_is_exact_and_bounded() -> None:
    contract = load_dense_static_support_contract()
    audit = cv2.imread(str(REPO_ROOT / contract["sources"]["or123_audit"]["path"]), cv2.IMREAD_COLOR)
    assert audit is not None
    segments, meta = _dense_segments_from_audit(audit, contract["vectorization"])
    assert meta == contract["expected_vectorization"]
    assert len(segments) == meta["dense_segment_count"]
    assert 1 <= len(segments) <= contract["vectorization"]["maximum_dense_segment_count"]
    assert len({tuple(segment) for segment in segments}) == len(segments)


def test_or125_material_and_original_gates_remain_frozen() -> None:
    contract = load_dense_static_support_contract()
    assert contract["material"]["source"] == "or122b_pre_response_bgr"
    assert contract["material"]["refits_allowed"] == 0
    assert contract["acceptance"]["development"]["minimum_mean_array_roi_edge_f1_delta"] == 0.1
    assert contract["acceptance"]["development"]["minimum_mean_full_frame_similarity_delta"] == 0.0004
