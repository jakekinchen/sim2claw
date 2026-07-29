from __future__ import annotations

import hashlib
import json

from sim2claw.paths import REPO_ROOT


DECISION = (
    REPO_ROOT
    / "configs/decisions/canonical_seeded_action_static_v2_closeout.json"
)


def test_v2_closeout_binds_pass_without_physical_authority() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    receipt_path = REPO_ROOT / decision["receipt"]["path"]
    assert (
        hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        == decision["receipt"]["sha256"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "canonical_seeded_action_static_v2_pass"
    assert receipt["passed"] is True
    assert receipt["direction_counts"] == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    assert receipt["minimum_selected_model_joint_margin_rad"] > 0.0
    assert receipt["row_zero_exact_live_anchor"] is True
    assert receipt["mapping_calibration_approved"] is False
    for key in (
        "dynamic_simulation_execution",
        "mapping_approval",
        "camera_open",
        "gateway",
        "serial",
        "physical_packet",
        "physical_motion",
        "task_attempt",
        "transfer_claim",
    ):
        assert decision["authority"][key] is False
