from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_plant_challenger_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_temporal_plan_is_source_bound_diagnostic_and_non_authoritative() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for binding in plan["source_bindings"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert plan["plant_paths"]["canonical_baseline"]["kind"] == (
        "direct_target_mujoco"
    )
    challenger = plan["plant_paths"]["diagnostic_challenger"]
    assert challenger["kind"] == "zero_order_hold_command_delay"
    assert challenger["delay_seconds"] == 0.11
    assert challenger["calibrated_plant"] is False
    assert plan["action_identity"]["sample_rate_hz"] == 40.0
    assert plan["action_identity"]["baseline_and_challenger_byte_identical"]
    assert plan["broader_case_enumeration"]["outcome_cherry_picking"] is False
    assert plan["v05_terminal_negative"]["gate_weakened"] is False
    assert not any(plan["authority"].values())
    assert not any(plan["pause_barrier"].values())


def test_temporal_plan_excludes_unrequested_model_expansion() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert set(plan["excluded_scope"]) == {
        "filters",
        "reward changes",
        "jitter",
        "deadband",
        "joint play",
        "posterior sampling",
        "second simulator",
        "ACT rewrite",
        "domain randomization",
    }
    forbidden = set(plan["action_identity"]["forbidden"])
    assert {"clipping", "smoothing", "retiming", "offset", "rate limiting"} <= forbidden
    assert plan["gateway_compatibility_gate"][
        "fail_closed_before_any_physical_packet"
    ]
