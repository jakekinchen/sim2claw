from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(
    "configs/evaluations/canonical_proxy_contact_temporal_v2.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_proxy_contact_contract_is_one_mechanism_and_action_frozen() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert contract["mechanism_change"][
        "mechanism_id"
    ] == "jaw_collision_mesh_to_named_proxy_only_v1"
    assert contract["mechanism_change"][
        "preserve_named_collision_primitives"
    ]
    assert contract["mechanism_change"][
        "mass_friction_damping_timing_and_actions_unchanged"
    ]
    assert contract["mechanism_change"]["diagnostic_challenger"]
    assert not contract["mechanism_change"]["calibrated_physical_geometry"]
    assert all(contract["unchanged_from_baseline"].values())
    assert contract["authority"]["dynamic_simulation"]
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "dynamic_simulation"
    )
    for key in (
        "base_temporal_contract",
        "temporal_receipt",
        "temporal_closeout",
        "contact_witness_receipt",
        "model_source",
        "temporal_implementation",
        "challenger_implementation",
        "predecessor_contract",
        "preexecution_closeout",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_proxy_contact_runner_has_no_hardware_or_parameter_fit_surface() -> None:
    source = (
        ROOT / "src/sim2claw/canonical_proxy_contact_temporal.py"
    ).read_text(encoding="utf-8")
    assert "serial" not in source.lower()
    assert "dynamixel" not in source.lower()
    assert "geom_friction[" not in source
    assert "body_mass[" not in source
    assert "dof_damping[" not in source
    assert "actuator_gainprm[" not in source
    assert "geom_contype[geom_id] = 0" in source
    assert "geom_conaffinity[geom_id] = 0" in source
