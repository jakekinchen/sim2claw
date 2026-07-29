from __future__ import annotations

import copy

import numpy as np
import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.rp04n_crown_track import (
    ANNOTATION_SCHEMA,
    discrete_frechet,
    load_contract,
    validate_annotations,
)


def test_rp04n_contract_is_frozen_and_action_free() -> None:
    contract = load_contract()
    assert len(contract["source"]["sample_indices"]) == 18
    assert contract["annotation"][
        "simulator_pixel_projection_hidden_until_both_passes_frozen"
    ] is True
    assert all(contract["forbidden"].values())
    assert not any(contract["authority"].values())
    assert "inspected RP04K selected-pawn 3D rows" in (
        contract["known_blinding_limitation"]
    )


def test_discrete_frechet_preserves_curve_order() -> None:
    left = np.asarray([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    same = np.asarray([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    reversed_curve = same[::-1].copy()
    assert discrete_frechet(left, same) == 0.0
    assert discrete_frechet(left, reversed_curve) == pytest.approx(2.0)


def test_annotation_validator_rejects_reordered_or_leaked_pass() -> None:
    order = [10, 20]
    annotation = {
        "schema_version": ANNOTATION_SCHEMA,
        "pass": "pass_a",
        "simulator_projection_visible_during_annotation": False,
        "rows": [
            {
                "kind": "anchor",
                "visibility": "visible",
                "crown_center_px": [1.0, 2.0],
            },
            {
                "kind": "carry",
                "sample_index": 10,
                "visibility": "visible",
                "crown_center_px": [2.0, 3.0],
            },
            {
                "kind": "carry",
                "sample_index": 20,
                "visibility": "occluded",
                "crown_center_px": None,
            },
        ],
    }
    result = validate_annotations(
        annotation, pass_name="pass_a", expected_order=order
    )
    assert set(result) == {10, 20}
    changed = copy.deepcopy(annotation)
    changed["rows"][1], changed["rows"][2] = (
        changed["rows"][2],
        changed["rows"][1],
    )
    with pytest.raises(FactoryArtifactError, match="order changed"):
        validate_annotations(
            changed, pass_name="pass_a", expected_order=order
        )
    changed = copy.deepcopy(annotation)
    changed["simulator_projection_visible_during_annotation"] = True
    with pytest.raises(FactoryArtifactError, match="invalid RP04N"):
        validate_annotations(
            changed, pass_name="pass_a", expected_order=order
        )
