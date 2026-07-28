from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.bidirectional_registration_masked_diagnostic import (
    MaskedDiagnosticError,
    _safe_bound,
    evaluate,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/bidirectional_pawn_push_v2_masked_static_cad_diagnostic_v1.json"
)


def test_masked_fit_only_diagnostic_is_deterministic(tmp_path: Path) -> None:
    receipt = evaluate(CONTRACT, tmp_path / "receipt.json")

    assert receipt["status"] == "diagnostic_complete"
    assert receipt["heldout_open_count"] == 0
    assert receipt["heldout_content_read"] is False
    assert receipt["physical_motion_commanded"] is False
    assert receipt["schedule_fault_isolated"] is True
    assert (
        receipt["compiled_transform_coherent_under_rejected_v1_camera"]
        is False
    )
    assert receipt["target_09_settle_diagnostic"][
        "first_within_gate_row"
    ] == 813
    assert not any(receipt["authority"].values())


def test_heldout_paths_fail_closed() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    changed = copy.deepcopy(contract["inputs"]["fit_manifest"])
    changed["path"] = "runs/example/heldout/member.json"
    with pytest.raises(MaskedDiagnosticError, match="heldout path is forbidden"):
        _safe_bound(changed)
