from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from sim2claw.canonical_transfer_readiness import (
    CanonicalTransferReadinessError,
    evaluate,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT / "configs/evaluations/canonical_transfer_readiness_v1.json"
)


def test_contract_is_read_only_and_fail_closed() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["authority"] == {
        "camera_open": False,
        "gateway": False,
        "serial": False,
        "physical_motion": False,
        "task_attempt": False,
        "physical_packet_freeze": False,
    }
    assert contract["gates"]["sample_hz"] == 40.0
    assert contract["gates"]["maximum_unplanned_start_delta_degrees"] == 10.0


def test_current_legacy_candidates_reject_and_name_exact_blockers(
    tmp_path: Path,
) -> None:
    receipt = evaluate(CONTRACT, tmp_path / "receipt.json")
    assert receipt["passed"] is False
    assert receipt["status"] == "canonical_transfer_readiness_reject"
    assert receipt["blockers"] == [
        "physical_model_mapping_approved",
        "sim_to_real_start_matches_live_anchor",
        "real_to_sim_source_start_matches_live_anchor",
    ]
    assert receipt["sim_to_real_candidate"][
        "maximum_first_arm_delta_degrees"
    ] == pytest.approx(163.5941184204471)
    assert receipt["real_to_sim_candidate"][
        "maximum_source_start_arm_delta_degrees"
    ] > 30.0
    assert receipt["decision"]["physical_packet_authorized"] is False
    assert (
        receipt["decision"]["next_action"]
        == "compile_fresh_actions_from_live_anchor_in_canonical_runtime"
    )


def test_evaluator_refuses_to_overwrite_receipt(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        CanonicalTransferReadinessError,
        match="immutable output already exists",
    ):
        evaluate(CONTRACT, output)


def test_evaluator_has_no_hardware_control_dependencies() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_transfer_readiness",
            fromlist=["unused"],
        )
    )
    for forbidden in (
        "SO101PhysicalGateway",
        "serial",
        "camera.open",
        ".set_torque(",
        "write_goal",
    ):
        assert forbidden not in source
