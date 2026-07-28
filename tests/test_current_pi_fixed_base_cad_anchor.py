from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.build_current_pi_fixed_base_cad_anchor import (
    AnchorBuildError,
    background_shift_decision,
    select_future_targets,
    validate_spec,
)
from tools.evaluate_current_pi_cad_keyed_joint_mapping import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = (
    ROOT
    / "configs/evaluations/current_pi_fixed_base_cad_anchor_v1.json"
)


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_spec_hashes_algorithm_roi_and_denies_hardware() -> None:
    spec = _spec()
    validate_spec(spec)
    assert canonical_sha256(spec["admissible_roi"]) == spec[
        "admissible_roi_sha256"
    ]
    assert canonical_sha256(spec["algorithm"]) == spec["algorithm_sha256"]
    assert spec["fit_poses"] == ["J", "S", "K", "L"]
    assert spec["authority"]["hardware_motion"] is False
    assert spec["authority"]["simulator_parameter_promotion"] is False


def test_spec_rejects_algorithm_tampering_and_heldout_source() -> None:
    spec = _spec()
    tampered = copy.deepcopy(spec)
    tampered["algorithm"]["canny_thresholds"][0] = 1
    with pytest.raises(AnchorBuildError, match="algorithm hash changed"):
        validate_spec(tampered)

    heldout = copy.deepcopy(spec)
    heldout["extra_source"] = (
        "runs/pi-link-tag-calibration/pose-m-fresh/pi.jpg"
    )
    with pytest.raises(AnchorBuildError, match="held-out"):
        validate_spec(heldout)


def test_background_shift_controls_require_both_advantages() -> None:
    selected = {"median_px": 1.0, "within_4_px_fraction": 0.8}
    passing = [
        {"metrics": {"median_px": 3.0, "within_4_px_fraction": 0.6}},
        {"metrics": {"median_px": 2.6, "within_4_px_fraction": 0.65}},
    ]
    assert background_shift_decision(
        selected, passing, 1.5, 0.1
    )["passed"]

    latch = copy.deepcopy(passing)
    latch[1]["metrics"] = {
        "median_px": 1.2,
        "within_4_px_fraction": 0.78,
    }
    decision = background_shift_decision(
        selected, latch, 1.5, 0.1
    )
    assert decision["passed"] is False
    assert decision["minimum_median_distance_advantage_px"] == pytest.approx(
        0.2
    )


def test_future_target_selection_is_separation_first_and_diverse() -> None:
    def row(name: str, joint: float, median: float) -> dict:
        return {
            "source_pair": [name, "S"],
            "alpha_on_second": 0.5,
            "joint_target_degrees": [joint, 0, 0, 0, 0, 0],
            "predicted_separation": {
                "median_px": median,
                "p90_px": median + 1.0,
            },
        }

    selected = select_future_targets(
        [
            row("J", 0.0, 30.0),
            row("K", 5.0, 29.0),
            row("L", 25.0, 28.0),
        ],
        20.0,
    )
    assert selected[0]["source_pair"][0] == "J"
    assert selected[1]["source_pair"][0] == "L"
