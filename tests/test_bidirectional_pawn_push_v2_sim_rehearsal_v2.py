from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v1.json"
)
V2 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v2.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v2_changes_only_arm_margin_and_declared_jaw_stop_semantics() -> None:
    v1 = _load(V1)
    v2 = _load(V2)

    for field in (
        "registration_candidate",
        "registration_heldout_evaluation",
        "candidate_manifest",
        "source_scene",
        "cases",
        "grid",
        "robustness_variants",
        "action_synthesis",
        "simulation",
        "camera_gate",
        "selection_rule",
        "authority",
    ):
        assert v2[field] == v1[field]

    unchanged_gates = dict(v1["gates"])
    arm_margin = unchanged_gates.pop("minimum_joint_limit_margin_rad")
    assert v2["gates"] == {
        **unchanged_gates,
        "minimum_arm_joint_limit_margin_rad": arm_margin,
    }
    assert arm_margin == 0.03490658503988659
    assert v2["closed_jaw_gate"] == {
        "target_semantics": (
            "declared closed lower-stop target separate from arm-joint margin"
        ),
        "target_tolerance_rad": 1e-12,
        "bounds_roundoff_tolerance_rad": 5e-6,
        "hardware_input_bounds_percent": [0.0, 100.0],
        "hardware_transform_source": (
            "candidate_manifest.candidate_config.physical_adapter."
            "joint_transform"
        ),
        "simulator_bounds_source": (
            "compiled MuJoCo left_gripper joint range"
        ),
        "unchanged_action_target": True,
    }
    assert all(v2["frozen_equivalence_to_v1"].values())
    assert not any(v2["authority"].values())


def test_v2_implementation_and_terminal_v1_are_hash_bound() -> None:
    contract = _load(V2)
    for field in ("implementation", "base_implementation"):
        binding = contract[field]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]

    negative = contract["supersedes_terminal_negative"]
    assert _sha(ROOT / negative["contract_path"]) == negative[
        "contract_sha256"
    ]
    assert _sha(ROOT / negative["receipt_path"]) == negative[
        "receipt_sha256"
    ]
    assert negative["v1_verdict_remains_terminal"] is True
