from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from sim2claw.bidirectional_pawn_push_v2_temporal_replay import _zoh_delay


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_jaw_successor_authorization_v1.json"
)
STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_static_jaw_successor_v1.json"
)
STATIC_RECEIPT = ROOT / (
    "runs/bidirectional-pawn-push-v2/"
    "20260728-v05-tj-jaw-successor-v1/static-freeze-v1/receipt.json"
)
REPLAY_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_replay_jaw_successor_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_jaw_successor_authorization_is_exact_and_nonphysical() -> None:
    authorization = json.loads(
        AUTHORIZATION.read_text(encoding="utf-8")
    )
    for binding in authorization["immutable_predecessors"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    for binding in authorization["jaw_target_provenance"].values():
        if isinstance(binding, dict):
            assert _sha(ROOT / binding["path"]) == binding["sha256"]
    identity = authorization["successor_action_identity"]
    assert identity["predecessor_closed_jaw_rad"] == -0.174533
    assert identity["successor_closed_jaw_rad"] == -0.1727003294848389
    assert identity["only_changed_column"] == "gripper"
    assert "C8-to-A6 action transplant" in identity["forbidden"]
    assert authorization["authority"]["static_simulation"] is True
    assert not any(
        value
        for key, value in authorization["authority"].items()
        if key != "static_simulation"
    )


def test_static_successor_is_bound_and_preserves_predecessor_identity() -> None:
    contract = json.loads(STATIC_CONTRACT.read_text(encoding="utf-8"))
    for field in (
        "authorization",
        "predecessor_static_contract",
        "predecessor_static_receipt",
        "temporal_plan",
        "rehearsal_contract",
        "implementation",
        "base_implementation",
    ):
        binding = contract[field]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    identity = contract["successor_identity"]
    assert identity == {
        "predecessor_closed_jaw_rad": -0.174533,
        "successor_closed_jaw_rad": -0.1727003294848389,
        "generate_predecessor_arm_tensor_first": True,
        "replace_only_gripper_column_after_arm_generation": True,
        "arm_columns_must_be_byte_identical": True,
        "row_count_order_timing_encoding_unchanged": True,
    }
    assert contract["authority"]["static_simulation"] is True
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key != "static_simulation"
    )


def test_static_successor_freezes_two_exact_actions_per_direction() -> None:
    receipt = json.loads(STATIC_RECEIPT.read_text(encoding="utf-8"))
    assert _sha(STATIC_RECEIPT) == (
        "64e8c4435e033e0f9c83b88374b11206ed02b80fcdbb62765ad9834c2248566c"
    )
    assert receipt["status"] == "static_action_freeze_pass"
    assert receipt["lane_counts"] == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    assert receipt["successor_identity"][
        "all_arm_columns_byte_identical"
    ]
    for case in receipt["eligible_cases"]:
        path = ROOT / case["action_path"]
        assert _sha(path) == case["action_sha256"]
        action = np.fromfile(path, dtype="<f8").reshape(case["action_shape"])
        assert np.all(action[:, 5] == -0.1727003294848389)


def test_temporal_replay_binds_actions_and_exact_zoh_semantics() -> None:
    contract = json.loads(REPLAY_CONTRACT.read_text(encoding="utf-8"))
    for field in (
        "static_receipt",
        "rehearsal_contract",
        "temporal_plan",
        "implementation",
    ):
        binding = contract[field]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    for case in contract["cases"]:
        assert _sha(ROOT / case["action_path"]) == case["action_sha256"]
    requested = np.arange(8 * 6, dtype="<f8").reshape(8, 6)
    applied, indices = _zoh_delay(
        requested, sample_hz=40.0, delay_seconds=0.11
    )
    assert indices.tolist() == [0, 0, 0, 0, 0, 0, 1, 2]
    assert np.array_equal(applied, requested[indices])
    assert contract["acceptance"]["minimum_cases_per_direction"] == 2
    assert contract["authority"]["dynamic_simulation"] is True
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key != "dynamic_simulation"
    )
