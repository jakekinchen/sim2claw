from __future__ import annotations

import json

import numpy as np

from sim2claw.observable_registration_shared_scalar_camera_response_development_fit import (
    DEFAULT_CONTRACT,
    apply_response,
)


def test_or86_contract_is_exactly_two_parameter_nonspatial_family() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    family = contract["family"]
    assert family["parameter_names"] == ["uniform_bgr_gain", "uniform_bgr_bias"]
    assert len(family["gain_values"]) * len(family["bias_values"]) == 35
    assert family["candidate_count"] == 35
    assert family["spatial_parameters"] == 0
    assert family["per_channel_parameters"] == 0
    assert family["per_frame_parameters"] == 0
    assert contract["resource_boundary"]["validation_reads_allowed"] == 0
    assert contract["resource_boundary"]["evaluator_heldout_reads_allowed"] == 0


def test_or86_response_is_uniform_and_clipped() -> None:
    source = np.asarray([[[0, 100, 255], [80, 80, 80]]], dtype=np.uint8)
    result = apply_response(source, gain=0.55, bias=48.0)
    assert result.dtype == np.uint8
    assert result.tolist() == [[[48, 103, 188], [92, 92, 92]]]
