from __future__ import annotations

import pytest

from sim2claw.sail.contracts import SailContractError
from sim2claw.sail.hardware_protocol import (
    REQUIRED_WORKCELL_IDENTITIES,
    classify_workcell_identity,
    compile_hardware_preflight,
)


def _complete_identity() -> dict:
    return {
        name: {"value": f"fixture-{name}", "matches_retired": True}
        for name in REQUIRED_WORKCELL_IDENTITIES
    }


def test_gold_20_no_authority_no_io() -> None:
    result = compile_hardware_preflight(
        authority={"owner": False, "capture": False, "motion": False, "gateway": False},
        identities={},
        policy_camera_ids=["overhead"],
        evaluator_only_camera_ids=["wrist"],
    )
    assert not result["capture_allowed"]
    assert not result["motion_allowed"]
    assert not result["physical_authority"]


def test_gold_21_missing_identity_is_new_related_workcell() -> None:
    identities = _complete_identity()
    identities.pop("fingertip_profile")
    assert (
        classify_workcell_identity(identities, claimed_same_as_retired=True)
        == "new_related_workcell"
    )


def test_complete_unchanged_identity_may_be_same_workcell() -> None:
    assert (
        classify_workcell_identity(_complete_identity(), claimed_same_as_retired=True)
        == "same_workcell"
    )


def test_gold_22_evaluator_camera_not_policy_input() -> None:
    result = compile_hardware_preflight(
        authority={},
        identities={},
        policy_camera_ids=["overhead"],
        evaluator_only_camera_ids=["wrist", "side", "depth"],
    )
    assert result["policy_camera_ids"] == ["overhead"]
    assert "wrist" not in result["policy_camera_ids"]
    with pytest.raises(SailContractError, match="evaluator-only camera"):
        compile_hardware_preflight(
            authority={},
            identities={},
            policy_camera_ids=["overhead", "wrist"],
            evaluator_only_camera_ids=["wrist"],
        )


def test_gold_23_hardware_evaluation_leakage_rejected() -> None:
    with pytest.raises(SailContractError, match="hardware evaluation"):
        compile_hardware_preflight(
            authority={},
            identities={},
            policy_camera_ids=["overhead"],
            evaluator_only_camera_ids=[],
            training_ids=["trial-001"],
            hardware_evaluation_ids=["trial-001"],
        )
