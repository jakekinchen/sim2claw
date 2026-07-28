from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_jaw_successor_authorization_v1.json"
)
STATIC_CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_static_jaw_successor_v1.json"
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
