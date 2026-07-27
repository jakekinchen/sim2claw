from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.img5349_registration import (
    REGISTRATION_CONTRACT,
    load_registration_contract,
    validated_studio_registration,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE_MANIFEST = (
    ROOT / "docs/reference/IPHONE_VIDEO_3DGS_RELEASE_20260719.json"
)


def _registration(contract: dict) -> dict:
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    source = contract["source_binding"]
    return validated_studio_registration(
        contract,
        release_manifest=manifest,
        model_name=source["splat_name"],
        model_sha256=source["splat_sha256"],
    )


def test_tracked_registration_is_proper_and_reproduces_heldout_summary() -> None:
    contract = load_registration_contract(ROOT / REGISTRATION_CONTRACT)
    result = _registration(contract)

    matrix = np.asarray(result["source_to_three_matrix_rows"])
    assert matrix.shape == (4, 4)
    assert result["heldout_corner_count"] == 166
    assert result["heldout_weighted_rms_px"] == pytest.approx(3.7585512868032063)
    assert result["corner_fit_rms_m"] < 1e-6
    assert result["d4_mapping"] == [
        "source[0]->h8",
        "source[1]->h1",
        "source[2]->a1",
        "source[3]->a8",
    ]
    assert result["authority"]["metric_scale"] is False
    assert result["authority"]["physical_robot_control"] is False
    assert (
        result["visual_overlay_palette"]["status"]
        == "accepted_current_physical_visual_only"
    )
    assert (
        result["visual_overlay_palette"]["shared_scene_or_evaluator_changed"]
        is False
    )


def test_registration_fails_closed_on_authority_or_source_drift() -> None:
    contract = load_registration_contract(ROOT / REGISTRATION_CONTRACT)
    contract["authority"]["collision_geometry"] = True
    with pytest.raises(ValueError, match="downstream authority"):
        _registration(contract)

    contract = load_registration_contract(ROOT / REGISTRATION_CONTRACT)
    contract["source_binding"]["splat_sha256"] = "0" * 64
    manifest = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="source binding"):
        validated_studio_registration(
            contract,
            release_manifest=manifest,
            model_name="IMG_5349-primary-real-splat.ply",
            model_sha256="f8f3bfe0a0f1fa13d54e47602dbf43f8e0448178c0e85f0f22a5f2115530443b",
        )
